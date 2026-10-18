const $=id=>document.getElementById(id);let busy=false,lastAnswers='',lastContext='',lastContextBadge='',lastWordNotice='',lastTranslationNotice='',lastSavedRevision=-1,currentChatId=null;const names={translation:'Natural translation',literal:'Literal translation',explanation:'Context explanation'};
function showSnackbar(text,failed=false){const bar=$('snackbar');bar.textContent=text;bar.className='snackbar visible'+(failed?' error':'');clearTimeout(window.snackbarTimer);window.snackbarTimer=setTimeout(()=>bar.className='snackbar',3500);}
window.selectDictionaryWord=index=>action('word-select',{index});
async function action(path,extra={}){if(busy)return;busy=true;try{const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({language:$('language').value,target_language:$('target').value,...extra})});const d=await r.json();if(!r.ok)throw Error(d.error||'Could not complete this action.');await refresh()}catch(e){$('error').textContent=e.message;if(path==='word-save')showSnackbar(e.message,true)}finally{busy=false}}
$('newChat').onclick=()=>action('new-chat');
for(const id of ['start','stop','analyze','speak'])$(id).onclick=()=>action(id);
$('analyze').onclick=()=>storageState?.preview_mode?action('preview-example',{index:Number($('previewExample').value)}):action('analyze');
$('contextRetry').onclick=()=> $('analyze').onclick();
$('contextMode').onchange=()=>action('context-mode',{mode:$('contextMode').value});
$('chatMode').onchange=()=>action('chat-mode',{mode:$('chatMode').value||null});
$('previewExample').onchange=()=>action('preview-example',{index:Number($('previewExample').value)});
let previewNames='';
for(const button of document.querySelectorAll('[data-idk-nav]')){
 button.onclick=async()=>{
  const wordbook=button.dataset.idkNav==='wordbook';
  $('conversationPage').hidden=wordbook;$('storagePanel').hidden=!wordbook;
  for(const nav of document.querySelectorAll('[data-idk-nav]'))nav.setAttribute('aria-pressed',String(nav===button));
  if(wordbook)await $('reviewTranslations').onclick();
 };
}
$('changeMeaning').onclick=()=>action('context-reopen',{snapshot_id:storageState?.snapshot_id});
let liveStreamId=null,liveRevision=-1;
function resetChatUi(){
  lastAnswers='';lastContext='';lastContextBadge='';lastWordNotice='';lastTranslationNotice='';
  liveStreamId=null;liveRevision=-1;window.archiveKey=null;
  for(const id of ['liveTranscript','source','selected','snapshotRange','targetSource','asrQuality','json','wordNotice','contextTopic','contextEvidence','contextPrompt','chatCategory','chatInfo','storageStatus','asr','api','elapsed','selectionLabel']){
    $(id).textContent='';
  }
  $('liveTranscript').textContent='Waiting for speech.';
  $('source').textContent='Speak after listening starts.';
  $('selected').textContent='Your translation will appear here.';
  $('selectionLabel').textContent='Choose Understand this when you need a little clarity.';
  $('asr').textContent='—';$('api').textContent='—';$('elapsed').textContent='00:00';
  $('level').textContent='— dBFS';$('fill').style.width='0';
  $('json').textContent='No result yet.';
  $('chatCategory').textContent='Automatic context';
  $('chatInfo').textContent='Context comes from the conversation.';
  $('contextCategory').textContent='No context selected';
  $('contextOrigin').textContent='';$('contextOrigin').hidden=true;
  $('contextSummary').className='context-summary unknown';
  $('contextQuestion').hidden=true;$('contextOptions').replaceChildren();
  $('answers').replaceChildren();$('number').textContent='—';
  $('savedTranslations').replaceChildren();$('savedTranslations').hidden=true;
  $('recallNotice').hidden=true;$('error').textContent='';
}
function showLive(live,active=true){
  if(live && live.stream_id===liveStreamId && live.revision<liveRevision)return;
  if(live?.stream_id!==liveStreamId){liveStreamId=live?.stream_id;liveRevision=-1;}
  if(live?.revision!==undefined)liveRevision=live.revision;
  const silent=live?.speech_status==='non_speech'||live?.asr_quality?.status==='non_speech';
  const text=live?.transcript||(silent?'No speech detected.':active?'Waiting for speech.':'Listening is paused.');
  let range=null;
  if(live?.sentence_based){if(live.draft_text)range={start:(live.committed_text||'').length+(live.committed_text?1:0),end:text.length};}
  else if(!silent&&live?.transcript)range=TranscriptView.lastSentence(text);
  TranscriptView.render($('liveTranscript'),text,range,'live');
  const count=live?.confirmed_sentences?.length||0;
$('liveProgress').textContent=silent?(live?.transcript?'No speech · keeping the previous transcript.':'No speech'):live?.sentence_based?`${count} sentence(s) captured · the highlighted sentence is live`:live?.partial?'Listening · the sentence may change':'Latest transcript · listening for the next word';
}
const liveEvents=new EventSource('/api/live');
liveEvents.addEventListener('transcript',event=>{try{showLive(JSON.parse(event.data));}catch(error){console.warn('Live transcript event failed',error);}});
window.addEventListener('pagehide',()=>liveEvents.close(),{once:true});
function elapsed(ms){const seconds=Math.floor((ms||0)/1000);return String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')}
let refreshing=false;
async function refresh(){if(refreshing)return;refreshing=true;try{const response=await fetch('/api/state',{signal:AbortSignal.timeout(7000)});if(!response.ok)throw Error('Server unavailable');const s=await response.json();const newChat=currentChatId!==null&&currentChatId!==s.chat_id;if(newChat)resetChatUi();currentChatId=s.chat_id;updateStorageControls(s);if(!newChat)window.updateDictionarySuggestions?.(s);$('language').value=s.source_language||'en';$('target').value=s.target_language||'ko';const active=['starting','recording','stopping'].includes(s.status),working=['transcribing','thinking','speaking'].includes(s.stage);$('start').disabled=active||s.model_status!=='ready';$('stop').disabled=!active||s.status==='stopping';$('analyze').disabled=!s.preview_mode&&(s.status!=='recording'||working);$('speak').disabled=!s.answers.length||['transcribing','thinking'].includes(s.stage);$('language').disabled=active;$('target').disabled=active;$('badge').textContent=({loading:'Model starting',idle:'Ready',recording:'● Recording',transcribing:'Transcribing',thinking:'Analyzing context',ready:'Choose an answer',speaking:'Playing audio',error:'Error',clarifying:'Choose a context'})[s.stage]||s.stage;$('badge').className='badge'+(s.model_status==='ready'?' active':'');$('error').textContent=[s.error,s.hardware_error&&'Knob: '+s.hardware_error].filter(Boolean).join('\n');
if(s.level){const db=20*Math.log10(Math.max(s.level.rms,1e-6));$('level').textContent=Math.round(db)+' dBFS';$('fill').style.width=Math.max(0,Math.min(100,(db+65)/65*100))+'%';$('elapsed').textContent=elapsed(s.level.elapsed_ms)}
$('contextMode').value=s.context_mode||'sentences';$('contextMode').disabled=working||Boolean(s.pending_context);
$('listener').textContent=s.preview_mode?'Example preview':active?'Listening':'Paused';
$('start').hidden=active;$('stop').hidden=!active;
$('contextRetry').disabled=working||busy;
showLive(s.live,active);
$('newChat').disabled=s.model_status!=='ready';
$('chatCategory').textContent=s.chat_mode?`${s.chat_mode} · active for this chat`:'Automatic context';
$('chatInfo').textContent=s.chat_mode?'The topic is inferred from the conversation. New chat resets this setting.':'Context comes from the conversation. Previous chats do not affect it.';
const recall=s.recall;const showRecall=recall&&recall.chat_id===s.chat_id&&Date.now()/1000-recall.time<10;
$('recallNotice').hidden=!showRecall;
$('recallNotice').textContent=showRecall?'Word seen again · '+recall.hits.map(h=>h.word+' → '+h.heard+' (saved meaning: '+h.saved_meaning+')').join(' · ')+' · this sentence may have a different meaning. Review LED alert':'';
for(const span of $('liveTranscript').querySelectorAll('.transcript-word'))span.classList.toggle('recall-word',Boolean(showRecall&&recall.hits.some(h=>span.textContent.replace(/[^\p{L}\p{N}]/gu,'').toLowerCase()===h.heard.toLowerCase())));
const archiveKey=JSON.stringify([s.chat_archive?.length,s.chat_id]);if(window.archiveKey!==archiveKey){window.archiveKey=archiveKey;$('chatArchive').replaceChildren();for(const chat of [...(s.chat_archive||[])].reverse()){const item=document.createElement('details');const label=document.createElement('summary');label.textContent=(chat.mode||'Automatic context')+' · '+new Date(chat.ended_at*1000).toLocaleString();item.append(label);for(const message of chat.messages||[]){const text=document.createElement('p');text.textContent=(message.translation?.source||message.transcript)+' → '+(message.translation?.translation||'');item.append(text);}$('chatArchive').append(item);}}

const frozen=s.snapshot;const basis=(s.event?.context_mode||s.requested_context_mode||s.context_mode)==='sentences'?'Up to 3 recent sentences':'Recent 30 seconds';$('snapshotRange').textContent=frozen?`${basis} · audio window ${frozen.window_seconds.toFixed(1)} seconds (${elapsed(frozen.window_start_ms)}–${elapsed(frozen.window_end_ms)})`:'Choose Understand this to keep the current moment.';
$('targetSource').textContent=s.event?.transcript && s.event?.asr_quality?.status!=='non_speech'?'The green sentence is the current analysis target.':'';
const badge=TranscriptView.contextBadge(s);const badgeKey=JSON.stringify(badge);if(badgeKey!==lastContextBadge){lastContextBadge=badgeKey;$('contextSummary').className='context-summary '+badge.kind;$('contextCategory').textContent=badge.label;$('contextOrigin').textContent=badge.origin;$('contextOrigin').hidden=!badge.origin;$('contextTopic').textContent=badge.topic;$('contextEvidence').textContent=badge.evidence?'Evidence: '+badge.evidence:'';}
const pending=s.pending_context;$('contextQuestion').hidden=!pending;
ClarificationView.render(pending,s.selected,(index,snapshot_id)=>action('context',{index,snapshot_id}),busy);
$('translationResult').hidden=Boolean(pending);
$('changeMeaning').hidden=!s.event?.clarification_options||s.stage!=='ready';
$('selected').lang=s.target_language||'ko';$('translationLanguage').textContent=({ko:'Korean',en:'English'})[s.target_language]||s.target_language||'Translation';
$('chatMode').value=s.chat_mode||'';$('chatMode').disabled=working||Boolean(pending)||s.preview_mode;
updateFlow(s);
const e=s.event;const frozenText=(e?.asr_quality?.status==='non_speech'?'No speech detected.':e?.model_context_text||e?.transcript)||'Choose Understand this to keep the current moment.';TranscriptView.render($('source'),frozenText,e?.transcript && e?.asr_quality?.status!=='non_speech'?TranscriptView.selectedRange(frozenText,s.context_decision?.source):null,'frozen');$('asr').textContent=e?.asr_seconds?e.asr_seconds.toFixed(2)+'s':'—';$('api').textContent=e?.api_seconds?e.api_seconds.toFixed(2)+'s':'—';$('json').textContent=e?JSON.stringify({transcript:e.transcript,asr_confidence:e.asr_confidence,asr_quality:e.asr_quality,asr_alternatives:e.asr_alternatives||[],result:e.translation},null,2):'No result yet.';
$('asrQuality').textContent=e?.asr_quality?.status==='non_speech'?'No speech detected.':e?.asr_quality?.status==='needs_review'?'Review the transcript. The recognizer marked it as uncertain.':'';
const word=s.words?.[s.word_index];
const wordKey=JSON.stringify([s.words,s.word_index,s.pending_context,s.generation,s.stage,s.answers,s.selected]);
if(wordKey!==lastAnswers){lastAnswers=wordKey;
  window.updateDictionarySelection?.(s.word_index,s.words);
  $('answers').replaceChildren();for(const [i,answer] of s.answers.entries()){const card=document.createElement('button');card.className='answer'+(i===s.selected?' chosen':'');card.setAttribute('aria-pressed',String(i===s.selected));card.disabled=working;const label=document.createElement('strong');label.textContent=(i+1)+' · '+(names[answer.kind]||answer.kind);const text=document.createElement('span');text.textContent=answer.text;card.append(label,text);card.onclick=()=>action('select',{index:i});$('answers').append(card);}
  const selectedAnswer=s.answers[s.selected];
  $('selected').textContent=selectedAnswer?.text||s.event?.translation?.translation||'Your translation will appear here.';
  $('selectionLabel').textContent=selectedAnswer?(s.selected+1)+' / '+s.answers.length+' · '+(names[selectedAnswer.kind]||selectedAnswer.kind):word?'Rotate the knob to choose a word, then press it to save.':'Choose Understand this when you need a little clarity.';
  $('number').textContent=selectedAnswer?String(s.selected+1):'—';
}
$('wordNotice').textContent=s.word_notice||'';
if(s.word_notice&&s.word_notice!==lastWordNotice){lastWordNotice=s.word_notice;showSnackbar(s.word_notice,!s.word_notice.endsWith('saved to your wordbook.'));}
if(s.translation_notice&&s.translation_notice!==lastTranslationNotice){lastTranslationNotice=s.translation_notice;showSnackbar(s.translation_notice,!s.translation_notice.endsWith('to your saved sentences.'));}
if(s.saved_translation_revision!==lastSavedRevision){lastSavedRevision=s.saved_translation_revision;refreshSavedTranslations().catch(()=>{});}
window.currentWordState=s;
$('hardware').textContent=s.hardware?.knob_ok?'Connected · 0x'+s.hardware.address.toString(16):'Not detected';$('logs').textContent=JSON.stringify(s.hardware,null,2)+'\n\n'+s.logs.join('\n');}catch(e){$('badge').textContent='Connection interrupted';$('badge').className='badge';$('listener').textContent='Reconnecting';for(const id of ['analyze','speak','saveTranslation','changeMeaning'])$(id).disabled=true;}finally{refreshing=false}}

$('reviewWords').onclick=async()=>{try{
 $('savedTranslations').hidden=true;$('reviewWords').setAttribute('aria-pressed','true');$('reviewTranslations').setAttribute('aria-pressed','false');
 const entries=await storageRequest('words');$('savedWords').replaceChildren();
 const note=document.createElement('p');note.textContent=entries.length?'Recently saved words · up to 50':'No saved words yet.';$('savedWords').append(note);
 for(const entry of entries){const card=document.createElement('article');card.className='answer';const title=document.createElement('strong');title.textContent=entry.expression+' → '+entry.meaning;const example=document.createElement('p');example.textContent=entry.example;card.append(title,example);$('savedWords').append(card);}
 $('savedWords').hidden=false;$('reviewStatus').textContent=entries.length?'Up to 50 recently saved words.':'No saved words yet.';
}catch(error){$('reviewStatus').textContent=error.message;}};

let storageState = null, storageBusy = false;

function storageMessage(message, failed = false) {
  $('storageStatus').textContent = message;
  $('storageStatus').className = failed ? 'error' : 'storage-status';
}

function updateStorageControls(s) {
  storageState = s;
  const ready = s?.event?.asr_quality?.status !== 'non_speech'
    && !/^\s*\[BLANK_AUDIO\]\s*$/i.test(s?.event?.transcript || '')
    && Boolean(s?.event?.translation?.translation) && !s?.preview_mode
    && !s?.pending_context
    && !['loading', 'thinking', 'transcribing', 'clarifying', 'error'].includes(s?.stage);
  $('saveTranslation').disabled = storageBusy || !ready;
  $('reviewTranslations').disabled = storageBusy;
}

async function storageRequest(path, options = {}) {
  const response = await fetch('/api/' + path, options);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Storage request failed.');
  return data;
}

function renderSavedTranslations(container, entries, emptyText) {
  container.replaceChildren();
  const note = document.createElement('p');
  note.textContent = entries.length ? emptyText.full : emptyText.empty;
  container.append(note);
  for (const entry of entries) {
    const card = document.createElement('article');
    card.className = 'answer';
    const label = document.createElement('strong');
    label.textContent = entry.source_language.toUpperCase() + ' → '
      + entry.target_language.toUpperCase() + ' · '
      + new Date(entry.created_at).toLocaleString();
    const source = document.createElement('p');
    source.className = 'source';
    source.textContent = entry.source;
    const translation = document.createElement('p');
    translation.className = 'selected';
    translation.textContent = entry.translation;
    card.append(label, source, translation);
    for (const alternative of entry.alternatives || []) {
      const line = document.createElement('p');
      line.textContent = alternative.context + ': ' + alternative.translation;
      card.append(line);
    }
    container.append(card);
  }
  container.hidden = false;
}

// Shared fetch for both the always-visible "Saved sentences" strip at the
// bottom of the conversation page and the full list on the Wordbook tab, so
// pressing the physical knob (which has no browser-side response to react to)
// and the on-screen Save button both keep every view in sync via one fetch.
async function refreshSavedTranslations() {
  const entries = await storageRequest('translations');
  if (!Array.isArray(entries)) throw Error('Invalid saved translation list.');
  renderSavedTranslations($('recentSavedTranslations'), entries.slice(0, 5),
    {full: 'Last ' + Math.min(entries.length, 5) + ' saved · press the knob or Save translation to add more.',
     empty: 'Nothing saved yet. Press the knob, or Save translation, to keep a result here.'});
  if (!$('savedTranslations').hidden) {
    renderSavedTranslations($('savedTranslations'), entries,
      {full: 'Most recent saved translations (up to 50).', empty: 'No saved translations yet.'});
  }
  $('savedCount').textContent = entries.length === 50 ? '50+' : String(entries.length);
  return entries.length;
}
async function loadSavedTranslations() { return refreshSavedTranslations(); }

$('saveTranslation').onclick = async () => {
  if (storageBusy || $('saveTranslation').disabled) return;
  storageBusy = true;
  updateStorageControls(storageState);
  storageMessage('Saving…');
  try {
    const saved = await storageRequest('save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: '{}'
    });
    let message = 'Saved translation #' + saved.id + '.';
    try { await refreshSavedTranslations(); }
    catch (error) { message += ' The saved list could not refresh.'; }
    storageMessage(message);
  } catch (error) {
    $('reviewStatus').textContent=error.message;
  } finally {
    storageBusy = false;
    updateStorageControls(storageState);
  }
};

