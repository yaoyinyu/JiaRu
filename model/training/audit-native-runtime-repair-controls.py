"""冻结图变换的完整原尺寸部署控制；继承同一输入/权重的严格CUDA参考，不重跑原预算。"""
import argparse
import importlib.util
import json
import math
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import numpy as np
import onnx

T=Path(__file__).resolve().parent;R=T.parent.parent;O=None
s=importlib.util.spec_from_file_location('pointwise_io',T/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
heads=d.load(T/'export-pretrained-native-candidate-v2.py','pointwise_heads');tool=None


def validate():
    p=d.read(d.bind(O/'plan.json'));assert p['runner']==d.bind(__file__);transform=d.load(d.checked(p['transform']),'frozen_runtime_transform')
    ready=d.read(d.bind(O/'readiness.json'));assert ready['ok'] and ready['plan']==d.bind(O/'plan.json')
    proof=d.read(p['graphProof']);source=onnx.load(d.checked(proof['originalGraph']));g,pr=transform.transform(source)
    assert pr==proof['proof'] and g.SerializeToString()==d.checked(p['onnx']).read_bytes()
    assert transform.restore(g,pr).SerializeToString()==d.checked(proof['originalGraph']).read_bytes()
    assert len(p['cases'])==p['count'] and [c['ordinal'] for c in p['cases']]==list(range(1,p['count']+1))
    if p['scope']=='learned':assert d.read(p['independentFullControl'])['fullIndependentControlGatePassed']
    strict=d.read(p['strictCuda']);assert len(strict['records'])==p['count']
    for c,row in zip(p['cases'],strict['records'],strict=True):
        assert c['ordinal']==row['ordinal'] and c['input']==row['input'];heads.read_heads(row['raw'],c['h'],c['w'])
    if p['scope']=='learned':
        ledger=d.read(p['roleLedger']);assert len(ledger['all162UpstreamAndCurrentRoles'])==162 and len(ledger['excludedConsumed8'])==8
        assert all(c['record']['developmentTrainingAllowed'] and c['record']['cohort']!='heldoutDevelopment8' for c in p['cases'])
    return p,strict


def cpu():
    import onnxruntime as ort
    p,strict=validate();guard=d.load(d.checked(p['readOnlyGuard']),'runtime_repair_guard');guard.install_read_only_ultralytics_image_check();root=O/'cpu';root.mkdir();(root/'raw').mkdir();(root/'events').mkdir();started=0;rows=[]
    d.new(root/'attempt.json',dict(plan=d.bind(O/'plan.json'),pid=os.getpid(),resumeAllowed=False))
    try:
        opts=ort.SessionOptions();opts.log_severity_level=3;opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session=ort.InferenceSession(str(d.checked(p['onnx'])),sess_options=opts,providers=['CPUExecutionProvider'])
        d.new(root/'environment.json',dict(version=ort.__version__,providers=session.get_providers(),intra=4,inter=1,optimization='disabled'))
        for c in p['cases']:
            i,h,w=c['ordinal'],c['h'],c['w'];x=heads.input_array(c['input'],h,w);started+=1
            d.new(root/'events'/f'{i:03d}-started.json',dict(ordinal=i,input=c['input'],plan=d.bind(O/'plan.json')))
            values=session.run(list(p['outputs'].values()),{'candidate':x});assert len(values)==2
            raw=heads.save_heads(root/'raw',f'{i:03d}',values[0],values[1],h,w);parity=heads.compare(heads.read_heads(strict['records'][i-1]['raw'],h,w),heads.read_heads(raw,h,w),h,w)
            row=dict(backend='cpuOrt',ordinal=i,input=c['input'],raw=raw,parity=parity);rows.append(row);d.new(root/'events'/f'{i:03d}-confirmed.json',row)
            if i==1 or i%10==0 or i==p['count']:print(json.dumps(dict(cpu=i,total=p['count'],maxAbs=max(x['parity']['maxAbsoluteDifference'] for x in rows),passed=sum(heads.passed(x['parity']) for x in rows))),flush=True)
        gate=all(heads.passed(r['parity']) for r in rows);d.new(root/'report.json',dict(ok=True,plan=d.bind(O/'plan.json'),records=rows,actualInputs=started,cpuFullGatePassed=gate,productHold=True));d.new(root/'terminal.json',dict(phase='closed',report=d.bind(root/'report.json'),actualInputs=started))
    except BaseException as e:
        d.new(root/'failure.json',dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),actualStartedInputs=started,resumeAllowed=False));d.new(root/'terminal.json',dict(phase='failed',failure=d.bind(root/'failure.json'),actualInputs=started));raise
    finally:guard.remove_ultralytics_label_caches(O)


