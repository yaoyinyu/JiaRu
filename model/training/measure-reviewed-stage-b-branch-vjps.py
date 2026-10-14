"""分别测量固定权重的分支VJP；不把不同反传顺序视为逐坐标真值。"""
import argparse
import importlib.util
import json
import os
import traceback
from pathlib import Path
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
d=load(HERE/'reviewed-role-development-data.py','branch_vjp_data')

def statistics(mask,presence,records,g):
    g.require(mask.dtype==presence.dtype==np.float32 and mask.shape==presence.shape and mask.ndim==2 and len(records)==len(mask),'branch VJP matrices')
    g.require(np.isfinite(mask).all() and np.isfinite(presence).all(),'finite branch matrices')
    flags=np.asarray([r['positive'] for r in records],bool)
    g.require(flags.any() and (~flags).any() and not np.any(mask[~flags]),'same candidate reject mask VJP zero')
    a=mask.astype(np.float64);b=presence.astype(np.float64);mean=a[flags].mean(axis=0);norms=np.linalg.norm(a[flags],axis=1)
    individual=[{'candidateIdentity':r['candidateIdentity'],'positive':r['positive'],**g.pair(x,y)} for r,x,y in zip(records,a,b,strict=True)]
    groups={}
    for i,row in enumerate(records):groups.setdefault(row['sourceGroup'],[]).append(i)
    grouped=[{'sourceGroup':name,'candidateInputs':len(indices),'positiveInputs':int(flags[indices].sum()),
        'groupMean':g.pair(a[indices].mean(axis=0),b[indices].mean(axis=0))} for name,indices in groups.items()]
    return {'candidateInputs':len(records),'positiveInputs':int(flags.sum()),'rejectInputs':int((~flags).sum()),
        'cohortMean':g.pair(a.mean(axis=0),b.mean(axis=0)),'positiveMean':g.pair(mean,b[flags].mean(axis=0)),
        'rejectPresenceContributionToCohortMask':g.pair(a.mean(axis=0),b[~flags].sum(axis=0)/len(records)),
        'perCandidate':individual,'sourceGroups':grouped,
        'positiveMaskPresenceOpposedCount':sum(r['positive'] and r['opposed'] for r in individual),
        'groupMaskPresenceOpposedCount':sum(r['groupMean']['opposed'] for r in grouped),
        'maskGradientDiversity':{'fullPositiveDenominator':int(flags.sum()),'zeroMaskGradientPositives':int((norms==0).sum()),
            'positiveMeanNorm':float(np.linalg.norm(mean)),'meanIndividualNorm':float(norms.mean()),
            'meanNormToMeanIndividualNorm':float(np.linalg.norm(mean)/norms.mean()) if norms.mean()>0 else None,
            'positiveGradientsOpposedToPositiveMean':int((a[flags]@mean<0).sum())},
        'definition':'分别对原mask损失和原类别平衡presence损失求FP32 VJP；FP64仅用于存档张量统计，组合方向是测量向量的代数和，不声称等于原整项FP32反传。',
        'limits':'固定最终权重、无增强train输入的瞬时测量；不能证明训练全程冲突、因果、AdamW实际更新、可学习性或质量改善。',
        'originalTotalGradientReconstructionGateStillFailed':True}

