"""完整train固定权重presence输入捕获；实际双头RAW字节保真先于任何分析。"""
import argparse
import hashlib
import importlib.util
import json
import os
import traceback
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
def load(path,name):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=load(HERE/'reviewed-role-development-data.py','presence_capture_data')
c=load(HERE/'train-reviewed-stage-b-augmentation-control.py','presence_capture_control')
g=load(HERE/'audit-reviewed-stage-b-shared-gradients.py','presence_capture_fidelity')
require=c.require
def sha(a):return hashlib.sha256(np.asarray(a).tobytes()).hexdigest()

def observe_input(module,inputs,storage):
    require(isinstance(module,torch.nn.Linear) and module.in_features==128 and module.out_features==1 and len(inputs)==1,'actual presence Linear128 input')
    value=inputs[0].detach().cpu().contiguous().numpy().copy()
    require(value.dtype==np.float32 and value.shape==(1,128) and np.isfinite(value).all(),'finite float32 feature128')
    storage.append(value)
    # 显式返回None，不替换输入或参与原计算。

def resources(ref):
    e=d.read(ref)
    for bound in [*e['inputs'].values(),*e['sources'].values()]:d.checked(bound)
    require(e['purpose']=='full_train_fixed_control_presence_feature_capture_only','capture purpose')
    require(d.checked(e['sources']['runner'])==Path(__file__).resolve(),'runner identity')
    scope=d.read(e['inputs']['scope']);training=d.read(e['inputs']['training']);audit=d.read(e['inputs']['replay']);plan=d.read(training['inputs']['plan'])
    require(scope['inputs']['controlTraining']==e['inputs']['training'] and scope['inputs']['controlReplay']==e['inputs']['replay'] and scope['inputs']['controlWeights']==e['inputs']['weights']==training['inputs']['weights'],'fixed failed control authority')
    require(audit['ok'] and not audit['trainQualityGatePassed'] and audit['training']==e['inputs']['training'],'failed full control audit')
    require(scope['candidateIdentities']==plan['candidateIdentities']==e['candidateIdentities'] and e['counts']==scope['counts']==plan['counts'],'all fixed candidates/counts')
    require(e['budget']=={'maximumAttempts':1,'fullNativeForwardInputs':74,'optimizerSteps':0,'autogradEvaluations':0,'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,'restartAllowed':False},'independent capture budget')
    require(e['precision']==plan['precision'] and e['capture']=={'module':'presence','inputIndex':0,'featureDimension':128,'storage':'float32_1x128','allBothHeadsBitwiseExactRequired':True,'hookMustReturnNone':True},'observation/precision contract')
    _,data,rows,net,band,metric,guard,cleanup=c.resources(Path(training['inputs']['plan']['path']))
    return e,training,plan,data,rows,net,guard,cleanup

def execute(ref,root):
    e,training,plan,data,rows,net,guard,cleanup=resources(ref);started=sequence=0;records=[];claimed=False
    try:
        root.mkdir(parents=True,exist_ok=False);(root/'records').mkdir();(root/'events').mkdir()
        d.new(root/'attempt.json',{'execution':ref,'attemptConsumed':True,'restartAllowed':False})
        claimed=True
        def event(phase,**fields):
            nonlocal sequence
            sequence+=1;value={'sequence':sequence,'phase':phase,'forwardInputsStarted':started,'confirmedInputs':len(records),'optimizerSteps':0,**fields}
            d.new(root/'events'/f'{sequence:06d}.json',value);return value
        event('claimed');c.base.set_precision();samples=c.base.load_samples(rows)
        model=net.NativeConditionalMaskRefiner().cuda().float().eval();model.requires_grad_(False)
        model.load_state_dict(torch.load(d.checked(e['inputs']['weights']),map_location='cpu',weights_only=True),strict=True)
        before=c.tensors_sha(model);d.new(root/'environment.json',c.base.environment());captured=[]
        handle=model.presence.register_forward_pre_hook(lambda module,args:observe_input(module,args,captured))
        try:
            for i,(row,sample,reference) in enumerate(zip(rows,samples,training['predictions'],strict=True),1):
                rgb,coarse,target,positive=sample;captured.clear();started+=1;event('input_started',candidateIdentity=row['candidateIdentity'])
                with torch.inference_mode():logits,presence=model(torch.from_numpy(net.pack(rgb,coarse))[None].cuda())
                a=logits[0,0].float().cpu().numpy().copy();b=np.array(float(presence[0,0]),np.float32)
                with np.load(d.checked(reference),allow_pickle=False) as raw:fidelity=g.heads_exact(a,b,raw['logits'],raw['presenceLogit'])
                require(len(captured)==1,'exactly one presence observation per candidate');features=captured[0]
                path=root/'records'/f'{i:03d}.npz'
                with path.open('xb') as stream:
                    np.savez_compressed(stream,features=features,rawMask=a,rawPresence=b);stream.flush();os.fsync(stream.fileno())
                record={'candidateIdentity':row['candidateIdentity'],'sourceGroup':row['sourceGroup'],'positive':positive,'nativeSize':row['nativeSize'],
                    'referenceOutput':reference,'capture':d.bind(path),'featureSha256':sha(features),**fidelity}
                d.new(root/'records'/f'{i:03d}.json',record);records.append(record);event('input_confirmed',candidateIdentity=row['candidateIdentity'],record=d.bind(root/'records'/f'{i:03d}.json'))
                if i%10==0:print(json.dumps({'confirmedInputs':i,'total':len(rows)}),flush=True)
        finally:handle.remove()
        require(started==len(rows)==74 and c.tensors_sha(model)==before,'complete unchanged weights capture')
        report={'schemaVersion':1,'ok':True,'decision':'all74_fixed_presence_features_and_raw_head_fidelity_closed',
            'execution':ref,'records':records,'environment':d.bind(root/'environment.json'),'weightTensorHashes':before,
            'forwardInputs':started,'allBothHeadsBitwiseExact':True,'weightsUnchanged':True,'featureDimension':128,
            'optimizerSteps':0,'autogradEvaluations':0,'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,
            'controlQualityStillFailed':True,'headTrainingOrCandidateWeightsAllowed':False,'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',report);d.new(root/'terminal.json',event('closed'));return report
    except BaseException as error:
        if claimed:
            d.new(root/'failure.json',{'error':str(error),'traceback':traceback.format_exc(),'forwardInputsStarted':started,'confirmedInputs':len(records),'optimizerSteps':0,'restartAllowed':False,'conclusionsAllowed':False})
            if not (root/'terminal.json').exists():d.new(root/'terminal.json',event('failed'))
        raise
    finally:
        for path in cleanup:guard.remove_ultralytics_label_caches(Path(path))

def verify(path):
    saved=d.read(d.bind(path));e,training,plan,data,rows,net,guard,cleanup=resources(saved['execution'])
    try:
        require(saved['ok'] and saved['allBothHeadsBitwiseExact'] and saved['weightsUnchanged'] and saved['forwardInputs']==74,'complete capture flags')
        ledger=[json.loads(p.read_bytes()) for p in sorted((path.parent/'events').glob('*.json'))]
        require(len(ledger)==150 and [x['sequence'] for x in ledger]==list(range(1,151)) and ledger[0]['phase']=='claimed','complete unique capture events')
        features=[]
        for i,(record,row,reference) in enumerate(zip(saved['records'],rows,training['predictions'],strict=True),1):
            require(record['candidateIdentity']==row['candidateIdentity'] and record['positive']==row['presenceTarget'] and record['sourceGroup']==row['sourceGroup'] and record['nativeSize']==row['nativeSize'],'record identity/roles/native dimensions')
            require(record['referenceOutput']==reference,'same original RAW reference')
            with np.load(d.checked(record['capture']),allow_pickle=False) as archive:
                f=archive['features'].copy()
                require(f.dtype==np.float32 and f.shape==(1,128) and np.isfinite(f).all() and sha(f)==record['featureSha256'],'exact finite captured feature')
                with np.load(d.checked(reference),allow_pickle=False) as raw:gate=g.heads_exact(archive['rawMask'],archive['rawPresence'],raw['logits'],raw['presenceLogit'])
            require(all(record[k]==v for k,v in gate.items()),'all actual head hashes')
            start,confirm=ledger[2*i-1:2*i+1]
            require(start['phase']=='input_started' and start['candidateIdentity']==row['candidateIdentity'] and start['forwardInputsStarted']==i and start['confirmedInputs']==i-1,'started chronology')
            require(confirm['phase']=='input_confirmed' and confirm['candidateIdentity']==row['candidateIdentity'] and confirm['forwardInputsStarted']==confirm['confirmedInputs']==i and d.read(confirm['record'])==record,'confirmed chronology')
            features.append(f[0])
        require(ledger[-1]==json.loads((path.parent/'terminal.json').read_bytes()) and ledger[-1]['phase']=='closed' and all(x['optimizerSteps']==0 for x in ledger),'closed zero optimizer ledger')
        state=torch.load(d.checked(e['inputs']['weights']),map_location='cpu',weights_only=True)
        require({name:sha(t.contiguous().numpy()) for name,t in state.items()}==saved['weightTensorHashes'],'all fixed weights unchanged')
        env=d.read(saved['environment']);require(not env['cudaMatmulAllowTf32'] and not env['cudnnAllowTf32'] and not env['autocastEnabled'] and env['float32MatmulPrecision']=='highest','strict actual FP32')
        require(saved['optimizerSteps']==saved['autogradEvaluations']==saved['internalValInputs']==saved['protectedInputs']==saved['newChatImageInputs']==0 and not saved['headTrainingOrCandidateWeightsAllowed'],'no optimization or role drift')
        return {'ok':True,'capture':d.bind(path),'all74ActualHeadsBitwiseFidelityReplayed':True,'featuresShape':[74,128],
            'featureMatrixSha256':sha(np.stack(features)),'eventCount':150,'allWeightsUnchanged':True,'newModelCalls':0,
            'optimizerSteps':0,'headTrainingOrCandidateWeightsAllowed':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for root in cleanup:guard.remove_ultralytics_label_caches(Path(root))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    r=verify(a.verify_report.resolve()) if a.verify_report else execute(d.bind(a.execution),a.output.resolve())
    print(json.dumps({'ok':r['ok'],'decision':r.get('decision'),'forwardInputs':r.get('forwardInputs'),'featuresShape':r.get('featuresShape'),'optimizerSteps':0},ensure_ascii=False))
