"""完整74严格CUDA无反馈模块钩子；原双头逐字节保真失败即禁止层归因。"""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
import onnx
import torch
HERE=Path(__file__).resolve().parent
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
a=load(HERE/'materialize-reviewed-native-deployment.py','observation_cuda_assets')
g=load(HERE/'prepare-reviewed-native-observation.py','observation_cuda_graph')
d=a.d


def resources(ref):
    e=d.read(ref)
    for bound in [*e['sources'].values(),*e['inputs'].values()]: d.checked(bound)
    if e['sources']['runner']!=d.bind(__file__): raise ValueError('frozen CUDA capture source')
    assets=d.read(e['inputs']['assets']); control=d.read(e['inputs']['controlTrace'])
    if e['mapping']!=g.mapping(onnx.load(d.checked(assets['models']['learned']))): raise ValueError('actual learned graph module binding')
    g.require_fidelity(control,len(assets['cases']),'control')
    if control.get('newProjectModelInputs')!=222: raise ValueError('actual full74 project controls')
    if e['budget']!={'maximumAttempts':1,'strictCudaInputs':74,'optimizerSteps':0,'backward':0,'valInputs':0,'protectedInputs':0,'restartAllowed':False}: raise ValueError('exact new once-only strict CUDA budget')
    _,training,data,rows,net,guard,cleanup=a.resources(assets['execution'])
    if len(assets['cases'])!=74 or e['candidateIdentities']!=assets['candidateIdentities']: raise ValueError('full train-only identities')
    return e,assets,net,guard,cleanup


def capture(ref,root):
    e,assets,net,guard,cleanup=resources(ref); started=0; records=[]; handles=[]
    try:
        root.mkdir(exist_ok=False); (root/'events').mkdir(); (root/'buffers').mkdir()
        d.new(root/'attempt.json',{'execution':ref,'restartAllowed':False})
        a.c.base.set_precision(); model=net.NativeConditionalMaskRefiner().cuda().float().eval(); model.requires_grad_(False)
        state=torch.load(d.checked(assets['weights']['learned']),map_location='cpu',weights_only=True); model.load_state_dict(state,strict=True)
        hashes=a.c.tensors_sha(model); mapping=e['mapping']; current={}
        for row in mapping:
            name=row['module']; module=model.get_submodule(name)
            if type(module).__name__!=row['operation']: raise ValueError('same actual module class')
            def hook(module,args,out,name=name):
                if name in current: raise ValueError('one module capture per input')
                current[name]=out.detach().cpu().numpy().copy()
            handles.append(module.register_forward_hook(hook))
        environment=a.c.base.environment(); d.new(root/'environment.json',environment)
        for i,c in enumerate(assets['cases'],1):
            current.clear(); x=np.frombuffer(d.checked({k:c['input'][k] for k in ('path','sha256')}).read_bytes(),np.float32).reshape(c['input']['shape']).copy()
            started=i; d.new(root/'events'/f'{2*i-1:03d}.json',{'phase':'started','ordinal':i,'candidateIdentity':c['candidateIdentity'],'input':c['input']})
            with torch.inference_mode(): mask,presence=model(torch.from_numpy(x).cuda())
            arrays={'mask':mask.cpu().numpy().copy(),'presence':presence.cpu().numpy().copy()}
            shapes=g.shapes(c['h'],c['w'],mapping); outputs={}
            if set(current)!={r['module'] for r in mapping}: raise ValueError('complete actual module hooks')
            for key,arr in list(arrays.items())+[(f'layer{j:02d}',current[row['module']]) for j,row in enumerate(mapping)]:
                if list(arr.shape)!=shapes[key]: raise ValueError('actual native hook shape')
                outputs[key]=a.save(root/'buffers'/f'{i:03d}-{key}.bin',arr)
            same=all(arrays[h].tobytes()==np.fromfile(d.checked({k:c['references']['learned'][h][k] for k in ('path','sha256')}),np.float32).tobytes() for h in ('mask','presence'))
            record={'ordinal':i,'candidateIdentity':c['candidateIdentity'],'outputs':outputs,'originalHeadsBitwiseEqual':same}
            records.append(record); d.new(root/'events'/f'{2*i:03d}.json',{'phase':'confirmed','record':record})
        if hashes!=a.c.tensors_sha(model): raise ValueError('all model tensor bytes unchanged')
        terminal={'phase':'closed','started':started,'confirmed':len(records)}; d.new(root/'terminal.json',terminal)
        result={'ok':True,'execution':ref,'environment':environment,'weightTensorHashes':hashes,'records':records,
            'allOriginalHeadsBitwiseEqual':all(r['originalHeadsBitwiseEqual'] for r in records),
            'strictCudaInputs':started,'optimizerSteps':0,'backward':0,'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',result); return result
    except BaseException as error:
        if root.exists(): d.new(root/'termination.json',{'ok':False,'error':repr(error),'started':started,'confirmed':len(records),'restartAllowed':False,'productHold':True})
        raise
    finally:
        for handle in handles: handle.remove()
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


