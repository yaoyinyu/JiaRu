"""一次双路径容量实验；固定LR/PCGrad/loss/64轮384步保持。"""
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


t=module('dual_previous_trainer',Path(__file__).with_name('train-native-fixed-lr-microfit.py'))
contract=module('fixed_lr_contract',Path(__file__).with_name('native-fixed-lr-contract.py'))
a=t.a
j=t.j
s=module('dual_capacity_static',Path(__file__).with_name('audit-native-dual-path-head-feasibility.py'))
b=module('dual_capacity_browser',Path(__file__).with_name('verify-native-dual-path-head-browser.py'))
g=t.g
projection=t.projection
save_weights=t.save_weights
metrics=t.metrics


def training_contract(current,previous):
    expected=dict(previous)
    expected['initialization']='fresh seeded40770param dual zero-output head; old context seed1605, independent local seed1606, no prior corrective weights'
    if current!=expected or current['epochs']!=64 or current['expectedOptimizerSteps']!=384 or current['learningRate']!=.0003 or current['minimumLearningRate']!=.0003:raise ValueError('dual architecture only; training schedule unchanged')
    return {'initial':.0003,'minimum':.0003,'optimizerSteps':384}


def validate(plan):
    for value in plan['inputs'].values():a.checked(value)
    previous=a.read(a.checked(plan['inputs']['previousCapacityPlan']))
    old=t.verify(a.checked(plan['inputs']['previousCapacityReport']))
    if old['qualityDecision']!='native_capacity_fail_no_full30' or old['metrics']['jointPassCount']!=26:raise ValueError('previous failed budget preserved')
    training_contract(plan['training'],previous['training'])
    for key in ('loss','gates','candidateIds','approval','maximumExperiments','upstreamModelCalls','gradientAggregation'):
        if plan[key]!=previous[key]:raise ValueError('architecture changed '+key)
    for key in ('parentPlan','baseWeights','baseLogits','lossSource','projectionSource','journalSource','boundarySource'):
        if plan['inputs'][key]!=previous['inputs'][key]:raise ValueError('fixed native input/source '+key)
    for key,path in [('trainerSource',Path(__file__)),('originalTrainerSource',Path(t.__file__)),('staticRunner',Path(s.__file__)),('browserVerifier',Path(b.__file__)),('headSource',Path(s.h.__file__))]:
        if plan['inputs'][key]!=a.bind(path):raise ValueError('executed source not bound '+key)
    execution=a.read(a.checked(plan['inputs']['executionPlan']));parent,records=s.validate(execution)
    static=a.read(a.checked(plan['inputs']['staticReport']));browser=a.read(a.checked(plan['inputs']['browserReport']))
    if static['inputs']['plan']!=plan['inputs']['executionPlan'] or browser['inputs']['staticReport']!=plan['inputs']['staticReport'] or not static['ok'] or not browser['ok']:raise ValueError('new head prerequisites')
    if browser!=b.build(Path(browser['inputs']['staticReport']['path']),Path(browser['inputs']['liveBrowser']['path'])):raise ValueError('new browser reconstruction_mismatch')
    if static['architecture']!=s.architecture_proof(plan['training']['seed']) or static['parameterCount']!=40770:raise ValueError('new architecture identity')
    rows=static['gradient']['perCandidate']
    if [row['id'] for row in rows]!=plan['candidateIds'] or len(rows)!=45:raise ValueError('new all45 gradients')
    for i,row in enumerate(rows,1):
        if a.read(Path(plan['inputs']['staticReport']['path']).parent/f'gradient-record-{i:03d}.json')!=row or row['finiteUsedParameterTensors']!=22 or row['branchOutputWeightGradientsNonzero']!={k:row['positive'] for k in ('context','local')}:raise ValueError('new branch gradient record')
    scope=a.read(a.checked(plan['inputs']['dualScope']))
    if scope['candidateIds']!=plan['candidateIds'] or scope['qualityGatesUnchanged']!=plan['gates'] or scope['inputs']['capacityReport']!=plan['inputs']['previousCapacityReport'] or scope['reachability']!=plan['reachability']:raise ValueError('current scope/reachability')
    if plan['full30PilotAllowed'] or plan['formalTrainingApprovedImages'] or plan['maximumExperiments']!=1:raise ValueError('diagnostic only')
    return execution,parent,records


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
        projection_generator=torch.Generator().manual_seed(plan['gradientAggregation']['orderSeed'])
        projection_count=0
        for epoch in range(1,config['epochs']+1):
            state.update(phase='training',epochInFlight=epoch);journal.write(output/'progress.json',state.copy())
            order=torch.randperm(len(data),generator=generator).tolist();epoch_loss=0.;head.train()
            for window_start in range(0,len(order),config['accumulation']):
                window=order[window_start:window_start+config['accumulation']];optimizer.zero_grad(set_to_none=True)
                task_gradients=[]
                for index in window:
                    item=tensors[index];delta=head(item['packed']);logits=h.compose_native_logits(item['base'],delta,item['band'])
                    loss,_=loss_model.conditional_mask_loss(logits,item['target'],editable_band=item['band'],boundary_weight=plan['loss']['boundaryWeight'])
                    if not torch.isfinite(loss):raise ValueError('loss nonfinite')
                    individual=torch.autograd.grad(loss,tuple(head.parameters()),allow_unused=False)
                    task_gradients.append(torch.cat([value.detach().reshape(-1) for value in individual]))
                    epoch_loss+=float(loss.detach())
                aggregate,projection_metadata=projection.project_mean(torch.stack(task_gradients),generator=projection_generator)
                projection_count+=projection_metadata['projectionCount']
                offset=0
                for param in head.parameters():
                    param.grad=aggregate[offset:offset+param.numel()].reshape_as(param).clone()
                    offset+=param.numel()
                if any(p.grad is None or not torch.isfinite(p.grad).all() for p in head.parameters()):raise ValueError('gradient nonfinite/missing')
                norm=torch.nn.utils.clip_grad_norm_(head.parameters(),1.,error_if_nonfinite=True)
                state.update(optimizerStepInFlight=True,learningRate=float(optimizer.param_groups[0]['lr']),attemptedNextStep=state['optimizerSteps']+1,gradientNorm=float(norm),pcgradProjectionCount=projection_count)
                journal.write(output/'progress.json',state.copy());optimizer.step()
                if any(not torch.isfinite(p).all() for p in head.parameters()):raise ValueError('post optimizer parameters nonfinite')
                state.update(optimizerSteps=state['optimizerSteps']+1,optimizerStepInFlight=False,attemptedNextStep=None)
                journal.write(output/'progress.json',state.copy())
            scheduler.step();history.append({'epoch':epoch,'meanTrainingLoss':epoch_loss/len(data),'optimizerSteps':state['optimizerSteps']})
            state.update(completedEpochs=epoch,epochInFlight=None);journal.write(output/'history.json',history.copy());journal.write(output/'progress.json',state.copy())
            if epoch%8==0:
                j.checkpoint(output/'checkpoint.pt',head,optimizer,scheduler,generator,history,{**state,'projectionOrderRngState':projection_generator.get_state().tolist()},plan_path)
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
                'architecture':s.architecture_proof(config['seed']),
                'gradientAggregation':plan['gradientAggregation'],'projectionCount':projection_count,
                'learningRateContract':{'initial':config['learningRate'],'minimum':config['minimumLearningRate'],'optimizerSteps':384},
                'scope':'Train-only dual context+local fresh head; same constant LR0.0003/PCGrad/fixed band loss/base/64epochs384steps, final only. Empty rejection inherited from fixed base, not independent negative generalization. No formal quality/threshold selection.'}
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
    if report['architecture']!=s.architecture_proof(plan['training']['seed']):raise ValueError('architecture proof mismatch')
    with np.load(a.checked(report['finalDeltas']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=plan['candidateIds']:raise ValueError('final identities')
        deltas=[saved[f'delta_{i:03d}'].copy() for i in range(45)]
    rows,summary=metrics(data,deltas,h)
    if rows!=report['perCandidate'] or summary!=report['metrics'] or report['ok']!=s.core.passed(summary,plan['gates']):raise ValueError('reconstruction_mismatch: final native metrics')
    journal=j.verify_events(path.parent,a.read(path.parent/'progress.json'),report['history'])
    events=[a.read(p)['value'] for p in sorted((path.parent/'progress-events').glob('*.json'))]
    previous=a.read(a.checked(plan['inputs']['previousCapacityPlan']))
    expected=training_contract(plan['training'],previous['training'])
    if report['learningRateContract']!=expected:raise ValueError('LR report contract mismatch')
    rates=contract.verify_recorded_rates(events,expected)
    if report['gradientAggregation']!=plan['gradientAggregation'] or report['projectionCount']!=a.read(path.parent/'progress.json')['pcgradProjectionCount']:raise ValueError('projection recording fidelity')
    return {'ok':True,'decision':'verified_native_capacity_quality_result','qualityDecision':report['decision'],'metrics':summary,'journal':journal,'learningRateRecording':rates}


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
