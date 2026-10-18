"""Bounded PCM memory and immutable, button-time context snapshots."""
from collections import deque
from queue import Queue, Full
from threading import Lock
import time

class RollingContext:
    def __init__(self, rate=16000, seconds=30):
        self.rate=rate;self.limit=int(rate*seconds)*2
        self.lock=Lock();self.parts=deque();self.size=0;self.total=0;self.sequence=0
        self.pending=Queue(maxsize=2)
    def append(self, pcm):
        with self.lock:
            self.parts.append(bytes(pcm));self.size+=len(pcm);self.total+=len(pcm)
            while self.size>self.limit:
                part=self.parts.popleft();drop=min(len(part),self.size-self.limit)
                self.size-=drop
                if drop<len(part):self.parts.appendleft(part[drop:])
    def snapshot(self):
        with self.lock:
            pcm=b''.join(self.parts);end=self.total//2
            return {'pcm':pcm,'window_start_ms':max(0,end-len(pcm)//2)*1000//self.rate,
                    'window_end_ms':end*1000//self.rate,'window_seconds':len(pcm)/(self.rate*2)}
    def freeze(self):
        with self.lock:
            if not self.size:raise ValueError('아직 마이크 입력이 없습니다.')
            self.sequence+=1
            # Capture under the same lock as append, so later audio cannot enter this request.
            pcm=b''.join(self.parts);end=self.total//2
            item={'pcm':pcm,'request_id':self.sequence,'pressed_at':time.time(),
                  'window_start_ms':max(0,end-len(pcm)//2)*1000//self.rate,
                  'window_end_ms':end*1000//self.rate,'window_seconds':len(pcm)/(self.rate*2)}
            try:self.pending.put_nowait(item)
            except Full:raise ValueError('이미 분석 대기 중입니다.')
            return {k:v for k,v in item.items() if k!='pcm'}
