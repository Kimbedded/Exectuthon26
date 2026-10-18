"""Reviewed word senses for reliable clarification; no translated sentence substitutions."""
import re
# These are word meanings and evidence patterns, never canned translations.
SENSES={
 'ground': [('전기·회로의 접지','The topic is electrical circuits and electrical grounding.',r'\b(circuit|electrical|voltage|pcb|wiring)\b|전기|회로|접지'),
            ('바닥이나 땅','The topic is the physical floor or earth surface.',r'\b(outside|outdoors|floor|dropped|soil|garden)\b|바닥|땅|야외')],
 'port': [('컴퓨터·네트워크 연결 포트','The topic is computer network or hardware connection ports.',r'\b(router|network|usb|ethernet|tcp|socket)\b|네트워크|라우터'),
          ('배가 드나드는 항구','The topic is a maritime harbor for ships.',r'\b(ship|boat|harbor|cargo|sailing)\b|선박|항구')],
 'bank': [('금융기관인 은행','The topic is a financial bank.',r'\b(money|loan|deposit|account|finance)\b|은행|대출'),
          ('강가나 강둑','The topic is the bank alongside a river.',r'\b(river|stream|fishing|shore)\b|강둑|강가')],
}

def catalog_decision(source,context):
    for word,senses in SENSES.items():
        if not re.search(r'\b'+word+r'\b',source,re.I):continue
        # Do not use the ambiguous word itself as evidence for its own meaning.
        evidence_text=context+'\n'+source
        matches=[re.search(pattern,evidence_text,re.I) for _,_,pattern in senses]
        if sum(m is not None for m in matches)==1:
            i=next(i for i,m in enumerate(matches) if m)
            return {'needs_clarification':False,'topic':senses[i][1],'evidence':matches[i].group(),
                    'question':None,'options':[],'decision_method':'reviewed_word_senses'}
        return {'needs_clarification':True,'topic':None,'evidence':None,
                'question':f'여기서 “{word}”는 어떤 뜻인가요?',
                'options':[x[0] for x in senses],'option_contexts':[x[1] for x in senses],
                'decision_method':'reviewed_word_senses'}
    return None

def broad_clarification():
    return {'needs_clarification':True,'topic':None,'evidence':None,
            'question':'주제를 확정하지 못했습니다. 어느 쪽에 더 가까운가요?',
            'options':['업무·기술 분야의 전문적인 대화','일상생활의 일반적인 대화'],
            'option_contexts':['The speaker is using words in a professional or technical context.',
                               'The speaker is using everyday, nontechnical meanings.'],
            'decision_method':'broad_context_fallback'}
