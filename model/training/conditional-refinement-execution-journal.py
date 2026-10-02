"""不可覆盖的执行事件日志，避免Windows读者阻止os.replace进度文件。"""
from __future__ import annotations
import json
import os
from pathlib import Path
import torch


def write_durable_new(path,value):
    """唯一文件只创建一次；flush/fsync完成后才继续优化。"""
    with Path(path).open('xb') as stream:
        stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
        stream.flush();os.fsync(stream.fileno())


class ExecutionJournal:
    def __init__(self):self.sequences={}

    def write(self,path,value):
        path=Path(path);folder=path.parent/f'{path.stem}-events';folder.mkdir(parents=True,exist_ok=True)
        seq=self.sequences.get(path,0)+1
        write_durable_new(folder/f'{seq:06d}.json',{'sequence':seq,'value':value})
        self.sequences[path]=seq
        # 训练中不创建共享快照；只有终态一次创建，旧事件永不替换。
        if path.name=='progress.json' and value['phase']=='closed':
            write_durable_new(path,value)


def checkpoint(path,model,optimizer,scheduler,generator,history,state,plan_path):
    """每8轮保留唯一取证快照；不覆盖、不提供恢复权限。"""
    import hashlib
    target=path.parent/f"forensic-epoch-{state['completedEpochs']:03d}.pt"
    with target.open('xb') as stream:
        torch.save({'model':{n:v.detach().cpu() for n,v in model.state_dict().items()},'optimizer':optimizer.state_dict(),
            'scheduler':scheduler.state_dict(),'samplerRng':generator.get_state(),'torchRng':torch.get_rng_state(),
            'cudaRng':torch.cuda.get_rng_state_all(),'history':history,'state':state,'planSha256':hashlib.sha256(Path(plan_path).read_bytes()).hexdigest(),
            'use':'forensic only; no authorization to resume a consumed experiment'},stream)
        stream.flush();os.fsync(stream.fileno())


def verify_events(folder,final_state,history):
    events=sorted((folder/'progress-events').glob('*.json'))
    values=[]
    for seq,path in enumerate(events,1):
        row=json.loads(path.read_text(encoding='utf-8'))
        if path.name!=f'{seq:06d}.json' or row['sequence']!=seq:raise ValueError('event sequence gap')
        values.append(row['value'])
    if not values or values[-1]!=final_state:raise ValueError('journal terminal state')
    confirmations=[r['optimizerSteps'] for r in values if not r['optimizerStepInFlight']]
    actual=[]
    for step in confirmations:
        if not actual or step!=actual[-1]:actual.append(step)
    if actual!=list(range(385)):raise ValueError('all384 confirmed steps')
    in_flight=[r['attemptedNextStep'] for r in values if r['optimizerStepInFlight']]
    if in_flight!=list(range(1,385)):raise ValueError('all384 in-flight events')
    if sum(r['phase']=='final-evaluation' for r in values)!=1:raise ValueError('one final evaluation')
    saved=[]
    for seq,path in enumerate(sorted((folder/'history-events').glob('*.json')),1):
        row=json.loads(path.read_text(encoding='utf-8'))
        if path.name!=f'{seq:06d}.json' or row['sequence']!=seq or row['value']!=history[:seq]:raise ValueError('history journal')
        saved.append(row)
    if len(saved)!=64:raise ValueError('64 epoch history events')
    return {'progressEvents':len(events),'historyEvents':len(saved),'confirmedOptimizerSteps':384,'finalEvaluations':1}
