"""四分支尾链FP64数学反事实；保留原参考，不批准实际部署修补。"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import numpy as np
import onnx
import scipy
import scipy.special
from onnx import numpy_helper
HERE=Path(__file__).resolve().parent
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load(HERE/'analyze-native-convolution-decomposition.py','tail_math_helper');g=h.g;d=h.d
comparator=load(HERE/'verify-native-multiscale-browser-v2.py','tail_comparator')
read_tensor=g.read_tensor

def runtime_binding():
    return h.runtime_binding()|{'scipyVersion':scipy.__version__,'erfModules':[d.bind(scipy.special._ufuncs.__file__),d.bind(scipy.special._special_ufuncs.__file__)]}

def gn64(x,gamma,beta,groups,epsilon):
    if x.dtype!=np.float64 or x.ndim!=4 or type(groups)!=int or groups<=0 or x.shape[1]%groups or gamma.dtype!=np.float32 or beta.dtype!=np.float32 or gamma.shape!=(x.shape[1],1,1) or beta.shape!=gamma.shape or not math.isfinite(epsilon) or epsilon<=0 or any(not np.isfinite(a).all() for a in (x,gamma,beta)):raise ValueError('frozen FP64 input and original F32 affine/epsilon')
    flat=x.reshape(x.shape[0],groups,-1);mean=flat.mean(axis=2,keepdims=True);centered=flat-mean;variance=np.square(centered).mean(axis=2,keepdims=True);std=np.sqrt(variance+epsilon)
    result=(centered/std).reshape(x.shape)*gamma.astype(np.float64)+beta.astype(np.float64)
    if not np.isfinite(result).all():raise ValueError('GN64 finite')
    return result,{'elementsPerGroup':flat.shape[2],'mean':mean.tolist(),'centeredVariance':variance.tolist(),'std':std.tolist(),'epsilonFromOriginalFloat32':epsilon,'inputStorageDomain':'float64'}

def gelu64(x,constants):
    if x.dtype!=np.float64 or not np.isfinite(x).all():raise ValueError('GELU64 finite domain')
    if constants['sqrt2FromOriginalFloat32']!=float(np.float32(np.sqrt(2))) or constants['oneFromOriginalFloat32']!=1. or constants['halfFromOriginalFloat32']!=.5:raise ValueError('original F32 GELU constant bits')
    result=(x*(constants['oneFromOriginalFloat32']+scipy.special.erf(x/constants['sqrt2FromOriginalFloat32'])))*constants['halfFromOriginalFloat32']
    if not np.isfinite(result).all():raise ValueError('GELU64 finite result')
    return result,{'originalFloat32ConstantsPromoted':True,'erfCalculation':'scipy.special.erf_float64'}

def delta64(x,weight,bias,maximum_pixels):
    if x.dtype!=np.float64 or x.ndim!=4 or weight.dtype!=np.float32 or weight.shape!=(1,x.shape[1],1,1) or bias.dtype!=np.float32 or bias.shape!=(1,) or type(maximum_pixels)!=int or not 1<=maximum_pixels<=4096 or any(not np.isfinite(a).all() for a in (x,weight,bias)):raise ValueError('original output head / FP64 input / bounded chunks')
    runtime_binding();n,c,height,width=x.shape;out=np.empty((n,1,height*width),np.float64);kernel=weight.astype(np.float64).reshape(c,1);chunks=0;covered=0
    for batch in range(n):
        flat=x[batch].reshape(c,-1)
        for start in range(0,height*width,maximum_pixels):
            end=min(start+maximum_pixels,height*width);out[batch,0,start:end]=(flat[:,start:end].T@kernel).reshape(-1)+float(bias[0]);chunks+=1;covered+=end-start
    if not np.isfinite(out).all() or covered!=n*height*width:raise ValueError('whole native delta finite')
    return out.reshape(n,1,height,width),{'chunks':chunks,'coveredOutputPixels':covered,'maximumOutputPixelsPerChunk':maximum_pixels,'realOriginalBiasUsed':True}

def seed32(candidate):
    if candidate.dtype!=np.float32 or candidate.ndim!=4 or candidate.shape[:2]!=(1,4) or not np.isfinite(candidate).all():raise ValueError('original native four-channel F32 input')
    return candidate[:,3:4]*np.float32(8)-np.float32(4)

def final_mask64(seed,delta):
    if seed.dtype!=np.float32 or delta.dtype!=np.float64 or seed.shape!=delta.shape or not np.isfinite(seed).all() or not np.isfinite(delta).all():raise ValueError('original seed / native delta domains')
    result=seed.astype(np.float64)+delta
    if not np.isfinite(result).all():raise ValueError('final F64 mask finite')
    return result,{'roundingBoundary':'float64 seed+delta then once to float32','originalSeedStorageDomain':'float32'}

def save(path,a):
    if a.dtype not in (np.float32,np.float64) or not np.isfinite(a).all():raise ValueError('finite explicit storage')
    dtype='<f4' if a.dtype==np.float32 else '<f8'
    with path.open('xb') as f:f.write(a.astype(dtype,copy=False).tobytes());f.flush();os.fsync(f.fileno())
    return d.bind(path)|{'shape':list(a.shape),'dtype':'float32' if a.dtype==np.float32 else 'float64'}

def validate_scope(p):
    count=len(p['cases']);budgets={'newGroupNorm64':2*count,'newGelu64':4*count,'newDelta64':4*count,'newFinalMaskAdd64':4*count,'total':14*count}
    if p['purpose']!='full68_four_branch_tail_mathematical_counterfactual_not_deployment' or p['fullCandidateCount']!=count or count!=68 or p['branchCandidateCount']!=4*count or p['analyticalEvaluationsAllowed']!=budgets or p['inheritedGn64Results']!=2*count:raise ValueError('full frozen four-branch denominator')
    if p['branches']!=['wasm_actual_conv','wasm_conv64','cuda_actual_conv','cuda_conv64'] or p['requiredNumericDifferenceUnchanged']!=1e-4 or p['requiredDecodedPixelDifferencesUnchanged']!=0 or p['requiredPresenceDecisionDifferencesUnchanged']!=0 or p['maximumOutputPixelsPerChunk']!=4096 or p['numpyBlasThreadsRequired']!=1:raise ValueError('original quality / full native chunk / branch order')
    for k in ('newFullModelInputsAllowed','newOnnxOperatorInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):
        if p[k]!=0:raise ValueError('no neural execution / protected inputs')
    for k in ('allOriginalMaskSeedPlusDeltaByteFidelityRequired','compareOnlyOriginalStrictCudaReference','mathematicalCounterfactualCannotProveActualFp32RepairOrFullModelUnreachable','originalParametersConstantsReferencesRolesAndFailuresPreserved','productHold'):
        if p[k] is not True:raise ValueError('diagnostic guard '+k)
    if p['formalReleaseAllowed'] or p['fullModelLearnedGatePassed']:raise ValueError('HOLD preserved')

def resources(execution):
    e=d.read(d.bind(execution))
    for ref in e['sources'].values():d.checked(ref)
    if e['sources']['auditor']!=d.bind(__file__) or e['runtime']!=runtime_binding():raise ValueError('frozen source / runtime')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    model=onnx.load(d.checked(p['model']));nodes={n.name:n for n in model.graph.node};initializers={i.name:i for i in model.graph.initializer}
    for bound in p['tailNodeBindings']:
        n=nodes[bound['name']]
        if hashlib.sha256(n.SerializeToString()).hexdigest()!=bound['nodeProtoSha256'] or list(n.input)!=bound['inputs'] or list(n.output)!=bound['outputs'] or n.op_type!=bound['opType']:raise ValueError('actual tail node bytes')
    gn_scope=d.read(p['inputs']['gnScope']);names=gn_scope['parameterNames']|{'deltaWeight':'delta.weight','deltaBias':'delta.bias'};parameters={}
    for key,ref in p['parameters'].items():
        a=read_tensor(ref);original=numpy_helper.to_array(initializers[names[key]])
        if a.dtype!=np.float32 or original.dtype!=a.dtype or original.shape!=a.shape or original.tobytes()!=a.tobytes():raise ValueError('all original tail parameter bytes')
        parameters[key]=a
    if p['groupNorm']!=gn_scope['groupNorm'] or float(parameters['epsilon'][0])!=p['groupNorm']['epsilon']:raise ValueError('same group / epsilon')
    conv=d.read(p['inputs']['convDecomposition']);gn=d.read(p['inputs']['gnDecomposition']);trace=d.read(p['inputs']['trace']);full=d.read(p['inputs']['originalFullScope']);old=d.read(p['inputs']['originalFullFailure'])
    if not conv['ok'] or not gn['ok'] or not trace['allOwnHeadsBitwiseIdenticalAllBackends'] or not trace['layerConclusionsAllowed'] or old['fullModelLearnedGatePassed'] or old['summary']['wasm']['failedOrdinals']!=[40]:raise ValueError('original full fidelity / failure preserved')
    if [c['ordinal'] for c in p['cases']]!=list(range(1,69)) or len(conv['records'])!=68 or len(gn['records'])!=68 or len(full['cases'])!=68:raise ValueError('all original candidates')
    for c,cr,gr,fc in zip(p['cases'],conv['records'],gn['records'],full['cases'],strict=True):
        if c['candidateIdentity']!=cr['candidateIdentity'] or c['candidateIdentity']!=gr['candidateIdentity'] or c['candidateIdentity']!=fc['candidateIdentity'] or c['candidateIdentity']['identity']['split']!='train' or list(c['branches'])!=p['branches']:raise ValueError('stable native train identities / branches')
        expected={'wasm_actual_conv':{'originalConvOutput':cr['inputs']['wasmOutput'],'inheritedGn64':gr['gn64']['wasm'],'presence':c['originalWasmHeads']['presence']},'wasm_conv64':{'conv64':cr['conv64']['wasm'],'presence':c['originalWasmHeads']['presence']},'cuda_actual_conv':{'originalConvOutput':cr['inputs']['strictCudaOutput'],'inheritedGn64':gr['gn64']['strictCuda'],'presence':c['originalCudaHeads']['presence']},'cuda_conv64':{'conv64':cr['conv64']['strictCuda'],'presence':c['originalCudaHeads']['presence']}}
        if c['branches']!=expected or c['candidateInput']!=fc['input'] or c['originalCudaHeads']!=fc['references']['learned']:raise ValueError('existing computation provenance / strict reference')
        seed=seed32(read_tensor(c['candidateInput']))
        for delta_ref,heads in [(c['originalCudaDelta'],c['originalCudaHeads']),(c['originalWasmDelta'],c['originalWasmHeads'])]:
            stored=read_tensor(heads['mask']);actual=seed+read_tensor(delta_ref)
            if actual.dtype!=stored.dtype or actual.shape!=stored.shape or actual.tobytes()!=stored.tobytes():raise ValueError('original final mask seed+delta bitwise fidelity')
            read_tensor(heads['presence'])
        for branch in c['branches'].values():
            for ref in branch.values():read_tensor(ref)
    return e,p,parameters

def stage_event(execution,c,branch,stage,inputs):
    return {'ordinal':c['ordinal'],'branch':branch,'stage':stage,'candidateIdentity':c['candidateIdentity'],'execution':d.bind(execution),'inputs':inputs}

def evaluate_case(c,p,parameters,run):
    seed=seed32(read_tensor(c['candidateInput']));references={k:read_tensor(ref) for k,ref in c['originalCudaHeads'].items()};records=[]
    for branch,inputs in c['branches'].items():
        if 'inheritedGn64' in inputs:gn=inputs['inheritedGn64'];gn_stats={'inheritedOriginalGn64':True}
        else:
            fn=lambda:gn64(read_tensor(inputs['conv64']),parameters['gamma'],parameters['beta'],p['groupNorm']['groups'],p['groupNorm']['epsilon'])
            gn,gn_stats=run(branch,'gn64',{'conv64':inputs['conv64']},fn)
        gelu,gelu_stats=run(branch,'gelu64',{'gn64':gn},lambda:gelu64(read_tensor(gn),p['gelu']))
        delta,delta_stats=run(branch,'delta64',{'gelu64':gelu},lambda:delta64(read_tensor(gelu),parameters['deltaWeight'],parameters['deltaBias'],p['maximumOutputPixelsPerChunk']))
        mask,mask_stats=run(branch,'mask64',{'delta64':delta,'candidateInput':c['candidateInput']},lambda:final_mask64(seed,read_tensor(delta)))
        mask32,round_stats=run(branch,'mask32',{'mask64':mask},lambda:(read_tensor(mask).astype(np.float32),{'singleFinalFloat32Rounding':True}))
        array=read_tensor(mask32);presence=read_tensor(inputs['presence']);height,width=array.shape[2:]
        parity=comparator.compare_outputs(references['mask'].reshape(-1),references['presence'].reshape(-1),array.reshape(-1),presence.reshape(-1),height,width)
        delta_error=float(np.abs(read_tensor(delta)-read_tensor(c['originalCudaDelta']).astype(np.float64)).max())
        records.append({'branch':branch,'gn64':gn,'gelu64':gelu,'delta64':delta,'mask64':mask,'mask32':mask32,'presence':inputs['presence'],'statistics':{'gn64':gn_stats,'gelu64':gelu_stats,'delta64':delta_stats,'mask64':mask_stats,'mask32':round_stats},'originalCudaParity':parity,'counterfactualNumericPixelAndPresenceGatesPassed':all(parity[k] for k in ('numericGatePassed','decodedPixelGatePassed','presenceDecisionMatched','allReferenceAndCapturedHeadsFinite')),'delta64AgainstOriginalCudaMaxAbs':delta_error,'actualFp32RepairProven':False})
    return {'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'branches':records}

def summarize(p,records):
    if [r['ordinal'] for r in records]!=[c['ordinal'] for c in p['cases']]:raise ValueError('all cases before counterfactual conclusions')
    summary={}
    for name in p['branches']:
        rows=[next(b for b in r['branches'] if b['branch']==name) for r in records]
        if len(rows)!=p['fullCandidateCount']:raise ValueError('full branch denominator')
        summary[name]={'candidateCount':len(rows),'maxAbs':max(r['originalCudaParity']['maxAbsoluteDifference'] for r in rows),'failedOrdinals':[record['ordinal'] for record,row in zip(records,rows,strict=True) if not row['counterfactualNumericPixelAndPresenceGatesPassed']],'decodedPixelDifferences':sum(r['originalCudaParity']['decodedMaskPixelDifference'] for r in rows),'presenceFailed':sum(not r['originalCudaParity']['presenceDecisionMatched'] for r in rows),'delta64AgainstOriginalCudaMaxAbs':max(r['delta64AgainstOriginalCudaMaxAbs'] for r in rows),'actualFp32RepairProven':False}
    return summary

def make_report(execution,root,p,records):
    return {'schemaVersion':1,'ok':True,'decision':'full68_four_branch_tail_counterfactual_reconstructed_diagnostic_only','inputs':{'execution':d.bind(execution),'auditor':d.bind(__file__)},'records':records,'summary':summarize(p,records),'startEvents':[d.bind(x) for x in sorted((root/'events').glob('*.json'))],'analyticalEvaluationsConsumed':p['analyticalEvaluationsAllowed'],'inheritedGn64Results':p['inheritedGn64Results'],'candidateCount':len(records),'branchCandidateCount':len(records)*4,'originalFinalHeadByteFidelityPreserved':True,'actualFp32RepairOrWholeModelUnreachableProven':False,'newModelCalls':0,'newTorchInputs':0,'newOnnxOperatorInputs':0,'optimizerSteps':0,'valInputs':0,'protectedInputs':0,'newChatImageInputs':0,'oldFailuresAndConsumedBudgetsPreserved':True,'fullModelLearnedGatePassed':False,'formalReleaseAllowed':False,'productHold':True}

def execute(execution,root):
    if root.exists():raise ValueError('mathematical budget consumed; readonly replay only')
    e,p,parameters=resources(execution)
    if e['outputRoot']!=str(root):raise ValueError('frozen exclusive output root')
    root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'results').mkdir();records=[];started=0
    try:
        for c in p['cases']:
            def run(branch,stage,inputs,fn):
                nonlocal started
                stem=f'{c["ordinal"]:03d}-{branch}-{stage}'
                if stage!='mask32':d.new(root/'events'/(stem+'-start.json'),stage_event(execution,c,branch,stage,inputs));started+=1
                a,stats=fn();return save(root/'results'/(stem+'.bin'),a),stats
            record=evaluate_case(c,p,parameters,run);d.new(root/'results'/f'{c["ordinal"]:03d}-record.json',record);records.append(record)
            print(json.dumps({'ordinal':c['ordinal'],'newMathematicalStagesCompleted':len(records)*14}),flush=True)
        report=make_report(execution,root,p,records);d.new(root/'report.json',report);print(json.dumps({'ok':True,'summary':report['summary']}))
    except BaseException as err:
        d.new(root/'execution-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(err),'execution':d.bind(execution),'analyticalStagesStarted':started,'completeCandidateRecords':len(records),'newModelCalls':0,'formalReleaseAllowed':False,'productHold':True});raise

def reconstruct(root):
    old=d.read(d.bind(root/'report.json'));execution=d.checked(old['inputs']['execution']);e,p,parameters=resources(execution);records=[];expected_events=[]
    for c in p['cases']:
        def run(branch,stage,inputs,fn):
            stem=f'{c["ordinal"]:03d}-{branch}-{stage}'
            if stage!='mask32':
                event=root/'events'/(stem+'-start.json');expected_events.append(event.name)
                if d.read(d.bind(event))!=stage_event(execution,c,branch,stage,inputs):raise ValueError('exact stage event identity')
            a,stats=fn();ref=d.bind(root/'results'/(stem+'.bin'))|{'dtype':'float32' if stage=='mask32' else 'float64','shape':list(a.shape)};stored=read_tensor(ref)
            if a.dtype!=stored.dtype or a.tobytes()!=stored.tobytes():raise ValueError('mathematical stage byte replay')
            return ref,stats
        record=evaluate_case(c,p,parameters,run)
        if record!=d.read(d.bind(root/'results'/f'{c["ordinal"]:03d}-record.json')):raise ValueError('full counterfactual record replay')
        records.append(record)
    if sorted(x.name for x in (root/'events').glob('*.json'))!=sorted(expected_events) or len(expected_events)!=p['analyticalEvaluationsAllowed']['total'] or len(list((root/'results').glob('*.bin')))!=18*len(p['cases']):raise ValueError('complete stage/raw denominator')
    return make_report(execution,root,p,records)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execution',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-report',action='store_true');a=parser.parse_args();root=a.output.resolve()
    if a.verify_report:
        r=reconstruct(root)
        if r!=d.read(d.bind(root/'report.json')):raise ValueError('counterfactual reconstruction_mismatch')
        print(json.dumps({'ok':True,'replayedMathematicalStages':r['analyticalEvaluationsConsumed']['total'],'newModelCalls':0,'fullModelLearnedGatePassed':False}))
    else:execute(a.execution.resolve(),root)
