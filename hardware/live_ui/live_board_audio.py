#!/usr/bin/env python3
"""Board USB microphone -> rolling Whisper/QNN -> existing FastAPI translation."""
import argparse
import collections
import ctypes
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
import wave
import re
import sys
from asr_uncertainty import quality

import numpy as np
import torch
import executorch
from executorch.extension.pybindings.portable_lib import _load_for_executorch
from executorch.runtime import Runtime
from transformers import AutoProcessor, AutoTokenizer

ROOT=Path('/home/arduino/asr-executorch-test')
RATE=16000
_OUTPUT_LOCK=threading.Lock()

def emit(kind,payload):
    with _OUTPUT_LOCK:
        print(kind+" "+json.dumps(payload,ensure_ascii=False),flush=True)

class ASR:
    def __init__(self,language):
        torch.set_num_threads(4)
        self.core=ctypes.CDLL(str(Path(next(iter(executorch.__path__)))/'lib/libexecutorch.so'),mode=ctypes.RTLD_GLOBAL)
        self.backend=ctypes.CDLL(str(ROOT/'qnn/libqnn_executorch_backend.so'),mode=ctypes.RTLD_GLOBAL)
        assert Runtime.get().backend_registry.is_available('QnnBackend')
        self.processor=AutoProcessor.from_pretrained(str(ROOT/'model'),local_files_only=True)
        self.tokenizer=AutoTokenizer.from_pretrained(str(ROOT/'model'),local_files_only=True)
        self.model=_load_for_executorch(str(ROOT/'qnn/whisper_qnn_fp16.pte'))
        self.limit=int(self.model.run_method('get_max_context_len',[])[0])
        self.start=int(self.model.run_method('decoder_start_token_id',[])[0])
        self.eos=int(self.model.run_method('get_eos_id',[])[0])
        self.set_language(language)
    def set_language(self,language):
        token='<|'+language+'|>'
        if token not in self.tokenizer.get_vocab():raise ValueError('Unsupported language token')
        self.prefix=[self.tokenizer.convert_tokens_to_ids(token),self.tokenizer.convert_tokens_to_ids('<|transcribe|>'),self.tokenizer.convert_tokens_to_ids('<|notimestamps|>')]
    def _decode(self,hidden,forced=None,on_partial=None):
        ids=[];scores=[];branches=[];cur=self.start;no_speech=0.;last_partial=""
        mask=torch.full((1,1,1,self.limit),-255.,dtype=torch.float32)
        for pos in range(self.limit):
            mask[0,0,0,pos]=0
            logits=self.model.run_method('decoder',[torch.tensor([[cur]],dtype=torch.int64),mask,hidden,torch.tensor([pos],dtype=torch.int64)])[0][0,-1,:].float()
            if pos==0:
                token=self.tokenizer.convert_tokens_to_ids('<|nospeech|>')
                no_speech=float(torch.exp(logits[token]-torch.logsumexp(logits,dim=0)).item())
            if pos<len(self.prefix):cur=self.prefix[pos]
            else:
                values,indices=torch.topk(logits,2)
                cur=int(forced[pos]) if forced is not None and pos<len(forced) else int(indices[0])
                if cur<self.eos:
                    scores.append(float((logits[cur]-torch.logsumexp(logits,dim=0)).item()))
                    first,second=map(int,indices.tolist())
                    pieces=[self.tokenizer.decode([x],skip_special_tokens=True) for x in [first,second]]
                    if first<self.eos and second<self.eos and all(any(c.isalnum() for c in piece) for piece in pieces):
                        branches.append({'position':pos,'alternative_token':second,'margin':float(values[0]-values[1])})
            ids.append(cur)
            if on_partial and pos>=len(self.prefix):
                text=self.tokenizer.decode(ids,skip_special_tokens=True)
                if cur!=self.eos:
                    match=re.match(r'^(.*[\s.!?。！？])',text,re.S)
                    text=match.group(1).strip() if match else ''
                else:text=text.strip()
                if text and text!=last_partial and not text.startswith(('[','(')):
                    on_partial(text);last_partial=text
            if cur==self.eos:break
        return {'ids':ids,'text':self.tokenizer.decode(ids,skip_special_tokens=True).strip(),
            'average_logprob':sum(scores)/len(scores) if scores else None,
            'branches':branches,'no_speech':no_speech,'truncated':ids[-1]!=self.eos}

    def transcribe(self,audio,clipped_fraction=0.,on_partial=None,include_alternatives=True):
        tick=time.perf_counter()
        with torch.inference_mode():
            features=self.processor(audio,sampling_rate=RATE,return_tensors='pt').input_features.contiguous()
            hidden=self.model.run_method('encoder',[features])[0]
            primary=self._decode(hidden,on_partial=on_partial)
            margin=min((x['margin'] for x in primary['branches']),default=None)
            diagnostic=quality(primary['text'],primary['average_logprob'],margin,primary['truncated'],clipped_fraction,primary['no_speech'])
            alternatives=[]
            if include_alternatives and diagnostic['status']=='needs_review' and primary['branches']:
                branch=min(primary['branches'],key=lambda x:x['margin'])
                forced=primary['ids'][:branch['position']]+[branch['alternative_token']]
                alternative=self._decode(hidden,forced)
                alt_quality=quality(alternative['text'],alternative['average_logprob'],None,alternative['truncated'],no_speech_probability=alternative['no_speech'])
                if alternative['text'] and ' '.join(alternative['text'].casefold().split())!=' '.join(primary['text'].casefold().split()) and not alternative['truncated'] and alt_quality['status']!='non_speech':
                    alternatives.append({'text':alternative['text'],'average_token_logprob':alternative['average_logprob'],
                        'method':'one second-best token branch, then greedy decoding','branch_position':branch['position']})
        return {'transcript':primary['text'],'asr_seconds':time.perf_counter()-tick,'asr_tokens':len(primary['ids']),
            'truncated':primary['truncated'],'asr_confidence':None,'asr_quality':diagnostic,'asr_alternatives':alternatives}

