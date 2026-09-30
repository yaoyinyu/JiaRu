"""独立BF16数值修复容量门：全轮完成后一次终评，逐优化步原子记录状态。"""
from __future__ import annotations
import argparse
import json
import os
import tempfile
import time
import traceback
from pathlib import Path
import numpy as np
import torch
import importlib.util


def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


old=load('bf16_original_capacity','train-conditional-nail-refinement-microfit.py')
a=old.a


def atomic_json(path,value):
    """仅原子替换自身进度文件；不可用作覆盖冻结计划或历史报告。"""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=f'.{path.name}.',dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def validate(plan):
    records,feasibility=old.validate(plan)
    previous=a.read(a.checked(plan['inputs']['previousCapacityPlan']))
    failure=a.read(a.checked(plan['inputs']['previousExecutionFailure']))
    gradient=a.read(a.checked(plan['inputs']['bf16Gradient']))
    for binding in gradient['inputs'].values():a.checked(binding)
    for key in ['candidateIds','approval','training','loss','gates','cacheCleanupRoots','full30PilotAllowed']:
        if plan[key]!=previous[key]:raise ValueError(f'numerical repair changed fixed contract: {key}')
    if not failure['budget']['attemptConsumed'] or failure['budget']['originalAttemptMayRestart']:raise ValueError('old consumed budget')
    if gradient['optimizerSteps']!=0 or gradient['candidateIds']!=plan['candidateIds'] or len(gradient['batches'])!=23 or not gradient['ok']:raise ValueError('BF16 initial gate')
    if plan['precision']!={'autocast':'bfloat16','loss':'float32','lossScaling':False,'gradientNormClip':1.0}:raise ValueError('BF16 fixed precision')
    if plan['repairBudget']['maximumExperiments']!=1 or plan['repairBudget']['oldAttemptMayRestart']:raise ValueError('separate once-only repair budget')
    return records,feasibility


