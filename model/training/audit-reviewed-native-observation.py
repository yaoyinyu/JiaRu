"""复用不可覆盖捕获传输；新范围逐项验真，先全输出保真再允许逐层解释。"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import onnx
HERE=Path(__file__).resolve().parent
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
tr=load(HERE/'audit-native-joint-fulltrace.py','reviewed_observation_transport')
g=load(HERE/'prepare-reviewed-native-observation.py','reviewed_observation_graph')
d=tr.d
original_compare=tr.full.compare
tr.HTML=tr.HTML.replace("+row.ordinal+'/68'","+row.ordinal+'/'+c.cases.length").replace('执行本阶段WASM/WebGPU各68输入','执行本阶段完整WASM/WebGPU输入')


def resources(execution):
    e=d.read(d.bind(execution))
    for ref in e['sources'].values(): d.checked(ref)
    for ref in e['runtimeFiles'].values(): d.checked(ref)
    if e['sources']['runner']!=d.bind(__file__) or e['sources']['transport']!=d.bind(tr.__file__) or e['sources']['graph']!=d.bind(g.__file__): raise ValueError('frozen executor and helpers')
    p=d.read(e['scope']); n=len(p['cases'])
    if p['budget']!={'maximumAttempts':1,'inputsPerBackend':n,'backends':['cpu','wasm','webgpu'],'totalBackendInputs':3*n,'restartAllowed':False,'optimizerSteps':0,'valInputs':0,'protectedInputs':0,'newChatImageInputs':0}: raise ValueError('exact stage budget')
    if p['requiredMaxAbs']!=1e-4 or p['requiredDecodedPixelDifferences']!=0 or p['formalReleaseAllowed'] or not p['productHold']: raise ValueError('unchanged quality and HOLD')
    if [c['ordinal'] for c in p['cases']]!=list(range(1,n+1)) or len(p['candidateIdentities'])!=n or [c['candidateIdentity'] for c in p['cases']]!=p['candidateIdentities']: raise ValueError('complete stable cohort')
    original=onnx.load(d.checked(p['originalGraph'])); actual=onnx.load(d.checked(p['graph']))
    if p['mapping']: g.verify_graph(original,actual,p['mapping'])
    elif actual.SerializeToString()!=original.SerializeToString(): raise ValueError('unobserved baseline graph')
    if p['outputs']!=g.specs(p['mapping']): raise ValueError('actual output-derived schema')
    for c in p['cases']:
        if c['outputShapes']!=g.shapes(c['h'],c['w'],p['mapping']): raise ValueError('original native output shapes')
        for ref in (c['input'],c['resizeRatios']): tr.tensor(ref)
    for gate in e['prerequisites']:
        report=d.read(gate['report']); g.require_fidelity(report,gate['count'],gate['kind'])
        if report['inputs']['preparation']!=gate['preparation']: raise ValueError('exact independent stage gate')
    if p['projectInputs']:
        prior=d.read(p['originalReport']); expected=d.read(d.read(d.read(prior['inputs']['preparation'])['execution'])['scope'])['cases']
        if n!=len(expected) or n!=74: raise ValueError('full project denominator')
        for c,o in zip(p['cases'],expected,strict=True):
            for k in ('ordinal','candidateIdentity','h','w','input','resizeRatios','references'):
                if c[k]!=o[k]: raise ValueError('original actual project binding')
            if c['candidateIdentity']['identity']['split']!='train': raise ValueError('train-only')
            for b in ('cpu','wasm','webgpu'):
                if c['ownUninstrumentedHeads'][p['kind']][b]!=prior['captures'][b][c['ordinal']-1]['outputs']: raise ValueError('same backend original heads')
    elif p['kind']!='control' or n!=4: raise ValueError('independent synthetic controls only')
    total=sum(sum(__import__('math').prod(s)*4 for s in c['outputShapes'].values()) for c in p['cases'])*3
    if p['expectedRawCaptureBytes']!=total or p['captureCountDerivedFromActualOutputsAndCases']!=n*len(p['outputs'])*3: raise ValueError('actual full bytes and cardinality')
    return e,p,{p['kind']:p['graph']},None


def fidelity(c,kind,backend,outputs):
    if c['ownUninstrumentedHeads'] is None: return True # 独立baseline仅提供参照，不能作为观测通过门。
    return all(tr.tensor(outputs[h]).tobytes()==tr.tensor(c['ownUninstrumentedHeads'][kind][backend][h]).tobytes() for h in ('mask','presence'))


def compare(c,kind,outputs,unused):
    if c['references'] is None: return None
    comparator=load(HERE/'verify-native-multiscale-browser-v2.py','observation_final_compare')
    return original_compare(c,kind,outputs,comparator)


def control_gate(e):
    if not e['prerequisites']: raise ValueError('learned cannot run without actual new control fidelity')
    return e['prerequisites'][-1]['report']


tr.resources=resources; tr.fidelity=fidelity; tr.control_gate=control_gate; tr.full.compare=compare


def reconstruct(root):
    result=tr.reconstruct(root)
    prep=d.read(result['inputs']['preparation']); e,p,_,_=resources(d.checked(prep['execution']))
    if root.resolve()!=Path(e['stageRoot']).resolve() or prep['kind']!=p['kind']: raise ValueError('frozen exact stage identity')
    if d.checked(prep['html']).read_bytes()!=tr.HTML.encode(): raise ValueError('frozen actual page bytes')
    result['observationReader']=d.bind(__file__)
    result['purpose']=p['purpose']; result['syntheticBaselineOnly']=not p['mapping']
    result['newProjectModelInputs']=3*len(p['cases']) if p['projectInputs'] else 0
    result['syntheticModelInputs']=0 if p['projectInputs'] else 3*len(p['cases'])
    result['layerConclusionsAllowed']=bool(result['layerConclusionsAllowed'] and p['projectInputs'] and p['mapping'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--execution',type=Path); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--serve',action='store_true'); p.add_argument('--audit',action='store_true'); p.add_argument('--verify-report',action='store_true'); p.add_argument('--port',type=int,default=8853)
    a=p.parse_args(); root=a.output.resolve()
    if a.serve:
        prep=d.read(d.bind(root/'preparation.json')); e,_,_,_=resources(d.checked(prep['execution']))
        if root!=Path(e['stageRoot']).resolve(): raise ValueError('exact server stage')
        tr.serve(root,a.port)
    elif a.audit or a.verify_report:
        result=reconstruct(root)
        if a.verify_report:
            if result!=d.read(d.bind(root/'report.json')): raise ValueError('reconstruction_mismatch')
        else: d.new(root/'report.json',result)
        print(json.dumps({k:result[k] for k in ('ok','kind','allOwnHeadsBitwiseIdenticalAllBackends','layerConclusionsAllowed','summary','actualRawTensorCount')}))
    else:
        e,scope,_,_=resources(a.execution.resolve())
        if root!=Path(e['stageRoot']).resolve(): raise ValueError('exact prepare stage')
        tr.prepare(a.execution.resolve(),root,scope['kind'])
