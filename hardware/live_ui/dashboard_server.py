#!/usr/bin/env python3
"""Resident ASR/Qwen dashboard and physical IDK Button controller."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import subprocess,sys,threading,signal,urllib.request,time
from hardware_bridge import HardwareBridge

ROOT=Path(__file__).resolve().parent
LOCK=threading.RLock()
STATE={'status':'loading','stage':'loading','model_status':'loading','level':None,'event':None,'history':[],'logs':[],'error':None,'session':0,'answers':[],'selected':0,'hardware':None,'hardware_error':None}
PROCESS=None;SPEECH=None;SPEECH_ID=0;SERIAL='3220953353';CLOSING=False;HARDWARE=None
STAGES={'loading':3,'idle':0,'recording':1,'transcribing':2,'thinking':3,'ready':4,'speaking':5,'error':6}

def display(selection=None):
    if HARDWARE:
        HARDWARE.display(STAGES.get(STATE['stage'],0),-1 if selection is None else selection,len(STATE['answers']))

def stage(value):
    STATE['stage']=value;display()
    print('Stage: '+value,flush=True)
    (ROOT/'runtime-state.json').write_text(json.dumps(STATE,ensure_ascii=False,indent=2)+'\n')

def consume(proc):
    for line in proc.stdout:
        line=line.strip()
        with LOCK:
            if line.startswith(('LEVEL ','EVENT ','MODEL ','SESSION ','PHASE ')):
                try:kind,payload=line.split(' ',1);data=json.loads(payload)
                except (ValueError,TypeError):continue
                if kind=='MODEL':
                    STATE['model_status']=data['status'];print('Board model: '+data['status'],flush=True)
                    STATE['status']='idle' if data['status']=='ready' else 'error';stage(STATE['status'])
                elif kind=='LEVEL':STATE['level']=data
                elif kind=='PHASE':
                    if STATE['stage']!='speaking':stage(data['state'])
                elif kind=='SESSION':
                    STATE['status']=data['status'];STATE['error']=data.get('error') or STATE['error']
                    stage('error' if STATE['error'] else 'ready' if STATE['answers'] else 'idle')
                else:
                    STATE['event']=data;STATE['history']=(STATE['history']+[data])[-25:];STATE['error']=data.get('api_error')
                    answers=(data.get('translation') or {}).get('answers')
                    if answers:STATE['answers']=answers;display()
                    elif (data.get('asr_quality') or {}).get('status')=='non_speech':STATE['answers']=[];STATE['selected']=0;display()
            else:
                STATE['logs']=(STATE['logs']+[line])[-100:]
                if line.startswith('READY:'):STATE['status']='recording';stage('recording')
    proc.wait()
    with LOCK:
        if not CLOSING:STATE.update(status='error',model_status='error',error='보드 모델 연결이 종료되었습니다.');stage('error')

def initialize():
    global PROCESS
    try:
        payload={'transcript':'Hello.','target_language':'ko'}
        request=urllib.request.Request('http://127.0.0.1:8000/interpret',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=180) as response:
            if response.status!=200:raise RuntimeError('LLM warm-up failed')
        with LOCK:
            if CLOSING:return
            PROCESS=subprocess.Popen([sys.executable,'-u',str(ROOT/'run_live_mic.py'),'--serial',SERIAL,'--resident','--button-ui',
                '--pid-file','/home/arduino/asr-executorch-test/live-mic/dashboard-resident.pid'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            threading.Thread(target=consume,args=(PROCESS,),daemon=True).start()
    except Exception as error:
        with LOCK:STATE.update(status='error',model_status='error',error=str(error));stage('error')

def send(command):
    if PROCESS is None or PROCESS.poll() is not None:raise RuntimeError('모델 연결을 확인하세요.')
    PROCESS.stdin.write(json.dumps(command)+'\n');PROCESS.stdin.flush()

def start(data):
    with LOCK:
        if STATE['model_status']!='ready':raise ValueError('모델 준비가 완료될 때까지 기다려 주세요.')
        if STATE['status'] in {'starting','recording','stopping'}:return
        language=data.get('language','en');target=data.get('target_language','ko')
        if language not in {'en','ko'} or target not in {'en','ko'}:raise ValueError('Unsupported language')
        send({'action':'start','language':language,'target_language':target})
        STATE.update(status='starting',level=None,event=None,history=[],error=None,session=STATE['session']+1,answers=[],selected=0,target_language=target,source_language=language)
        stage('recording')

def analyze():
    with LOCK:
        if STATE['status']!='recording':raise ValueError('입력을 먼저 시작하세요.')
        if STATE['stage'] in {'thinking','transcribing','speaking'}:return
        send({'action':'analyze'});STATE['error']=None;stage('recording')

def stop():
    with LOCK:
        if STATE['status'] in {'starting','recording'}:send({'action':'stop'});STATE['status']='stopping'

def speak():
    global SPEECH,SPEECH_ID
    with LOCK:
        if not STATE['answers']:raise ValueError('아직 선택할 답변이 없습니다.')
        if STATE['stage'] in {'thinking','transcribing'}:raise ValueError('현재 분석 중입니다.')
        if SPEECH is not None and SPEECH.poll() is None:SPEECH.terminate()
        text=STATE['answers'][STATE['selected']]['text']
        voice='Yuna (한국어(한국))' if STATE.get('target_language','ko')=='ko' else 'Samantha (영어(미국))'
        SPEECH_ID+=1;request_id=SPEECH_ID
        SPEECH=subprocess.Popen(['/usr/bin/say','-v',voice,text],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        proc=SPEECH;STATE['error']=None
        STATE['tts']={'request_id':request_id,'status':'playing','selected':STATE['selected']}
        with (ROOT/'tts-events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),**STATE['tts']})+'\n')
        stage('speaking')
    def done():
        _,error=proc.communicate()
        with LOCK:
            status='interrupted' if proc is not SPEECH else 'error' if proc.returncode else 'completed'
            with (ROOT/'tts-events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'request_id':request_id,'status':status,'exit_code':proc.returncode})+'\n')
            # Completion from an interrupted player must not overwrite the new player.
            if CLOSING or proc is not SPEECH:return
            STATE['tts']['status']=status
            if proc.returncode:STATE['error']='TTS: '+error.strip();stage('error')
            else:stage('ready')
    threading.Thread(target=done,daemon=True).start()

def choose_transcript(index):
    with LOCK:
        if STATE['stage'] in {'thinking','transcribing','speaking'}:raise ValueError('현재 작업이 끝난 뒤 선택하세요.')
        row=STATE.get('event') or {}
        primary=row.get('asr_primary_transcript',row.get('transcript'))
        candidates=[primary]+[x['text'] for x in row.get('asr_alternatives',[])]
        if type(index)!=int or not 0<=index<len(candidates) or not candidates[index]:raise ValueError('Invalid transcript candidate')
        chosen=candidates[index];session=STATE['session'];STATE['error']=None
        payload={'transcript':chosen,'context':'','source_language':STATE.get('source_language','en'),
            'target_language':STATE.get('target_language','ko'),'elapsed_ms':row.get('elapsed_ms')}
        original=dict(row);stage('thinking')
    def translate_choice():
        tick=time.perf_counter()
        try:
            request=urllib.request.Request('http://127.0.0.1:8000/interpret/button',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response);status=response.status
            with LOCK:
                if CLOSING or STATE['session']!=session:return
                updated={**original,'asr_primary_transcript':primary,'transcript':chosen,'asr_selected_index':index,
                    'translation':result,'http_status':status,'api_seconds':time.perf_counter()-tick}
                updated.pop('api_error',None)
                STATE['event']=updated;STATE['answers']=result['answers'];STATE['selected']=0
                STATE['history']=(STATE['history']+[updated])[-25:];display(0);stage('ready')
        except Exception as error:
            with LOCK:
                if CLOSING or STATE['session']!=session:return
                STATE['error']=str(error);stage('error')
    threading.Thread(target=translate_choice,daemon=True).start()

def hardware_error(message):
    with LOCK:STATE['hardware_error']=message

def hardware_sample(value):
    with LOCK:
        if CLOSING:return
        previous=STATE['hardware'];STATE['hardware']=value;STATE['hardware_error']=None
        if not previous:return
        if STATE['answers']:STATE['selected']=min(value['selected'],len(STATE['answers'])-1)
        changed={key:value[key]-previous[key] for key in ['rotations','clicks','holds']}
        if not any(changed.values()):return
        event={'time':time.time(),'delta':changed,'state':value,'stage':STATE['stage']}
        with (ROOT/'hardware-events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        if STATE['model_status']!='ready':return
        try:
            if changed['holds']>0:
                if STATE['status'] not in {'starting','recording','stopping'}:start({})
                else:analyze()
            elif changed['clicks']>0:
                if STATE['answers'] and STATE['stage'] in {'ready','speaking'}:speak()
                elif STATE['status'] not in {'starting','recording','stopping'}:start({})
                else:analyze()
        except Exception as error:STATE['error']=str(error)
def save_current_translation():
    with LOCK:
        if STATE['stage'] in {'thinking', 'transcribing'}:
            raise ValueError('Wait for the current analysis to finish.')
        result = (STATE.get('event') or {}).get('translation')
        if not result:
            raise ValueError('No translation to save yet.')
        payload = {key: result[key] for key in (
            'elapsed_ms', 'source_language', 'target_language',
            'source', 'translation_confidence', 'translation', 'alternatives'
        )}
        body = json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(
        'http://127.0.0.1:8000/translations',
        data=body,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,data,content_type='application/json; charset=utf-8'):
        raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path == '/':
            self.reply(200, (ROOT / 'dashboard.html').read_bytes(),
                       'text/html; charset=utf-8')
        elif self.path == '/api/state':
            with LOCK:
                self.reply(200, STATE)
        elif self.path == '/api/translations':
            try:
                with urllib.request.urlopen(
                    'http://127.0.0.1:8000/translations', timeout=10
                ) as response:
                    result = json.load(response)
                self.reply(200, result)
            except Exception:
                self.reply(502, {
                    'error': 'Could not load saved translations. Check that FastAPI is running.'
                })
        else:
            self.reply(404, {'error': 'Not found'})
    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://127.0.0.1:8010','http://localhost:8010'}:self.reply(403,{'error':'Invalid origin'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=2048:raise ValueError('Request too large')
            data=json.loads(self.rfile.read(length) or b'{}')
            if self.path=='/api/start':start(data)
            elif self.path == '/api/save':
                try:
                    saved = save_current_translation()
                except ValueError as error:
                    self.reply(400, {'error': str(error)})
                    return
                except Exception:
                    self.reply(502, {'error': 'Could not save translation. Check that FastAPI is running.'})
                    return
                self.reply(201, saved)
                return
            elif self.path=='/api/stop':stop()
            elif self.path=='/api/analyze':analyze()
            elif self.path=='/api/speak':speak()
            elif self.path=='/api/transcript':choose_transcript(data.get('index'))
            elif self.path=='/api/select':
                with LOCK:
                    index=data.get('index')
                    if type(index)!=int or not 0<=index<len(STATE['answers']):raise ValueError('Invalid selection')
                    STATE['selected']=index;display(index)
            else:self.reply(404,{'error':'Not found'});return
            self.reply(200,{'ok':True})
        except Exception as error:self.reply(400,{'error':str(error)})
    def log_message(self,*args):pass

if __name__=='__main__':
    def terminate(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    server=ThreadingHTTPServer(('127.0.0.1',8010),Handler)
    HARDWARE=HardwareBridge(SERIAL,hardware_sample,hardware_error);HARDWARE.start()
    threading.Thread(target=initialize,daemon=True).start()
    print('Dashboard: http://127.0.0.1:8010',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        CLOSING=True
        with LOCK:
            if SPEECH is not None and SPEECH.poll() is None:SPEECH.terminate()
            if PROCESS is not None and PROCESS.poll() is None:send({'action':'shutdown'})
        if PROCESS is not None:
            try:PROCESS.wait(timeout=195)
            except subprocess.TimeoutExpired:PROCESS.terminate()
        HARDWARE.close();server.server_close()
