import os
"""Mac -> ADB -> Arduino Router -> MCU, with cumulative physical event counters."""
import json,shlex,subprocess,threading,time

class HardwareBridge:
    def __init__(self,serial,on_sample,on_error):
        self.serial=serial;self.on_sample=on_sample;self.on_error=on_error
        self.closed=threading.Event();self.lock=threading.Lock();self.desired=(0,0,0);self.sent=None;self.red_led=False;self.red_led_sent=None;self.green_led=False;self.green_led_sent=None;self.recall_until=0
    def rpc(self,method,*args):
        result=subprocess.run([os.environ.get('IDK_ADB','/opt/homebrew/bin/adb'),'-s',self.serial,'shell',shlex.join(['arduino-router-cli','--',method,*map(str,args)])],capture_output=True,text=True,timeout=3)
        if 'Got RPC response: ' in result.stdout:
            value=json.loads(result.stdout.split('Got RPC response: ',1)[1])
            return json.loads(value) if isinstance(value,str) else value
        # Defensive: on a stale firmware build, arduino-router-cli's own result
        # printer has been observed to panic (stderr) on an int8 ack even though
        # the request already reached the MCU. Not expected on current firmware,
        # but treat it as a sent-but-unprintable command rather than a failure.
        if 'panic: unsupported type: int8' in result.stderr:return None
        raise RuntimeError(result.stdout.strip() or result.stderr.strip())
    def display(self,state,selected,count):
        with self.lock:self.desired=(state,selected,count)
    def set_red_led(self,enabled):
        with self.lock:self.red_led=bool(enabled)
    def set_green_led(self,enabled):
        with self.lock:self.green_led=bool(enabled)
    def flash_recall(self,seconds=3):
        with self.lock:self.recall_until=time.monotonic()+seconds
    def clear_recall(self):
        with self.lock:self.recall_until=0
    def run(self):
        while not self.closed.is_set():
            try:
                with self.lock:
                    now=time.monotonic()
                    desired=((3,0,0) if int(now*6)%2==0 else (0,0,0)) if now<self.recall_until else self.desired
                    red_led=self.red_led
                    green_led=self.green_led
                if red_led!=self.red_led_sent:
                    self.rpc('idk.led',int(red_led));self.red_led_sent=red_led
                if green_led!=self.green_led_sent:
                    self.rpc('idk.green',int(green_led));self.green_led_sent=green_led
                if desired!=self.sent:self.rpc('idk.set',*desired);self.sent=desired
                value=self.rpc('idk.read')
                if value.get('firmware')!='idk-button-1':raise RuntimeError('IDK MCU firmware not detected')
                self.on_sample(value)
                if value.get('state')!=desired[0] or value.get('answer_count')!=desired[2]:self.sent=None
            except Exception as error:self.sent=None;self.on_error(str(error))
            self.closed.wait(.1)
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def close(self):
        self.closed.set();self.thread.join(timeout=4)
        try:self.rpc('idk.led',0)
        except Exception:pass
        try:self.rpc('idk.green',0)
        except Exception:pass
        try:self.rpc('idk.set',0,0,0)
        except Exception:pass
