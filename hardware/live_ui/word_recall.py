"""Repeated exposure cues, based on word forms rather than semantic equivalence."""
import re,time
from collections import Counter
TOKEN=re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*",re.UNICODE)
def forms(word):
    word=word.casefold().replace('’',"'");out={word}
    if word.endswith("'s"):out.add(word[:-2])
    if word.isascii() and len(word)>3:
        if word.endswith('ies'):out.add(word[:-3]+'y')
        elif word.endswith('s') and not word.endswith(('ss','us','is')):out.add(word[:-1])
        if word.endswith(('ches','shes','xes','zes','ses')):out.add(word[:-2])
    return out
def spoken_text(text):
    # Whisper sound captions are not spoken vocabulary occurrences.
    return re.sub(r'[\[(][^\])]*(?:audience|applause|music|laugh|chatter|inaudible|silence|blank_audio|speaking in|박수|웃음|음악)[^\])]*[\])]', '',text,flags=re.I)
class RecallTracker:
    def __init__(self):self.previous=Counter();self.tokens=[];self.last={}
    def update(self,text,entries,*,silent=False,now=None):
        if silent or not text.strip():return []
        now=time.monotonic() if now is None else now
        text=spoken_text(text)
        if not text.strip():return []
        tokens=[m.group() for m in TOKEN.finditer(text)]
        if len(tokens)<len(self.tokens) and [x.casefold() for x in self.tokens[:len(tokens)]]==[x.casefold() for x in tokens]:return []
        counts=Counter();actual={}
        for entry in entries:
            key=entry['expression'].casefold()
            # Multiword expressions are not yet eligible for single-word cues.
            if len(TOKEN.findall(key))!=1:continue
            matches=[t for t in tokens if forms(t)&forms(key)]
            counts[key]=len(matches)
            if matches:actual[key]=matches[-1]
        hits=[]
        for entry in entries:
            key=entry['expression'].casefold()
            if counts[key]>self.previous[key] and now-self.last.get(key,-1e9)>=8:
                hits.append({'word':entry['expression'],'heard':actual[key],'saved_meaning':entry['meaning']})
                self.last[key]=now
        self.previous=counts;self.tokens=tokens
        return hits
