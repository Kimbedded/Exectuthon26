"""Do not replay old words while a rolling ASR window decodes its known prefix."""
def merge_partial(previous, incoming):
    old=previous.split();new=incoming.split()
    if not old:return incoming
    if not new:return previous
    if len(new)<3 and len(old)>=3:return previous
    width=min(3,len(new),len(old));anchor=new[:width]
    positions=[i for i in range(len(old)-width+1) if old[i:i+width]==anchor]
    aligned=old[positions[0]:] if len(positions)==1 else old
    # A decode revisits old tokens before it reaches the new speech. Retain the
    # readable tail until the decoder catches up; final ASR may still revise it.
    if len(new)<len(aligned):return ' '.join(aligned)
    return incoming

import re
from difflib import SequenceMatcher

def sentence_units(text):
    """(text, end offset, is_complete), with unfinished tails kept separate."""
    units=[];start=0
    for match in re.finditer(r'''[.!?。！？]+["'”’)]*(?=\s|$)''',text):
        prefix=text[:match.end()].rstrip('"\'”’)')
        initial=re.search(r'\b[A-Z]\.$',prefix) and not re.search(r'\d\s+[A-Z]\.$',prefix)
        if match.group()[0]=='.' and (re.search(r'\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e)\.$',prefix,re.I) or initial):continue
        value=text[start:match.end()].strip()
        if value:units.append((value,match.end(),True))
        start=match.end()
    tail=text[start:].strip()
    if tail:units.append((tail,len(text),False))
    return units

def normalized(text):return re.sub(r'[^\w\s]','',text.casefold()).strip()

def similar(a,b):
    a=normalized(a);b=normalized(b)
    return a==b or (min(len(a.split()),len(b.split()))>=3 and SequenceMatcher(None,a,b).ratio()>=.82)

class SentenceLedger:
    """Immutable confirmed sentences plus a revisable tail; bounded by sentence count."""
    def __init__(self,limit=6):
        self.limit=limit;self.confirmed=[];self.draft='';self.previous=[]
        self.last_committed_end=-1;self.short_candidate=None;self.short_count=0
    def update(self,text,*,partial=False,silent=False,start_ms=0,end_ms=0):
        if silent or not text.strip():return self.view(silent=True)
        units=sentence_units(text);candidate=units
        if self.confirmed:
            matches=[i for i,u in enumerate(units) if similar(u[0],self.confirmed[-1])]
            if start_ms>self.last_committed_end:pass
            elif matches:candidate=units[matches[-1]+1:]
            else:
                # A partial decode has not caught up to the confirmed anchor yet.
                return self.view()
        if not partial:
            complete=[u for u in candidate if u[2]]
            # The first raw sentence may be cut by the old audio-window edge.
            # A matching completed sentence later in both decodes anchors a stable
            # boundary; close the preceding prefix at that sentence boundary.
            matcher=SequenceMatcher(None,[normalized(u[0]) for u in self.previous],
                                     [normalized(u[0]) for u in complete],autojunk=False)
            count=max((block.b+block.size for block in matcher.get_matching_blocks() if block.size),default=0)
            for unit in complete[:count]:
                self.confirmed.append(unit[0]);self.last_committed_end=end_ms
            self.confirmed=self.confirmed[-self.limit:]
            if count:
                old_units=sentence_units(self.draft)
                if len(old_units)>=count and all(similar(old_units[i][0],complete[i][0]) for i in range(count)):
                    self.draft=' '.join(u[0] for u in old_units[count:])
                candidate=candidate[count:]
            self.previous=[u for u in candidate if u[2]]
        incoming=' '.join(u[0] for u in candidate)
        if partial:
            self.draft=merge_partial(self.draft,incoming) if incoming else self.draft
        elif incoming:
            if len(incoming.split())<len(self.draft.split()) and not count and not self.draft.startswith(incoming):
                if self.short_candidate==incoming:self.short_count+=1
                else:self.short_candidate=incoming;self.short_count=1
                if self.short_count>=2:self.draft=incoming
            elif self.draft.startswith(incoming) and len(incoming)<len(self.draft) and not count:
                # Prefix-only finals are decoder regressions, not deletion commands.
                pass
            else:self.draft=incoming;self.short_candidate=None;self.short_count=0
        # Empty/regressed windows never erase an already displayed unfinished tail.
        return self.view()
    def view(self,silent=False):
        committed=' '.join(self.confirmed)
        return {'transcript':' '.join(x for x in [committed,self.draft] if x),
                'committed_text':committed,'draft_text':self.draft,'confirmed_sentences':list(self.confirmed),
                'speech_status':'non_speech' if silent else 'speech','sentence_based':True}


def sentence_request(row, mode='sentences'):
    text=row['transcript']
    if mode=='time':return {'transcript':text,'context':''}
    units=sentence_units(text)
    if not units:return {'transcript':text,'context':''}
    source=units[-1][0]
    # The completed frozen decode may contain newer context than the live ledger
    # captured at button press. Do not replace those nearby sentences with an
    # older topic. The ledger still supplies context for a one-sentence window.
    history=units[:-1] or sentence_units(row.get('frozen_sentence_context',''))
    if history and similar(history[-1][0],source):history=history[:-1]
    return {'transcript':source,'context':' '.join(x[0] for x in history[-4:])}
