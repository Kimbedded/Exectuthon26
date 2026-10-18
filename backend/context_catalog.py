"""Reviewed word senses for reliable clarification; no translated sentence substitutions."""
import re
# These are word meanings and evidence patterns, never canned translations.
SENSES={
 'ground': [('Electrical grounding','The topic is electrical circuits and electrical grounding.',r'\b(circuits?|electrical|voltage|pcb|wiring|ground\s+(?:rail|wire|terminal|connection))\b|전기|회로|접지'),
            ('The floor or earth beneath you','The topic is the physical floor or earth surface.',r'\b(outside|outdoors|floor|dropped|soil|garden|beneath\s+(?:your|my|our|the)\s+feet)\b|바닥|땅|야외')],
 'port': [('A computer or network connection','The topic is computer network or hardware connection ports.',r'\b(router|network|usb|ethernet|tcp|socket)\b|네트워크|라우터'),
          ('A harbor for boats and ships','The topic is a maritime harbor for ships.',r'\b(ship|boat|harbor|cargo|sailing)\b|선박|항구')],
 'bank': [('A financial bank','The topic is a financial bank.',r'\b(money|loan|deposit|account|finance)\b|은행|대출'),
          ('The edge of a river','The topic is the bank alongside a river.',r'\b(river|stream|fishing|shore)\b|강둑|강가')],
}

def catalog_decision(source,context):
    for word,senses in SENSES.items():
        if not re.search(r'\b'+word+r'\b',source,re.I):continue
        # Do not use the ambiguous word itself as evidence for its own meaning.
        # A specific constraint in the current sentence outranks stale history.
        matches=[re.search(pattern,source,re.I) for _,_,pattern in senses]
        if not any(matches):matches=[re.search(pattern,context,re.I) for _,_,pattern in senses]
        common={'phrase':word,'meaning_options':[x[0] for x in senses],
                'option_contexts':[x[1] for x in senses]}
        if sum(m is not None for m in matches)==1:
            i=next(i for i,m in enumerate(matches) if m)
            return {**common,'needs_clarification':False,'topic':senses[i][1],'evidence':matches[i].group(),
                    'question':None,'options':[],'selected_option':i,'decision_method':'reviewed_word_senses'}
        return {**common,'needs_clarification':True,'topic':None,'evidence':None,
                'question':f'What do you mean by “{word}” here?',
                'options':[x[0] for x in senses],'option_contexts':[x[1] for x in senses],
                'decision_method':'reviewed_word_senses'}
    return None

def broad_clarification():
    return {'needs_clarification':True,'topic':None,'evidence':None,
            'question':'Please say one more sentence explaining what you mean.',
            'options':['Professional or technical conversation','Everyday conversation'],
            'option_contexts':['The speaker is using words in a professional or technical context.',
                               'The speaker is using everyday, nontechnical meanings.'],
            'decision_method':'broad_context_fallback'}
