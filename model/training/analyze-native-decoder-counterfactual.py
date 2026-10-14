"""从原dec1.0输出开始的双分支解码尾链数学诊断。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('decoder_tail_helper',HERE/'analyze-native-tail-counterfactual.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
d=t.d;read_tensor=t.read_tensor;runtime_binding=t.runtime_binding

def conv64(x,weight,maximum_pixels):
    if x.dtype!=np.float64 or x.ndim!=4 or weight.dtype!=np.float32 or weight.ndim!=4 or weight.shape[1]!=x.shape[1] or weight.shape[2:]!=(3,3) or type(maximum_pixels)!=int or not 1<=maximum_pixels<=4096 or not np.isfinite(x).all() or not np.isfinite(weight).all():raise ValueError('FP64 propagated input / original F32 kernel / bounded chunks')
    runtime_binding();n,c,h,w=x.shape
    if min(n,c,h,w,weight.shape[0])<=0:raise ValueError('positive native dimensions')
    padded=np.pad(x,((0,0),(0,0),(1,1),(1,1)),mode='constant');windows=np.lib.stride_tricks.sliding_window_view(padded,(3,3),axis=(2,3));kernel=weight.astype(np.float64).reshape(weight.shape[0],-1).T
    out=np.empty((n,weight.shape[0],h*w),np.float64);covered=0;chunks=0
    for batch in range(n):
        for start in range(0,h*w,maximum_pixels):
            end=min(start+maximum_pixels,h*w);positions=np.arange(start,end);patches=windows[batch,:,positions//w,positions%w,:,:]
            out[batch,:,start:end]=(patches.reshape(end-start,c*9)@kernel).T;covered+=end-start;chunks+=1
    if covered!=n*h*w or not np.isfinite(out).all():raise ValueError('whole original convolution coverage')
    return out.reshape(n,weight.shape[0],h,w),{'inputStorageDomain':'float64','originalKernelStorageDomain':'float32','biasPresent':False,'coveredOutputPixelsPerChannel':covered,'chunks':chunks,'maximumOutputPixelsPerChunk':maximum_pixels,'wholeNativeOutputCovered':True}

def validate_scope(p):
    count=len(p['cases']);stages=('firstGn64','firstGelu64','conv64','lastGn64','lastGelu64','delta64','finalMaskAdd64')
    if p['purpose']!='full68_two_branch_whole_last_decoder_fp64_counterfactual_not_deployment' or count!=68 or p['fullCandidateCount']!=count or p['branchCandidateCount']!=2*count or p['analyticalEvaluationsAllowed']!={k:2*count for k in stages}|{'total':14*count} or p['branches']!=['wasm_dec1_0','cuda_dec1_0']:raise ValueError('full frozen two-branch denominator')
    if p['requiredNumericDifferenceUnchanged']!=1e-4 or p['requiredDecodedPixelDifferencesUnchanged']!=0 or p['requiredPresenceDecisionDifferencesUnchanged']!=0 or p['maximumOutputPixelsPerChunk']!=4096 or p['numpyBlasThreadsRequired']!=1:raise ValueError('fixed original quality and native chunks')
    for k in ('newFullModelInputsAllowed','newOnnxOperatorInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):
        if p[k]!=0:raise ValueError('no neural/protected execution')
    for k in ('allOriginalReferencesAndParametersUnchanged','actualFp32RepairOrWholeModelUnreachableCannotBeProvenByMath','oldFailuresAndConsumedBudgetsPreserved','productHold'):
        if p[k] is not True:raise ValueError('diagnostic guard '+k)
    if p['fullModelLearnedGatePassed'] or p['formalReleaseAllowed']:raise ValueError('HOLD preserved')

def resources(execution):
    e=d.read(d.bind(execution))
    for ref in e['sources'].values():d.checked(ref)
    if e['sources']['auditor']!=d.bind(__file__) or e['runtime']!=runtime_binding():raise ValueError('frozen source and runtime')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    model=onnx.load(d.checked(p['model']));nodes={n.name:n for n in model.graph.node};outputs={o:n for n in model.graph.node for o in n.output};initializers={i.name:i for i in model.graph.initializer}
    for bound in p['nodeBindings']:
        n=nodes[bound['name']]
        if hashlib.sha256(n.SerializeToString()).hexdigest()!=bound['nodeProtoSha256'] or list(n.input)!=bound['inputs'] or list(n.output)!=bound['outputs'] or n.op_type!=bound['opType']:raise ValueError('actual original semantic node bytes')
    previous=d.read(p['inputs']['previousTailScope']);gnscope=d.read(previous['inputs']['gnScope']);parameters={}
    for key,ref in p['parameters'].items():
        name=ref.get('initializerName') or gnscope['parameterNames'][key];a=read_tensor(ref);initializer=initializers[name];original=numpy_helper.to_array(initializer)
        if a.dtype!=np.float32 or a.shape!=original.shape or a.tobytes()!=original.tobytes() or ('tensorProtoSha256' in ref and ref['tensorProtoSha256']!=hashlib.sha256(initializer.SerializeToString()).hexdigest()):raise ValueError('original initializer / stored parameter bytes')
        parameters[key]=a
    for prefix,config,key in [('dec1.1',p['firstGroupNorm'],'firstEpsilon'),('dec1.4',p['lastGroupNorm'],'epsilon')]:
        reshape=nodes[f'/dec1/{prefix}/Reshape'];constant=outputs[reshape.input[1]]
        if numpy_helper.to_array(constant.attribute[0].t).tolist()!=[0,4,-1] or config!={'groups':4,'channels':16,'epsilon':float(parameters[key][0]),'centeredVariance':True,'nativeChannelFirstOrder':True}:raise ValueError('actual original four-group normalization')
    if parameters['convWeight'].shape!=(16,16,3,3) or len(nodes['/dec1/dec1.3/Conv'].input)!=2:raise ValueError('original no-bias middle convolution')
    parent=d.read(p['inputs']['parentScope']);trace=d.read(p['inputs']['trace']);full=d.read(p['inputs']['originalFullScope']);old=d.read(p['inputs']['originalFullFailure']);tail=d.read(p['inputs']['currentTailCounterfactual'])
    if not trace['layerConclusionsAllowed'] or not trace['allOwnHeadsBitwiseIdenticalAllBackends'] or old['fullModelLearnedGatePassed'] or old['summary']['wasm']['failedOrdinals']!=[40] or not tail['ok'] or any(tail['summary'][b]['failedOrdinals']!=[40] for b in ('wasm_actual_conv','wasm_conv64')):raise ValueError('original full fidelity and failure')
    modules={r['module']:i for i,r in enumerate(parent['mapping'])}
    if [c['ordinal'] for c in p['cases']]!=list(range(1,69)):raise ValueError('all original native candidates')
    for c,original,cap,fc,prev in zip(p['cases'],parent['cases'],trace['captures']['wasm'],full['cases'],previous['cases'],strict=True):
        if any(c['candidateIdentity']!=r['candidateIdentity'] for r in (original,cap,fc,prev)) or c['candidateIdentity']['identity']['split']!='train' or c['candidateInput']!=fc['input'] or c['originalCudaHeads']!=fc['references']['learned'] or c['originalWasmHeads']!=prev['originalWasmHeads']:raise ValueError('stable original train identities / final references')
        expected={'wasm_dec1_0':{'firstGnInput':cap['outputs'][f'layer{modules["dec1.0"]:02d}'],'presence':c['originalWasmHeads']['presence']},'cuda_dec1_0':{'firstGnInput':original['strictCudaLayers']['dec1.0'],'presence':c['originalCudaHeads']['presence']}}
        if c['branches']!=expected:raise ValueError('actual precise starting boundary')
        seed=t.seed32(read_tensor(c['candidateInput']))
        for delta,heads in [(c['originalCudaDelta'],c['originalCudaHeads']),(c['originalWasmDelta'],c['originalWasmHeads'])]:
            a=seed+read_tensor(delta);b=read_tensor(heads['mask'])
            if a.dtype!=b.dtype or a.shape!=b.shape or a.tobytes()!=b.tobytes():raise ValueError('original final head byte fidelity')
            read_tensor(heads['presence'])
        for b in c['branches'].values():
            a=read_tensor(b['firstGnInput']);read_tensor(b['presence'])
            if a.dtype!=np.float32 or a.shape[:2]!=(1,16) or a.shape[2:]!=seed.shape[2:]:raise ValueError('native complete first input')
    return e,p,parameters

def evaluate_case(c,p,parameters,run):
    seed=t.seed32(read_tensor(c['candidateInput']));refs={k:read_tensor(r) for k,r in c['originalCudaHeads'].items()};records=[]
    for branch,inputs in c['branches'].items():
        first,first_stats=run(branch,'firstGn64',{'firstGnInput':inputs['firstGnInput']},lambda:t.gn64(read_tensor(inputs['firstGnInput']).astype(np.float64),parameters['firstGamma'],parameters['firstBeta'],p['firstGroupNorm']['groups'],p['firstGroupNorm']['epsilon']))
        fg,fg_stats=run(branch,'firstGelu64',{'firstGn64':first},lambda:t.gelu64(read_tensor(first),p['gelu']))
        conv,conv_stats=run(branch,'conv64',{'firstGelu64':fg},lambda:conv64(read_tensor(fg),parameters['convWeight'],p['maximumOutputPixelsPerChunk']))
        last,last_stats=run(branch,'lastGn64',{'conv64':conv},lambda:t.gn64(read_tensor(conv),parameters['gamma'],parameters['beta'],p['lastGroupNorm']['groups'],p['lastGroupNorm']['epsilon']))
        lg,lg_stats=run(branch,'lastGelu64',{'lastGn64':last},lambda:t.gelu64(read_tensor(last),p['gelu']))
        delta,delta_stats=run(branch,'delta64',{'lastGelu64':lg},lambda:t.delta64(read_tensor(lg),parameters['deltaWeight'],parameters['deltaBias'],p['maximumOutputPixelsPerChunk']))
        mask,mask_stats=run(branch,'finalMaskAdd64',{'delta64':delta,'candidateInput':c['candidateInput']},lambda:t.final_mask64(seed,read_tensor(delta)))
        rounded,round_stats=run(branch,'mask32',{'mask64':mask},lambda:(read_tensor(mask).astype(np.float32),{'singleFinalFloat32Rounding':True}))
        a=read_tensor(rounded);presence=read_tensor(inputs['presence']);height,width=a.shape[2:];parity=t.comparator.compare_outputs(refs['mask'].reshape(-1),refs['presence'].reshape(-1),a.reshape(-1),presence.reshape(-1),height,width)
        delta_error=float(np.abs(read_tensor(delta)-read_tensor(c['originalCudaDelta']).astype(np.float64)).max())
        records.append({'branch':branch,'firstGn64':first,'firstGelu64':fg,'conv64':conv,'lastGn64':last,'lastGelu64':lg,'delta64':delta,'mask64':mask,'mask32':rounded,'presence':inputs['presence'],'statistics':{'firstGn64':first_stats,'firstGelu64':fg_stats,'conv64':conv_stats,'lastGn64':last_stats,'lastGelu64':lg_stats,'delta64':delta_stats,'mask64':mask_stats,'mask32':round_stats},'originalCudaParity':parity,'counterfactualNumericPixelAndPresenceGatesPassed':all(parity[k] for k in ('numericGatePassed','decodedPixelGatePassed','presenceDecisionMatched','allReferenceAndCapturedHeadsFinite')),'delta64AgainstOriginalCudaMaxAbs':delta_error,'actualFp32RepairProven':False})
    return {'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'branches':records}

def make_report(execution,root,p,records):
    return {'schemaVersion':1,'ok':True,'decision':'full68_two_branch_decoder_counterfactual_reconstructed_diagnostic_only','inputs':{'execution':d.bind(execution),'auditor':d.bind(__file__)},'records':records,'summary':t.summarize(p,records),'startEvents':[d.bind(x) for x in sorted((root/'events').glob('*.json'))],'analyticalEvaluationsConsumed':p['analyticalEvaluationsAllowed'],'candidateCount':len(records),'branchCandidateCount':len(records)*2,'preciseStartingBoundary':'actual captured dec1.0 output','originalFinalHeadByteFidelityPreserved':True,'actualFp32RepairOrWholeModelUnreachableProven':False,'newModelCalls':0,'newTorchInputs':0,'newOnnxOperatorInputs':0,'optimizerSteps':0,'valInputs':0,'protectedInputs':0,'newChatImageInputs':0,'oldFailuresAndConsumedBudgetsPreserved':True,'fullModelLearnedGatePassed':False,'formalReleaseAllowed':False,'productHold':True}

def execute(execution,root):
    if root.exists():raise ValueError('mathematical budget consumed; readonly replay only')
    e,p,parameters=resources(execution)
    if e['outputRoot']!=str(root):raise ValueError('frozen exclusive root')
    root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'results').mkdir();records=[];started=0
    try:
        for c in p['cases']:
            def run(branch,stage,inputs,fn):
                nonlocal started
                stem=f'{c["ordinal"]:03d}-{branch}-{stage}'
                if stage!='mask32':d.new(root/'events'/(stem+'-start.json'),t.stage_event(execution,c,branch,stage,inputs));started+=1
                a,stats=fn();return t.save(root/'results'/(stem+'.bin'),a),stats
            record=evaluate_case(c,p,parameters,run);d.new(root/'results'/f'{c["ordinal"]:03d}-record.json',record);records.append(record);print(json.dumps({'ordinal':c['ordinal'],'newMathematicalStagesCompleted':len(records)*14}),flush=True)
        report=make_report(execution,root,p,records);d.new(root/'report.json',report);print(json.dumps({'ok':True,'summary':report['summary']}))
    except BaseException as err:
        d.new(root/'execution-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(err),'execution':d.bind(execution),'analyticalStagesStarted':started,'completeCandidateRecords':len(records),'newModelCalls':0,'formalReleaseAllowed':False,'productHold':True});raise

def reconstruct(root):
    old=d.read(d.bind(root/'report.json'));execution=d.checked(old['inputs']['execution']);e,p,parameters=resources(execution);records=[];events=[]
    for c in p['cases']:
        def run(branch,stage,inputs,fn):
            stem=f'{c["ordinal"]:03d}-{branch}-{stage}'
            if stage!='mask32':
                event=root/'events'/(stem+'-start.json');events.append(event.name)
                if d.read(d.bind(event))!=t.stage_event(execution,c,branch,stage,inputs):raise ValueError('exact stage event identity')
            a,stats=fn();ref=d.bind(root/'results'/(stem+'.bin'))|{'dtype':'float32' if stage=='mask32' else 'float64','shape':list(a.shape)};stored=read_tensor(ref)
            if stored.dtype!=a.dtype or stored.tobytes()!=a.tobytes():raise ValueError('mathematical stage byte replay')
            return ref,stats
        record=evaluate_case(c,p,parameters,run)
        if record!=d.read(d.bind(root/'results'/f'{c["ordinal"]:03d}-record.json')):raise ValueError('full decoder record replay')
        records.append(record)
    if sorted(x.name for x in (root/'events').glob('*.json'))!=sorted(events) or len(events)!=p['analyticalEvaluationsAllowed']['total'] or len(list((root/'results').glob('*.bin')))!=16*len(p['cases']):raise ValueError('complete event/raw denominator')
    return make_report(execution,root,p,records)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execution',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-report',action='store_true');a=parser.parse_args();root=a.output.resolve()
    if a.verify_report:
        r=reconstruct(root)
        if r!=d.read(d.bind(root/'report.json')):raise ValueError('decoder reconstruction_mismatch')
        print(json.dumps({'ok':True,'replayedMathematicalStages':r['analyticalEvaluationsConsumed']['total'],'newModelCalls':0,'fullModelLearnedGatePassed':False}))
    else:execute(a.execution.resolve(),root)
