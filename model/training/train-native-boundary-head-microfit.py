"""冻结基底的原像素窄带一次容量训练；完整终轮唯一终评，无续训。"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
import os
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


s=module('native_microfit_static',Path(__file__).with_name('audit-native-boundary-head-feasibility.py'));a=s.a
j=module('native_microfit_journal',Path(__file__).with_name('conditional-refinement-execution-journal.py'))
b=module('native_microfit_browser',Path(__file__).with_name('verify-native-boundary-head-browser.py'))


def validate(plan):
    for binding in plan['inputs'].values():a.checked(binding)
    feasibility=a.read(plan['inputs']['executionPlan']['path']);parent,records=s.validate(feasibility)
    static=a.read(plan['inputs']['staticReport']['path']);browser=a.read(plan['inputs']['browserReport']['path'])
    rebuilt=b.build(Path(browser['inputs']['staticReport']['path']),Path(browser['inputs']['liveBrowser']['path']))
    if rebuilt!=browser or not static['ok'] or not browser['ok']:raise ValueError('browser/static prerequisites')
    if static['inputs']['plan']!=plan['inputs']['executionPlan'] or plan['gates']!=parent['qualityGatesUnchanged']:raise ValueError('frozen gates/identity')
    if plan['candidateIds']!=parent['candidateIds'] or plan['approval']!={'mode':'one_train_only_native_head_capacity_diagnostic','formalTrainingApprovedImages':0}:raise ValueError('diagnostic approval')
    config=plan['training']
    if config['epochs']!=64 or config['nativeBatchSize']!=1 or config['accumulation']!=8 or config['expectedOptimizerSteps']!=384 or plan['full30PilotAllowed']:raise ValueError('preregistered fixed budget')
    if plan['maximumExperiments']!=1 or plan['upstreamModelCalls']!=0:raise ValueError('no restart/upstream call')
    return feasibility,parent,records


def save_weights(path,head):
    with path.open('xb') as stream:
        torch.save({n:v.detach().cpu() for n,v in head.state_dict().items()},stream);stream.flush();os.fsync(stream.fileno())


def metrics(data,deltas,h):
    rows=[];source_sizes={}
    for item,delta in zip(data,deltas,strict=True):
        row=item['row'];probability=h.apply_native_delta(item['base'],delta,item['band']);pred=probability>=.5
        target=item['target']>=.5;source_path=a.checked(row['sourceImage'])
        if source_path not in source_sizes:
            with Image.open(source_path) as source:source_sizes[source_path]=source.size
        width,height=source_sizes[source_path];x0,y0,x1,y1=row['cropBox']
        truth=np.zeros((height,width),bool);guess=np.zeros_like(truth);truth[y0:y1,x0:x1]=target;guess[y0:y1,x0:x1]=pred
        if not np.array_equal(probability[~item['band']].view(np.uint32),item['base'][~item['band']].view(np.uint32)):raise ValueError('outside frozen bit contract')
        entry={'id':row['id'],'positive':bool(row['presenceTarget']),'predictedPixels':int(pred.sum()),'outsideProbabilityBitParity':True}
        if row['presenceTarget']:
            iou=float((truth&guess).sum()/max(1,(truth|guess).sum()));bi,bf=s.core.metric_tool.boundary_metrics(truth,guess,2)
            entry.update(iou=iou,boundaryIou=bi,boundaryF1=bf,jointPass=iou>=.75 and bi>=.75 and bf>=.9)
        else:entry['rejected']=not pred.any()
        rows.append(entry)
    positive=[r for r in rows if r['positive']];negative=[r for r in rows if not r['positive']]
    summary={'positiveCount':len(positive),'emptyCount':len(negative),'meanIou':float(np.mean([r['iou'] for r in positive])),
             'meanBoundaryIou':float(np.mean([r['boundaryIou'] for r in positive])),'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in positive])),
             'jointPassCount':sum(r['jointPass'] for r in positive),'jointInstancePassRate':sum(r['jointPass'] for r in positive)/len(positive),
             'emptyRejectedCount':sum(r['rejected'] for r in negative),'emptyOutputPixels':sum(r['predictedPixels'] for r in negative)}
    return rows,summary


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
                    loss,_=loss_model.conditional_mask_loss(logits,item['target'],boundary_weight=plan['loss']['boundaryWeight'])
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
                'scope':'Train-only capacity, fixed base/45 candidates, native4px correction, final only. Empty rejection inherited from fixed base, not independent negative generalization. No formal quality/threshold selection.'}
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
