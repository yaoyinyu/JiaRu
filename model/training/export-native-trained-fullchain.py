"""真实训练权重原尺寸完整图导出及严格CUDA/CPU ORT两头验收。"""
import argparse
import importlib.util
import json
import os
import traceback
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('learned_fullchain_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
h=d.load(HERE/'export-pretrained-native-candidate-v2.py','learned_fullchain_heads')
repair=d.load(HERE/'onnx-native-fullchain-repairs.py','learned_fullchain_repair')


def validate(path):
    p=d.read(d.bind(path));assert p['exporter']==d.bind(__file__) and p['purpose']=='learned_native_fullchain_synthetic_interface'
    for ref in p['inputs'].values():d.checked(ref)
    control=d.read(p['inputs']['independentFullControl']);assert control['fullIndependentControlGatePassed'] and control['all27Inputs54RawCompleteFinite']
    assert all(v['passed']==9 for v in control['summary'].values())
    assert len(p['cases'])==9 and [c['ordinal'] for c in p['cases']]==list(range(1,10))
    assert p['stateTensorCount']==300 and p['requiredAbsoluteDifference']==1e-4 and p['requiredDecodedPixelDifference']==0
    assert p['budget']==dict(exportTraceMax=3,cuda=9,cpuOrt=9,wasm=9,webgpu=9,optimizerSteps=0,protected=0,newChatImages=0)
    for c in p['cases']:h.input_array(c['input'],c['h'],c['w']);assert c['sourceImageIdentity'] is None
    model,net,state=h.model_from_plan(p,p['inputs']['learnedWeights']);return p,model,net,state


def execute(path,root):
    import torch
    import onnx
    import onnxruntime as ort
    p,model,net,state=validate(path);ready=d.read(d.bind(path.with_name('readiness.json')));assert ready['ok'] and ready['plan']==d.bind(path)
    root.mkdir();(root/'raw').mkdir();j=h.Journal(root);before=h.digest(state);rows=[]
    d.new(root/'attempt.json',dict(plan=d.bind(path),pid=os.getpid(),resumeAllowed=False))
    try:
        torch.set_num_threads(4);torch.set_float32_matmul_precision('highest');torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        assert torch.cuda.is_available()
        example=p['cases'][2];x=torch.from_numpy(h.input_array(example['input'],example['h'],example['w']))
        def started(module,args):j.begin('exportTrace',p['budget']['exportTraceMax'],shape=[1,4,example['h'],example['w']])
        handle=model.register_forward_pre_hook(started);rawpath=root/'trained-raw.onnx'
        try:
            with torch.inference_mode():torch.onnx.export(model,x,str(rawpath),input_names=['candidate'],output_names=['mask_logits','presence_logit'],dynamic_axes={'candidate':{2:'height',3:'width'},'mask_logits':{2:'height',3:'width'}},opset_version=18,dynamo=False,do_constant_folding=False)
        finally:handle.remove()
        raw=onnx.load(rawpath);onnx.checker.check_model(raw,full_check=True);repaired,proof=repair.transform(raw)
        candidate=root/'candidate-native.onnx';onnx.save(repaired,candidate)
        d.new(root/'graph-proof.json',dict(ok=True,raw=d.bind(rawpath),candidate=d.bind(candidate),repair=d.bind(HERE/'onnx-native-fullchain-repairs.py'),proof=proof,
                                          completeInputs=[v.name for v in repaired.graph.input],completeOutputs=[v.name for v in repaired.graph.output]))
        assert [v.name for v in repaired.graph.input]==['candidate'] and [v.name for v in repaired.graph.output]==['mask_logits','presence_logit']
        opts=ort.SessionOptions();opts.log_severity_level=3;opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session=ort.InferenceSession(str(candidate),sess_options=opts,providers=['CPUExecutionProvider'])
        model=model.cuda().eval().requires_grad_(False);torch.set_num_threads(4);torch.cuda.reset_peak_memory_stats()
        d.new(root/'environment.json',dict(torch=torch.__version__,onnx=onnx.__version__,ort=ort.__version__,cudaTF32=torch.backends.cuda.matmul.allow_tf32,cudnnTF32=torch.backends.cudnn.allow_tf32,
                                          actualTorchThreads=torch.get_num_threads(),float32Matmul=torch.get_float32_matmul_precision(),cpuProviders=session.get_providers(),cpuThreads=4,interThreads=1,graphOptimization='disabled'))
        for c in p['cases']:
            i,height,width=c['ordinal'],c['h'],c['w'];x=h.input_array(c['input'],height,width)
            j.begin('cuda',9,ordinal=i)
            with torch.inference_mode():a,b=model(torch.from_numpy(x).cuda())
            cuda=h.save_heads(root/'raw',f'{i:03d}-cuda',a,b,height,width);j.event('model_input_confirmed',kind='cuda',ordinal=i,raw=cuda)
            if torch.cuda.max_memory_allocated()>4294967296:raise MemoryError('CUDA allocated guard exceeded')
            j.begin('cpuOrt',9,ordinal=i);a,b=session.run(None,{'candidate':x});cpu=h.save_heads(root/'raw',f'{i:03d}-cpuOrt',a,b,height,width);j.event('model_input_confirmed',kind='cpuOrt',ordinal=i,raw=cpu)
            parity=h.compare(h.read_heads(cuda,height,width),h.read_heads(cpu,height,width),height,width);rows.append(dict(ordinal=i,input=c['input'],cuda=cuda,cpuOrt=cpu,parity=parity))
            print(json.dumps(dict(learnedCpu=i,maxAbs=parity['maxAbsoluteDifference'],passed=h.passed(parity))),flush=True)
        assert before==h.digest(model.state_dict());gate=all(h.passed(r['parity']) for r in rows)
        report=dict(ok=True,exporter=d.bind(__file__),plan=d.bind(path),decision='learned_cpu_full9_pass_browser_pending' if gate else 'learned_cpu_full9_failed',
                    onnx=d.bind(candidate),graphProof=d.bind(root/'graph-proof.json'),environment=d.bind(root/'environment.json'),records=rows,actualBudget=j.counts,
                    stateHashesBefore=before,stateHashesAfter=h.digest(model.state_dict()),cpuFull9GatePassed=gate,learnedForwardCalls=sum(j.counts.values()),
                    peakCudaAllocatedBytes=torch.cuda.max_memory_allocated(),qualityQualificationAllowed=False,formalReleaseAllowed=False,productHold=True)
        d.new(root/'report.json',report);term=j.event('closed',report=d.bind(root/'report.json'));d.new(root/'terminal.json',term)
    except BaseException as e:
        d.new(root/'failure.json',dict(ok=False,type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),actualBudget=j.counts,confirmedRows=rows,resumeAllowed=False))
        term=j.event('failed',failure=d.bind(root/'failure.json'));d.new(root/'terminal.json',term);raise