def capture_session(a,asr,stop_event,trigger=None):
    if trigger is None:trigger=threading.Event();trigger.set()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    asr.set_language(a.language)
    print('READY: board LavMicro-U capture starting; speak now.',flush=True)
    capture=subprocess.Popen(['arecord','-q','-D',a.device,'-t','raw','-f','S16_LE','-r',str(RATE),'-c','1'],stdout=subprocess.PIPE)
    ring=collections.deque();lock=threading.Lock();state={'bytes':0,'total_bytes':0,'started':None,'ended':False}
    limit=int(a.window*RATE)*2
    def receive():
        last_level=0.0
        try:
            while True:
                chunk=capture.stdout.read(3200)
                if not chunk:break
                with lock:
                    if state['started'] is None:state['started']=time.monotonic()
                    ring.append(chunk);state['bytes']+=len(chunk);state['total_bytes']+=len(chunk)
                    while state['bytes']>limit:
                        first=ring.popleft();excess=state['bytes']-limit
                        if len(first)>excess:ring.appendleft(first[excess:]);state['bytes']-=excess
                        else:state['bytes']-=len(first)
                    elapsed=state['total_bytes']/(RATE*2)
                now=time.monotonic()
                if now-last_level>=.5:
                    samples=np.frombuffer(chunk,dtype='<i2').astype(np.float32)/32768
                    emit('LEVEL',{'elapsed_ms':int(elapsed*1000),'rms':float(np.sqrt(np.mean(samples*samples))),'peak':float(np.max(np.abs(samples)))})
                    last_level=now
        finally:
            state['ended']=True
    threading.Thread(target=receive,daemon=True).start()
    rows=[];previous=None;next_snapshot=a.interval;wall_started=time.monotonic()
    try:
        while not stop_event.is_set():
            with lock:
                elapsed=state['total_bytes']/(RATE*2);ended=state['ended']
                pcm=b''.join(ring) if elapsed>=next_snapshot and (not a.manual or trigger.is_set()) else None
            if ended:raise RuntimeError('Microphone disconnected or capture stopped')
            if a.duration and elapsed>=a.duration and pcm is None:break
            if state['started'] is None and time.monotonic()-wall_started>10:raise RuntimeError('No microphone samples received')
            if pcm is None:time.sleep(.05);continue
            trigger.clear()
            next_snapshot=elapsed+a.interval
            audio=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
            recent=audio[-min(len(audio),RATE*2):]
            row={'elapsed_ms':int(elapsed*1000),'window_seconds':len(audio)/RATE,'rms':float(np.sqrt(np.mean(audio*audio))),
                'recent_rms':float(np.sqrt(np.mean(recent*recent))),'peak':float(np.max(np.abs(audio))),
                'clipped_fraction':float(np.mean(np.abs(audio)>=.999))}
            tick=time.perf_counter()
            if row['recent_rms']<a.silence_rms:
                row.update(status='non_speech',transcript='',message='No speech detected.',asr_quality={'status':'non_speech','reasons':['low_audio_level']})
            else:
                emit('PHASE',{'state':'transcribing'})
                row.update(asr.transcribe(audio,clipped_fraction=row['clipped_fraction']));row['status']='transcribed'
                if row['transcript'] and not row['truncated'] and row['asr_quality']['status']!='non_speech' and (a.manual or row['transcript']!=previous) and not a.asr_only:
                    request={'transcript':row['transcript'],'context':'','source_language':a.language,'target_language':a.target_language,'elapsed_ms':row['elapsed_ms']}
                    emit('PHASE',{'state':'thinking'})
                    started=time.perf_counter()
                    try:
                        with urllib.request.urlopen(urllib.request.Request(a.api,data=json.dumps(request).encode(),headers={'Content-Type':'application/json'}),timeout=180) as response:
                            row['translation']=json.load(response);row['http_status']=response.status
                    except Exception as error:row['api_error']=repr(error)
                    row['api_seconds']=time.perf_counter()-started
                if row['asr_quality']['status']=='non_speech':
                    row.update(status='non_speech',message='No speech detected.',asr_alternatives=[])
                previous=row.get('transcript')
            row['processing_seconds']=time.perf_counter()-tick
            rows.append(row)
            with wave.open(str(a.output_dir/'latest.wav'),'wb') as w:w.setparams((1,2,RATE,0,'NONE','not compressed'));w.writeframes(pcm)
            (a.output_dir/'latest.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
            with (a.output_dir/'events.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            emit('EVENT',row)
            emit('PHASE',{'state':'error' if row.get('api_error') else 'ready' if row.get('translation') else 'recording'})
            if a.duration and elapsed>=a.duration:break
    except KeyboardInterrupt:pass
    finally:
        capture.terminate()
        try:capture.wait(timeout=3)
        except subprocess.TimeoutExpired:capture.kill();capture.wait()
        (a.output_dir/'session.json').write_text(json.dumps({'settings':vars(a)|{'output_dir':str(a.output_dir)},'rows':rows},ensure_ascii=False,indent=2)+'\n')
        print('STOPPED',flush=True)

def listen_session(a, asr, stop_event, control):
    from queue import Empty
    asr.set_language(a.language)
    capture=subprocess.Popen(['arecord','-q','-D',a.device,'-t','raw','-f','S16_LE','-r',str(RATE),'-c','1'],stdout=subprocess.PIPE)
    ended=threading.Event()
    def receive():
        last=0.
        try:
            while not stop_event.is_set():
                chunk=capture.stdout.read(3200)
                if not chunk:break
                control.append(chunk)
                if time.monotonic()-last>=.5:
                    samples=np.frombuffer(chunk,dtype='<i2').astype(np.float32)/32768
                    emit('LEVEL',{'elapsed_ms':control.snapshot()['window_end_ms'],'rms':float(np.sqrt(np.mean(samples*samples))),'peak':float(np.max(np.abs(samples)))})
                    last=time.monotonic()
        finally:ended.set()
    threading.Thread(target=receive,daemon=True).start()
    print('READY: continuously listening; button freezes the previous 30 seconds.',flush=True)
    next_live=time.monotonic()+a.interval
    try:
        while not stop_event.is_set():
            if ended.is_set():raise RuntimeError('Microphone disconnected or capture stopped')
            try:sample=control.pending.get_nowait();requested=True
            except Empty:
                if time.monotonic()<next_live:time.sleep(.03);continue
                sample=control.snapshot();requested=False
            if not sample['pcm']:time.sleep(.05);continue
            audio=np.frombuffer(sample.pop('pcm'),dtype='<i2').astype(np.float32)/32768
            row={**sample,'capture_session_id':a.session_id,'elapsed_ms':sample['window_end_ms'],'rms':float(np.sqrt(np.mean(audio*audio))),
                 'peak':float(np.max(np.abs(audio))),'clipped_fraction':float(np.mean(np.abs(audio)>=.999))}
            cycle_started=time.monotonic()
            if requested:emit('PHASE',{'state':'transcribing'})
            # Inspect the complete frozen window: a quiet last two seconds must not discard earlier speech.
            if row['rms']<a.silence_rms:
                row.update(status='non_speech',transcript='',message='No speech detected.',asr_quality={'status':'non_speech','reasons':['low_audio_level']},asr_alternatives=[])
            else:
                def partial(text):
                    emit('LIVE_PARTIAL',{'transcript':text,'window_start_ms':row['window_start_ms'],'window_end_ms':row['window_end_ms'],'window_seconds':row['window_seconds'],'capture_session_id':a.session_id,'partial':True})
                row.update(asr.transcribe(audio,clipped_fraction=row['clipped_fraction'],on_partial=None if requested else partial,include_alternatives=requested));row['status']='transcribed'
                if row['asr_quality']['status']=='non_speech':row.update(status='non_speech',message='No speech detected.',asr_alternatives=[])
            emit('EVENT' if requested else 'LIVE',row)
            # Snapshot events and the live transcript have separate channels. Neither calls Qwen here.
            next_live=cycle_started+a.interval
    finally:
        capture.terminate()
        try:capture.wait(timeout=3)
        except subprocess.TimeoutExpired:capture.kill();capture.wait()
        print('STOPPED',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device',default='plughw:CARD=LavMicroU,DEV=0')
    p.add_argument('--language',default='en');p.add_argument('--target-language',default='ko')
    p.add_argument('--window',type=float,default=30);p.add_argument('--interval',type=float,default=5)
    p.add_argument('--duration',type=float,default=60,help='Capture seconds; 0 runs until Ctrl-C')
    p.add_argument('--api',default='http://127.0.0.1:8000/interpret/enriched')
    p.add_argument('--asr-only',action='store_true');p.add_argument('--silence-rms',type=float,default=0.001)
    p.add_argument('--output-dir',type=Path,default=ROOT/'live-mic/session')
    p.add_argument('--resident',action='store_true')
    p.add_argument('--manual',action='store_true')
    a=p.parse_args()
    if not 0<a.interval<=a.window<=30 or a.duration<0:p.error('Require 0 < interval <= window <= 30, duration >= 0')
    asr=ASR(a.language)
    if not a.resident:
        return capture_session(a,asr,threading.Event())
    # Warm encoder and decoder without opening the microphone.
    asr.transcribe(np.zeros(RATE,dtype=np.float32))
    emit('MODEL',{'status':'ready','backend':'ExecuTorch/QNN','resident':True})
    from rolling_context import RollingContext
    worker=None;stop_event=threading.Event();control=None
    try:
        for line in sys.stdin:
            command=json.loads(line)
            if command.get('action')=='start':
                if worker and worker.is_alive():continue
                if command.get('language','en') not in {'en','ko'} or command.get('target_language','ko') not in {'en','ko'}:
                    emit('MODEL',{'status':'error','error':'Unsupported language'});continue
                a.language=command.get('language','en');a.target_language=command.get('target_language','ko');a.session_id=command.get('session_id',0)
                stop_event=threading.Event();control=RollingContext(RATE,a.window)
                def run():
                    try:listen_session(a,asr,stop_event,control)
                    except Exception as error:emit('SESSION',{'status':'error','error':str(error)})
                    finally:emit('SESSION',{'status':'stopped'})
                worker=threading.Thread(target=run,daemon=True);worker.start()
            elif command.get('action')=='analyze':
                try:
                    if not worker or not worker.is_alive():raise ValueError('먼저 듣기를 시작해 주세요.')
                    emit('SNAPSHOT',{**control.freeze(),'capture_session_id':a.session_id})
                except ValueError as error:emit('REQUEST_ERROR',{'error':str(error)})
            elif command.get('action')=='stop':
                stop_event.set()
                if worker:worker.join(timeout=30)
            elif command.get('action')=='shutdown':break
    finally:
        stop_event.set()
        if worker:worker.join(timeout=30)

if __name__=='__main__':main()