def reconstruct_cpu():
    p,strict=validate();guard=d.load(d.checked(p['readOnlyGuard']),'runtime_repair_guard');guard.install_read_only_ultralytics_image_check();root=O/'cpu';r=d.read(d.bind(root/'report.json'));term=d.read(d.bind(root/'terminal.json'))
    assert r['plan']==d.bind(O/'plan.json') and r['actualInputs']==p['count'] and len(r['records'])==p['count'] and len(list((root/'raw').glob('*.bin')))==2*p['count']
    assert term==dict(phase='closed',report=d.bind(root/'report.json'),actualInputs=p['count'])
    for c,row in zip(p['cases'],r['records'],strict=True):
        i,h,w=c['ordinal'],c['h'],c['w'];assert row['ordinal']==i and row['input']==c['input']
        parity=heads.compare(heads.read_heads(strict['records'][i-1]['raw'],h,w),heads.read_heads(row['raw'],h,w),h,w);assert row['parity']==parity
        assert d.read(d.bind(root/'events'/f'{i:03d}-confirmed.json'))==row
        assert d.read(d.bind(root/'events'/f'{i:03d}-started.json'))==dict(ordinal=i,input=c['input'],plan=d.bind(O/'plan.json'))
    assert r['cpuFullGatePassed']==all(heads.passed(row['parity']) for row in r['records'])
    return p,strict,r


def browser():
    p,_,cr=reconstruct_cpu();assert cr['cpuFullGatePassed'],'CPU failed; no browser admission'
    bp=d.read(p['priorBrowserPlan']);runtime=d.read(p['runtimeProof']);html=d.load(T/'serve-native-two-head-controls.py','pointwise_browser').HTML
    if p['scope']=='learned':html=html.replace('完整图两头独立控制','真实训练域仿射修复验收').replace('仅合成数组；不展示预测图，产品保持HOLD。','现有训练输入；不展示图片，不授正式质量或发布资格。')
    oldsend=" await send('/capture/live-browser.json',result,claim+'-terminal');";assert html.count(oldsend)==1
    html=html.replace(oldsend," result.submissionCounters=globalThis.__nailSubmissionStats;await send('/capture/live-browser.json',result,claim+'-terminal');",1)
    b=O/'browser';b.mkdir();(b/'browser.html').write_bytes(html.encode('utf8'));js=O/'browser-inline.js';js.write_bytes(html.split('<script>')[1].split('</script>')[0].encode('utf8'))
    r=subprocess.run(['node.exe','--check',str(js)],capture_output=True,text=True);assert r.returncode==0,r.stderr
    schedule=[dict(backend=backend,ordinal=c['ordinal'],h=c['h'],w=c['w'],input=dict(url=f"/assets/input-{c['ordinal']}",sha256=c['input']['sha256'])) for backend in ['wasm','webgpu'] for c in p['cases']]
    browser={**bp,'schedule':schedule,'operatorPlan':d.bind(O/'plan.json'),'html':d.bind(b/'browser.html'),'assets':{'model':p['onnx'],**{f"input-{c['ordinal']}":c['input'] for c in p['cases']}},'runtimeFiles':{**bp['runtimeFiles'],'ort.all.min.js':runtime['patched']}}
    d.new(b/'plan.json',browser);d.new(b/'config.json',dict(planSha256=d.bind(b/'plan.json')['sha256'],model={'url':'/assets/model','sha256':browser['assets']['model']['sha256']},schedule=browser['schedule'],outputs=browser['outputs'],expectedUserAgent=browser['expectedUserAgent'],expectedAdapter=browser['expectedAdapter'],requiredDeviceLimits=browser['requiredDeviceLimits']))
    for name in ['capture','started','metadata','http-events']:(b/name).mkdir()
    for ref in [*browser['assets'].values(),*browser['runtimeFiles'].values()]:d.checked(ref)
    d.new(O/'cpu-replay.json',dict(ok=True,plan=d.bind(O/'plan.json'),report=d.bind(O/'cpu/report.json'),cpuFullGatePassed=True,newInputs=0))
    print(json.dumps(dict(ok=True,cpuFullGatePassed=True,browserBudget=2*p['count'])),flush=True)


