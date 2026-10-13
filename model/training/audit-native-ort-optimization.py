"""固定ONNX与全候选，单变量禁用CPU图优化；不替换旧判决或阈值。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('ort_ablation_data', HERE/'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s);s.loader.exec_module(d)


def resources(plan_path):
    plan = d.read(d.bind(plan_path))
    if plan['purpose'] != 'all68_cpu_ort_disable_graph_optimization_only' or plan['nativeInputsAllowed'] != 68 or any(plan[k] for k in ('optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed')):
        raise ValueError('all68 optimization-only scope')
    for ref in plan['inputs'].values():
        d.checked(ref)
    helper = d.load(d.checked(plan['inputs']['precisionHelper']), 'ort_optimization_precision_helper')
    strict = d.read(plan['inputs']['strictReport'])
    previous = helper.reconstruct(d.checked(strict['inputs']['plan']),strict['captures'])
    if strict != previous or not strict['strictFp32CapacityPassed']:
        raise ValueError('strict reference reconstruction_mismatch')
    _, old, _, scope, _, rows, _, _, guard, native = helper.resources(d.checked(strict['inputs']['plan']))
    try:
        if plan['inputs']['onnx'] != old['inputs']['onnx'] or scope['inputs']['trainedWeights'] != strict['sameWeights']:
            raise ValueError('same learned model bytes')
        return plan, helper, strict, old, rows, guard, native
    except BaseException:
        for path in native['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(path))
        raise


def reconstruct(plan_path, captures):
    plan, helper, strict, old, rows, guard, native = resources(plan_path)
    try:
        if [r['candidateIdentity'] for r in captures] != [r['candidateIdentity'] for r in rows]:
            raise ValueError('all68 captured identity')
        records=[]
        for previous,reference,captured in zip(old['records'],strict['captures'],captures,strict=True):
            h,w=previous['h'],previous['w']
            actual_mask=helper.buffer(captured['mask'],h*w);actual_presence=helper.buffer(captured['presence'],1)
            stats={}
            for label,paths,m,p in (('strictCuda',reference['paths'],'strict-mask','strict-presence'),('cpuTorch',reference['paths'],'cpu-mask','cpu-presence'),('oldOptimizedOrt',previous['paths'],'cpu-mask','cpu-presence'),('oldTf32',previous['paths'],'mask','presence')):
                stats[label]=helper.compare.compare_outputs(helper.buffer(paths[m],h*w),helper.buffer(paths[p],1),actual_mask,actual_presence,h,w)
            records.append({'candidateIdentity':previous['candidateIdentity'],'ordinal':previous['ordinal'],'comparisons':stats})
        summary={label:{'maxAbs':max(r['comparisons'][label]['maxAbsoluteDifference'] for r in records),
            'numericFailed':sum(not r['comparisons'][label]['numericGatePassed'] for r in records),
            'pixelDifferences':sum(r['comparisons'][label]['decodedMaskPixelDifference'] for r in records),
            'presenceFailed':sum(not r['comparisons'][label]['presenceDecisionMatched'] for r in records)} for label in ('strictCuda','cpuTorch','oldOptimizedOrt','oldTf32')}
        passed=all(r['comparisons']['strictCuda'][key] for r in records for key in ('numericGatePassed','decodedPixelGatePassed','presenceDecisionMatched'))
        return {'schemaVersion':1,'ok':True,'decision':'cpu_graph_optimization_ablation_reconstructed',
            'inputs':{'plan':d.bind(plan_path),'auditor':d.bind(__file__)},'captures':captures,'records':records,'summary':summary,
            'strictFp32CpuGatePassed':passed,'graphOptimizationLevel':'ORT_DISABLE_ALL','oldTf32DeploymentFailurePreserved':True,
            'newOrtInputs':68,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,
            'browserAdmitted':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for path in native['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(path))


def run(plan_path,root):
    if root.exists():
        raise ValueError('output exists; use read-only replay')
    plan,helper,strict,old,rows,guard,native=resources(plan_path)
    captures=[]
    try:
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session=ort.InferenceSession(str(d.checked(plan['inputs']['onnx'])),sess_options=options,providers=['CPUExecutionProvider'])
        root.mkdir(parents=True,exist_ok=False)
        for previous in old['records']:
            h,w=previous['h'],previous['w']
            x=helper.buffer(previous['paths']['input'],4*h*w).reshape(1,4,h,w)
            mask,presence=session.run(None,{'candidate':x})
            if mask.shape!=(1,1,h,w) or presence.shape!=(1,1) or any(a.dtype!=np.float32 or not np.isfinite(a).all() for a in (mask,presence)):
                raise ValueError('two-head native shapes/finite float32')
            paths={}
            for name,value in (('mask',mask),('presence',presence)):
                path=root/f'{previous["ordinal"]:03d}-{name}.bin'
                with path.open('xb') as stream:
                    stream.write(value.tobytes());stream.flush();os.fsync(stream.fileno())
                paths[name]=d.bind(path)
            captures.append({'candidateIdentity':previous['candidateIdentity'],'ordinal':previous['ordinal'],**paths})
    except BaseException as error:
        if root.exists():
            d.new(root/'failure.json',{'ok':False,'type':type(error).__name__,'message':str(error),'completedInputs':len(captures),'optimizerSteps':0})
        raise
    finally:
        for path in native['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(path))
    result=reconstruct(plan_path,captures);d.new(root/'report.json',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--verify-report',type=Path);args=parser.parse_args()
    if args.verify_report:
        old=d.read(d.bind(args.verify_report));d.checked(old['inputs']['auditor'])
        result=reconstruct(d.checked(old['inputs']['plan']),old['captures'])
        if result!=old:raise ValueError('ORT ablation reconstruction_mismatch')
    else:result=run(args.plan.resolve(),args.output.resolve())
    print(json.dumps({k:result[k] for k in ('ok','strictFp32CpuGatePassed','summary','optimizerSteps')}))
