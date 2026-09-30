"""固定全候选的一次train-only容量门；仅最终轮判定，不读取val/test。"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image


def load(name, filename):
    path=Path(__file__).with_name(filename)
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


a=load('conditional_capacity_auditor','audit-conditional-nail-refinement-feasibility.py')
browser=load('conditional_capacity_browser','verify-conditional-nail-refinement-browser.py')
metric_tool=load('conditional_native_metrics','train-development-cycle-016-roi-refinement-pilot.py')


def validate(plan):
    for binding in plan['inputs'].values():a.checked(binding)
    static=a.read(plan['inputs']['staticReport']['path'])
    feasibility=a.read(static['inputs']['plan']['path'])
    records=a.validate(feasibility)
    saved=a.read(plan['inputs']['browserReport']['path'])
    if browser.build(Path(saved['inputs']['staticReport']['path']),Path(saved['inputs']['liveBrowser']['path']))!=saved:raise ValueError('browser replay')
    if [r['id'] for r in records]!=plan['candidateIds'] or plan['approval']['mode']!='one_train_only_capacity_diagnostic':raise ValueError('all45 approval')
    if plan['training']['epochs']!=64 or plan['training']['expectedOptimizerSteps']!=384 or plan['full30PilotAllowed']:raise ValueError('budget/full split')
    return records,feasibility


def native_metrics(records, logits_array):
    rows=[]
    for row,logits in zip(records,logits_array,strict=True):
        # 与浏览器共享float32概率及PIL bilinear逆映射；正式指标在原图2像素口径。
        probability=(1/(1+np.exp(-np.clip(logits,-80,80)))).astype(np.float32)
        with Image.open(a.checked(row['paths']['nativeTarget'])) as image:target_crop=np.asarray(image).copy()>=128
        predicted_crop=np.asarray(Image.fromarray(probability).resize(tuple(row['nativeSize']),Image.Resampling.BILINEAR))>=.5
        with Image.open(a.checked(row['sourceImage'])) as image:width,height=image.size
        x0,y0,x1,y1=row['cropBox']
        target=np.zeros((height,width),bool);prediction=np.zeros_like(target)
        target[y0:y1,x0:x1]=target_crop;prediction[y0:y1,x0:x1]=predicted_crop
        pixels=int(prediction.sum())
        if row['presenceTarget']:
            iou=float((target&prediction).sum()/max(1,(target|prediction).sum()))
            bi,bf=metric_tool.boundary_metrics(target,prediction,2)
            rows.append({'id':row['id'],'positive':True,'predictedPixels':pixels,'iou':iou,'boundaryIou':bi,'boundaryF1':bf,'jointPass':iou>=.75 and bi>=.75 and bf>=.9})
        else:rows.append({'id':row['id'],'positive':False,'predictedPixels':pixels,'rejected':pixels==0})
    positive=[r for r in rows if r['positive']];negative=[r for r in rows if not r['positive']]
    summary={'positiveCount':len(positive),'emptyCount':len(negative),'meanIou':float(np.mean([r['iou'] for r in positive])),
        'meanBoundaryIou':float(np.mean([r['boundaryIou'] for r in positive])),'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in positive])),
        'jointPassCount':sum(r['jointPass'] for r in positive),'jointInstancePassRate':sum(r['jointPass'] for r in positive)/len(positive),
        'emptyRejectedCount':sum(r['rejected'] for r in negative),'emptyOutputPixels':sum(r['predictedPixels'] for r in negative)}
    return rows,summary


def passed(metrics,gates):
    return metrics['positiveCount']==34 and metrics['emptyCount']==11 and metrics['jointInstancePassRate']>=gates['minimumJointInstancePassRate'] and metrics['meanBoundaryF1']>=gates['minimumMeanBoundaryF1'] and metrics['meanIou']>=gates['minimumMeanIou'] and metrics['emptyRejectedCount']==11 and metrics['emptyOutputPixels']==0


def train(plan_path,output):
    plan=a.read(plan_path);records,feasibility=validate(plan)
    if output.exists():raise FileExistsError('once-only output already claimed')
    output.mkdir(parents=True)
    a.write_new(output/'claim.json',{'plan':a.bind(plan_path),'phase':'claimed_no_optimizer_steps_yet','maximumExperiments':1})
    torch.set_num_threads(2);torch.manual_seed(plan['training']['seed']);torch.cuda.manual_seed_all(plan['training']['seed'])
    torch.set_float32_matmul_precision('high')
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    data=[a.pixel_input(r) for r in records]
    images=torch.from_numpy(np.stack([r[0] for r in data]));targets=torch.from_numpy(np.stack([r[1] for r in data]))
    model,architecture=a.load_model(feasibility);model=model.cuda();model.backbone.gradient_checkpointing_enable()
    backbone=[p for n,p in model.named_parameters() if n.startswith('backbone.')]
    decoder=[p for n,p in model.named_parameters() if not n.startswith('backbone.')]
    config=plan['training']
    optimizer=torch.optim.AdamW([{'params':backbone,'lr':config['backboneLearningRate']},{'params':decoder,'lr':config['decoderLearningRate']}],weight_decay=config['weightDecay'])
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=config['epochs'],eta_min=config['backboneLearningRate']*.05)
    scaler=torch.amp.GradScaler('cuda')
    generator=torch.Generator().manual_seed(config['seed']);steps=0;history=[];start=time.perf_counter()
    for epoch in range(1,config['epochs']+1):
        model.train();order=torch.randperm(len(records),generator=generator).tolist()
        batches=[order[i:i+config['batchSize']] for i in range(0,len(order),config['batchSize'])]
        epoch_loss=0.
        for w in range(0,len(batches),config['accumulation']):
            window=batches[w:w+config['accumulation']];sample_count=sum(len(b) for b in window)
            optimizer.zero_grad(set_to_none=True)
            for indices in window:
                x=images[indices].cuda();target=targets[indices].cuda()
                with torch.amp.autocast('cuda'):logits=model(x)
                loss,_=architecture.conditional_mask_loss(logits,target,boundary_weight=plan['loss']['boundaryWeight'])
                if not torch.isfinite(loss):raise ValueError('nonfinite train loss')
                scaler.scale(loss*(len(indices)/sample_count)).backward()
                epoch_loss+=float(loss.detach())*len(indices)
            scaler.unscale_(optimizer);torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
            before=scaler.get_scale();scaler.step(optimizer);scaler.update()
            if scaler.get_scale()<before:raise ValueError('AMP skipped optimizer step; fixed budget not fulfilled')
            steps+=1
        scheduler.step();history.append({'epoch':epoch,'optimizerSteps':steps,'meanTrainLoss':epoch_loss/len(records),'seconds':time.perf_counter()-start})
        if epoch==1 or epoch%8==0:print(json.dumps({'epoch':epoch,'epochs':config['epochs'],'optimizerSteps':steps,'loss':history[-1]['meanTrainLoss']}),flush=True)
    if steps!=config['expectedOptimizerSteps']:raise ValueError('optimizer step count')
    model.eval();model.backbone.gradient_checkpointing_disable();outputs=[]
    with torch.inference_mode():
        for begin in range(0,len(records),config['batchSize']):
            with torch.amp.autocast('cuda'):logits=model(images[begin:begin+config['batchSize']].cuda())
            outputs.extend(logits.float().cpu().numpy()[:,0])
    array=np.stack(outputs).astype(np.float32)
    np.savez_compressed(output/'final-logits.npz',candidateIds=np.asarray(plan['candidateIds']),logits=array)
    torch.save({'model':model.cpu().state_dict(),'planSha256':a.sha(plan_path),'optimizerSteps':steps},output/'final-weights.pt')
    rows,metrics=native_metrics(records,array);ok=passed(metrics,plan['gates'])
    report={'schemaVersion':1,'ok':ok,'decision':'conditional_capacity_microfit_pass_pending_full_split' if ok else 'conditional_capacity_microfit_fail_no_full30',
        'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'finalWeights':a.bind(output/'final-weights.pt'),'finalLogits':a.bind(output/'final-logits.npz'),
        'completedEpochs':config['epochs'],'completedOptimizerSteps':steps,'history':history,'perCandidate':rows,'metrics':metrics,'gates':plan['gates'],
        'elapsedSeconds':time.perf_counter()-start,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
        'scope':'Only fixed all45 train capacity; no independent validation, historical-score comparison or publication. Failed original denominators remain unchanged.'}
    a.write_new(output/'microfit-report.json',report)
    return report


def verify(path):
    report=a.read(path);plan=a.read(a.checked(report['inputs']['plan']));records,_=validate(plan)
    for b in report['inputs'].values():a.checked(b)
    a.checked(report['finalWeights']);a.checked(report['finalLogits'])
    with np.load(report['finalLogits']['path'],allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=plan['candidateIds'] or saved['logits'].shape!=(45,384,384):raise ValueError('all45 output identity')
        rows,metrics=native_metrics(records,saved['logits'])
    ok=passed(metrics,plan['gates'])
    expected='conditional_capacity_microfit_pass_pending_full_split' if ok else 'conditional_capacity_microfit_fail_no_full30'
    if rows!=report['perCandidate'] or metrics!=report['metrics'] or report['ok']!=ok or report['decision']!=expected or report['completedEpochs']!=64 or report['completedOptimizerSteps']!=384:raise ValueError('capacity replay mismatch')
    return {'ok':True,'decision':'verified','microfitDecision':report['decision'],'metrics':metrics}


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    guard=load('conditional_train_guard','train-yolo-seg.py');guard.install_read_only_ultralytics_image_check()
    plan=a.read(args.plan if args.plan else a.read(args.verify_report)['inputs']['plan']['path'])
    try:
        result=verify(args.verify_report) if args.verify_report else train(args.plan.resolve(),args.output.resolve())
        print(json.dumps({k:result[k] for k in ['ok','decision','metrics']},ensure_ascii=False),flush=True)
    finally:
        for root in plan['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))


if __name__=='__main__':main()