def verify():
    p,strict,cr=reconstruct_cpu();b=O/'browser';bp=d.read(d.bind(b/'plan.json'));live=d.read(d.bind(b/'capture/live-browser.json'));claim=d.read(d.bind(b/'claim.json'))
    assert bp['operatorPlan']==d.bind(O/'plan.json') and bp['assets']['model']==p['onnx']
    assert live['phase']=='closed' and not live['errors'] and live['crossOriginIsolated'] and not live['virtualTime']
    assert live['planSha256']==d.bind(b/'plan.json')['sha256'] and live['claim']==claim['claim'] and live['userAgent']==bp['expectedUserAgent'] and live['adapterInfo']==bp['expectedAdapter']
    assert live['webgpuDevice']['grantedLimits']==bp['requiredDeviceLimits'] and live['submissionCounters']['configuredLimit']==1
    expected=[(backend,i) for backend in ['wasm','webgpu'] for i in range(1,p['count']+1)];assert expected==[(r['backend'],r['ordinal']) for r in live['records']]==[(r['backend'],r['ordinal']) for r in live['started']]
    assert len(list((b/'capture').glob('*.bin')))==4*p['count'] and len(list((b/'started').glob('*.json')))==2*p['count']
    rows=list(cr['records'])
    for row in live['records']:
        backend,i=row['backend'],row['ordinal'];c=p['cases'][i-1];rid=claim['claim']+'-'+backend+'-'+str(i);assert row['requestId']==rid
        assert d.read(d.bind(b/'started'/f'{backend}-{i}.json'))==dict(claim=claim['claim'],requestId=rid,backend=backend,ordinal=i,h=c['h'],w=c['w'],inputSha256=c['input']['sha256'])
        raw={}
        for label,shape in [('mask',[1,1,c['h'],c['w']]),('presence',[1,1])]:
            f=b/'capture'/f'{backend}-{i}-{label}.bin';ref=dict(binding=d.bind(f),shape=shape,dtype='float32',bytes=f.stat().st_size)
            assert row['outputs'][label]==dict(shape=shape,dtype='float32',sha256=d.bind(f)['sha256'],bytes=f.stat().st_size);raw[label]=ref
        parity=heads.compare(heads.read_heads(strict['records'][i-1]['raw'],c['h'],c['w']),heads.read_heads(raw,c['h'],c['w']),c['h'],c['w']);rows.append(dict(backend=backend,ordinal=i,input=c['input'],raw=raw,parity=parity))
    files=[b/'claim.json',*sorted((b/'started').glob('*.json')),*sorted((b/'capture').glob('*'))];events=[d.read(d.bind(f)) for f in (b/'http-events').glob('*.json')];ids=set()
    for f in files:
        meta=d.read(d.bind(b/'metadata'/f'{f.parent.name}-{f.name}.json'));hits=[e for e in events if e['requestId']==meta['requestId']];route='/claim' if f.name=='claim.json' else '/started/'+f.stem.replace('-','/') if f.parent.name=='started' else '/capture/'+f.name
        assert 1<=len(hits)<=2 and meta['sha256']==d.bind(f)['sha256'] and meta['bytes']==f.stat().st_size
        assert all(e['path']==route and e['declaredSha256']==meta['sha256'] and e['declaredBytes']==meta['bytes'] for e in hits);ids.add(meta['requestId'])
    assert len(files)==6*p['count']+2 and ids=={e['requestId'] for e in events}
    summary={backend:dict(inputs=p['count'],passed=sum(heads.passed(r['parity']) for r in rows if r['backend']==backend),maxAbsoluteDifference=max(r['parity']['maxAbsoluteDifference'] for r in rows if r['backend']==backend),decodedPixels=[r['parity']['decodedMaskPixelDifference'] for r in rows if r['backend']==backend]) for backend in ['cpuOrt','wasm','webgpu']};gate=all(v['passed']==p['count'] for v in summary.values())
    report=dict(ok=True,reader=d.bind(__file__),plan=d.bind(O/'plan.json'),decision=('cuda_style_affine_'+p['scope']+'_pass') if gate else ('cuda_style_affine_'+p['scope']+'_failed'),records=rows,summary=summary,
                allFrozenInputsRawCompleteFinite=True,fullIndependentControlGatePassed=(gate and p['scope']=='independent'),fullLearnedDeploymentGatePassed=(gate and p['scope']=='learned'),learnedInputs=(3*p['count'] if p['scope']=='learned' else 0),submissionCounters=live['submissionCounters'],actualNetworkBytes=None,formalReleaseAllowed=False,productHold=True)
    f=O/'report.json'
    if f.exists():assert d.read(d.bind(f))==report
    else:d.new(f,report)
    print(json.dumps(dict(ok=True,decision=report['decision'],summary=summary)),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['cpu','verify-cpu','browser','verify']);a.add_argument('--root',type=Path,required=True);v=a.parse_args();O=v.root.resolve()
    if v.mode=='verify-cpu':
        p,strict,r=reconstruct_cpu();print(json.dumps(dict(ok=True,cpuFullGatePassed=r['cpuFullGatePassed'],inputs=p['count'],newInputs=0)))
    else:{'cpu':cpu,'browser':browser,'verify':verify}[v.mode]()