def reconstruct(path,root):
    p,model,net,state=validate(path);r=d.read(d.bind(root/'report.json'));assert r['plan']==d.bind(path) and r['exporter']==d.bind(__file__)
    import onnx
    proof=d.read(r['graphProof']);graph,expected=repair.transform(onnx.load(d.checked(proof['raw'])));assert expected==proof['proof'] and graph.SerializeToString()==d.checked(r['onnx']).read_bytes()
    assert len(r['records'])==9 and len(list((root/'raw').glob('*.bin')))==36
    for c,row in zip(p['cases'],r['records'],strict=True):
        assert row['ordinal']==c['ordinal'] and row['input']==c['input']
        assert row['parity']==h.compare(h.read_heads(row['cuda'],c['h'],c['w']),h.read_heads(row['cpuOrt'],c['h'],c['w']),c['h'],c['w'])
    events=[d.read(d.bind(f)) for f in sorted((root/'events').glob('*.json'))]
    assert [e['sequence'] for e in events]==list(range(1,len(events)+1)) and events[-1]==d.read(d.bind(root/'terminal.json')) and events[-1]['phase']=='closed'
    for kind in ['cuda','cpuOrt']:
        for phase in ['model_input_started','model_input_confirmed']:assert [e['ordinal'] for e in events if e['phase']==phase and e['kind']==kind]==list(range(1,10))
    trace=sum(e['phase']=='model_input_started' and e['kind']=='exportTrace' for e in events)
    assert 1<=trace<=3 and r['actualBudget']==dict(exportTrace=trace,cuda=9,cpuTorch=0,cpuOrt=9) and events[-1]['modelInputsStarted']==r['actualBudget']
    assert r['stateHashesBefore']==r['stateHashesAfter']==h.digest(state) and r['learnedForwardCalls']==18+trace
    assert r['cpuFull9GatePassed']==all(h.passed(row['parity']) for row in r['records'])
    return p,r


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--plan',type=Path,required=True);a.add_argument('--root',type=Path,required=True);a.add_argument('--verify',action='store_true');v=a.parse_args()
    if v.verify:
        p,r=reconstruct(v.plan.resolve(),v.root.resolve());print(json.dumps(dict(ok=True,cpuFull9GatePassed=r['cpuFull9GatePassed'],newInputs=0)))
    else:execute(v.plan.resolve(),v.root.resolve())
