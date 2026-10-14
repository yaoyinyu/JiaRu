"""只读比较同输入首GN原始/候选真实缓冲；不批准完整模型或发布。"""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('operator_compare_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def compare_pair(reference,original,patched):
    if reference.dtype!=np.float64 or original.dtype!=np.float32 or patched.dtype!=np.float32 or original.shape!=reference.shape or patched.shape!=reference.shape or any(not np.isfinite(a).all() for a in (reference,original,patched)):raise ValueError('own FP64 reference / same native actual F32 domains')
    old=original.astype(np.float64)-reference;new=patched.astype(np.float64)-reference
    return {'originalMaxAbs':float(np.max(np.abs(old))),'patchedMaxAbs':float(np.max(np.abs(new))),'actualOutputChangeMaxAbs':float(np.max(np.abs(patched.astype(np.float64)-original.astype(np.float64)))),'originalMeanAbs':float(np.mean(np.abs(old))),'patchedMeanAbs':float(np.mean(np.abs(new))),'originalRms':float(np.sqrt(np.mean(old*old))),'patchedRms':float(np.sqrt(np.mean(new*new)))}


def reconstruct(execution):
    e=d.read(d.bind(execution))
    for ref in e['sources'].values():d.checked(ref)
    if e['sources']['auditor']!=d.bind(__file__) or e['newModelCallsAllowed']!=0:raise ValueError('frozen pure read-only comparison')
    runner=d.load(d.checked(e['sources']['runner']),'comparison_gn_runner');buffer=d.load(d.checked(e['sources']['tensorReader']),'comparison_buffer')
    scope=d.read(e['scope']);runner.validate_scope(scope)
    old=d.read(e['original']);new=d.read(e['patched']);runner.require_original_gate(old)
    if old['stage']!='original' or new['stage']!='patched' or not new['ok'] or new['originalGate']!=e['original'] or new['operatorInputsConsumed']!=408 or len(new['records'])!=408:raise ValueError('original408 then patched408 frozen stages')
    for key in ('formalReleaseAllowed','fullModelBrowserGatePassed'):
        if old[key] or new[key]:raise ValueError('operator evidence cannot approve full graph')
    if not old['productHold'] or not new['productHold']:raise ValueError('HOLD')
    original_prep=d.read(old['inputs']['preparation']);patched_prep=d.read(new['inputs']['preparation'])
    if original_prep['execution']!=patched_prep['execution'] or d.read(original_prep['execution'])['scope']!=e['scope']:raise ValueError('same execution / scope')
    records=[];full_fidelity=[]
    for backend in scope['requiredBackends']:
        a=old['captures'][backend];b=new['captures'][backend]
        if len(a)!=136 or len(b)!=136 or [r['ordinal'] for r in a]!=list(range(1,137)) or [r['ordinal'] for r in b]!=list(range(1,137)):raise ValueError('full ordered per-backend contexts')
        for case,original,patched in zip(scope['cases'],a,b,strict=True):
            for cap in (original,patched):
                if cap['candidateIdentity']!=case['candidateIdentity'] or cap['candidateOrdinal']!=case['candidateOrdinal'] or cap['inputOrigin']!=case['inputOrigin'] or cap['inputSha256']!=case['input']['sha256'] or cap['targetShape']!=case['ownInputFp64Reference']['shape']:raise ValueError('same stable candidate/origin/input/native output')
            reference=buffer.read_tensor(case['ownInputFp64Reference']);x=buffer.read_tensor(original['output']);y=buffer.read_tensor(patched['output']);stats=compare_pair(reference,x,y)
            ordinal=case['contextOrdinal'];oldrow=old['records'][scope['requiredBackends'].index(backend)*136+ordinal-1];newrow=new['records'][scope['requiredBackends'].index(backend)*136+ordinal-1]
            if stats['originalMaxAbs']!=oldrow['difference']['maxAbs'] or stats['patchedMaxAbs']!=newrow['difference']['maxAbs'] or (stats['patchedMaxAbs']<=1e-4)!=newrow['numericGatePassed']:raise ValueError('record error reconstruction')
            fidelity=None
            if backend=='wasm' and case['inputOrigin']=='wasm_dec1_0':
                stored=buffer.read_tensor(case['originalFullGraphFirstGnOutput']);fidelity=x.tobytes()==stored.tobytes();full_fidelity.append(fidelity)
            records.append({'backend':backend,'contextOrdinal':ordinal,'candidateOrdinal':case['candidateOrdinal'],'inputOrigin':case['inputOrigin'],'candidateIdentity':case['candidateIdentity'],'originalOutput':original['output'],'patchedOutput':patched['output'],'ownFp64Reference':case['ownInputFp64Reference'],'statistics':stats,'originalWasmSameOriginFullGraphBitwiseIdentical':fidelity})
    summary={}
    for backend in scope['requiredBackends']:
        selected=[r['statistics'] for r in records if r['backend']==backend];original_max=max(r['originalMaxAbs'] for r in selected);patched_max=max(r['patchedMaxAbs'] for r in selected)
        summary[backend]={'contextCount':136,'originalMaxAbs':original_max,'patchedMaxAbs':patched_max,'ratioOfMaxima':original_max/patched_max if patched_max else None,'improvedContexts':sum(r['patchedMaxAbs']<r['originalMaxAbs'] for r in selected),'regressedContexts':sum(r['patchedMaxAbs']>r['originalMaxAbs'] for r in selected),'equalContexts':sum(r['patchedMaxAbs']==r['originalMaxAbs'] for r in selected),'patchedNumericGatePassed':all(r['patchedMaxAbs']<=1e-4 for r in selected)}
    if len(full_fidelity)!=68:raise ValueError('full original WASM same-origin fidelity denominator')
    return {'schemaVersion':1,'ok':True,'decision':'same_input_first_gn_real_operator_comparison_reconstructed','inputs':{'execution':d.bind(execution),'auditor':d.bind(__file__),'original':e['original'],'patched':e['patched'],'scope':e['scope']},'records':records,'summary':summary,'originalWasmSameOriginFullGraphFirstGnBitwiseIdentical':all(full_fidelity),'sameOriginFidelityCandidateCount':68,'bothStagesAll408OwnInputNumericGatesPassed':old['allOperatorNumericGatesPassed'] and new['allOperatorNumericGatesPassed'],'newModelCalls':0,'newTorchInputs':0,'optimizerSteps':0,'valInputs':0,'protectedInputs':0,'newChatImageInputs':0,'actualFirstGnOnlyFullModelRepairProven':False,'fullModelLearnedGatePassed':False,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    if a.verify_report:
        prior=d.read(d.bind(a.verify_report));result=reconstruct(d.checked(prior['inputs']['execution']))
        if result!=prior:raise ValueError('report reconstruction_mismatch')
    else:
        root=a.output.resolve();root.mkdir(exist_ok=False);result=reconstruct(a.execution.resolve());d.new(root/'report.json',result)
    print(json.dumps({k:result[k] for k in ('ok','decision','summary','originalWasmSameOriginFullGraphFirstGnBitwiseIdentical','bothStagesAll408OwnInputNumericGatesPassed','newModelCalls')}))