def resources(ref):
    e=d.read(ref)
    for bound in [*e['sources'].values(),*e['inputs'].values()]:d.checked(bound)
    assert e['purpose']=='independent_mask_presence_branch_vjp_measurement_not_total_gradient_reconstruction'
    assert d.checked(e['sources']['runner'])==Path(__file__).resolve()
    assert e['budget']=={'maximumAttempts':1,'forwardInputs':74,'autogradEvaluations':145,'optimizerSteps':0,'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,'restartAllowed':False}
    assert e['measurementDefinition']=={'mask':'original_positive_mask_loss_VJP_or_exact_zero_for_same_candidate_reject',
        'presence':'original_class_balanced_presence_loss_VJP','statistics':'float64_from_saved_float32_vectors',
        'rawFidelity':'all74_both_heads_bitwise_same_saved_training_RAW','originalTotalGradientGate':'failed_preserved_not_reclassified_no_total_gradient_claim'}
    failure=d.read(e['inputs']['originalFailure']);forensic=d.read(e['inputs']['forensics'])
    assert failure['conclusionsAllowed'] is False and forensic['originalDiagnosticStillFailed'] and forensic['numericalReconstruction']['frozenComponentGatePassed'] is False
    g=load(d.checked(e['sources']['originalDiagnosticRunner']),'branch_vjp_original')
    result=g.resources(e['inputs']['originalExecution'])
    assert [r['candidateIdentity'] for r in result[6]]==e['candidateIdentities']
    return e,g,result

def execute(ref,root):
    e,g,(_,training,_,plan,trainer,data,rows,net,band,metric,guard,cleanup)=resources(ref)
    started=backwards=sequence=0;records=[];masks=[];presences=[]
    try:
        root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'vectors').mkdir()
        d.new(root/'attempt.json',{'execution':ref,'restartAllowed':False})
        def event(phase,**fields):
            nonlocal sequence
            sequence+=1;value={'sequence':sequence,'phase':phase,'forwardInputsStarted':started,'autogradEvaluationsCompleted':backwards,'optimizerSteps':0,**fields}
            d.new(root/'events'/f'{sequence:06d}.json',value);return value
        event('claimed');trainer.set_precision();samples=trainer.load_samples(rows)
        model=net.NativeConditionalMaskRefiner().cuda().float().eval().requires_grad_(True)
        weights=d.read(e['inputs']['originalExecution'])['inputs']['weights']
        model.load_state_dict(torch.load(d.checked(weights),map_location='cpu',weights_only=True),strict=True);before=trainer.tensors_sha(model)
        named=[(name,p) for name,p in model.named_parameters() if name.startswith(('enc1.','enc2.','enc3.'))];params=[p for _,p in named]
        parameter_count=sum(p.numel() for p in params);d.new(root/'environment.json',trainer.environment())
        for i,(row,sample,reference) in enumerate(zip(rows,samples,training['predictions'],strict=True),1):
            rgb,coarse,target,positive=sample;x=torch.from_numpy(net.pack(rgb,coarse))[None].cuda();truth=torch.from_numpy((target>0).astype(np.float32))[None,None].cuda()
            started+=1;event('input_started',candidateIdentity=row['candidateIdentity'])
            logits,presence=model(x);a=logits[0,0].detach().cpu().numpy().copy();b=presence[0,0].detach().cpu().numpy().copy()
            with np.load(d.checked(reference),allow_pickle=False) as stored:fidelity=g.heads_exact(a,b,stored['logits'],stored['presenceLogit'])
            mask,p=g.losses(logits,presence,truth,positive,plan['counts']['train'],band)
            if positive:gm=g.vector(torch.autograd.grad(mask,params,retain_graph=True));backwards+=1
            else:gm=np.zeros(parameter_count,np.float32)
            gp=g.vector(torch.autograd.grad(p,params));backwards+=1
            path=root/'vectors'/f'{i:03d}.npz'
            with path.open('xb') as stream:
                np.savez_compressed(stream,mask=gm,presence=gp,rawMask=a,rawPresence=b);stream.flush();os.fsync(stream.fileno())
            record={'candidateIdentity':row['candidateIdentity'],'sourceGroup':row['sourceGroup'],'positive':positive,
                'nativeSize':row['nativeSize'],'referenceOutput':reference,'vectors':d.bind(path),**fidelity,
                'maskGradientSha256':g.sha(gm),'presenceGradientSha256':g.sha(gp)}
            d.new(root/'vectors'/f'{i:03d}.json',record);records.append(record);masks.append(gm);presences.append(gp)
            event('input_confirmed',candidateIdentity=row['candidateIdentity'],record=d.bind(root/'vectors'/f'{i:03d}.json'))
            if i%10==0:print(json.dumps({'confirmedInputs':i,'autogradEvaluations':backwards}),flush=True)
        assert started==74 and backwards==145 and before==trainer.tensors_sha(model)
        stats=statistics(np.stack(masks),np.stack(presences),records,g)
        report={'ok':True,'decision':'independent_branch_vjp_measurement_closed_original_total_gate_still_failed',
            'execution':ref,'records':records,'statistics':stats,'environment':d.bind(root/'environment.json'),
            'parameterNames':[name for name,_ in named],'parameterShapes':[list(p.shape) for _,p in named],
            'weightTensorHashes':before,'forwardInputs':started,'autogradEvaluations':backwards,'optimizerSteps':0,
            'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,'weightsUnchanged':True,'all74HeadsBitwiseExact':True,
            'originalTotalGradientReconstructionGatePassed':False,'trainQualityGatePassed':False,'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',report);d.new(root/'terminal.json',event('closed'));return report
    except BaseException as error:
        if (root/'attempt.json').exists():
            d.new(root/'failure.json',{'error':str(error),'traceback':traceback.format_exc(),'forwardInputsStarted':started,
                'autogradEvaluationsCompleted':backwards,'confirmedCandidates':len(records),'optimizerSteps':0,'restartAllowed':False,'conclusionsAllowed':False})
            if not (root/'terminal.json').exists():d.new(root/'terminal.json',event('failed'))
        raise
    finally:
        for item in cleanup:guard.remove_ultralytics_label_caches(Path(item))

