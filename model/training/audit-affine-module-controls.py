"""原仿射依赖闭包捕获和重放；完整分母先于复现结论，不授予完整模型资格。"""
import argparse
import importlib.util
import json
import os
import traceback
from pathlib import Path

import numpy as np
import onnx

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('affine_module_io',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
tensor=d.load(HERE/'audit-pretrained-native-boundary.py','affine_module_tensor')


def resources(path):
    p=d.read(d.bind(path));assert p['purpose']=='original_affine_dependency_module_controls' and p['runner']==d.bind(__file__)
    for ref in [*p['inputs'].values(),p['browserServer']]:d.checked(ref)
    req=d.read(p['inputs']['requirements']);proof=d.read(req['graphProof'])
    original=onnx.load(d.checked(proof['originalGraph']))
    extract=d.load(d.checked(proof['extractor']),'affine_module_extractor')
    graph,detail=extract.extract(original,req['inputName'],[1,32,'half_height','half_width'],list(req['outputs'].values()))
    assert detail==proof['proof'] and graph.SerializeToString()==d.checked(p['inputs']['onnx']).read_bytes()
    assert p['inputName']==req['inputName'] and p['outputs']==req['outputs'] and p['inputChannels']==32
    assert len(p['cases'])==9 and [x['ordinal'] for x in p['cases']]==list(range(1,10))
    for c,old in zip(p['cases'],req['cases'],strict=True):
        assert c==dict(ordinal=old['ordinal'],h=old['h'],w=old['w'],input=old['input']['binding'])
        tensor.tensor(old['input'],[1,32,c['h'],c['w']])
    assert p['budget']==req['plannedBudgetAfterDetailedReadiness']
    params=d.load(HERE/'onnx-materialize-static-unsqueeze.py','affine_module_params')
    gamma,_=params.static_value(graph,'enc2.4.weight');beta,_=params.static_value(graph,'enc2.4.bias')
    assert gamma.shape==beta.shape==(32,) and gamma.dtype==beta.dtype==np.float32
    assert np.array_equal(gamma,np.ones(32,np.float32)) and np.array_equal(beta,np.zeros(32,np.float32))
    return p,req


def reference(c):
    return np.frombuffer(d.checked(c['input']).read_bytes(),dtype='<f4').reshape(1,32,c['h'],c['w'])


def stats(raw,c):
    x=reference(c);values={k:tensor.tensor(v,list(x.shape)) for k,v in raw.items()}
    delta={k:a.astype(np.float64)-x.astype(np.float64) for k,a in values.items()}
    effective=values['after_bias'].astype(np.float64)-values['after_scale'].astype(np.float64)
    return dict(comparisons={k:dict(maxAbsoluteDifference=float(np.abs(a).max()),valuesAbove1e4=int((np.abs(a)>1e-4).sum()),signedMeanDifference=float(a.mean())) for k,a in delta.items()},
                effectiveBias=dict(maxAbsoluteValue=float(np.abs(effective).max()),signedMean=float(effective.mean()),values=int(effective.size)))


def cpu(path,root):
    import onnxruntime as ort
    p,_=resources(path);ready=d.read(d.bind(path.with_name('readiness.json')));assert ready['ok'] and ready['plan']==d.bind(path)
    root.mkdir(exist_ok=False);(root/'raw').mkdir();(root/'events').mkdir();count=0;rows=[]
    d.new(root/'attempt.json',dict(plan=d.bind(path),pid=os.getpid(),automaticResumeAllowed=False))
    try:
        opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;opts.log_severity_level=3
        session=ort.InferenceSession(str(d.checked(p['inputs']['onnx'])),sess_options=opts,providers=['CPUExecutionProvider'])
        assert session.get_session_options().intra_op_num_threads==4 and session.get_session_options().inter_op_num_threads==1
        d.new(root/'environment.json',dict(onnxruntime=ort.__version__,intraThreads=4,interThreads=1,providers=session.get_providers(),graphOptimization='disabled'))
        for c in p['cases']:
            i=c['ordinal'];d.new(root/'events'/f'{i:03d}-started.json',dict(plan=d.bind(path),ordinal=i,input=c['input']));count+=1
            outputs=session.run(list(p['outputs'].values()),{p['inputName']:reference(c)})
            raw={k:tensor.save(root/'raw'/f'{i:03d}-{k}.bin',v) for k,v in zip(p['outputs'],outputs,strict=True)}
            row=dict(backend='cpuOrt',ordinal=i,input=c['input'],raw=raw,**stats(raw,c));rows.append(row)
            d.new(root/'events'/f'{i:03d}-confirmed.json',row)
            print(json.dumps(dict(confirmed=i,max=max(x['maxAbsoluteDifference'] for x in row['comparisons'].values()))),flush=True)
        gate=all(x['valuesAbove1e4']==0 for r in rows for x in r['comparisons'].values())
        d.new(root/'report.json',dict(ok=True,plan=d.bind(path),records=rows,actualInputs=count,full9CpuGatePassed=gate,formalReleaseAllowed=False,productHold=True))
        d.new(root/'terminal.json',dict(phase='closed',report=d.bind(root/'report.json'),actualInputs=count))
    except BaseException as error:
        d.new(root/'failure.json',dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),startedInputs=count,automaticResumeAllowed=False));raise


