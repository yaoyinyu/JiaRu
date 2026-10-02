"""编辑带BCE单变量一次容量训练；固定原循环、预算、日志与最终判定。"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import time
from pathlib import Path
import numpy as np
import torch


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


t=module('band_objective_original_trainer',Path(__file__).with_name('train-native-boundary-head-microfit.py'))
g=module('band_objective_gradient_gate',Path(__file__).with_name('audit-native-band-objective-gradients.py'))
a=t.a
j=t.j
s=t.s
s.native_data=g.c.native_data
save_weights=t.save_weights
metrics=t.metrics


def validate(plan):
    for value in plan['inputs'].values():
        a.checked(value)
    previous=a.read(a.checked(plan['inputs']['previousCapacityPlan']))
    for key in ('training','gates','candidateIds','approval','maximumExperiments','upstreamModelCalls'):
        if plan[key]!=previous[key]:
            raise ValueError('BCE domain single variable changed '+key)
    expected_loss={'kind':'native fixed-band mean BCE(empty-band full-ROI fallback) +positive Dice +0.2softBoundaryIoU','boundaryWeight':.2}
    if plan['loss']!=expected_loss or plan['full30PilotAllowed'] or plan['formalTrainingApprovedImages']!=0:
        raise ValueError('fixed loss/diagnostic scope')
    gradient_plan=a.read(a.checked(plan['inputs']['gradientPlan']))
    parent,records,static=g.validate(gradient_plan)
    gradient_path=a.checked(plan['inputs']['gradientReport'])
    g.verify(gradient_path)
    gradient=a.read(gradient_path)
    if gradient['inputs']['plan']!=plan['inputs']['gradientPlan'] or gradient['architecture']!=static['architecture']:
        raise ValueError('gradient report identity')
    if plan['inputs']['parentPlan']!=gradient_plan['inputs']['parentPlan'] or plan['candidateIds']!=parent['candidateIds'] or plan['gates']!=parent['qualityGatesUnchanged']:
        raise ValueError('frozen data/gates/denominator')
    for key in ('staticReport','browserReport','interfaceExecutionPlan','bandScope'):
        if plan['inputs'][key]!=gradient_plan['inputs'][key]:
            raise ValueError('reused evidence identity: '+key)
    for key,path in [('trainerSource',Path(__file__)),('originalTrainerSource',Path(t.__file__)),('lossSource',Path(g.loss_model.__file__)),('gradientRunner',Path(g.__file__)),('contextSource',Path(g.c.h.__file__))]:
        if plan['inputs'][key]!=a.bind(path):
            raise ValueError('executed source not bound: '+key)
    old=a.read(a.checked(plan['inputs']['previousCapacityReport']))
    if old['decision']!='native_capacity_fail_no_full30' or old['completedEpochs']!=64 or old['optimizerSteps']!=384:
        raise ValueError('previous consumed capacity not closed FAIL')
    return gradient_plan,parent,records


def train(plan_path,output):
    plan=a.read(plan_path);_,parent,records=validate(plan)
    if output.exists():raise FileExistsError('single experiment already claimed')
    output.mkdir(parents=True);j.write_durable_new(output/'claim.json',{'plan':a.bind(plan_path),'attemptConsumed':True,'restartAllowed':False})
    state={'phase':'claimed','completedEpochs':0,'optimizerSteps':0,'optimizerStepInFlight':False,'attemptedNextStep':None,'qualityDecision':'not_evaluated'}
    journal=j.ExecutionJournal();journal.write(output/'progress.json',state.copy())
    start=time.perf_counter();history=[]
    try:
        h,data=s.native_data(parent,records)
        # 只用副本转换CUDA，避免PIL只读数组警告；不写数据目录。
        tensors=[{'packed':torch.from_numpy(item['packed'][None].copy()).cuda(),
                  'base':torch.from_numpy(item['base'][None,None].copy()).cuda(),
                  'band':torch.from_numpy(item['band'][None,None].copy()).cuda(),
                  'target':torch.from_numpy(item['target'][None,None].copy()).cuda()} for item in data]
        config=plan['training'];torch.set_num_threads(2);torch.manual_seed(config['seed']);torch.cuda.manual_seed_all(config['seed'])
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        torch.backends.cudnn.deterministic=True;torch.backends.cudnn.benchmark=False
        head=h.NativeBoundaryNailRefiner().cuda();head.requires_grad_(True)
        loss_model=module('native_microfit_loss',a.checked(plan['inputs']['lossSource']))
        optimizer=torch.optim.AdamW(head.parameters(),lr=config['learningRate'],weight_decay=config['weightDecay'])
        scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=config['epochs'],eta_min=config['minimumLearningRate'])
        generator=torch.Generator().manual_seed(config['seed']);torch.cuda.reset_peak_memory_stats()
        for epoch in range(1,config['epochs']+1):
            state.update(phase='training',epochInFlight=epoch);journal.write(output/'progress.json',state.copy())
            order=torch.randperm(len(data),generator=generator).tolist();epoch_loss=0.;head.train()
            for window_start in range(0,len(order),config['accumulation']):
                window=order[window_start:window_start+config['accumulation']];optimizer.zero_grad(set_to_none=True)
                for index in window:
                    item=tensors[index];delta=head(item['packed']);logits=h.compose_native_logits(item['base'],delta,item['band'])
                    loss,_=loss_model.conditional_mask_loss(logits,item['target'],editable_band=item['band'],boundary_weight=plan['loss']['boundaryWeight'])
                    if not torch.isfinite(loss):raise ValueError('loss nonfinite')
                    (loss/len(window)).backward();epoch_loss+=float(loss.detach())
                if any(p.grad is None or not torch.isfinite(p.grad).all() for p in head.parameters()):raise ValueError('gradient nonfinite/missing')
                norm=torch.nn.utils.clip_grad_norm_(head.parameters(),1.,error_if_nonfinite=True)
                state.update(optimizerStepInFlight=True,attemptedNextStep=state['optimizerSteps']+1,gradientNorm=float(norm))
                journal.write(output/'progress.json',state.copy());optimizer.step()
                if any(not torch.isfinite(p).all() for p in head.parameters()):raise ValueError('post optimizer parameters nonfinite')
                state.update(optimizerSteps=state['optimizerSteps']+1,optimizerStepInFlight=False,attemptedNextStep=None)
                journal.write(output/'progress.json',state.copy())
            scheduler.step();history.append({'epoch':epoch,'meanTrainingLoss':epoch_loss/len(data),'optimizerSteps':state['optimizerSteps']})
            state.update(completedEpochs=epoch,epochInFlight=None);journal.write(output/'history.json',history.copy());journal.write(output/'progress.json',state.copy())
            if epoch%8==0:
                j.checkpoint(output/'checkpoint.pt',head,optimizer,scheduler,generator,history,state,plan_path)
                print(json.dumps({'phase':'training','completedEpochs':epoch,'optimizerSteps':state['optimizerSteps'],'meanLoss':history[-1]['meanTrainingLoss']},ensure_ascii=False),flush=True)
        if state['optimizerSteps']!=config['expectedOptimizerSteps']:raise ValueError('step budget')
        state.update(phase='final-evaluation');journal.write(output/'progress.json',state.copy());head.eval();deltas=[]
        with torch.inference_mode():
            for item in tensors:
                values=head(item['packed']).cpu().numpy()[0,0].copy()
                if not np.isfinite(values).all():raise ValueError('final native delta nonfinite')
                deltas.append(values)
        save_weights(output/'final-head-weights.pt',head)
        with (output/'final-deltas.npz').open('xb') as stream:
            np.savez_compressed(stream,candidateIds=np.array(plan['candidateIds']),**{f'delta_{i:03d}':v for i,v in enumerate(deltas)})
            stream.flush();os.fsync(stream.fileno())
        rows,summary=metrics(data,deltas,h);passed=s.core.passed(summary,plan['gates'])
        decision='native_capacity_pass_pending_full_split' if passed else 'native_capacity_fail_no_full30'
        report={'schemaVersion':1,'ok':passed,'decision':decision,'inputs':{'plan':a.bind(plan_path),**plan['inputs']},
                'finalWeights':a.bind(output/'final-head-weights.pt'),'finalDeltas':a.bind(output/'final-deltas.npz'),
                'metrics':summary,'perCandidate':rows,'history':history,'gates':plan['gates'],
                'completedEpochs':64,'optimizerSteps':384,'actualFinalHeadForwardCandidates':45,'upstreamModelCalls':0,
                'cudaPeakAllocatedBytes':torch.cuda.max_memory_allocated(),'elapsedSeconds':time.perf_counter()-start,
                'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
                'architecture':g.c.architecture_proof(config['seed']),
                'scope':'Train-only capacity, only BCE domain changed to fixed4px band mean; same base/45 identities and native[1,3,9] head, final only. Empty rejection inherited from fixed base, not independent negative generalization. No formal quality/threshold selection.'}
        j.write_durable_new(output/'microfit-report.json',report)
        state.update(phase='closed',qualityDecision=decision);journal.write(output/'progress.json',state.copy())
        j.verify_events(output,state,history);return report
    except BaseException as error:
        j.write_durable_new(output/'execution-failure-report.json',{'schemaVersion':1,'ok':False,'decision':'native_capacity_execution_failed_budget_consumed',
                            'inputs':{'plan':a.bind(plan_path),'trainer':a.bind(Path(__file__))},'stateBeforeException':state.copy(),
                            'exception':repr(error),'attemptConsumed':True,'restartAllowed':False,'qualityEvaluated':state['phase'] in ['final-evaluation','closed']})
        raise


def verify(path):
    report=a.read(path);plan_path=a.checked(report['inputs']['plan']);plan=a.read(plan_path);_,parent,records=validate(plan)
    for binding in report['inputs'].values():a.checked(binding)
    a.checked(report['finalWeights']);h,data=s.native_data(parent,records)
    if report['architecture']!=g.c.architecture_proof(plan['training']['seed']):raise ValueError('architecture proof mismatch')
    with np.load(a.checked(report['finalDeltas']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=plan['candidateIds']:raise ValueError('final identities')
        deltas=[saved[f'delta_{i:03d}'].copy() for i in range(45)]
    rows,summary=metrics(data,deltas,h)
    if rows!=report['perCandidate'] or summary!=report['metrics'] or report['ok']!=s.core.passed(summary,plan['gates']):raise ValueError('reconstruction_mismatch: final native metrics')
    journal=j.verify_events(path.parent,a.read(path.parent/'progress.json'),report['history'])
    return {'ok':True,'decision':'verified_native_capacity_quality_result','qualityDecision':report['decision'],'metrics':summary,'journal':journal}


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    plan=a.read(args.plan if args.plan else a.read(args.verify_report)['inputs']['plan']['path']);parent=a.read(plan['inputs']['parentPlan']['path'])
    guard=module('native_microfit_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    try:
        result=verify(args.verify_report) if args.verify_report else train(args.plan.resolve(),args.output.resolve())
        print(json.dumps(result if args.verify_report else {k:result[k] for k in ['ok','decision','metrics']},ensure_ascii=False),flush=True)
    finally:
        for directory in parent['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':main()
