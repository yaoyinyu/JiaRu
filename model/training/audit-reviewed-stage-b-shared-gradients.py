"""固定失败权重的全train共享梯度诊断；同RAW保真、独立预算、优化0。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import traceback
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F

HERE=Path(__file__).resolve().parent
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','shared_gradient_data')
def require(ok,message):
    if not ok:raise ValueError('reconstruction_mismatch: '+message)
def sha(value):return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def heads_exact(mask,presence,reference_mask,reference_presence):
    for a,b in ((mask,reference_mask),(presence,reference_presence)):
        require(a.dtype==b.dtype==np.float32 and a.shape==b.shape,'head shape/storage')
        require(np.isfinite(a).all() and np.isfinite(b).all(),'all heads finite')
        require(a.tobytes()==b.tobytes(),'same failed weight RAW bitwise fidelity')
    return {'maskSha256':sha(mask),'presenceSha256':sha(presence),'allHeadBytesExactlySaved':True}


def losses(logits,presence,truth,positive,counts,band):
    flag=torch.tensor([float(positive)],device=truth.device)
    count=counts['positiveInputs'] if positive else counts['rejectInputs']
    weighted_presence=0.5*counts['candidateInputs']/(2*count)*F.binary_cross_entropy_with_logits(presence.reshape(-1).float(),flag)
    if not positive:return None,weighted_presence
    p=logits.float().sigmoid();t=truth.float()
    bce=F.binary_cross_entropy_with_logits(logits.float(),t)
    dice=1-(2*(p*t).sum()+1)/(p.sum()+t.sum()+1)
    mask=bce+dice+0.2*band.soft_boundary(p,t)+2*band.boundary_band_bce(logits,t,4)
    return mask,weighted_presence


def vector(gradients):
    require(all(g is not None and torch.isfinite(g).all() for g in gradients),'finite used encoder gradients')
    return np.concatenate([g.detach().cpu().contiguous().numpy().reshape(-1) for g in gradients]).astype(np.float32)


def pair(mask,presence):
    a=np.asarray(mask,dtype=np.float64);b=np.asarray(presence,dtype=np.float64)
    require(a.shape==b.shape and a.ndim==1 and np.isfinite(a).all() and np.isfinite(b).all(),'gradient pair domain')
    an=float(np.linalg.norm(a));bn=float(np.linalg.norm(b));dot=float(a@b)
    return {'maskNorm':an,'presenceNorm':bn,'dot':dot,
            'cosine':float(np.clip(dot/(an*bn),-1,1)) if an>0 and bn>0 else None,
            'presenceNormToMaskNorm':bn/an if an>0 else None,
            'opposed':dot<0,'combinedGradientDotAgainstMask':float(a@(a+b))}


def summarize(mask,presence,total,records):
    require(mask.dtype==presence.dtype==total.dtype==np.float32 and mask.shape==presence.shape==total.shape and mask.ndim==2 and mask.shape[0]==len(records),'full gradient matrix domain')
    require(np.isfinite(mask).all() and np.isfinite(presence).all() and np.isfinite(total).all(),'gradient matrices finite')
    flags=np.asarray([r['positive'] for r in records],bool)
    require(flags.any() and (~flags).any() and not np.any(mask[~flags]),'same-candidate reject mask gradient zero')
    require(np.allclose(total,mask+presence,rtol=1e-5,atol=1e-6),'frozen total gradient component reconstruction')
    m=mask.astype(np.float64);p=presence.astype(np.float64)
    summary={'candidateInputs':len(records),'positiveInputs':int(flags.sum()),'rejectInputs':int((~flags).sum()),
        'cohortMean':pair(m.mean(axis=0),p.mean(axis=0)),
        'positiveMean':pair(m[flags].mean(axis=0),p[flags].mean(axis=0)),
        'rejectPresenceContributionToCohortMask':pair(m.mean(axis=0),p[~flags].sum(axis=0)/len(records)),
        'componentSumMaximumAbsoluteError':float(np.abs(total.astype(np.float64)-m-p).max()),
        'perCandidate':[{'candidateIdentity':row['candidateIdentity'],'positive':row['positive'],**pair(a,b)} for row,a,b in zip(records,m,p,strict=True)]}
    positive_norms=np.linalg.norm(m[flags],axis=1);positive_mean=m[flags].mean(axis=0)
    summary['maskGradientDiversity']={'fullPositiveDenominator':int(flags.sum()),'zeroMaskGradientPositives':int((positive_norms==0).sum()),
        'positiveMeanNorm':float(np.linalg.norm(positive_mean)),'meanIndividualNorm':float(positive_norms.mean()),
        'meanNormToMeanIndividualNorm':float(np.linalg.norm(positive_mean)/positive_norms.mean()) if positive_norms.mean()>0 else None,
        'positiveGradientsOpposedToPositiveMean':int((m[flags]@positive_mean<0).sum())}
    groups={}
    for i,row in enumerate(records):groups.setdefault(row['sourceGroup'],[]).append(i)
    summary['sourceGroups']=[{'sourceGroup':name,'candidateInputs':len(indices),'positiveInputs':int(flags[indices].sum()),
        'rejectInputs':int((~flags[indices]).sum()),'groupMean':pair(m[indices].mean(axis=0),p[indices].mean(axis=0))} for name,indices in groups.items()]
    summary['positiveMaskPresenceOpposedCount']=sum(row['positive'] and row['opposed'] for row in summary['perCandidate'])
    summary['groupMaskPresenceOpposedCount']=sum(row['groupMean']['opposed'] for row in summary['sourceGroups'])
    summary['scope']='固定最终权重、原输入的瞬时raw loss梯度；不含AdamW预条件或实际更新，不证明训练全程冲突、因果、不可学习或质量改善。'
    return summary


def resources(execution_ref):
    e=d.read(execution_ref)
    for ref in list(e['inputs'].values())+list(e['sources'].values()):d.checked(ref)
    require(e['purpose']=='full_train_same_saved_raw_shared_encoder_gradient_diagnostic','diagnostic purpose')
    require(d.checked(e['sources']['runner'])==Path(__file__).resolve(),'runner identity')
    scope=d.read(e['inputs']['scope']);training=d.read(e['inputs']['training']);audit=d.read(e['inputs']['trainingReplay']);plan=d.read(training['inputs']['plan'])
    require(audit['ok'] and not audit['trainQualityGatePassed'] and audit['training']==e['inputs']['training'],'failed quality authority')
    require(e['inputs']['weights']==training['inputs']['weights'] and scope['inputs']['training']==e['inputs']['training'],'same failed weights')
    trainer=module(d.checked(plan['sources']['trainer']),'shared_gradient_original_trainer')
    p,data,rows,net,band,metric,guard,cleanup=trainer.resources(Path(training['inputs']['plan']['path']))
    require(scope['candidateIdentities']==plan['candidateIdentities']==e['candidateIdentities']==[r['candidateIdentity'] for r in rows],'full all-candidate identity')
    positive=sum(r['presenceTarget'] for r in rows);n=len(rows)
    require(e['budget']=={'maximumAttempts':1,'maximumForwardInputs':n,'maximumAutogradEvaluations':3*positive+2*(n-positive),
        'optimizerSteps':0,'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,'restartAllowed':False},'independent diagnostic budget')
    require(e['precision']==plan['precision'] and e['rawHeadFidelity']=='bitwise_all74_before_any_conclusion' and e['componentSumTolerance']=={'relative':1e-5,'absolute':1e-6},'fidelity/precision contract')
    return e,training,audit,plan,trainer,data,rows,net,band,metric,guard,cleanup


def execute(execution_ref,root):
    e,training,audit,plan,trainer,data,rows,net,band,metric,guard,cleanup=resources(execution_ref)
    started=backwards=0;records=[];mask_vectors=[];presence_vectors=[];total_vectors=[]
    try:
        root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();sequence=0
        def event(phase,**fields):
            nonlocal sequence
            sequence+=1;row={'sequence':sequence,'phase':phase,'forwardInputsStarted':started,'autogradEvaluationsCompleted':backwards,
                'optimizerSteps':0,**fields};d.new(root/'events'/f'{sequence:06d}.json',row);return row
        d.new(root/'attempt.json',{'execution':execution_ref,'attemptConsumed':True,'restartAllowed':False})
        require(torch.cuda.is_available(),'registered CUDA unavailable')
        samples=trainer.load_samples(rows);trainer.set_precision()
        model=net.NativeConditionalMaskRefiner().cuda().float().eval();model.requires_grad_(True)
        state=torch.load(d.checked(e['inputs']['weights']),map_location='cpu',weights_only=True);model.load_state_dict(state,strict=True)
        before=trainer.tensors_sha(model);named=[(name,param) for name,param in model.named_parameters() if name.startswith(('enc1.','enc2.','enc3.'))]
        params=[p for _,p in named];parameter_names=[name for name,_ in named];parameter_shapes=[list(p.shape) for p in params]
        parameter_count=sum(p.numel() for p in params);d.new(root/'environment.json',trainer.environment());event('claimed')
        for row,sample,reference in zip(rows,samples,training['predictions'],strict=True):
            rgb,coarse,target,positive=sample
            x=torch.from_numpy(net.pack(rgb,coarse))[None].cuda();truth=torch.from_numpy((target>0).astype(np.float32))[None,None].cuda()
            started+=1;event('input_started',candidateIdentity=row['candidateIdentity'])
            logits,presence=model(x);actual_mask=logits[0,0].detach().cpu().numpy().copy();actual_presence=presence[0,0].detach().cpu().numpy().copy()
            with np.load(d.checked(reference),allow_pickle=False) as stored:expected_mask=stored['logits'].copy();expected_presence=stored['presenceLogit'].copy()
            fidelity=heads_exact(actual_mask,actual_presence,expected_mask,expected_presence)
            mask_loss,presence_loss=losses(logits,presence,truth,positive,plan['counts']['train'],band)
            total_loss=trainer.objective(logits,presence,truth,positive,plan['counts']['train'],band)
            require(torch.isfinite(total_loss) and torch.isfinite(presence_loss) and (mask_loss is None or torch.isfinite(mask_loss)),'all component losses finite')
            if positive:
                gm=vector(torch.autograd.grad(mask_loss,params,retain_graph=True));backwards+=1
            else:gm=np.zeros(parameter_count,np.float32)
            gp=vector(torch.autograd.grad(presence_loss,params,retain_graph=True));backwards+=1
            gt=vector(torch.autograd.grad(total_loss,params));backwards+=1
            require(np.allclose(gt,gm+gp,rtol=1e-5,atol=1e-6),'total/component gradient fidelity')
            mask_vectors.append(gm);presence_vectors.append(gp);total_vectors.append(gt)
            records.append({'candidateIdentity':row['candidateIdentity'],'sourceGroup':row['sourceGroup'],'positive':positive,
                'nativeSize':row['nativeSize'],'referenceOutput':reference,**fidelity,'lossMask':float(mask_loss.detach()) if positive else 0.,
                'lossWeightedPresence':float(presence_loss.detach()),'lossTotal':float(total_loss.detach()),
                'maskGradientSha256':sha(gm),'presenceGradientSha256':sha(gp),'totalGradientSha256':sha(gt)})
            event('input_confirmed',candidateIdentity=row['candidateIdentity'])
            if len(records)%10==0:print(json.dumps({'confirmedInputs':len(records),'total':len(rows),'autogradEvaluations':backwards}),flush=True)
        require(trainer.tensors_sha(model)==before,'zero-optimization weights changed')
        require(started==e['budget']['maximumForwardInputs'] and backwards==e['budget']['maximumAutogradEvaluations'],'complete diagnostic budget')
        masks=np.stack(mask_vectors);presences=np.stack(presence_vectors);totals=np.stack(total_vectors)
        path=root/'shared-encoder-gradients.npz'
        with path.open('xb') as stream:
            np.savez_compressed(stream,mask=masks,presence=presences,total=totals,parameterNames=np.asarray(parameter_names),
                parameterShapes=np.asarray([json.dumps(s) for s in parameter_shapes]),
                candidateIdentities=np.asarray([json.dumps(r['candidateIdentity'],sort_keys=True) for r in records]))
            stream.flush();os.fsync(stream.fileno())
        stats=summarize(masks,presences,totals,records)
        terminal=event('closed',allRawHeadsBitwiseExact=True,allWeightsUnchanged=True);d.new(root/'terminal.json',terminal)
        report={'schemaVersion':1,'ok':True,'decision':'full_train_raw_fidelity_and_shared_gradient_diagnostic_closed',
            'execution':execution_ref,'gradientArchive':d.bind(path),'environment':d.bind(root/'environment.json'),
            'records':records,'parameterNames':parameter_names,'parameterShapes':parameter_shapes,'sharedEncoderParameterCount':parameter_count,
            'statistics':stats,'forwardInputs':started,'autogradEvaluations':backwards,'allRawHeadsBitwiseExact':True,
            'weightsUnchanged':True,'weightTensorHashes':before,'qualityMetricsUnchanged':training['metrics'],
            'trainQualityGatePassed':False,'optimizerSteps':0,'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,
            'restartAllowed':False,'causalRootCauseOrInterventionQualityProven':False,'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',report);return report
    except BaseException as error:
        if 'sequence' in locals():
            d.new(root/'failure.json',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),
                'forwardInputsStarted':started,'autogradEvaluationsCompleted':backwards,'confirmedCandidates':len(records),
                'attemptConsumed':True,'restartAllowed':False,'conclusionsAllowed':False,'optimizerSteps':0})
            terminal=event('failed');d.new(root/'terminal.json',terminal)
        raise
    finally:
        for path in [*cleanup,root]:guard.remove_ultralytics_label_caches(Path(path))


def verify(report_path):
    ref=d.bind(report_path);saved=d.read(ref)
    e,training,audit,plan,trainer,data,rows,net,band,metric,guard,cleanup=resources(saved['execution'])
    try:
        require(saved['allRawHeadsBitwiseExact'] and saved['weightsUnchanged'] and not saved['trainQualityGatePassed'],'fidelity/old failure flags')
        require(saved['qualityMetricsUnchanged']==training['metrics'],'failed quality preserved')
        require([r['candidateIdentity'] for r in saved['records']]==e['candidateIdentities'],'full recorded candidates')
        for actual,row in zip(saved['records'],rows,strict=True):
            require(actual['positive']==row['presenceTarget'] and actual['sourceGroup']==row['sourceGroup'] and actual['nativeSize']==row['nativeSize'],'record roles/groups/native shapes')
        with np.load(d.checked(saved['gradientArchive']),allow_pickle=False) as archive:
            mask=archive['mask'].copy();presence=archive['presence'].copy();total=archive['total'].copy()
            require(archive['parameterNames'].tolist()==saved['parameterNames'] and [json.loads(s) for s in archive['parameterShapes'].tolist()]==saved['parameterShapes'],'encoder tensor identities/shapes')
            require(archive['candidateIdentities'].tolist()==[json.dumps(r['candidateIdentity'],sort_keys=True) for r in rows],'archive stable identities')
        require(mask.shape==(len(rows),saved['sharedEncoderParameterCount']),'full gradient denominator')
        require(sum(math.prod(s) for s in saved['parameterShapes'])==saved['sharedEncoderParameterCount'],'encoder flattened domain')
        for record,gm,gp,gt,reference in zip(saved['records'],mask,presence,total,training['predictions'],strict=True):
            require(record['referenceOutput']==reference and record['allHeadBytesExactlySaved'],'same RAW binding')
            with np.load(d.checked(reference),allow_pickle=False) as archive:a=archive['logits'].copy();b=archive['presenceLogit'].copy()
            require(record['maskSha256']==sha(a) and record['presenceSha256']==sha(b),'actual/reference RAW hashes')
            require([record[k] for k in ('maskGradientSha256','presenceGradientSha256','totalGradientSha256')]==[sha(x) for x in (gm,gp,gt)],'gradient tensor hashes')
            require(all(math.isfinite(record[k]) for k in ('lossMask','lossWeightedPresence','lossTotal')),'loss scalars finite')
        stats=summarize(mask,presence,total,saved['records']);require(d.raw(stats)==d.raw(saved['statistics']),'statistics full bytes')
        ledger=[json.loads(p.read_bytes()) for p in sorted((report_path.parent/'events').glob('*.json'))]
        require([r['sequence'] for r in ledger]==list(range(1,len(ledger)+1)) and len(ledger)==2*len(rows)+2,'all diagnostic events')
        require([r['candidateIdentity'] for r in ledger if r['phase']=='input_started']==[r['candidateIdentity'] for r in ledger if r['phase']=='input_confirmed']==e['candidateIdentities'],'event candidate identities')
        require(ledger[-1]==json.loads((report_path.parent/'terminal.json').read_bytes()) and ledger[-1]['phase']=='closed','terminal exact')
        expected_backwards=0
        require(ledger[0]['phase']=='claimed' and ledger[0]['forwardInputsStarted']==ledger[0]['autogradEvaluationsCompleted']==0,'initial event')
        for i,r in enumerate(rows,1):
            start,confirm=ledger[2*i-1:2*i+1]
            require(start['phase']=='input_started' and confirm['phase']=='input_confirmed' and start['forwardInputsStarted']==confirm['forwardInputsStarted']==i,'input event chronology')
            require(start['autogradEvaluationsCompleted']==expected_backwards,'start autograd chronology')
            expected_backwards+=3 if r['presenceTarget'] else 2;require(confirm['autogradEvaluationsCompleted']==expected_backwards,'autograd budget chronology')
        require(all(x['optimizerSteps']==0 for x in ledger),'zero optimizer ledger')
        require(saved['forwardInputs']==len(rows) and saved['autogradEvaluations']==expected_backwards and saved['optimizerSteps']==0,'zero optimization complete budget')
        env=d.read(saved['environment']);require(not env['cudaMatmulAllowTf32'] and not env['cudnnAllowTf32'] and not env['autocastEnabled'] and env['float32MatmulPrecision']=='highest','actual precision')
        final_weights=torch.load(d.checked(e['inputs']['weights']),map_location='cpu',weights_only=True)
        require({name:sha(t.contiguous().numpy()) for name,t in final_weights.items()}==saved['weightTensorHashes'],'failed weights unchanged')
        encoder=[(name,t) for name,t in final_weights.items() if name.startswith(('enc1.','enc2.','enc3.'))]
        require([name for name,_ in encoder]==saved['parameterNames'] and [list(t.shape) for _,t in encoder]==saved['parameterShapes'],'full frozen encoder membership')
        return {'ok':True,'diagnostic':ref,'all74RawBitwiseFidelityReplayed':True,'fullGradientsStatisticsRebuilt':True,
            'statistics':stats,'forwardInputsPreviouslyConsumed':len(rows),'autogradEvaluationsPreviouslyConsumed':expected_backwards,
            'newModelCalls':0,'optimizerSteps':0,'newChatImageInputs':0,'trainQualityGatePassed':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for path in cleanup:guard.remove_ultralytics_label_caches(Path(path))


def main():
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    if a.verify_report:r=verify(a.verify_report.resolve())
    else:r=execute(d.bind(a.execution),a.output.resolve())
    print(json.dumps({'ok':r['ok'],'statistics':{k:r['statistics'][k] for k in ('cohortMean','positiveMaskPresenceOpposedCount','groupMaskPresenceOpposedCount','maskGradientDiversity')},'optimizerSteps':0},ensure_ascii=False))
if __name__=='__main__':main()