def reconstruct_cpu(path,root):
    p,req=resources(path);r=d.read(d.bind(root/'report.json'))
    assert r['plan']==d.bind(path) and len(r['records'])==r['actualInputs']==9
    assert d.read(d.bind(root/'terminal.json'))==dict(phase='closed',report=d.bind(root/'report.json'),actualInputs=9)
    assert len(list((root/'raw').glob('*.bin')))==18 and len(list((root/'events').glob('*.json')))==18
    for c,row in zip(p['cases'],r['records'],strict=True):
        assert row==dict(backend='cpuOrt',ordinal=c['ordinal'],input=c['input'],raw=row['raw'],**stats(row['raw'],c))
        assert d.read(d.bind(root/'events'/f"{c['ordinal']:03d}-confirmed.json"))==row
        assert d.read(d.bind(root/'events'/f"{c['ordinal']:03d}-started.json"))==dict(plan=d.bind(path),ordinal=c['ordinal'],input=c['input'])
    assert r['full9CpuGatePassed']==all(x['valuesAbove1e4']==0 for row in r['records'] for x in row['comparisons'].values())
    env=d.read(d.bind(root/'environment.json'));assert env['intraThreads']==4 and env['interThreads']==1 and env['providers']==['CPUExecutionProvider']
    return p,req,r


def write(path,value):
    if path.exists():assert d.read(d.bind(path))==value,'immutable replay drift'
    else:d.new(path,value)