def verify(path):
    saved=d.read(d.bind(path)); e,assets,net,guard,cleanup=resources(saved['execution'])
    try:
        root=path.parent; n=len(assets['cases']); mapping=e['mapping']; records=saved['records']
        if len(records)!=n or saved['strictCudaInputs']!=n or saved['optimizerSteps']!=0 or saved['backward']!=0: raise ValueError('complete actual CUDA budget')
        state=torch.load(d.checked(assets['weights']['learned']),map_location='cpu',weights_only=True)
        model=net.NativeConditionalMaskRefiner().float().eval(); model.load_state_dict(state,strict=True)
        if saved['weightTensorHashes']!=a.c.tensors_sha(model): raise ValueError('actual original model weight bytes')
        env=d.read(d.bind(root/'environment.json'))
        if env!=saved['environment'] or env['cudaMatmulAllowTf32'] or env['cudnnAllowTf32'] or env['autocastEnabled'] or env['float32MatmulPrecision']!='highest' or env['torchThreads']!=4: raise ValueError('strict actual CUDA environment')
        flags=[]
        for i,(c,record) in enumerate(zip(assets['cases'],records,strict=True),1):
            shape=g.shapes(c['h'],c['w'],mapping)
            if record['ordinal']!=i or record['candidateIdentity']!=c['candidateIdentity'] or set(record['outputs'])!=set(shape): raise ValueError('complete stable CUDA outputs')
            for key,ref in record['outputs'].items():
                arr=np.fromfile(d.checked({k:ref[k] for k in ('path','sha256')}),np.float32)
                if ref['dtype']!='float32' or ref['shape']!=shape[key] or arr.size!=int(np.prod(shape[key])) or not np.isfinite(arr).all(): raise ValueError('native F32 full shape and finite')
            same=all(d.checked({k:record['outputs'][h][k] for k in ('path','sha256')}).read_bytes()==d.checked({k:c['references']['learned'][h][k] for k in ('path','sha256')}).read_bytes() for h in ('mask','presence'))
            if same!=record['originalHeadsBitwiseEqual']: raise ValueError('actual own original CUDA heads')
            flags.append(same)
            if d.read(d.bind(root/'events'/f'{2*i-1:03d}.json'))!={'phase':'started','ordinal':i,'candidateIdentity':c['candidateIdentity'],'input':c['input']} or d.read(d.bind(root/'events'/f'{2*i:03d}.json'))!={'phase':'confirmed','record':record}: raise ValueError('all unique ordered CUDA events')
        if len(list((root/'events').glob('*.json')))!=2*n or len(list((root/'buffers').glob('*.bin')))!=n*len(shape): raise ValueError('actual persistent cardinality')
        if d.read(d.bind(root/'terminal.json'))!={'phase':'closed','started':n,'confirmed':n} or d.read(d.bind(root/'attempt.json'))!={'execution':saved['execution'],'restartAllowed':False}: raise ValueError('closed nonrestartable CUDA')
        if saved['allOriginalHeadsBitwiseEqual']!=all(flags): raise ValueError('full original-head fidelity summary')
        return {'ok':True,'report':d.bind(path),'allOriginalHeadsBitwiseEqual':all(flags),'candidateCount':n,'actualRawTensorCount':n*len(shape),'newModelCalls':0,'productHold':True}
    finally:
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--execution',type=Path); p.add_argument('--output',type=Path); p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    result=verify(args.verify_report.resolve()) if args.verify_report else capture(d.bind(args.execution),args.output.resolve())
    print(json.dumps({'ok':result['ok'],'strictCudaInputs':result.get('strictCudaInputs'),'allOriginalHeadsBitwiseEqual':result['allOriginalHeadsBitwiseEqual']}))
