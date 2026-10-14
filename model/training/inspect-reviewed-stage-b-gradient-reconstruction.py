"""单候选数值取证：保存各梯度与误差，不作全train归因或修改原失败。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
d=load(HERE/'reviewed-role-development-data.py','reconstruction_data')

def error_summary(mask,presence,total):
    if not (mask.shape==presence.shape==total.shape and mask.dtype==presence.dtype==total.dtype==np.float32
            and all(np.isfinite(x).all() for x in (mask,presence,total))):raise ValueError('reconstruction_mismatch: tensor domain')
    summed=mask+presence;delta=total.astype(np.float64)-summed.astype(np.float64)
    limit=1e-6+1e-5*np.abs(summed.astype(np.float64));bad=np.abs(delta)>limit
    index=int(np.argmax(np.abs(delta)))
    return {'frozenComponentGatePassed':bool(np.allclose(total,summed,rtol=1e-5,atol=1e-6)),
        'failedCoordinates':int(bad.sum()),'coordinateCount':int(mask.size),'maximumAbsoluteError':float(np.abs(delta).max()),
        'errorL2Norm':float(np.linalg.norm(delta)),'totalL2Norm':float(np.linalg.norm(total.astype(np.float64))),
        'maximumErrorCoordinate':index,'atMaximumError':{'mask':float(mask[index]),'presence':float(presence[index]),
            'float32ComponentSum':float(summed[index]),'directTotal':float(total[index]),'frozenAllowedError':float(limit[index])},
        'originalTolerance':{'relative':1e-5,'absolute':1e-6},'originalFailureNotReclassified':True,
        'causeOrGradientConflictConclusionAllowed':False}

def resources(ref):
    e=d.read(ref)
    for bound in [*e['sources'].values(),*e['inputs'].values()]:d.checked(bound)
    assert e['purpose']=='one_failed_candidate_gradient_reconstruction_forensics_only'
    assert d.checked(e['sources']['runner'])==Path(__file__).resolve()
    failure=d.read(e['inputs']['failure']);terminal=d.read(e['inputs']['terminal'])
    assert failure['conclusionsAllowed'] is False and terminal['phase']=='failed' and failure['forwardInputsStarted']==e['candidateOrdinal']
    assert e['budget']=={'maximumAttempts':1,'forwardInputs':1,'autogradEvaluations':3,'optimizerSteps':0,'internalValInputs':0,'protectedInputs':0,'restartAllowed':False}
    g=load(d.checked(e['sources']['failedDiagnosticRunner']),'original_gradient')
    result=g.resources(e['inputs']['failedExecution'])
    assert result[6][e['candidateOrdinal']-1]['candidateIdentity']==e['candidateIdentity']
    return e,g,result

def execute(ref,root):
    e,g,(_,training,_,plan,trainer,data,rows,net,band,metric,guard,cleanup)=resources(ref)
    started=backwards=0
    try:
        root.mkdir(exist_ok=False,parents=True);d.new(root/'attempt.json',{'execution':ref,'restartAllowed':False})
        row=rows[e['candidateOrdinal']-1];sample=trainer.load_samples([row])[0];rgb,coarse,target,positive=sample
        assert positive
        trainer.set_precision();model=net.NativeConditionalMaskRefiner().cuda().float().eval().requires_grad_(True)
        model.load_state_dict(torch.load(d.checked(e['inputs']['weights']),map_location='cpu',weights_only=True),strict=True)
        before=trainer.tensors_sha(model);params=[p for name,p in model.named_parameters() if name.startswith(('enc1.','enc2.','enc3.'))]
        x=torch.from_numpy(net.pack(rgb,coarse))[None].cuda();truth=torch.from_numpy((target>0).astype(np.float32))[None,None].cuda()
        d.new(root/'input-started.json',{'candidateIdentity':row['candidateIdentity'],'forwardInputsStarted':1,'optimizerSteps':0});started=1
        logits,presence=model(x);a=logits[0,0].detach().cpu().numpy().copy();b=presence[0,0].detach().cpu().numpy().copy()
        reference=training['predictions'][e['candidateOrdinal']-1]
        with np.load(d.checked(reference),allow_pickle=False) as archive:fidelity=g.heads_exact(a,b,archive['logits'],archive['presenceLogit'])
        mask,p=g.losses(logits,presence,truth,positive,plan['counts']['train'],band)
        total=trainer.objective(logits,presence,truth,positive,plan['counts']['train'],band)
        vectors=[]
        for loss in (mask,p,total):
            vectors.append(g.vector(torch.autograd.grad(loss,params,retain_graph=len(vectors)<2)));backwards+=1
        path=root/'tensors.npz'
        with path.open('xb') as stream:
            np.savez_compressed(stream,mask=vectors[0],presence=vectors[1],total=vectors[2],rawMask=a,rawPresence=b)
            stream.flush();os.fsync(stream.fileno())
        assert before==trainer.tensors_sha(model)
        report={'ok':True,'decision':'single_candidate_forensic_tensors_saved_not_full_cohort_conclusion',
            'execution':ref,'candidateIdentity':row['candidateIdentity'],'tensors':d.bind(path),'referenceOutput':reference,
            'rawFidelity':fidelity,'numericalReconstruction':error_summary(*vectors),'environment':trainer.environment(),
            'forwardInputs':started,'autogradEvaluations':backwards,'optimizerSteps':0,'weightsUnchanged':True,
            'originalDiagnosticStillFailed':True,'fullCohortGradientConclusionAllowed':False,
            'trainQualityGatePassed':False,'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',report);d.new(root/'terminal.json',{'phase':'closed','forwardInputs':started,'autogradEvaluations':backwards,'optimizerSteps':0});return report
    except BaseException as error:
        if (root/'attempt.json').exists():
            d.new(root/'failure.json',{'error':str(error),'forwardInputsStarted':started,'autogradEvaluationsCompleted':backwards,'optimizerSteps':0,'restartAllowed':False})
        raise
    finally:
        for path in cleanup:guard.remove_ultralytics_label_caches(Path(path))

def verify(path):
    saved=d.read(d.bind(path));e,g,(_,training,_,plan,trainer,data,rows,net,band,metric,guard,cleanup)=resources(saved['execution'])
    try:
        with np.load(d.checked(saved['tensors']),allow_pickle=False) as archive:
            stats=error_summary(archive['mask'],archive['presence'],archive['total'])
            with np.load(d.checked(saved['referenceOutput']),allow_pickle=False) as original:
                fidelity=g.heads_exact(archive['rawMask'],archive['rawPresence'],original['logits'],original['presenceLogit'])
        assert d.raw(stats)==d.raw(saved['numericalReconstruction']) and fidelity==saved['rawFidelity']
        assert saved['candidateIdentity']==e['candidateIdentity'] and saved['forwardInputs']==1 and saved['autogradEvaluations']==3 and saved['optimizerSteps']==0
        return {'ok':True,'forensics':d.bind(path),'numericalReconstruction':stats,'rawFidelity':fidelity,'newModelCalls':0,
            'optimizerSteps':0,'fullCohortGradientConclusionAllowed':False,'originalDiagnosticStillFailed':True,'productHold':True}
    finally:
        for item in cleanup:guard.remove_ultralytics_label_caches(Path(item))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    r=verify(a.verify_report.resolve()) if a.verify_report else execute(d.bind(a.execution),a.output.resolve())
    print(json.dumps(r,ensure_ascii=False))