def forensic_checkpoint(path,model,optimizer,scheduler,generator,history,state,plan_path):
    temporary=path.with_suffix('.pt.tmp')
    try:
        torch.save({'model':{n:v.detach().cpu() for n,v in model.state_dict().items()},'optimizer':optimizer.state_dict(),
            'scheduler':scheduler.state_dict(),'samplerRng':generator.get_state(),'torchRng':torch.get_rng_state(),
            'cudaRng':torch.cuda.get_rng_state_all(),'history':history,'state':state,'planSha256':a.sha(plan_path),
            'use':'forensic only; does not authorize replaying consumed optimizer steps'},temporary)
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def train(plan_path,output):
    plan=a.read(plan_path);records,feasibility=validate(plan)
    if output.exists():raise FileExistsError('separate once-only output already claimed; no resume/restart')
    output.mkdir(parents=True)
    claim={'plan':a.bind(plan_path),'pid':os.getpid(),'maximumExperiments':1,'phase':'claimed','scope':'new numerical repair; not old v1 continuation'}
    a.write_new(output/'claim.json',claim)
    state={'phase':'claimed','pid':os.getpid(),'completedEpochs':0,'epochInProgress':0,'optimizerSteps':0,'optimizerStepInFlight':False,'finalEvaluationPerformed':False,'planSha256':a.sha(plan_path)}
    atomic_json(output/'progress.json',state);start=time.perf_counter();history=[];steps=0
    try:
        if not torch.cuda.is_bf16_supported():raise RuntimeError('BF16 unavailable')
        config=plan['training'];torch.set_num_threads(2);torch.manual_seed(config['seed']);torch.cuda.manual_seed_all(config['seed']);torch.set_float32_matmul_precision('high')
        data=[a.pixel_input(r) for r in records]
        images=torch.from_numpy(np.stack([r[0] for r in data]));targets=torch.from_numpy(np.stack([r[1] for r in data]))
        model,architecture=a.load_model(feasibility);model=model.cuda();model.backbone.gradient_checkpointing_enable()
        optimizer=torch.optim.AdamW([
            {'params':[p for n,p in model.named_parameters() if n.startswith('backbone.')],'lr':config['backboneLearningRate']},
            {'params':[p for n,p in model.named_parameters() if not n.startswith('backbone.')],'lr':config['decoderLearningRate']}],weight_decay=config['weightDecay'])
        scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=config['epochs'],eta_min=config['backboneLearningRate']*.05)
        generator=torch.Generator().manual_seed(config['seed'])
        for epoch in range(1,config['epochs']+1):
            model.train();order=torch.randperm(len(records),generator=generator).tolist()
            batches=[order[i:i+config['batchSize']] for i in range(0,len(order),config['batchSize'])];epoch_loss=0.
            state.update(phase='training',epochInProgress=epoch);atomic_json(output/'progress.json',state)
            for window_index,w in enumerate(range(0,len(batches),config['accumulation']),1):
                window=batches[w:w+config['accumulation']];sample_count=sum(len(b) for b in window)
                optimizer.zero_grad(set_to_none=True)
                for indices in window:
                    with torch.amp.autocast('cuda',dtype=torch.bfloat16):logits=model(images[indices].cuda())
                    loss,_=architecture.conditional_mask_loss(logits,targets[indices].cuda(),boundary_weight=plan['loss']['boundaryWeight'])
                    if not torch.isfinite(loss):raise ValueError('nonfinite BF16 train loss')
                    (loss*(len(indices)/sample_count)).backward();epoch_loss+=float(loss.detach())*len(indices)
                norm=torch.nn.utils.clip_grad_norm_(model.parameters(),plan['precision']['gradientNormClip'],error_if_nonfinite=True)
                state.update(optimizerStepInFlight=True,attemptedNextStep=steps+1,windowInEpoch=window_index)
                atomic_json(output/'progress.json',state)
                optimizer.step();steps+=1
                state.update(optimizerSteps=steps,optimizerStepInFlight=False,gradientNormBeforeClip=float(norm),elapsedSeconds=time.perf_counter()-start)
                atomic_json(output/'progress.json',state)
            scheduler.step();history.append({'epoch':epoch,'optimizerSteps':steps,'meanTrainLoss':epoch_loss/len(records),'seconds':time.perf_counter()-start})
            state.update(completedEpochs=epoch,lastMeanTrainLoss=history[-1]['meanTrainLoss']);atomic_json(output/'progress.json',state)
            atomic_json(output/'history.json',history)
            if epoch%8==0:
                forensic_checkpoint(output/'latest-forensic-checkpoint.pt',model,optimizer,scheduler,generator,history,state.copy(),plan_path)
            if epoch==1 or epoch%8==0:print(json.dumps({'epoch':epoch,'epochs':config['epochs'],'optimizerSteps':steps,'loss':state['lastMeanTrainLoss']}),flush=True)
        if steps!=config['expectedOptimizerSteps']:raise ValueError('384 optimizer steps not fulfilled')
        state.update(phase='final-evaluation');atomic_json(output/'progress.json',state)
        model.eval();model.backbone.gradient_checkpointing_disable();outputs=[]
        with torch.inference_mode():
            for begin in range(0,len(records),config['batchSize']):
                with torch.amp.autocast('cuda',dtype=torch.bfloat16):logits=model(images[begin:begin+config['batchSize']].cuda())
                outputs.extend(logits.float().cpu().numpy()[:,0])
        array=np.stack(outputs).astype(np.float32)
        if not np.isfinite(array).all():raise ValueError('nonfinite final outputs')
        np.savez_compressed(output/'final-logits.npz',candidateIds=np.asarray(plan['candidateIds']),logits=array)
        torch.save({'model':model.cpu().state_dict(),'planSha256':a.sha(plan_path),'optimizerSteps':steps,'trainingPrecision':'bf16'},output/'final-weights.pt')
        rows,metrics=old.native_metrics(records,array);ok=old.passed(metrics,plan['gates'])
        report={'schemaVersion':1,'ok':ok,'decision':'conditional_capacity_microfit_pass_pending_full_split' if ok else 'conditional_capacity_microfit_fail_no_full30',
            'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'finalWeights':a.bind(output/'final-weights.pt'),'finalLogits':a.bind(output/'final-logits.npz'),
            'completedEpochs':config['epochs'],'completedOptimizerSteps':steps,'history':history,'perCandidate':rows,'metrics':metrics,'gates':plan['gates'],
            'trainingPrecision':plan['precision'],'elapsedSeconds':time.perf_counter()-start,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
            'scope':'All45 fixed train-only numerical repair; final epoch only, no independent validation or historical score comparison. Old FP16 failure unchanged.'}
        a.write_new(output/'microfit-report.json',report)
        state.update(phase='closed',finalEvaluationPerformed=True,qualityDecision=report['decision'],elapsedSeconds=time.perf_counter()-start)
        atomic_json(output/'progress.json',state);a.write_new(output/'terminal-report.json',{'ok':True,'executionDecision':'completed_all64_once','state':state,'qualityReport':a.bind(output/'microfit-report.json')})
        return report
    except BaseException as error:
        state.update(phase='execution-failed',elapsedSeconds=time.perf_counter()-start)
        failure={'ok':False,'decision':'bf16_capacity_execution_failed_no_completed_quality_decision','inputs':{'plan':a.bind(plan_path),**plan['inputs']},
            'state':state,'exceptionType':type(error).__name__,'exception':str(error),'traceback':traceback.format_exc(),'attemptConsumed':True,'restartAllowed':False,'qualityDecision':'unavailable'}
        atomic_json(output/'progress.json',state);a.write_new(output/'execution-failure-report.json',failure)
        raise


