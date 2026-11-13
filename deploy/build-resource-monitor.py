#!/usr/bin/env python3
"""Build-only resource watchdog. No Docker/network/subprocess/service operations.
Reviewed separately; no build authorization. Parent keeps independent7second stale
heartbeat/death gate. Service monitor remains separate with25second stale gate.
"""
import argparse,json,os,signal,sys,time
from pathlib import Path


def sample():
    with open('/proc/meminfo') as source:
        mem={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in source)}
    disk=os.statvfs('/')
    return {'free':disk.f_bavail*disk.f_frsize//1048576,'available':mem['MemAvailable']//1024,'swap':(mem['SwapTotal']-mem['SwapFree'])//1024}


def reason(row,start_free,start_swap,elapsed):
    if row['free']<35840:return 'disk-floor'
    if start_free-row['free']>16384:return 'disk-growth'
    if row['available']<4096:return 'ram-floor'
    if row['swap']-start_swap>256:return 'swap-growth'
    if elapsed>=2100:return 'overall-timeout'
    return None


def atomic(path,value):
    temporary=path.with_name(path.name+'.new')
    with temporary.open('w') as output:json.dump(value,output);output.write('\n')
    os.replace(temporary,path)


def monitor(root,parent,start_free,start_swap,start_monotonic,*,read=sample,clock=time.monotonic,sleep=time.sleep,alive=None,signal_parent=None,interval=5):
    root=Path(root);heartbeat=root/'resource.heartbeat';state=root/'resource-monitor.json'
    if alive is None:
        def alive():
            try:os.kill(parent,0);return True
            except ProcessLookupError:return False
    if signal_parent is None:signal_parent=lambda:os.kill(parent,signal.SIGTERM)
    next_check=clock();count=0
    try:
        while alive():
            began=clock()
            atomic(state,{'phase':'sampling','count':count,'monotonic':began})
            row=read();now=clock();elapsed=now-start_monotonic
            stop=reason(row,start_free,start_swap,elapsed)
            report={**row,'phase':'stop' if stop else 'checked','count':count,'monotonic':now,'elapsed':elapsed,'sample_seconds':now-began,'reason':stop}
            atomic(state,report)
            with (root/'resources-python.jsonl').open('a') as log:log.write(json.dumps(report)+'\n')
            if stop:
                with (root/'STOPPED').open('a') as log:log.write('resource-monitor:'+stop+'\n')
                signal_parent();return 1
            # Only completed successful resource/deadline sample renews heartbeat.
            heartbeat.touch();count+=1
            next_check+=interval
            sleep(max(0,next_check-clock()))
        return 0
    except BaseException as error:
        if not (root/'MONITORS_STOPPING').exists():
            with (root/'STOPPED').open('a') as log:log.write('resource-monitor-exception:'+type(error).__name__+'\n')
            try:signal_parent()
            except ProcessLookupError:pass
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root');parser.add_argument('parent',type=int);parser.add_argument('start_free',type=int);parser.add_argument('start_swap',type=int);parser.add_argument('start_monotonic',type=float);args=parser.parse_args()
    sys.exit(monitor(args.root,args.parent,args.start_free,args.start_swap,args.start_monotonic))