$('reviewTranslations').onclick = async () => {
  if (storageBusy) return;
  storageBusy = true;
  updateStorageControls(storageState);
  $('reviewStatus').textContent='Loading saved translations…';
  $('savedWords').hidden=true;$('reviewWords').setAttribute('aria-pressed','false');$('reviewTranslations').setAttribute('aria-pressed','true');
  try {
    const count = await loadSavedTranslations();
    $('reviewStatus').textContent=count + ' saved translation(s).';
  } catch (error) {
    $('reviewStatus').textContent=error.message;
  } finally {
    storageBusy = false;
    updateStorageControls(storageState);
  }
};

updateStorageControls(null);

refresh();setInterval(refresh,500);

function updateFlow(state){
 $('previewControl').hidden=!state.preview_mode;$('badge').hidden=Boolean(state.preview_mode);
 $('modeLabel').textContent=state.preview_mode?'EXECUTORCH HACKATHON · EXAMPLE PREVIEW':'EXECUTORCH HACKATHON · LOCAL AI';
 $('footerStatus').textContent=state.preview_mode?'Interactive preview · sample translations only':'Local processing · AI interpretations can be imperfect';
 const exampleNames=JSON.stringify(state.preview_examples||[]);
 if(exampleNames!==previewNames){
  previewNames=exampleNames;$('previewExample').replaceChildren();
  for(const [index,label] of (state.preview_examples||[]).entries()){
   const option=document.createElement('option');option.value=String(index);option.textContent=label;$('previewExample').append(option);
  }
 }
 if(state.preview_mode)$('previewExample').value=String(state.preview_example||0);
 const thinking=['thinking','transcribing'].includes(state.stage);
 const ready=Boolean(state.event?.translation)&&!state.pending_context;
 const pending=Boolean(state.pending_context);
 $('progressStrip').hidden=!thinking;
 $('progressTitle').textContent=state.stage==='transcribing'?'Listening back to this moment':'Finding the intended meaning';
 $('progressText').textContent='On-device processing can take a moment. This request keeps the context from your button press.';
 for(const [id,on] of [['stepListen',!thinking&&!pending&&!ready],['stepMeaning',thinking||pending],['stepTranslate',ready]])$(id).classList.toggle('idk-step-active',on);
 $('changeMeaning').disabled=thinking||busy;
 document.body.dataset.stage=state.stage;
}
document.addEventListener('keydown',event=>{
 if(!storageState?.pending_context||busy||event.altKey||event.ctrlKey||event.metaKey)return;
 if(event.target.closest('input,select,textarea,[contenteditable="true"]'))return;
 if(event.key==='1'||event.key==='2'){
  event.preventDefault();action('context',{index:Number(event.key)-1,snapshot_id:storageState.pending_context.snapshot_id});
 }
});
