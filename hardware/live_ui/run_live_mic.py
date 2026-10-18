#!/usr/bin/env python3
"""Launch the Arduino USB microphone rolling ASR and existing FastAPI translation."""
import argparse
import os
from pathlib import Path
import shlex
import math
import sys
import shutil
import subprocess
import urllib.request


def stop_remote(serial,pid_file):
    adb=os.environ.get('IDK_ADB') or shutil.which('adb') or '/opt/homebrew/bin/adb'
    code="""import os,signal,sys
from pathlib import Path
p=Path(sys.argv[1])
if p.exists():
    pid=int(p.read_text().strip())
    cmd=Path('/proc/'+str(pid)+'/cmdline')
    if cmd.exists() and b'/home/arduino/asr-executorch-test/live-mic/live_board_audio.py' in cmd.read_bytes().split(b'\\0'):
        os.kill(pid,signal.SIGINT)
"""
    subprocess.run([adb,'-s',serial,'shell',shlex.join(['python3','-c',code,pid_file])],timeout=8,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',required=True)
    parser.add_argument('--duration',type=float,default=0,help='0: continue until Ctrl-C')
    parser.add_argument('--language',default='en')
    parser.add_argument('--target-language',default='ko')
    parser.add_argument('--interval',type=float,default=1)
    parser.add_argument('--asr-only',action='store_true')
    parser.add_argument('--pid-file',default='/home/arduino/asr-executorch-test/live-mic/live-cli.pid')
    parser.add_argument('--button-ui',action='store_true')
    parser.add_argument('--resident',action='store_true')
    parser.add_argument('--pretty',action='store_true',help='Print concise live transcripts and translations')
    args=parser.parse_args()
    adb=os.environ.get('IDK_ADB') or shutil.which('adb') or '/opt/homebrew/bin/adb';base=[adb,'-s',args.serial]
    subprocess.run(base+['get-state'],check=True)
    if not args.asr_only:
        with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5) as response:
            if response.status!=200:raise RuntimeError('FastAPI is unavailable')
        subprocess.run(base+['reverse','tcp:8000','tcp:8000'],check=True)
    root='/home/arduino/asr-executorch-test'
    subprocess.run(base+['push',str(Path(__file__).with_name('live_board_audio.py')),root+'/live-mic/live_board_audio.py'],check=True)
    subprocess.run(base+['push',str(Path(__file__).with_name('asr_uncertainty.py')),root+'/live-mic/asr_uncertainty.py'],check=True)
    subprocess.run(base+['push',str(Path(__file__).with_name('rolling_context.py')),root+'/live-mic/rolling_context.py'],check=True)
    command=['env','LD_LIBRARY_PATH='+root+'/qnn:/home/arduino/.local/share/geniex/qairt/htp-files:/home/arduino/.local/share/geniex',
        'ADSP_LIBRARY_PATH=/home/arduino/.local/share/geniex/qairt/htp-files','OMP_NUM_THREADS=4',root+'/venv/bin/python',
        root+'/live-mic/live_board_audio.py','--duration',str(args.duration),'--interval',str(args.interval),
        '--language',args.language,'--target-language',args.target_language]
    if args.button_ui:command+=['--manual','--api','http://127.0.0.1:8000/interpret/button']
    if args.asr_only:command.append('--asr-only')
    if args.resident:command.append('--resident')
    wrapper='echo $$ > '+shlex.quote(args.pid_file)+'; exec '+shlex.join(command)
    proc=None
    try:
        proc=subprocess.Popen(base+['shell']+([] if args.resident else ['-t'])+[shlex.join(['sh','-c',wrapper])],stdout=subprocess.PIPE if args.pretty else None,stderr=subprocess.STDOUT if args.pretty else None,text=True)
        if args.pretty:
            import json
            for line in proc.stdout:
                clean=line.strip()
                if clean.startswith('EVENT '):
                    row=json.loads(clean[6:]);print('\n['+str(row['elapsed_ms']/1000)+'s] '+row.get('transcript',row['status']),flush=True)
                    if row.get('translation'):print('→ '+row['translation']['translation'],flush=True)
                    if row.get('api_error'):print('API: '+row['api_error'],flush=True)
                    if row.get('asr_seconds') is not None:print('전사 %.2f초 · 번역 %s'%(row['asr_seconds'],('%.2f초'%row['api_seconds']) if row.get('api_seconds') is not None else '—'),flush=True)
                elif clean.startswith('LEVEL ') and sys.stdout.isatty():
                    level=json.loads(clean[6:]);db=20*math.log10(max(level['rms'],1e-6));print('마이크 %5.1f dBFS · %5.1f초   '%(db,level['elapsed_ms']/1000),end='\r',flush=True)
                elif clean.startswith(('READY','STOPPED')):print(clean,flush=True)
        if proc.wait():raise RuntimeError('Board audio process exited with an error')
    except KeyboardInterrupt:
        stop_remote(args.serial,args.pid_file)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.terminate();proc.wait()

if __name__=='__main__':main()