def verify(path,root,output):
    p,req,cr=reconstruct_cpu(path,root/'cpu');b=root/'browser';bp=d.read(d.bind(b/'plan.json'));live=d.read(d.bind(b/'capture/live-browser.json'));claim=d.read(d.bind(b/'claim.json'))
    expected=[(backend,i) for backend in ['wasm','webgpu'] for i in range(1,10)]
    assert bp['operatorPlan']==d.bind(path) and bp['server']==p['browserServer'] and bp['outputs']==p['outputs']
    assert live['phase']=='closed' and not live['errors'] and not live['virtualTime'] and live['crossOriginIsolated']
    assert live['planSha256']==d.bind(b/'plan.json')['sha256'] and live['claim']==claim['claim']
    assert live['userAgent']==bp['expectedUserAgent'] and live['adapterInfo']==bp['expectedAdapter'] and live['webgpuDevice']['grantedLimits']==p['deviceProbeGrantedLimits']
    assert [(x['backend'],x['ordinal']) for x in live['records']]==expected==[(x['backend'],x['ordinal']) for x in live['started']]
    assert len(list((b/'capture').glob('*.bin')))==36 and len(list((b/'started').glob('*.json')))==18
    rows=list(cr['records'])
    for row in live['records']:
        backend,i=row['backend'],row['ordinal'];c=p['cases'][i-1];request=claim['claim']+'-'+backend+'-'+str(i)
        assert row['requestId']==request
        assert d.read(d.bind(b/'started'/f'{backend}-{i}.json'))==dict(claim=claim['claim'],requestId=request,backend=backend,ordinal=i,h=c['h'],w=c['w'],inputSha256=c['input']['sha256'])
        raw={}
        for label in p['outputs']:
            file=b/'capture'/f'{backend}-{i}-{label}.bin';ref=dict(binding=d.bind(file),shape=[1,32,c['h'],c['w']],dtype='float32',bytes=file.stat().st_size)
            assert row['outputs'][label]==dict(shape=ref['shape'],dtype='float32',sha256=ref['binding']['sha256'],bytes=ref['bytes'])
            tensor.tensor(ref,ref['shape']);raw[label]=ref
        rows.append(dict(backend=backend,ordinal=i,input=c['input'],raw=raw))
    files=[b/'claim.json',*sorted((b/'started').glob('*.json')),*sorted((b/'capture').glob('*'))];events=[d.read(d.bind(f)) for f in (b/'http-events').glob('*.json')];ids=set()
    for file in files:
        meta=d.read(d.bind(b/'metadata'/f'{file.parent.name}-{file.name}.json'));hits=[e for e in events if e['requestId']==meta['requestId']]
        route='/claim' if file.name=='claim.json' else '/started/'+file.stem.replace('-','/') if file.parent.name=='started' else '/capture/'+file.name
        assert 1<=len(hits)<=2 and meta['sha256']==d.bind(file)['sha256'] and meta['bytes']==file.stat().st_size
        assert all(e['declaredSha256']==meta['sha256'] and e['declaredBytes']==meta['bytes'] and e['path']==route for e in hits);ids.add(meta['requestId'])
    assert len(files)==56 and ids=={e['requestId'] for e in events} and len(rows)==27
    # 全27输入/54数组完整之后才比较跨环境结果。
    for row in rows[9:]:row.update(stats(row['raw'],p['cases'][row['ordinal']-1]))
    summary={backend:dict(inputs=9,passed=sum(all(x['valuesAbove1e4']==0 for x in r['comparisons'].values()) for r in rows if r['backend']==backend),maxAbsoluteDifference=max(x['maxAbsoluteDifference'] for r in rows if r['backend']==backend for x in r['comparisons'].values())) for backend in ['cpuOrt','wasm','webgpu']}
    reproduced=any(x['valuesAbove1e4']>0 for r in rows if r['backend']=='webgpu' for x in r['comparisons'].values())
    value=dict(ok=True,decision='affine_module_failure_reproduced' if reproduced else 'affine_module_failure_not_reproduced',reader=d.bind(__file__),plan=d.bind(path),
               records=rows,summary=summary,all27Inputs54ArraysCompleteFinite=True,newCudaInputs=0,actualInputs=27,fullModelGatePassed=False,
               actualNetworkBytes=None,formalReleaseAllowed=False,productHold=True)
    write(output,value);print(json.dumps(dict(ok=True,decision=value['decision'],summary=summary)),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['cpu','verify-cpu','verify']);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path);v=ap.parse_args()
    if v.mode=='cpu':cpu(v.plan.resolve(),v.root.resolve())
    elif v.mode=='verify-cpu':
        _,_,r=reconstruct_cpu(v.plan.resolve(),v.root.resolve());write(v.output.resolve(),dict(ok=True,plan=d.bind(v.plan),cpuReport=d.bind(v.root/'report.json'),full9CpuGatePassed=r['full9CpuGatePassed'],all18Raw18EventsReplayed=True,newModelInputs=0))
    else:verify(v.plan.resolve(),v.root.resolve(),v.output.resolve())
