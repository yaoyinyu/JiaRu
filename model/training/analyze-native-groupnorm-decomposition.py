"""同全候选GN64解析误差分解；不执行神经模型、不替换冻结CUDA参考。"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('gn_decomposition_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)

def read_tensor(ref):
    if ref['dtype'] not in ('float32','float64'):raise ValueError('explicit floating storage domain')
    path=d.checked({k:ref[k] for k in ('path','sha256')});dtype=np.dtype('<f4' if ref['dtype']=='float32' else '<f8')
    if any(not isinstance(n,int) or n<=0 for n in ref['shape']) or path.stat().st_size!=math.prod(ref['shape'])*dtype.itemsize:raise ValueError('native cardinality')
    a=np.fromfile(path,dtype).reshape(ref['shape'])
    if not np.isfinite(a).all():raise ValueError('all tensor elements finite')
    return a

def save64(path,a):
    if a.dtype!=np.float64 or not np.isfinite(a).all():raise ValueError('FP64 diagnostic finite storage')
    with path.open('xb') as f:f.write(a.astype('<f8',copy=False).tobytes());f.flush();os.fsync(f.fileno())
    return d.bind(path)|{'shape':list(a.shape),'dtype':'float64'}

def gn64(x,gamma,beta,groups,epsilon):
    if x.dtype!=np.float32 or x.ndim!=4 or not isinstance(groups,int) or groups<=0 or x.shape[1]%groups or gamma.dtype!=np.float32 or beta.dtype!=np.float32:raise ValueError('original F32 NCHW/group parameters')
    if gamma.shape!=(x.shape[1],1,1) or beta.shape!=gamma.shape or not np.isfinite(x).all() or not np.isfinite(gamma).all() or not np.isfinite(beta).all() or not math.isfinite(epsilon) or epsilon<=0:raise ValueError('original affine shape / finite epsilon')
    flat=x.astype(np.float64).reshape(x.shape[0],groups,-1);mean=flat.mean(axis=2,keepdims=True);centered=flat-mean;variance=np.square(centered).mean(axis=2,keepdims=True);std=np.sqrt(variance+epsilon)
    result=(centered/std).reshape(x.shape)*gamma.astype(np.float64)+beta.astype(np.float64)
    if not np.isfinite(result).all():raise ValueError('GN64 all finite')
    return result,{'dtype':'float64','elementsPerGroup':flat.shape[2],'mean':mean.tolist(),'centeredVariance':variance.tolist(),'std':std.tolist(),'epsilonFromOriginalFloat32':epsilon}

def decomposition(cx,cy,wx,wy,c64,w64,required_residual):
    if any(a.shape!=cx.shape for a in (cy,wx,wy,c64,w64)) or any(a.dtype!=np.float32 for a in (cx,cy,wx,wy)) or any(a.dtype!=np.float64 for a in (c64,w64)) or any(not np.isfinite(a).all() for a in (cx,cy,wx,wy,c64,w64)):raise ValueError('both domains, shapes and finite values')
    actual=wy.astype(np.float64)-cy.astype(np.float64);upstream=w64-c64;wasm_residual=wy.astype(np.float64)-w64;cuda_residual=cy.astype(np.float64)-c64;reconstructed=upstream+wasm_residual-cuda_residual;equation=float(np.max(np.abs(actual-reconstructed)))
    if equation>required_residual:raise ValueError('fixed FP64 equation residual failed')
    pos=tuple(int(i) for i in np.unravel_index(np.argmax(np.abs(actual)),actual.shape));at=lambda a:float(a[pos])
    return {'shape':list(cx.shape),'inputMaxAbs':float(np.max(np.abs(wx.astype(np.float64)-cx.astype(np.float64)))),'actualOutputMaxAbs':float(np.max(np.abs(actual))),'upstreamOutputMaxAbs':float(np.max(np.abs(upstream))),'wasmOwnRoundingMaxAbs':float(np.max(np.abs(wasm_residual))),'cudaOwnRoundingMaxAbs':float(np.max(np.abs(cuda_residual))),'roundingDifferenceMaxAbs':float(np.max(np.abs(wasm_residual-cuda_residual))),'hypotheticalExactGnOnWasmInputAgainstOriginalCudaMaxAbs':float(np.max(np.abs(w64-cy.astype(np.float64)))),'equationResidualMaxAbs':equation,'requiredEquationResidual':required_residual,'actualMaximumCoordinate':list(pos),'atActualMaximum':{'actual':at(actual),'upstream':at(upstream),'wasmOwnRounding':at(wasm_residual),'cudaOwnRounding':at(cuda_residual),'sum':at(reconstructed),'strictCudaOriginalOutput':at(cy),'wasmOriginalOutput':at(wy)},'hypotheticalResultIsNotDeployableOrRootCauseProof':True}

def validate_scope(p):
    if p['purpose']!='full68_readonly_groupnorm_fp64_upstream_and_own_rounding_decomposition' or p['fullCandidateCount']!=68 or len(p['cases'])!=68 or p['analyticalGroupNormEvaluationsAllowed']!=2*len(p['cases']):raise ValueError('full68 analytical budget')
    if p['requiredFp64EquationResidual']!=1e-12 or p['fullModelNumericDifferenceUnchanged']!=1e-4 or p['fullModelDecodedPixelDifferencesUnchanged']!=0 or p['formalReleaseAllowed']:raise ValueError('fixed quality / residual')
    for k in ('newFullModelInputsAllowed','newOnnxOperatorInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):
        if p[k]!=0:raise ValueError('no neural execution / role changes')
    for k in ('referenceCudaStorageUnchanged','all68OwnInputStatisticsAndOutputsRequired','statisticsAreDiagnosticOnlyNotDeploymentOrRootCauseProof','noReferenceReplacementOrEpsilonChange','oldFailuresAndConsumedBudgetsPreserved','productHold'):
        if p[k] is not True:raise ValueError('diagnostic guard '+k)
    if p['groupNorm']!={'groups':4,'channels':16,'epsilon':float(np.float32(1e-5)),'centeredVariance':True,'nativeChannelFirstOrder':True}:raise ValueError('original mathematical contract')

def resources(execution):
    e=d.read(d.bind(execution));d.checked(e['auditor']);d.checked(e['dataHelper'])
    if e['auditor']!=d.bind(__file__) or e['numpyVersion']!=np.__version__ or e['pythonVersion']!=sys.version:raise ValueError('frozen source / calculation runtime')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    trace=d.read(p['inputs']['trace']);control=d.read(p['inputs']['control']);parent=d.read(p['inputs']['parentScope']);analysis=d.read(p['inputs']['analysis']);old=d.read(p['inputs']['currentFullFailure']);inventory=d.read(p['inputs']['actualParameterInventory'])
    if not control['allOwnHeadsBitwiseIdenticalAllBackends'] or not trace['allOwnHeadsBitwiseIdenticalAllBackends'] or not trace['layerConclusionsAllowed'] or old['fullModelLearnedGatePassed'] or analysis['summary']['wasm']['firstCrossings'].get('dec1.4')!=[p['wasmFailureOrdinal']]:raise ValueError('all stage fidelity / preserve original failure')
    order=[(b,c['ordinal']) for b in ('cpu','wasm','webgpu') for c in parent['cases']]
    if [(r['backend'],r['ordinal']) for r in trace['records']]!=order or [(r['backend'],r['ordinal']) for r in old['records']]!=order:raise ValueError('all204 final parity order')
    for a,b in zip(trace['records'],old['records'],strict=True):
        if a['candidateIdentity']!=b['candidateIdentity'] or a['originalCudaParity']!=b['parity'] or not a['ownHeadsBitwiseIdentical']:raise ValueError('all final-head parity / identity')
    model=onnx.load(d.checked(p['model']));initializers={i.name:i for i in model.graph.initializer};nodes={n.output[0]:n for n in model.graph.node if len(n.output)==1};parameters={}
    add=nodes['/dec1/dec1.4/Add_output_0'];mul=nodes[add.input[0]]
    if add.op_type!='Add' or mul.op_type!='Mul' or [mul.input[1],add.input[1]]!=[p['parameterNames']['gamma'],p['parameterNames']['beta']]:raise ValueError('same affine source nodes')
    normalized=nodes['/dec1/dec1.4/InstanceNormalization_output_0'];sqrt=nodes[normalized.input[1]];epsilon_add=nodes[sqrt.input[0]]
    if normalized.op_type!='Div' or sqrt.op_type!='Sqrt' or epsilon_add.op_type!='Add' or epsilon_add.input[1]!=p['parameterNames']['epsilon']:raise ValueError('actual epsilon input chain')
    for key,name in p['parameterNames'].items():
        initializer=initializers[name];a=numpy_helper.to_array(initializer);stored=read_tensor(p['parameters'][key]);info=inventory['parameters'][key]
        if a.dtype!=np.float32 or a.shape!=stored.shape or a.tobytes()!=stored.tobytes() or hashlib.sha256(initializer.SerializeToString()).hexdigest()!=info['tensorProtoSha256'] or info['name']!=name:raise ValueError('original initializer and storage bytes')
        parameters[key]=stored
    if float(parameters['epsilon'][0])!=p['groupNorm']['epsilon']:raise ValueError('same epsilon bits')
    modules={r['module']:i for i,r in enumerate(parent['mapping'])};gn_layers={(r['backend'],r['ordinal']):r['layers'][modules['dec1.4']] for r in trace['layerRecords']}
    if [c['ordinal'] for c in p['cases']]!=list(range(1,len(p['cases'])+1)):raise ValueError('full native order')
    for c,original,cap in zip(p['cases'],parent['cases'],trace['captures']['wasm'],strict=True):
        if c['candidateIdentity']!=original['candidateIdentity'] or c['candidateIdentity']!=cap['candidateIdentity'] or c['candidateIdentity']['identity']['split']!='train':raise ValueError('original stable train identities')
        expected={'strictCudaInput':original['strictCudaLayers']['dec1.3'],'strictCudaOutput':original['strictCudaLayers']['dec1.4'],'wasmInput':cap['outputs'][f'layer{modules["dec1.3"]:02d}'],'wasmOutput':cap['outputs'][f'layer{modules["dec1.4"]:02d}']}
        if c['tensors']!=expected:raise ValueError('actual own-input/output provenance')
        for ref in c['tensors'].values():
            a=read_tensor(ref)
            if a.dtype!=np.float32 or a.shape[:2]!=(1,p['groupNorm']['channels']) or list(a.shape)!=c['tensors']['strictCudaInput']['shape']:raise ValueError('all original native finite F32')
    return e,p,parameters,gn_layers

def summarize(p,records):
    if len(records)!=len(p['cases']) or [r['ordinal'] for r in records]!=[c['ordinal'] for c in p['cases']]:raise ValueError('all cases before any summary')
    keys=['actualOutputMaxAbs','upstreamOutputMaxAbs','wasmOwnRoundingMaxAbs','cudaOwnRoundingMaxAbs','roundingDifferenceMaxAbs','hypotheticalExactGnOnWasmInputAgainstOriginalCudaMaxAbs','equationResidualMaxAbs']
    return {'candidateCount':len(records),'analyticalEvaluations':2*len(records),'maxima':{k:max(r['decomposition'][k] for r in records) for k in keys},'actualGnAboveFormalNumericDifference':[r['ordinal'] for r in records if r['decomposition']['actualOutputMaxAbs']>p['fullModelNumericDifferenceUnchanged']],'hypotheticalExactGnStillAboveFormalNumericDifference':[r['ordinal'] for r in records if r['decomposition']['hypotheticalExactGnOnWasmInputAgainstOriginalCudaMaxAbs']>p['fullModelNumericDifferenceUnchanged']],'requiredFp64EquationResidual':p['requiredFp64EquationResidual'],'allEquationResidualsPassed':all(r['decomposition']['equationResidualMaxAbs']<=p['requiredFp64EquationResidual'] for r in records),'failureCase':next(r for r in records if r['ordinal']==p['wasmFailureOrdinal']),'modelQualityOrRootCauseProven':False}

def execute(execution,root):
    if root.exists():raise ValueError('analytical scope consumed; readonly replay only')
    e,p,parameters,layers=resources(execution);root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'results').mkdir();records=[];started=0
    try:
        for c in p['cases']:
            arrays={k:read_tensor(ref) for k,ref in c['tensors'].items()};calculated={};stats={}
            for side,key in [('strictCuda','strictCudaInput'),('wasm','wasmInput')]:
                o=c['ordinal'];d.new(root/'events'/f'{o:03d}-{side}-start.json',{'ordinal':o,'side':side,'candidateIdentity':c['candidateIdentity'],'input':c['tensors'][key],'execution':d.bind(execution)});started+=1
                a,stats[side]=gn64(arrays[key],parameters['gamma'],parameters['beta'],p['groupNorm']['groups'],p['groupNorm']['epsilon']);calculated[side]=save64(root/'results'/f'{o:03d}-{side}-gn64.bin',a)
            result=decomposition(arrays['strictCudaInput'],arrays['strictCudaOutput'],arrays['wasmInput'],arrays['wasmOutput'],read_tensor(calculated['strictCuda']),read_tensor(calculated['wasm']),p['requiredFp64EquationResidual'])
            if result['actualOutputMaxAbs']!=layers[('wasm',c['ordinal'])]['maxAbs']:raise ValueError('original full layer reconstruction')
            record={'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'inputs':c['tensors'],'gn64':calculated,'statistics':stats,'decomposition':result};d.new(root/'results'/f'{c["ordinal"]:03d}-record.json',record);records.append(record)
        report=make_report(execution,root,p,records);d.new(root/'report.json',report);print(json.dumps({'ok':True,'summary':{k:v for k,v in report['summary'].items() if k!='failureCase'}}))
    except BaseException as error:
        d.new(root/'execution-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'execution':d.bind(execution),'analyticalEvaluationsStarted':started,'completeCandidateRecords':len(records),'newModelCalls':0,'formalReleaseAllowed':False,'productHold':True});raise

def make_report(execution,root,p,records):
    events=[d.bind(path) for path in sorted((root/'events').glob('*-start.json'))]
    return {'schemaVersion':1,'ok':True,'decision':'full68_fp64_groupnorm_error_decomposition_reconstructed','inputs':{'execution':d.bind(execution),'auditor':d.bind(__file__)},'records':records,'startEvents':events,'summary':summarize(p,records),'analyticalEvaluationsConsumed':2*len(records),'referenceCudaStorageUnchanged':True,'hypotheticalGn64CannotReplaceDeploymentOrCudaReference':True,'newModelCalls':0,'newTorchInputs':0,'newOnnxOperatorInputs':0,'optimizerSteps':0,'valInputs':0,'protectedInputs':0,'newChatImageInputs':0,'oldFailuresAndConsumedBudgetsPreserved':True,'fullModelLearnedGatePassed':False,'formalReleaseAllowed':False,'productHold':True}

def reconstruct(root):
    old=d.read(d.bind(root/'report.json'));execution=d.checked(old['inputs']['execution']);e,p,parameters,layers=resources(execution);records=[];expected_events=[]
    for c in p['cases']:
        record=d.read(d.bind(root/'results'/f'{c["ordinal"]:03d}-record.json'));arrays={k:read_tensor(ref) for k,ref in c['tensors'].items()};calculated={};stats={}
        for side,key in [('strictCuda','strictCudaInput'),('wasm','wasmInput')]:
            ev=root/'events'/f'{c["ordinal"]:03d}-{side}-start.json';expected_events.append(ev.name)
            if d.read(d.bind(ev))!={'ordinal':c['ordinal'],'side':side,'candidateIdentity':c['candidateIdentity'],'input':c['tensors'][key],'execution':d.bind(execution)}:raise ValueError('event identity')
            a,stats[side]=gn64(arrays[key],parameters['gamma'],parameters['beta'],p['groupNorm']['groups'],p['groupNorm']['epsilon']);stored=read_tensor(record['gn64'][side])
            if a.dtype!=stored.dtype or a.shape!=stored.shape or a.tobytes()!=stored.tobytes():raise ValueError('GN64 closed-form byte replay')
            calculated[side]=stored
        result=decomposition(arrays['strictCudaInput'],arrays['strictCudaOutput'],arrays['wasmInput'],arrays['wasmOutput'],calculated['strictCuda'],calculated['wasm'],p['requiredFp64EquationResidual'])
        expected={'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'inputs':c['tensors'],'gn64':record['gn64'],'statistics':stats,'decomposition':result}
        if record!=expected or result['actualOutputMaxAbs']!=layers[('wasm',c['ordinal'])]['maxAbs']:raise ValueError('full analytical record replay')
        records.append(expected)
    if sorted(x.name for x in (root/'events').glob('*-start.json'))!=sorted(expected_events) or len(list((root/'results').glob('*.bin')))!=p['analyticalGroupNormEvaluationsAllowed']:raise ValueError('whole event/tensor denominator')
    return make_report(execution,root,p,records)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execution',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-report',action='store_true');a=parser.parse_args();root=a.output.resolve()
    if a.verify_report:
        r=reconstruct(root)
        if r!=d.read(d.bind(root/'report.json')):raise ValueError('analytical reconstruction_mismatch')
        print(json.dumps({'ok':True,'replayedAnalyticalEvaluations':r['analyticalEvaluationsConsumed'],'newModelCalls':0,'fullModelLearnedGatePassed':False}))
    else:execute(a.execution.resolve(),root)