def verify(path):
    report=a.read(path);plan=a.read(a.checked(report['inputs']['plan']));records,_=validate(plan)
    for binding in report['inputs'].values():a.checked(binding)
    a.checked(report['finalWeights']);a.checked(report['finalLogits'])
    with np.load(report['finalLogits']['path'],allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=plan['candidateIds'] or saved['logits'].shape!=(45,384,384):raise ValueError('all45 output identity')
        rows,metrics=old.native_metrics(records,saved['logits'])
    ok=old.passed(metrics,plan['gates']);expected='conditional_capacity_microfit_pass_pending_full_split' if ok else 'conditional_capacity_microfit_fail_no_full30'
    progress=a.read(path.parent/'progress.json');terminal=a.read(path.parent/'terminal-report.json')
    if rows!=report['perCandidate'] or metrics!=report['metrics'] or report['ok']!=ok or report['decision']!=expected or report['completedEpochs']!=64 or report['completedOptimizerSteps']!=384:raise ValueError('final capacity replay')
    if progress['phase']!='closed' or progress['optimizerSteps']!=384 or progress['completedEpochs']!=64 or not progress['finalEvaluationPerformed'] or terminal['state']!=progress:raise ValueError('terminal progress')
    a.checked(terminal['qualityReport'])
    if len(report['history'])!=64 or any(r['epoch']!=i or r['optimizerSteps']!=i*6 for i,r in enumerate(report['history'],1)):raise ValueError('all64 history')
    return {'ok':True,'decision':'verified','microfitDecision':report['decision'],'metrics':metrics}


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    guard=old.load('bf16_capacity_guard','train-yolo-seg.py');guard.install_read_only_ultralytics_image_check()
    plan=a.read(args.plan if args.plan else a.read(args.verify_report)['inputs']['plan']['path'])
    try:
        result=verify(args.verify_report) if args.verify_report else train(args.plan.resolve(),args.output.resolve())
        print(json.dumps({k:result[k] for k in ['ok','decision','metrics']},ensure_ascii=False),flush=True)
    finally:
        for root in plan['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))


if __name__=='__main__':main()
