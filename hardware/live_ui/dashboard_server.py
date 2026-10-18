#!/usr/bin/env python3
"""Resident ASR/Qwen dashboard and physical IDK Button controller."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import uuid
from pathlib import Path
import subprocess,sys,threading,signal,urllib.request,time
from hardware_bridge import HardwareBridge
from dictionary_proxy import serve_dictionary, serve_dictionary_post
from word_recall import RecallTracker, forms, TOKEN, spoken_text
from asr_uncertainty import quality
from transcript_stream import merge_partial, SentenceLedger, sentence_request

ROOT=Path(__file__).resolve().parent
LOCK=threading.RLock()
RECALL=RecallTracker()
LIVE_SENTENCES=SentenceLedger();LIVE_CHANGED=threading.Condition(LOCK);LIVE_STREAM_ID=uuid.uuid4().hex;LIVE_REVISION=0
STATE={'chat_id':uuid.uuid4().hex,'chat_mode':None,'chat_messages':[],'chat_archive':[],'vocabulary':[],'recall':None,'status':'loading','stage':'loading','model_status':'loading','level':None,'event':None,'history':[],'logs':[],'error':None,'session':0,'words':[],'word_source':'','word_context':'','word_index':0,'word_notice':'','translation_notice':'','saved_translation_revision':0,'auto_saved_snapshot_id':None,'answers':[],'selected':0,'hardware':None,'hardware_error':None,'live':None,'snapshot':None,'snapshot_id':None,'context_decision':None,'pending_context':None,'generation':0,'context_mode':'sentences','frozen_sentence_context':'','requested_context_mode':'sentences','source_language':'en','target_language':'ko'}
try:
    STATE['chat_archive']=json.loads((ROOT/'chat-history.json').read_text())[-50:]
except (OSError,ValueError,TypeError):pass
PROCESS=None;SPEECH=None;SPEECH_ID=0;SERIAL='3220953353';CLOSING=False;HARDWARE=None
STAGES={'loading':3,'idle':0,'recording':1,'transcribing':2,'thinking':3,'ready':4,'speaking':5,'error':6,'clarifying':4}

def display(selection=None):
    # Current MCU has three digit slots. Word navigation uses cumulative rotation
    # counters and the screen highlight, so never send an out-of-range word index.
    if HARDWARE:
        HARDWARE.set_red_led(intention_mismatch())
        HARDWARE.set_green_led(translation_is_certain())
        HARDWARE.display(STAGES.get(STATE['stage'],0),-1 if selection is None else selection,len((STATE.get('pending_context') or {}).get('options',[])) or 0)

def translation_is_certain():
    """Return true only for a complete, calibrated, unambiguous button result."""
    if STATE.get('stage') != 'ready':
        return False
    translation=((STATE.get('event') or {}).get('translation') or {})
    confidence=translation.get('translation_confidence')
    if not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or confidence < 0.8:
        return False
    if translation.get('alternatives'):
        return False
    answers=STATE.get('answers') or []
    return len(answers)==3 and all(isinstance(answer,dict) and isinstance(answer.get('text'),str) and answer['text'].strip() for answer in answers)

def intention_mismatch():
    """Return whether the current user-visible result has unresolved intent."""
    if STATE.get('stage') in {'loading','idle','recording','transcribing','thinking','error'}:
        return False
    pending=STATE.get('pending_context')
    if pending and pending.get('kind')!='chat_mode':
        return True
    if (STATE.get('context_decision') or {}).get('needs_clarification'):
        return True
    alternatives=((STATE.get('event') or {}).get('translation') or {}).get('alternatives') or []
    return bool(alternatives)

def stage(value):
    STATE['stage']=value;display()
    print('Stage: '+value,flush=True)
    (ROOT/'runtime-state.json').write_text(json.dumps(STATE,ensure_ascii=False,indent=2)+'\n')

def consume(proc):
    kinds={'LEVEL','EVENT','LIVE','LIVE_PARTIAL','MODEL','SESSION','PHASE','SNAPSHOT','REQUEST_ERROR'}
    for line in proc.stdout:
        line=line.strip();kind,_,payload=line.partition(' ')
        with LOCK:
            if kind not in kinds:
                STATE['logs']=(STATE['logs']+[line])[-100:]
                if line.startswith('READY:'):STATE['status']='recording';stage('recording')
                continue
            try:data=json.loads(payload)
            except (ValueError,TypeError):continue
            if kind=='SNAPSHOT' and data.get('capture_session_id') is not None and data['capture_session_id']!=STATE['session']:continue
            if kind=='MODEL':
                STATE['model_status']=data['status']
                STATE['status']='idle' if data['status']=='ready' else 'error';stage(STATE['status'])
                if data['status']=='ready' and not CLOSING:
                    start({'language':STATE['source_language'],'target_language':STATE['target_language']})
            elif kind=='LEVEL':STATE['level']=data
            elif kind in {'LIVE','LIVE_PARTIAL'}:publish_live(data,partial=kind=='LIVE_PARTIAL')
            elif kind=='SNAPSHOT':
                STATE['snapshot']=data
                STATE['snapshot_id']=str(STATE['session'])+':'+str(data['request_id'])
            elif kind=='REQUEST_ERROR':STATE['error']=data['error'];stage('recording')
            elif kind=='PHASE':
                if STATE['stage']!='speaking':stage(data['state'])
            elif kind=='SESSION':
                STATE['status']=data['status'];STATE['error']=data.get('error')
                stage('error' if STATE['error'] else 'clarifying' if STATE.get('pending_context') else 'ready' if STATE['answers'] else 'idle')
            else:
                if data.get('capture_session_id') is not None and (data['capture_session_id']!=STATE['session'] or STATE['status'] not in {'recording','starting'}):continue
                data=normalize_event(data)
                data['frozen_sentence_context']=STATE.get('frozen_sentence_context','')
                data['context_mode']=STATE.get('requested_context_mode','sentences')
                STATE['history']=(STATE['history']+[data])[-25:]
                STATE['event']=data;STATE['error']=None
                if data.get('request_id') is not None:
                    STATE['snapshot']={k:data[k] for k in ['request_id','pressed_at','window_start_ms','window_end_ms','window_seconds'] if k in data}
                    STATE['snapshot_id']=str(STATE['session'])+':'+str(data['request_id'])
                if data['status']=='non_speech':
                    STATE.update(words=[],word_source='',word_notice='',answers=[],selected=0,pending_context=None,context_decision=None);display();stage('recording')
                else:process_snapshot(data)
    proc.wait()
    with LOCK:
        if not CLOSING:STATE.update(status='error',model_status='error',error='The board model connection closed.');stage('error')

def publish_live(data,partial=False):
    global LIVE_REVISION
    if data.get('capture_session_id') is not None and (data['capture_session_id']!=STATE['session'] or STATE['status'] not in {'recording','starting'}):return
    silent=(data.get('asr_quality') or {}).get('status')=='non_speech'
    view=LIVE_SENTENCES.update(data.get('transcript',''),partial=partial,silent=silent,
        start_ms=data.get('window_start_ms',0),end_ms=data.get('window_end_ms',0))
    previous=STATE.get('live') or {}
    if partial and all(view.get(k)==previous.get(k) for k in ['transcript','draft_text','speech_status']):return
    LIVE_REVISION+=1
    STATE['live']={**data,**view,'partial':partial,'revision':LIVE_REVISION,'stream_id':LIVE_STREAM_ID}
    LIVE_CHANGED.notify_all()
    if not partial:
        hits=RECALL.update(data.get('transcript',''),STATE.get('vocabulary',[]),silent=silent)
        if hits:
            STATE['recall']={'id':uuid.uuid4().hex,'chat_id':STATE['chat_id'],'hits':hits,'text':data.get('transcript',''),'time':time.time()}
            if HARDWARE:HARDWARE.flash_recall()

def normalize_event(data):
    if quality(data.get('transcript',''),None,None,False)['status']=='non_speech' or (data.get('asr_quality') or {}).get('status')=='non_speech':
        data={**data,'status':'non_speech','message':'No speech detected.','asr_quality':{**(data.get('asr_quality') or {}),'status':'non_speech'},'asr_alternatives':[]}
        data.pop('translation',None);data.pop('api_seconds',None)
    return data

def api_request(path,payload):
    request=urllib.request.Request('http://127.0.0.1:8000/'+path,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=180) as response:return json.load(response)

def dictionary_options(result, context, source_language, target_language):
    try:
        suggestions=api_request('dictionary/suggestions',{
            'source':result.get('source',''),
            'translation':result.get('translation',''),
            'source_language':source_language,
            'target_language':target_language,
            'context':context,
        })
    except Exception:
        return []
    options=[];seen=set()
    for term in suggestions.get('terms',[]):
        for match in term.get('matches',[]):
            meanings=match.get('meanings') or []
            meaning=meanings[0].get('meaning') if meanings else ''
            word=match.get('term') or term.get('observed')
            key=word.casefold()
            if not word or key in seen:
                continue
            seen.add(key)
            options.append({
                'word':word,'meaning':meaning,'status':'ready' if meaning else 'unresolved',
                'saved':None,'observed':term.get('observed',''),
                'match_type':match.get('match_type','similar'),
                'spelling_similarity':match.get('spelling_similarity',0),
            })
    return options

def process_snapshot(row):
    # Called under LOCK. A generation prevents old model responses replacing a newer snapshot.
    STATE['generation']+=1;generation=STATE['generation'];session=STATE['session']
    STATE.update(words=[],word_source='',word_notice='',event=dict(row),answers=[],selected=0,pending_context=None,context_decision=None,error=None)
    stage('thinking')
    text_request=sentence_request(row,row.get('context_mode','sentences'))
    row['model_context_text']='\n'.join(x for x in [text_request['context'],text_request['transcript']] if x)
    STATE['event']=dict(row)
    payload={**text_request,'source_language':STATE['source_language'],
             'target_language':STATE['target_language'],'elapsed_ms':row.get('elapsed_ms')}
    # Conversation style is optional. Ask about the actual ambiguous expression,
    # rather than making a first-time user choose a broad category first.
    def run():
        try:
            decision=api_request('context/resolve',payload)
            with LOCK:
                if CLOSING or session!=STATE['session'] or generation!=STATE['generation']:return
                STATE['context_decision']=decision
                if decision.get('decision_method')=='broad_context_fallback':
                    # Casual/Professional is a conversation preference, not a
                    # resolved word sense. Do not turn a failed analysis into a
                    # confident translation using only that category.
                    STATE['pending_context']=None
                    STATE['error']='The intended meaning is still unclear. Say one more sentence explaining the situation, then analyze again.'
                    stage('error');return
                if decision['needs_clarification']:
                    if len(decision['options'])!=2 or len(set(decision['options']))!=2:raise ValueError('Two distinct contexts are required')
                    STATE['pending_context']={**decision,'snapshot_id':STATE['snapshot_id']}
                    display(0);stage('clarifying');return
            translate_snapshot(row,payload,decision,session,generation)
        except Exception as error:
            with LOCK:
                if CLOSING or session!=STATE['session'] or generation!=STATE['generation']:return
                STATE['error']='Could not determine the context. Analyze again. '+str(error);stage('error')
    threading.Thread(target=run,daemon=True).start()

def translate_snapshot(row,payload,decision,session,generation,selection=None):
    # The original frozen transcript stays untouched, regardless of newer LIVE events.
    context=payload.get('context','')
    # Keep chat preference separate from the quoted conversation used to infer
    # a sense. A resolver must not cite "Professional" as spoken evidence.
    if STATE.get('chat_mode'):context+='\nChat category selected by the user (keep for this chat): '+STATE['chat_mode']
    if selection:context+='\nThe user explicitly selected this context: '+selection
    elif decision.get('topic'):context+='\nSupported topic: '+decision['topic']+'\nEvidence: '+decision.get('evidence','')
    request_payload={**payload,'context':context}
    # choose_context() already sets payload['context_selection'] (mapped through
    # option_contexts) for an explicit user pick — never override that. Only
    # fill it in here for an auto-resolve /context/resolve already settled
    # (reviewed rule or vote-share threshold), so translate() reuses that
    # result instead of independently resampling the same phrase and risking
    # a different, disagreeing split.
    if 'context_selection' not in request_payload and not selection and decision.get('topic') and not decision.get('needs_clarification'):
        request_payload['context_selection']=decision['topic']
    tick=time.perf_counter();result=api_request('interpret/button',request_payload)
    options=dictionary_options(result,context,STATE['source_language'],STATE['target_language'])
    with LOCK:
        if CLOSING or session!=STATE['session'] or generation!=STATE['generation']:return
        choices=decision if decision.get('options') else ({**decision,'options':decision['meaning_options'],
            'question':'Would you like to use a different meaning?'} if decision.get('meaning_options') else None)
        STATE['event']={**row,'chat_mode':STATE.get('chat_mode'),'translation':result,'translation_context':context,'api_seconds':time.perf_counter()-tick,'selected_context':selection,'clarification_options':choices}
        if selection:
            STATE['context_decision']={**decision,'needs_clarification':False,'topic':selection,
                'evidence':None,'question':None,'options':[],'decision_method':'user_selected_meaning'}
        STATE['chat_messages']=(STATE.get('chat_messages',[])+[dict(STATE['event'])])[-100:]
        STATE.update(answers=result['answers'],selected=0,pending_context=None,error=None)
        source=result.get('source') or decision.get('source') or payload['transcript']
        STATE.update(words=options,word_source=source,word_context=context,word_index=0,word_notice='')
        display(0);stage('ready')
    schedule_word()

def choose_context(index,snapshot_id):
    with LOCK:
        pending=STATE.get('pending_context')
        if not pending or pending['snapshot_id']!=snapshot_id:raise ValueError('This context question is stale. Choose from the current question.')
        if type(index)!=int or index not in (0,1):raise ValueError('Choose one context option.')
        if pending.get('kind')=='chat_mode':
            STATE['chat_mode']=['Casual','Professional'][index]
            STATE['pending_context']=None;process_snapshot(dict(STATE['event']));return
        row=dict(STATE['event']);session=STATE['session'];generation=STATE['generation']
        payload={**sentence_request(row,row.get('context_mode','sentences')),'source_language':STATE['source_language'],'target_language':STATE['target_language'],'elapsed_ms':row.get('elapsed_ms')}
        selection=pending['options'][index]
        STATE['event']={**row,'selected_context':selection}
        payload['context_selection']=pending.get('option_contexts',pending['options'])[index]
        STATE['pending_context']=None;stage('thinking')
    def run():
        try:translate_snapshot(row,payload,pending,session,generation,selection)
        except Exception as error:
            with LOCK:
                if CLOSING or session!=STATE['session'] or generation!=STATE['generation']:return
                STATE['pending_context']=pending;STATE['error']=str(error);stage('clarifying')
    threading.Thread(target=run,daemon=True).start()

def reopen_context(snapshot_id):
    """Reconsider only the currently displayed, completed frozen snapshot."""
    with LOCK:
        if snapshot_id != STATE.get('snapshot_id'):
            raise ValueError('This result is stale. Use the current translation.')
        if STATE['stage'] != 'ready' or STATE.get('pending_context'):
            raise ValueError('Wait for the translation to finish.')
        event=STATE.get('event') or {}
        choices=event.get('clarification_options')
        if not choices or len(choices.get('options',[])) != 2:
            raise ValueError('No meaning choices are available for this result.')
        STATE['generation']+=1
        STATE['event']={key:value for key,value in event.items()
                        if key not in {'translation','translation_context','selected_context','clarification_options'}}
        decision={**choices,'needs_clarification':True,'topic':None,'evidence':None}
        STATE.update(answers=[],words=[],word_source='',word_notice='',selected=0,error=None,
                     context_decision=decision,pending_context={**decision,'snapshot_id':snapshot_id})
        stage('clarifying')

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
    if PROCESS is None or PROCESS.poll() is not None:raise RuntimeError('Check the model connection.')
    PROCESS.stdin.write(json.dumps(command)+'\n');PROCESS.stdin.flush()

def start(data):
    global LIVE_SENTENCES
    with LOCK:
        if STATE['model_status']!='ready':raise ValueError('Wait until the model is ready.')
        if STATE['status'] in {'starting','recording','stopping'}:return
        language=data.get('language','en');target=data.get('target_language','ko')
        if language not in {'en','ko'} or target not in {'en','ko'}:raise ValueError('Unsupported language')
        LIVE_SENTENCES=SentenceLedger()
        send({'action':'start','language':language,'target_language':target,'session_id':STATE['session']+1})
        STATE.update(words=[],word_source='',word_notice='',status='starting',level=None,live=None,event=None,history=[],error=None,session=STATE['session']+1,generation=STATE['generation']+1,answers=[],selected=0,pending_context=None,context_decision=None,snapshot=None,snapshot_id=None,target_language=target,source_language=language)
        stage('recording')

def reset_chat_state():
    global RECALL,LIVE_SENTENCES,LIVE_REVISION,LIVE_STREAM_ID,SPEECH_ID
    preserved = {
        key: STATE.get(key)
        for key in ('chat_archive', 'vocabulary', 'vocabulary_error',
                    'context_mode', 'source_language', 'target_language',
                    'model_status', 'hardware', 'hardware_error')
    }
    STATE.update(
        chat_id=uuid.uuid4().hex, chat_mode=None, chat_messages=[], recall=None,
        status='idle', stage='idle', level=None, event=None, history=[], logs=[],
        error=None, words=[], word_source='', word_context='', word_index=0,
        word_notice='', answers=[], selected=0, live=None, snapshot=None,
        snapshot_id=None, context_decision=None, pending_context=None,
        frozen_sentence_context='', requested_context_mode=preserved['context_mode'],
        tts=None, generation=STATE.get('generation', 0) + 1,
    )
    STATE.update(preserved)
    RECALL=RecallTracker()
    LIVE_SENTENCES=SentenceLedger()
    LIVE_STREAM_ID=uuid.uuid4().hex
    LIVE_REVISION+=1
    SPEECH_ID+=1
    if HARDWARE:
        HARDWARE.clear_recall()
        HARDWARE.set_red_led(False)
        HARDWARE.set_green_led(False)
    if SPEECH is not None and SPEECH.poll() is None:
        SPEECH.terminate()


def new_chat():
    global RECALL,LIVE_SENTENCES,LIVE_REVISION,LIVE_STREAM_ID,SPEECH_ID
    with LOCK:
        if STATE['model_status']!='ready':raise ValueError('The model is still starting.')
        archive={'id':STATE['chat_id'],'mode':STATE.get('chat_mode'),'messages':STATE.get('chat_messages',[]),'ended_at':time.time()}
        STATE['chat_archive']=(STATE.get('chat_archive',[])+[archive])[-50:]
        (ROOT/'chat-history.json').write_text(json.dumps(STATE['chat_archive'],ensure_ascii=False,indent=2))
        # Stop and start are ordered on the board stdin; stop joins the old audio
        # worker before start creates an empty PCM ring for the new chat.
        send({'action':'stop'})
        reset_chat_state()
        start({'language':STATE['source_language'],'target_language':STATE['target_language']})
        LIVE_CHANGED.notify_all()

def refresh_vocabulary():
    while not CLOSING:
        try:
            entries=[]
            for offset in range(0,10000,100):
                with urllib.request.urlopen('http://127.0.0.1:8000/expressions?limit=100&offset='+str(offset),timeout=10) as response:batch=json.load(response)
                entries+=batch
                if len(batch)<100:break
            with LOCK:
                old={x['expression'].casefold() for x in STATE.get('vocabulary',[])}
                text=(STATE.get('live') or {}).get('transcript','')
                prime_vocabulary(entries,old,text)
                STATE['vocabulary']=entries
        except Exception as error:
            with LOCK:STATE['vocabulary_error']='Could not sync the wordbook: '+str(error)
        else:
            with LOCK:STATE['vocabulary_error']=None
        for _ in range(50):
            if CLOSING:return
            time.sleep(.1)

def prime_vocabulary(entries,old,text):
    tokens=TOKEN.findall(spoken_text(text))
    for entry in entries:
        key=entry['expression'].casefold()
        if key not in old:RECALL.previous[key]=sum(bool(forms(t)&forms(key)) for t in tokens)

def analyze():
    with LOCK:
        if STATE['status']!='recording':raise ValueError('Start listening first.')
        if STATE['stage'] in {'thinking','transcribing','speaking'}:return
        STATE['frozen_sentence_context']=(STATE.get('live') or {}).get('transcript','')
        STATE['requested_context_mode']=STATE.get('context_mode','sentences')
        STATE.update(words=[],word_source='',word_notice='',error=None,event=None,answers=[],selected=0,pending_context=None,context_decision=None);STATE['generation']+=1
        send({'action':'analyze'});stage('transcribing')

def stop():
    with LOCK:
        if STATE['status'] in {'starting','recording'}:
            send({'action':'stop'});STATE['status']='stopping';STATE['generation']+=1

def speak():
    global SPEECH,SPEECH_ID
    with LOCK:
        if not STATE['answers']:raise ValueError('There are no answers to play yet.')
        if STATE['stage'] in {'thinking','transcribing'}:raise ValueError('Analysis is still in progress.')
        if SPEECH is not None and SPEECH.poll() is None:SPEECH.terminate()
        text=STATE['answers'][STATE['selected']]['text']
        voice='Yuna (Korean (South Korea))' if STATE.get('target_language','ko')=='ko' else 'Samantha (English (United States))'
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

def hardware_error(message):
    with LOCK:
        STATE['hardware_error']=message
        if HARDWARE:
            HARDWARE.set_red_led(False)
            HARDWARE.set_green_led(False)

def hardware_sample(value):
    with LOCK:
        if CLOSING:return
        previous=STATE['hardware'];STATE['hardware']=value;STATE['hardware_error']=None
        display()
        if not previous:return
        changed={key:value[key]-previous[key] for key in ['rotations','clicks','holds']}
        pending=STATE.get('pending_context')
        count=len(pending['options']) if pending else len(STATE.get('words',[]))
        if count and changed['rotations']:
            if pending:STATE['selected']=(STATE['selected']+changed['rotations'])%count
            else:select_word((STATE['word_index']+changed['rotations'])%count)
        if not any(changed.values()):return
        event={'time':time.time(),'delta':changed,'state':value,'stage':STATE['stage']}
        with (ROOT/'hardware-events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        if STATE['model_status']!='ready':return
        # Workaround for a physical click that is not registering reliably:
        # every rotation step also confirms, in addition to still moving the
        # selection exactly as before (above). `changed['clicks']` itself is
        # left untouched (real click count, as logged in the event above);
        # only this local trigger value folds rotation in.
        effective_clicks=changed['clicks']+(abs(changed['rotations']) if not changed['holds'] else 0)
        try:
            if changed['holds']>0 or effective_clicks>0:
                pending=STATE.get('pending_context')
                if changed['holds']>0:new_chat()
                elif pending and effective_clicks>0 and not changed['holds']:
                    choose_context(STATE['selected'],pending['snapshot_id'])
                elif (effective_clicks>0 and not changed['holds'] and STATE['stage']=='ready' and STATE.get('answers')
                      and STATE.get('auto_saved_snapshot_id')!=STATE.get('snapshot_id')):
                    # The button's main job: press it to keep the sentence you
                    # just heard translated. Takes priority over word-saving
                    # below, which only applies once nothing is left to save.
                    # Guarded by snapshot_id so repeated clicks on the same
                    # result do not create duplicate saved entries.
                    threading.Thread(target=save_translation_safely,daemon=True).start()
                elif effective_clicks>0 and not changed['holds'] and STATE.get('words'):
                    index=STATE['word_index'];generation=STATE['generation']
                    threading.Thread(target=save_word_safely,args=(index,generation),daemon=True).start()
                elif STATE['status']=='recording':analyze()
                else:start({'language':STATE['source_language'],'target_language':STATE['target_language']})
        except Exception as error:
            STATE['error']=str(error)
            stage('error')
def schedule_word():
    with LOCK:
        if not STATE.get('words') or STATE.get('pending_context'):return
        index=STATE['word_index'];generation=STATE['generation'];session=STATE['session']
        token=STATE['words'][index]
        if token['status'] not in {'waiting','error'}:return
        payload={'source':STATE['word_source'],'index':index,'context':STATE['word_context'],'target_language':STATE['target_language']}
    def lookup():
        # Debounce rotations. Only the word the user rests on starts a model request.
        time.sleep(.35)
        with LOCK:
            if generation!=STATE['generation'] or session!=STATE['session'] or index!=STATE['word_index']:return
            if token['status'] not in {'waiting','error'}:return
            token['status']='loading'
        try:
            result=api_request('words/meaning',payload)
            with LOCK:
                if generation==STATE['generation'] and session==STATE['session'] and token in STATE['words']:token.update(result)
        except Exception:
            with LOCK:
                if generation==STATE['generation'] and session==STATE['session']:token.update(status='error',meaning=None)
    threading.Thread(target=lookup,daemon=True).start()

def select_word(index):
    with LOCK:
        if STATE.get('pending_context'):raise ValueError('Choose the context first.')
        if type(index)!=int or not 0<=index<len(STATE.get('words',[])):raise ValueError('Invalid word selection')
        STATE['word_index']=index;STATE['word_notice']='';schedule_word();display()

def save_current_word(index=None,generation=None):
    with LOCK:
        if generation is not None and generation!=STATE['generation']:raise ValueError('The result changed. Select the word again.')
        if index is not None and index!=STATE['word_index']:raise ValueError('The selected word changed. Press again.')
        if STATE.get('pending_context') or STATE['stage'] in {'thinking','transcribing','clarifying','error'}:raise ValueError('Wait until analysis is complete before saving.')
        tokens=STATE.get('words',[])
        if not tokens:raise ValueError('There are no similar or possible words to save.')
        token=tokens[STATE['word_index']]
        if token.get('saved'):return token['saved']
        if token.get('saving'):raise ValueError('The word is already being saved.')
        if token['status']!='ready' or not token.get('meaning'):raise ValueError('Wait for the word meaning before saving.')
        token['saving']=True
        payload={'expression':token['word'],'meaning':token['meaning'],'translation':token['meaning'],'example':STATE['word_source'],'target_language':STATE['target_language']}
    try:result=api_request('expressions',payload)
    finally:
        with LOCK:token['saving']=False
    with LOCK:
        token['saved']=result
        old={x['expression'].casefold() for x in STATE.get('vocabulary',[])}
        prime_vocabulary([result],old,(STATE.get('live') or {}).get('transcript',''))
        STATE['vocabulary']=[result]+STATE.get('vocabulary',[])
        if token in STATE.get('words',[]):STATE['word_notice']=token['word']+' saved to your wordbook.'
    return result

def save_word_safely(index=None,generation=None):
    try:save_current_word(index,generation)
    except Exception as error:
        with LOCK:STATE['word_notice']=str(error)

def save_translation_safely():
    # Fire-and-forget from a physical knob click: there is no HTTP caller
    # waiting on a response, so success/failure is reported through STATE for
    # the dashboard to pick up on its next poll (same pattern as word_notice).
    try:
        saved=save_current_translation()
        with LOCK:STATE['translation_notice']='Saved sentence #'+str(saved['id'])+' to your saved sentences.'
    except Exception as error:
        with LOCK:STATE['translation_notice']=str(error)

def save_current_translation():
    with LOCK:
        if STATE.get('pending_context') or STATE['stage'] in {'thinking', 'transcribing', 'clarifying'}:
            raise ValueError('Wait for the current analysis to finish.')
        event=STATE.get('event') or {}
        if (event.get('asr_quality') or {}).get('status')=='non_speech' or quality(event.get('transcript',''),None,None,False)['status']=='non_speech':
            raise ValueError('No speech detected.')
        result = event.get('translation')
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
        saved=json.load(response)
    with LOCK:
        STATE['saved_translation_revision']+=1
        STATE['auto_saved_snapshot_id']=STATE.get('snapshot_id')
    return saved

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,data,content_type='application/json; charset=utf-8'):
        raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if serve_dictionary(self, ROOT):return
        if self.path in {'/dashboard.css','/clarification_view.js','/dashboard.js','/idk_icons.js'}:
            self.reply(200,(ROOT/self.path[1:]).read_bytes(),
                       'text/css; charset=utf-8' if self.path.endswith('.css') else 'application/javascript; charset=utf-8')
            return
        if self.path == '/':
            self.reply(200, (ROOT / 'dashboard.html').read_bytes(),
                       'text/html; charset=utf-8')
        elif self.path == '/transcript_view.js':
            self.reply(200,(ROOT/'transcript_view.js').read_bytes(),'application/javascript; charset=utf-8')
        elif self.path == '/api/live':
            self.live_events()
        elif self.path == '/api/state':
            with LOCK:
                self.reply(200, STATE)
        elif self.path == '/api/words':
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/expressions',timeout=10) as response:self.reply(200,json.load(response))
            except Exception:self.reply(502,{'error':'Could not load the wordbook.'})
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
    def live_events(self):
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
        revision=-1
        try:
            while not CLOSING:
                with LIVE_CHANGED:
                    if revision==LIVE_REVISION:LIVE_CHANGED.wait(timeout=15)
                    revision=LIVE_REVISION;data=STATE.get('live')
                if data:
                    self.wfile.write(('event: transcript\ndata: '+json.dumps(data,ensure_ascii=False)+'\n\n').encode())
                else:self.wfile.write(b': listening\n\n')
                self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):pass

    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://127.0.0.1:8010','http://localhost:8010'}:self.reply(403,{'error':'Invalid origin'});return
        if serve_dictionary_post(self):return
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
            elif self.path=='/api/word-select':select_word(data.get('index'))
            elif self.path=='/api/word-save':
                self.reply(201,save_current_word(data.get('index'),data.get('generation')));return
            elif self.path=='/api/stop':stop()
            elif self.path=='/api/analyze':analyze()
            elif self.path=='/api/new-chat':new_chat()
            elif self.path=='/api/speak':speak()
            elif self.path=='/api/context-mode':
                mode=data.get('mode')
                if mode not in {'sentences','time'}:raise ValueError('Invalid context mode')
                with LOCK:STATE['context_mode']=mode
            elif self.path=='/api/context':choose_context(data.get('index'),data.get('snapshot_id'))
            elif self.path=='/api/context-reopen':reopen_context(data.get('snapshot_id'))
            elif self.path=='/api/chat-mode':
                mode=data.get('mode')
                if mode not in {None,'Casual','Professional'}:raise ValueError('Invalid conversation style')
                with LOCK:STATE['chat_mode']=mode
            elif self.path=='/api/select':
                with LOCK:
                    index=data.get('index')
                    count=len((STATE.get('pending_context') or {}).get('options',[])) or len(STATE['answers'])
                    if type(index)!=int or not 0<=index<count:raise ValueError('Invalid selection')
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
    threading.Thread(target=refresh_vocabulary,daemon=True).start()
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
        HARDWARE.set_red_led(False);HARDWARE.set_green_led(False);HARDWARE.close();server.server_close()
