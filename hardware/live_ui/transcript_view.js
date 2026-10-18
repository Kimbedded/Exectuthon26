(function(root){
  'use strict';
  function lastSentence(text){
    const value=text.trimEnd();const ends=[];
    const regex=/[.!?。！？]+["'”’)]*(?=\s|$)/g;let match;
    while((match=regex.exec(value))){
      const prefix=value.slice(0,regex.lastIndex).replace(/["'”’)]*$/,'');
      if(match[0][0]==='.' && (/\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e)\.$/i.test(prefix)||/\b[A-Z]\.$/.test(prefix)))continue;
      ends.push(regex.lastIndex);
    }
    let start=ends.length?(ends[ends.length-1]===value.length?(ends[ends.length-2]||0):ends[ends.length-1]):0;
    while(start<value.length && /\s/.test(value[start]))start++;
    return {start,end:value.length};
  }
  function selectedRange(text,source){
    if(source){const start=text.lastIndexOf(source);if(start>=0)return {start,end:start+source.length};}
    return lastSentence(text);
  }
  function tokens(text){let offset=0;return (text.match(/\s+|\S+/g)||[]).map(value=>{const token={value,start:offset,end:offset+value.length,word:/\S/.test(value)};offset=token.end;return token;});}
  const cache=new WeakMap();
  function render(container,text,range,kind){
    const key=JSON.stringify([text,range,kind]);const previous=cache.get(container);
    if(previous?.key===key)return;
    const shouldFollow=container.scrollHeight-container.scrollTop-container.clientHeight<55;
    const fragment=document.createDocumentFragment();let selected=null;
    for(const token of tokens(text)){
      const isSelected=range && token.end>range.start && token.start<range.end;
      let parent=fragment;
      if(isSelected){if(!selected){selected=document.createElement('span');selected.className='sentence-highlight '+(kind==='frozen'?'frozen-sentence':'live-sentence');fragment.append(selected);}parent=selected;}
      if(!token.word){parent.append(document.createTextNode(token.value));continue;}
      const word=document.createElement('span');word.className='transcript-word';word.textContent=token.value;
      word.dataset.start=String(token.start);word.dataset.end=String(token.end);
      if(isSelected)word.dataset.selected='true';
      parent.append(word);
    }
    container.replaceChildren(fragment);cache.set(container,{key,text});
    if(shouldFollow)container.scrollTop=container.scrollHeight;
  }
  function contextBadge(state){
    const decision=state.context_decision||{};
    if(state.pending_context)return {kind:'unknown',label:'Context check required',origin:'Waiting for user choice',topic:decision.question||'Choose the situation where this was said.',evidence:''};
    const selected=state.event?.selected_context||(decision.decision_method==='user_chat_category'?state.chat_mode:null);
    const topic=selected||decision.topic||'';
    if(!topic)return {kind:'unknown',label:['thinking','transcribing'].includes(state.stage)?'Analyzing context':'No context selected',origin:'',topic:'Analyze a context window to show the current context.',evidence:''};
    const technical=/\b(electrical|circuits?|grounding|software|mechanical|engineering|network|hardware|computer|professional|technical|financial)\b|전기|회로|접지|기계|조립|소프트웨어|하드웨어|네트워크|기술|전문|업무|금융|은행/i.test(topic);
    const casual=/\b(casual|everyday|nontechnical|physical floor|earth surface|river bank)\b|캐주얼|일상|일반적인|바닥|땅|강가|강둑/i.test(topic);
    const kind=technical===casual?'unknown':technical?'technical':'casual';
    const displayTopic=selected?selected:/electrical.*(?:ground|circuit)/i.test(topic)?'Electrical circuit · grounding':/physical floor|earth surface/i.test(topic)?'Floor · ground':/computer.*(?:network|port)/i.test(topic)?'Network · connection port':/financial bank/i.test(topic)?'Finance · bank':/bank alongside a river/i.test(topic)?'Riverside · river bank':topic;
    return {kind,label:kind==='technical'?'Technical · work context':kind==='casual'?'Everyday · casual context':'Technical / casual unclear',
      origin:selected?'User selection':kind==='unknown'?'Topic only':'Automatic classification · reference',
      topic:displayTopic,evidence:selected?'The selected context is applied.':decision.evidence||''};
  }
  const api={lastSentence,selectedRange,tokens,render,contextBadge};root.TranscriptView=api;
  if(typeof module!=='undefined' && module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