def verify(path):
    saved=d.read(d.bind(path));e,g,(_,training,_,plan,trainer,data,rows,net,band,metric,guard,cleanup)=resources(saved['execution'])
    try:
        assert saved['all74HeadsBitwiseExact'] and saved['weightsUnchanged'] and not saved['originalTotalGradientReconstructionGatePassed'] and not saved['trainQualityGatePassed']
        ledger=[json.loads(p.read_bytes()) for p in sorted((path.parent/'events').glob('*.json'))]
        assert len(ledger)==150 and [x['sequence'] for x in ledger]==list(range(1,151)) and ledger[0]['phase']=='claimed'
        masks=[];presences=[];backwards=0
        for i,(record,row,reference) in enumerate(zip(saved['records'],rows,training['predictions'],strict=True),1):
            assert record['candidateIdentity']==row['candidateIdentity'] and record['positive']==row['presenceTarget'] and record['sourceGroup']==row['sourceGroup'] and record['nativeSize']==row['nativeSize']
            assert record['referenceOutput']==reference
            with np.load(d.checked(record['vectors']),allow_pickle=False) as vectors:
                gm=vectors['mask'].copy();gp=vectors['presence'].copy()
                with np.load(d.checked(reference),allow_pickle=False) as raw:
                    fidelity=g.heads_exact(vectors['rawMask'],vectors['rawPresence'],raw['logits'],raw['presenceLogit'])
            assert all(record[k]==v for k,v in fidelity.items()) and record['maskGradientSha256']==g.sha(gm) and record['presenceGradientSha256']==g.sha(gp)
            start,confirm=ledger[2*i-1:2*i+1]
            assert start['phase']=='input_started' and start['candidateIdentity']==row['candidateIdentity'] and start['forwardInputsStarted']==i and start['autogradEvaluationsCompleted']==backwards
            backwards+=2 if row['presenceTarget'] else 1
            assert confirm['phase']=='input_confirmed' and confirm['candidateIdentity']==row['candidateIdentity'] and confirm['forwardInputsStarted']==i and confirm['autogradEvaluationsCompleted']==backwards
            assert d.read(confirm['record'])==record
            masks.append(gm);presences.append(gp)
        assert len(rows)==74 and backwards==145 and all(x['optimizerSteps']==0 for x in ledger)
        assert ledger[-1]==json.loads((path.parent/'terminal.json').read_bytes()) and ledger[-1]['phase']=='closed'
        stats=statistics(np.stack(masks),np.stack(presences),saved['records'],g);assert d.raw(stats)==d.raw(saved['statistics'])
        weights=d.read(e['inputs']['originalExecution'])['inputs']['weights'];state=torch.load(d.checked(weights),map_location='cpu',weights_only=True)
        assert {name:g.sha(t.contiguous().numpy()) for name,t in state.items()}==saved['weightTensorHashes']
        encoder=[(name,t) for name,t in state.items() if name.startswith(('enc1.','enc2.','enc3.'))]
        assert [name for name,_ in encoder]==saved['parameterNames'] and [list(t.shape) for _,t in encoder]==saved['parameterShapes']
        assert all(len(x)==sum(t.numel() for _,t in encoder) for x in masks+presences)
        env=d.read(saved['environment']);assert not env['cudaMatmulAllowTf32'] and not env['cudnnAllowTf32'] and not env['autocastEnabled'] and env['float32MatmulPrecision']=='highest'
        return {'ok':True,'measurement':d.bind(path),'statistics':stats,'all74RawHeadsBitwiseFidelityReplayed':True,
            'allBranchVectorsAndStableIdentitiesReplayed':True,'newModelCalls':0,'optimizerSteps':0,
            'originalTotalGradientGateStillFailed':True,'trainQualityGatePassed':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for item in cleanup:guard.remove_ultralytics_label_caches(Path(item))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    r=verify(a.verify_report.resolve()) if a.verify_report else execute(d.bind(a.execution),a.output.resolve())
    print(json.dumps({'ok':r['ok'],'statistics':{k:r['statistics'][k] for k in ('cohortMean','positiveMean','positiveMaskPresenceOpposedCount','groupMaskPresenceOpposedCount','maskGradientDiversity')}},ensure_ascii=False))
