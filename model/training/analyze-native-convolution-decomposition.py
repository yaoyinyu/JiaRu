"""原尺寸卷积FP64误差分解；仅数学诊断，不执行神经运行时。"""
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
import threadpoolctl
from onnx import numpy_helper

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('conv_math_helper',HERE/'analyze-native-groupnorm-decomposition.py')
g=importlib.util.module_from_spec(s);s.loader.exec_module(g);d=g.d
read_tensor=g.read_tensor;save64=g.save64

def runtime_binding():
    pools=threadpoolctl.threadpool_info()
    if not pools or any(p['user_api']!='blas' or p['num_threads']!=1 for p in pools):raise ValueError('frozen single-thread BLAS required')
    libraries=[]
    for p in pools:
        libraries.append({k:v for k,v in p.items() if k!='filepath'}|{'library':d.bind(p['filepath'])})
    return {'numpyVersion':np.__version__,'pythonVersion':sys.version,'threadpoolctlVersion':threadpoolctl.__version__,'blas':libraries}

def conv64(x,weight,maximum_pixels):
    if x.dtype!=np.float32 or weight.dtype!=np.float32 or x.ndim!=4 or weight.ndim!=4 or weight.shape[1]!=x.shape[1] or weight.shape[2:]!=(3,3):raise ValueError('original F32 NCHW kernel / absent bias')
    if type(maximum_pixels)!=int or maximum_pixels<1 or maximum_pixels>4096 or not np.isfinite(x).all() or not np.isfinite(weight).all():raise ValueError('finite native input / fixed chunk bound')
    runtime_binding()
    n,c,h,w=x.shape;out_channels=weight.shape[0]
    if min(n,c,h,w,out_channels)<=0:raise ValueError('positive native dimensions')
    padded=np.pad(x.astype(np.float64),((0,0),(0,0),(1,1),(1,1)),mode='constant')
    windows=np.lib.stride_tricks.sliding_window_view(padded,(3,3),axis=(2,3))
    kernel=weight.astype(np.float64).reshape(out_channels,-1).T
    out=np.empty((n,out_channels,h*w),dtype=np.float64);chunks=0;covered=0
    for batch in range(n):
        for start in range(0,h*w,maximum_pixels):
            end=min(start+maximum_pixels,h*w);positions=np.arange(start,end)
            # 原NCHW通道、行、列核序；分块仅限制临时矩阵，保留全图零填充邻域。
            patches=windows[batch,:,positions//w,positions%w,:,:]
            matrix=patches.reshape(end-start,c*9)
            out[batch,:,start:end]=(matrix@kernel).T;chunks+=1;covered+=end-start
    result=out.reshape(n,out_channels,h,w)
    if covered!=n*h*w or not np.isfinite(result).all():raise ValueError('whole original output coverage / finite')
    return result,{'dtype':'float64','inputShape':list(x.shape),'outputShape':list(result.shape),'kernelShape':list(weight.shape),'biasPresent':False,'padding':[1,1,1,1],'stride':[1,1],'dilation':[1,1],'chunks':chunks,'coveredOutputPixelsPerChannel':covered,'maximumOutputPixelsPerChunk':maximum_pixels,'wholeNativeOutputCovered':True}

def decomposition(cx,cy,wx,wy,c64,w64,residual):
    result=g.decomposition(cx,cy,wx,wy,c64,w64,residual)
    result['hypotheticalExactConvOnWasmInputAgainstOriginalCudaMaxAbs']=result.pop('hypotheticalExactGnOnWasmInputAgainstOriginalCudaMaxAbs')
    return result

def validate_scope(p):
    if p['purpose']!='full68_readonly_tail_conv_fp64_upstream_and_own_rounding_decomposition' or p['fullCandidateCount']!=len(p['cases']) or not p['cases'] or p['analyticalConvolutionEvaluationsAllowed']!=2*len(p['cases']):raise ValueError('full frozen analytical denominator')
    if p['requiredFp64EquationResidual']!=1e-12 or p['fullModelNumericDifferenceUnchanged']!=1e-4 or p['fullModelDecodedPixelDifferencesUnchanged']!=0 or p['formalReleaseAllowed']:raise ValueError('fixed quality / residual')
    for k in ('newFullModelInputsAllowed','newOnnxOperatorInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):
        if p[k]!=0:raise ValueError('no neural execution / role changes')
    for k in ('all68OwnInputsAndOriginalOutputReferencesRequired','noTorchOrNeuralRuntimeAllowed','fp64DiagnosticDoesNotReplaceCudaOrProveWholeModelReachability','originalWeightsBiasCandidateIdentitiesAndRolesUnchanged','oldFailuresAndConsumedBudgetsPreserved','productHold'):
        if p[k] is not True:raise ValueError('diagnostic guard '+k)
    if p['convolution']!={'inputLayout':'NCHW','operation':'cross-correlation','group':1,'pads':[1,1,1,1],'strides':[1,1],'dilations':[1,1],'kernelShape':[3,3],'outChannels':16,'inChannels':16,'accumulation':'float64','biasPresent':False,'biasInputAbsentPreserved':True}:raise ValueError('actual convolution contract')
    if p['maximumOutputPixelsPerChunk']!=4096 or p['numpyBlasThreadsRequired']!=1 or set(p['parameters'])!={'weight'}:raise ValueError('frozen chunk / runtime / absent bias')

def resources(execution):
    e=d.read(d.bind(execution))
    for k in ('auditor','mathHelper','dataHelper'):d.checked(e[k])
    if e['auditor']!=d.bind(__file__) or e['mathHelper']!=d.bind(HERE/'analyze-native-groupnorm-decomposition.py') or e['runtime']!=runtime_binding():raise ValueError('frozen source and mathematical runtime')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    trace=d.read(p['inputs']['trace']);parent=d.read(p['inputs']['parentScope']);old=d.read(p['inputs']['originalFullFailure']);gn=d.read(p['inputs']['gnDecomposition']);gnscope=d.read(p['inputs']['gnScope']);control=d.read(gnscope['inputs']['control'])
    if not trace['layerConclusionsAllowed'] or not trace['allOwnHeadsBitwiseIdenticalAllBackends'] or not control['allOwnHeadsBitwiseIdenticalAllBackends'] or old['fullModelLearnedGatePassed'] or not gn['summary']['allEquationResidualsPassed'] or gn['summary']['actualGnAboveFormalNumericDifference']!=[40]:raise ValueError('whole trace fidelity / prior failure')
    if p['model']!=gnscope['model'] or len(p['cases'])!=len(parent['cases']) or len(p['cases'])!=len(gnscope['cases']):raise ValueError('same model and full denominator')
    order=[(b,c['ordinal']) for b in ('cpu','wasm','webgpu') for c in parent['cases']]
    if [(r['backend'],r['ordinal']) for r in trace['records']]!=order or [(r['backend'],r['ordinal']) for r in old['records']]!=order:raise ValueError('all original final parity order')
    for a,b in zip(trace['records'],old['records'],strict=True):
        if a['candidateIdentity']!=b['candidateIdentity'] or a['originalCudaParity']!=b['parity'] or not a['ownHeadsBitwiseIdentical']:raise ValueError('all final parity / identity')
    model=onnx.load(d.checked(p['model']));matches=[n for n in model.graph.node if n.name==p['nodeName']]
    if len(matches)!=1:raise ValueError('unique original semantic node')
    node=matches[0];initializers={i.name:i for i in model.graph.initializer};ref=p['parameters']['weight']
    if node.op_type!='Conv' or list(node.input)!=['/dec1/dec1.2/Mul_1_output_0',ref['initializerName']] or hashlib.sha256(node.SerializeToString()).hexdigest()!=p['nodeProtoSha256']:raise ValueError('actual two slots / no bias / node bytes')
    initializer=initializers[ref['initializerName']];a=numpy_helper.to_array(initializer);weight=read_tensor(ref)
    if a.dtype!=np.float32 or a.shape!=(16,16,3,3) or a.tobytes()!=weight.tobytes() or hashlib.sha256(initializer.SerializeToString()).hexdigest()!=ref['tensorProtoSha256']:raise ValueError('original kernel storage and TensorProto')
    modules={r['module']:i for i,r in enumerate(parent['mapping'])};layers={(r['backend'],r['ordinal']):r['layers'][modules['dec1.3']] for r in trace['layerRecords']}
    if [c['ordinal'] for c in p['cases']]!=list(range(1,len(p['cases'])+1)):raise ValueError('all native order')
    for c,original,cap,prior in zip(p['cases'],parent['cases'],trace['captures']['wasm'],gnscope['cases'],strict=True):
        if c['candidateIdentity']!=original['candidateIdentity'] or c['candidateIdentity']!=cap['candidateIdentity'] or c['candidateIdentity']!=prior['candidateIdentity'] or c['candidateIdentity']['identity']['split']!='train':raise ValueError('stable train identity')
        expected={'strictCudaInput':original['strictCudaLayers']['dec1.2'],'strictCudaOutput':original['strictCudaLayers']['dec1.3'],'wasmInput':cap['outputs'][f'layer{modules["dec1.2"]:02d}'],'wasmOutput':cap['outputs'][f'layer{modules["dec1.3"]:02d}']}
        if c['tensors']!=expected or expected['strictCudaOutput']!=prior['tensors']['strictCudaInput'] or expected['wasmOutput']!=prior['tensors']['wasmInput']:raise ValueError('actual own inputs / downstream GN provenance')
        for ref in c['tensors'].values():
            a=read_tensor(ref)
            if a.dtype!=np.float32 or a.shape[:2]!=(1,16) or list(a.shape)!=c['tensors']['strictCudaInput']['shape']:raise ValueError('all native finite F32 shape')
    return e,p,weight,layers

def summarize(p,records):
    if len(records)!=len(p['cases']) or [r['ordinal'] for r in records]!=[c['ordinal'] for c in p['cases']]:raise ValueError('all cases before summary')
    keys=['actualOutputMaxAbs','upstreamOutputMaxAbs','wasmOwnRoundingMaxAbs','cudaOwnRoundingMaxAbs','roundingDifferenceMaxAbs','hypotheticalExactConvOnWasmInputAgainstOriginalCudaMaxAbs','equationResidualMaxAbs']
    return {'candidateCount':len(records),'analyticalEvaluations':2*len(records),'maxima':{k:max(r['decomposition'][k] for r in records) for k in keys},'actualConvAboveFormalNumericDifference':[r['ordinal'] for r in records if r['decomposition']['actualOutputMaxAbs']>p['fullModelNumericDifferenceUnchanged']],'hypotheticalExactConvAboveFormalNumericDifference':[r['ordinal'] for r in records if r['decomposition']['hypotheticalExactConvOnWasmInputAgainstOriginalCudaMaxAbs']>p['fullModelNumericDifferenceUnchanged']],'requiredFp64EquationResidual':p['requiredFp64EquationResidual'],'allEquationResidualsPassed':all(r['decomposition']['equationResidualMaxAbs']<=p['requiredFp64EquationResidual'] for r in records),'downstreamFailureOrdinal40':next(r for r in records if r['ordinal']==40),'modelQualityOrRootCauseProven':False}

def record_for(c,arrays,calculated,statistics,p,layers):
    result=decomposition(arrays['strictCudaInput'],arrays['strictCudaOutput'],arrays['wasmInput'],arrays['wasmOutput'],read_tensor(calculated['strictCuda']),read_tensor(calculated['wasm']),p['requiredFp64EquationResidual'])
    if result['actualOutputMaxAbs']!=layers[('wasm',c['ordinal'])]['maxAbs']:raise ValueError('original full layer reconstruction')
    return {'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'inputs':c['tensors'],'conv64':calculated,'statistics':statistics,'decomposition':result}

def make_report(execution,root,p,records):
    return {'schemaVersion':1,'ok':True,'decision':'full_native_fp64_convolution_error_decomposition_reconstructed','inputs':{'execution':d.bind(execution),'auditor':d.bind(__file__)},'records':records,'startEvents':[d.bind(x) for x in sorted((root/'events').glob('*-start.json'))],'summary':summarize(p,records),'analyticalEvaluationsConsumed':2*len(records),'originalKernelAndAbsentBiasUnchanged':True,'referenceCudaStorageUnchanged':True,'hypotheticalConv64CannotReplaceDeploymentOrCudaReference':True,'newModelCalls':0,'newTorchInputs':0,'newOnnxOperatorInputs':0,'optimizerSteps':0,'valInputs':0,'protectedInputs':0,'newChatImageInputs':0,'oldFailuresAndConsumedBudgetsPreserved':True,'fullModelLearnedGatePassed':False,'formalReleaseAllowed':False,'productHold':True}

def execute(execution,root):
    if root.exists():raise ValueError('analytical scope consumed; readonly replay only')
    e,p,weight,layers=resources(execution)
    if e['outputRoot']!=str(root):raise ValueError('frozen exclusive output root')
    root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'results').mkdir();records=[];started=0
    try:
        for c in p['cases']:
            arrays={k:read_tensor(ref) for k,ref in c['tensors'].items()};calculated={};stats={}
            for side,key in [('strictCuda','strictCudaInput'),('wasm','wasmInput')]:
                o=c['ordinal'];d.new(root/'events'/f'{o:03d}-{side}-start.json',{'ordinal':o,'side':side,'candidateIdentity':c['candidateIdentity'],'input':c['tensors'][key],'execution':d.bind(execution)});started+=1
                a,stats[side]=conv64(arrays[key],weight,p['maximumOutputPixelsPerChunk']);calculated[side]=save64(root/'results'/f'{o:03d}-{side}-conv64.bin',a)
            record=record_for(c,arrays,calculated,stats,p,layers);d.new(root/'results'/f'{c["ordinal"]:03d}-record.json',record);records.append(record)
            print(json.dumps({'ordinal':c['ordinal'],'completeAnalyticalEvaluations':2*len(records)}),flush=True)
        report=make_report(execution,root,p,records);d.new(root/'report.json',report)
        print(json.dumps({'ok':True,'summary':{k:v for k,v in report['summary'].items() if k!='downstreamFailureOrdinal40'}}))
    except BaseException as error:
        d.new(root/'execution-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'execution':d.bind(execution),'analyticalEvaluationsStarted':started,'completeCandidateRecords':len(records),'newModelCalls':0,'formalReleaseAllowed':False,'productHold':True});raise

def reconstruct(root):
    old=d.read(d.bind(root/'report.json'));execution=d.checked(old['inputs']['execution']);e,p,weight,layers=resources(execution);records=[];events=[]
    for c in p['cases']:
        record=d.read(d.bind(root/'results'/f'{c["ordinal"]:03d}-record.json'));arrays={k:read_tensor(ref) for k,ref in c['tensors'].items()};stats={}
        for side,key in [('strictCuda','strictCudaInput'),('wasm','wasmInput')]:
            ev=root/'events'/f'{c["ordinal"]:03d}-{side}-start.json';events.append(ev.name)
            if d.read(d.bind(ev))!={'ordinal':c['ordinal'],'side':side,'candidateIdentity':c['candidateIdentity'],'input':c['tensors'][key],'execution':d.bind(execution)}:raise ValueError('event identity')
            a,stats[side]=conv64(arrays[key],weight,p['maximumOutputPixelsPerChunk']);stored=read_tensor(record['conv64'][side])
            if a.dtype!=stored.dtype or a.shape!=stored.shape or a.tobytes()!=stored.tobytes():raise ValueError('Conv64 mathematical byte replay')
        expected=record_for(c,arrays,record['conv64'],stats,p,layers)
        if record!=expected:raise ValueError('full analytical record replay')
        records.append(expected)
    if sorted(x.name for x in (root/'events').glob('*-start.json'))!=sorted(events) or len(list((root/'results').glob('*.bin')))!=p['analyticalConvolutionEvaluationsAllowed']:raise ValueError('whole event/tensor denominator')
    return make_report(execution,root,p,records)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execution',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-report',action='store_true');a=parser.parse_args();root=a.output.resolve()
    if a.verify_report:
        r=reconstruct(root)
        if r!=d.read(d.bind(root/'report.json')):raise ValueError('analytical reconstruction_mismatch')
        print(json.dumps({'ok':True,'replayedAnalyticalEvaluations':r['analyticalEvaluationsConsumed'],'newModelCalls':0,'fullModelLearnedGatePassed':False}))
    else:execute(a.execution.resolve(),root)
