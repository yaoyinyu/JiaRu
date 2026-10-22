"""训练域原尺寸部署保真；冻结完整角色/原输入、四端预算与独占RAW。"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import numpy as np
import onnx

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('real_input_deployment_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
h=d.load(HERE/'export-pretrained-native-candidate-v2.py','real_input_deployment_heads')
chain=d.load(HERE/'onnx-native-fullchain-repairs.py','real_input_deployment_chain')
presence=d.load(HERE/'onnx-blocked-presence-reductions.py','real_input_deployment_presence')


def checked_graph(template,base_report,candidate):
    cpu=d.read(base_report['cpuReport']);proof=d.read(cpu['graphProof']);raw=onnx.load(d.checked(proof['raw']));graph,first=chain.transform(raw);graph,second=presence.transform(graph)
    if graph.SerializeToString()!=d.checked(candidate).read_bytes():raise ValueError('actual learned graph chain reconstruction_mismatch')
    return dict(raw=proof['raw'],first=first,second=second,originalFullGraphInverseBytes=True,allOriginalWeightsBiasThresholdsUnchanged=True)


def unpack_record(row,net):
    path=d.checked(row['input']);height,width=row['nativeSize']
    with np.load(path,allow_pickle=False) as z:
        rgb=z['nativeRgb'];seed=z['nativeCoarse'];target=z['nativeTarget']
        if rgb.dtype!=np.uint8 or seed.dtype!=np.uint8 or target.dtype!=np.uint8 or rgb.shape!=(height,width,3) or seed.shape!=target.shape!=(height,width):raise ValueError('original native NPZ domain')
        values=net.pack(rgb,seed)
        if values.shape!=(4,height,width) or values.dtype!=np.float32 or not np.isfinite(values).all():raise ValueError('original pack domain')
        if hashlib.sha256(values.tobytes()).hexdigest()!=row['packedSha256'] or hashlib.sha256(target.tobytes()).hexdigest()!=row['targetSha256']:raise ValueError('original native pack/target bytes mismatch')
    return values


def prepare(requirements,root):
    req=d.read(d.bind(requirements));assert req['purpose'].startswith('learned_train') and req['purpose'].endswith('_real_input_deployment_fidelity') and req['budgetConsumed']==0
    result=d.read(req['prerequisite']);assert result['fullLearnedSyntheticInterfacePassed'] and all(v['passed']==9 for v in result['summary'].values())
    parent=d.read(result['plan']);base=d.read(parent['sourceReport']);template=d.read(base['plan'])
    assert req['learnedWeights']==template['inputs']['learnedWeights'] and req['candidate']==parent['onnx'] and template['stateTensorCount']==300
    ledger=d.read(req['roleLedger']);materialization=d.read(req['sourceMaterialization']);records=req['records'];n=len(records)
    positive=sum(r['presenceTarget'] for r in records);excluded=len(ledger['excludedConsumed8']);source_count=len({d.key(r['candidateIdentity']['identity']) for r in records})
    assert req['denominator']==dict(sourceImages=source_count,trainInputs=n,positive=positive,conditionalReject=n-positive,excludedConsumed=excluded,backendInputs=4*n,rawHeads=8*n)
    assert len(materialization['records'])==len(ledger['all162UpstreamAndCurrentRoles'])==n+excluded
    assert [r['ordinal'] for r in records]==ledger['selectedTrain154']==list(range(1,n+1))
    upstream={r['ordinal']:r for r in materialization['records']};seen=set()
    guard=d.load(HERE/'train-yolo-seg.py','real_input_deployment_guard');guard.install_read_only_ultralytics_image_check()
    cleanup_roots={root,*[Path(r['input']['path']).parent for r in records]};removed=[]
    try:
        model,net,state=h.model_from_plan(template,req['learnedWeights']);digests=h.digest(state);assert len(digests)==300
        graph_proof=checked_graph(template,base,req['candidate']);cases=[];(root/'inputs').mkdir()
        for row in records:
            original=upstream[row['ordinal']];assert original['developmentTrainingAllowed'] and original['cohort']!='heldoutDevelopment8'
            for key in ['candidateIdentity','input','packedSha256','nativeSize','presenceTarget','cohort','sourceImage','annotation','sourceApproval','cropBox','targetSha256']:assert row[key]==original[key],key
            ci=row['candidateIdentity'];key=(*d.key(ci['identity']),ci['sourceGroup'],ci['candidateIndex'],ci['coarseMaskSha256']);assert key not in seen;seen.add(key)
            assert ci['identity']['split']=='train' and row['currentUse']=='training_domain_deployment_fidelity_only'
            for ref in [row['sourceImage'],row['annotation'],row['sourceApproval'],ci['stageARaw']]:d.checked(ref)
            values=unpack_record(row,net);height,width=row['nativeSize'];assert 16<=min(height,width)<=max(height,width)<=1536
            assert row['cropBox'][2]-row['cropBox'][0]==width and row['cropBox'][3]-row['cropBox'][1]==height
            path=root/'inputs'/f"{row['ordinal']:03d}.bin"
            with path.open('xb') as stream:stream.write(values.tobytes());stream.flush();os.fsync(stream.fileno())
            ref=d.bind(path);assert ref['sha256']==row['packedSha256'];cases.append(dict(ordinal=row['ordinal'],h=height,w=width,input=ref,record=row))
        assert all(not r['developmentTrainingAllowed'] and r['cohort']=='heldoutDevelopment8' for r in ledger['excludedConsumed8'])
        assert sum(r['presenceTarget'] for r in records)==positive
        # 原九尺寸完整资源包络覆盖16..1536；本清单最大517。静态活跃上限不授完整进程峰值。
        upper=max(r['estimatedActiveUpperBytes'] for r in parent['resources']);assert upper<2147483648 and max(max(c['h'],c['w']) for c in cases)==req['storage']['maximumInputSide']
        resources=[dict(ordinal=c['ordinal'],h=c['h'],w=c['w'],inheritedFull1536LiveUpperBytes=upper,staticActiveUpperBytes=upper,insideControlledDomain=True,fullProcessPeakQualified=False) for c in cases]
        rawbytes=4*sum(4*c['h']*c['w']+4 for c in cases);assert rawbytes==req['storage']['rawHeadBytes'] and shutil.disk_usage(root).free>rawbytes+1073741824
        d.new(root/'graph-proof.json',dict(ok=True,proof=graph_proof,candidate=req['candidate'],sourceModelPlan=base['plan']))
        plan=dict(purpose='training_domain_native_full_deployment_fidelity',runner=d.bind(__file__),requirements=d.bind(requirements),prerequisite=req['prerequisite'],sourceModelPlan=base['plan'],sourceModelReport=parent['sourceReport'],learnedWeights=req['learnedWeights'],model=req['candidate'],graphProof=d.bind(root/'graph-proof.json'),
                  roleLedger=req['roleLedger'],sourceMaterialization=req['sourceMaterialization'],readOnlyGuard=d.bind(HERE/'train-yolo-seg.py'),cases=cases,stateTensorCount=300,stateHashes=digests,resources=resources,budget=req['proposedBudget'],denominator=req['denominator'],
                  budgetKeyMapping=dict(cuda='strictCuda',cpuOrt='cpuOrt',wasm='wasm',webgpu='webgpu'),outputs=dict(mask='mask_logits',presence='presence_logit'),
                  cpuPolicy=dict(strictFloat32=True,cudaTF32=False,cudnnTF32=False,torchThreads=4,ortIntraThreads=4,ortInterThreads=1,ortExecution='sequential',graphOptimization='disabled',cudaAllocatedGuardBytes=4294967296),
                  browserPolicy=dict(priorBrowserPlan=d.bind(Path(result['plan']['path']).parent/'browser/plan.json'),oneSessionPerBackend=True,wasmThreads=1,sameIsolatedRuntime=True,graphOptimization='disabled',realClock=True,retrySameUploadMax=2),
                  requiredAbsoluteDifference=1e-4,requiredDecodedPixelDifference=0,requiredPresenceDecisionDifference=0,hypothesis=req['hypothesis'],continueCondition=req['continueCondition'],stop=req['stop'],sourceIndependentQualificationAllowed=False,qualityQualificationAllowed=False,fullProcessPeakQualified=False,formalReleaseAllowed=False,productHold=True)
        d.new(root/'plan.json',plan);d.new(root/'readiness.json',dict(ok=True,plan=d.bind(root/'plan.json'),complete300StateStrictLoaded=True,allInputPackBytesAndRolesVerified=True,excludedConsumedPixelReads=0,graphChainReconstructedByteExact=True,allSizesInsideFullIndependentControlDomain=True,maximumStaticActiveBytes=upper,diskFreeBytes=shutil.disk_usage(root).free,newModelInputs=0,fullProcessPeakQualified=False,productHold=True))
        print(json.dumps(dict(ok=True,inputs=n,positive=positive,reject=n-positive,excluded=excluded,budget=plan['budget'],staticUpperBytes=upper,newModelInputs=0)),flush=True)
    finally:
        for path in sorted(cleanup_roots):removed.extend(guard.remove_ultralytics_label_caches(path))


def validate(root,load_state=False):
    p=d.read(d.bind(root/'plan.json'));assert p['runner']==d.bind(__file__);ready=d.read(d.bind(root/'readiness.json'));assert ready['ok'] and ready['plan']==d.bind(root/'plan.json')
    req=d.read(p['requirements']);result=d.read(p['prerequisite']);assert result['fullLearnedSyntheticInterfacePassed'] and req['candidate']==p['model'] and req['learnedWeights']==p['learnedWeights']
    template=d.read(p['sourceModelPlan']);base=d.read(p['sourceModelReport']);proof=d.read(p['graphProof']);assert checked_graph(template,base,p['model'])==proof['proof']
    ledger=d.read(p['roleLedger']);n=len(p['cases']);assert len(ledger['all162UpstreamAndCurrentRoles'])==n+len(ledger['excludedConsumed8']) and [c['ordinal'] for c in p['cases']]==ledger['selectedTrain154']==list(range(1,n+1))
    for c in p['cases']:
        assert c['record']['developmentTrainingAllowed'] and c['record']['cohort']!='heldoutDevelopment8' and c['input']['sha256']==c['record']['packedSha256']
        h.input_array(c['input'],c['h'],c['w'])
    model=net=state=None
    if load_state:
        model,net,state=h.model_from_plan(template,p['learnedWeights']);assert len(state)==300 and h.digest(state)==p['stateHashes']
    return p,model,net,state


def execute_cpu(root):
    guard=d.load(HERE/'train-yolo-seg.py','real_execution_guard');guard.install_read_only_ultralytics_image_check();p,model,net,state=validate(root,load_state=True)
    import torch
    import onnxruntime as ort
    run=root/'cpu';run.mkdir();(run/'raw').mkdir();journal=h.Journal(run);rows=[];n=len(p['cases']);before=h.digest(state)
    d.new(run/'attempt.json',dict(plan=d.bind(root/'plan.json'),pid=os.getpid(),resumeAllowed=False))
    try:
        options=ort.SessionOptions();options.log_severity_level=3;options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session=ort.InferenceSession(str(d.checked(p['model'])),sess_options=options,providers=['CPUExecutionProvider'])
        assert torch.cuda.is_available();torch.set_float32_matmul_precision('highest');torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        model=model.cuda().eval().requires_grad_(False);torch.set_num_threads(4);torch.cuda.reset_peak_memory_stats()
        d.new(run/'environment.json',dict(torch=torch.__version__,onnxruntime=ort.__version__,cudaTF32=torch.backends.cuda.matmul.allow_tf32,cudnnTF32=torch.backends.cudnn.allow_tf32,float32Matmul=torch.get_float32_matmul_precision(),actualTorchThreads=torch.get_num_threads(),cpuOrtThreads=session.get_session_options().intra_op_num_threads,interThreads=session.get_session_options().inter_op_num_threads,providers=session.get_providers(),graphOptimization='disabled',cudaDevice=torch.cuda.get_device_name()))
        for c in p['cases']:
            i,height,width=c['ordinal'],c['h'],c['w'];x=h.input_array(c['input'],height,width);journal.begin('cuda',n,ordinal=i,input=c['input']);start=time.perf_counter()
            with torch.inference_mode():a,b=model(torch.from_numpy(x).cuda())
            cuda=h.save_heads(run/'raw',f'{i:03d}-cuda',a,b,height,width);journal.event('model_input_confirmed',kind='cuda',ordinal=i,raw=cuda)
            if torch.cuda.max_memory_allocated()>p['cpuPolicy']['cudaAllocatedGuardBytes']:raise MemoryError('strict CUDA allocated guard exceeded')
            journal.begin('cpuOrt',n,ordinal=i,input=c['input']);a,b=session.run(list(p['outputs'].values()),{'candidate':x});cpu=h.save_heads(run/'raw',f'{i:03d}-cpuOrt',a,b,height,width);journal.event('model_input_confirmed',kind='cpuOrt',ordinal=i,raw=cpu)
            reference=h.read_heads(cuda,height,width);actual=h.read_heads(cpu,height,width);parity=h.compare(reference,actual,height,width)
            rows.append(dict(ordinal=i,input=c['input'],cuda=cuda,cpuOrt=cpu,parity=parity,headMaxAbsoluteDifference={k:float(np.abs(a-b).max()) for k,a,b in zip(['mask','presence'],reference,actual,strict=True)}))
            if i==1 or i%10==0 or i==n:print(json.dumps(dict(cpuConfirmed=i,total=n,passed=sum(h.passed(row['parity']) for row in rows),maxAbs=max(row['parity']['maxAbsoluteDifference'] for row in rows))),flush=True)
        assert before==h.digest(model.state_dict())==p['stateHashes'];gate=all(h.passed(row['parity']) for row in rows)
        report=dict(ok=True,runner=d.bind(__file__),plan=d.bind(root/'plan.json'),decision=f'real_input_cpu_full{n}_pass_browser_pending' if gate else f'real_input_cpu_full{n}_failed',records=rows,actualBudget=journal.counts,stateHashesBefore=before,stateHashesAfter=h.digest(model.state_dict()),cpuFullGatePassed=gate,peakCudaAllocatedBytes=torch.cuda.max_memory_allocated(),qualityQualificationAllowed=False,formalReleaseAllowed=False,productHold=True)
        d.new(run/'report.json',report);d.new(run/'terminal.json',journal.event('closed',report=d.bind(run/'report.json')))
    except BaseException as error:
        d.new(run/'failure.json',dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),actualBudget=journal.counts,confirmedRecords=rows,resumeAllowed=False));d.new(run/'terminal.json',journal.event('failed',failure=d.bind(run/'failure.json')));raise
    finally:
        for path in {root,*[Path(c['record']['input']['path']).parent for c in p['cases']]}:guard.remove_ultralytics_label_caches(path)


def reconstruct_cpu(root):
    p,_,_,_=validate(root);run=root/'cpu';r=d.read(d.bind(run/'report.json'));n=len(p['cases']);assert r['plan']==d.bind(root/'plan.json') and r['runner']==d.bind(__file__) and len(r['records'])==n
    assert len(list((run/'raw').glob('*.bin')))==4*n and r['actualBudget']==dict(exportTrace=0,cuda=n,cpuTorch=0,cpuOrt=n)
    assert r['stateHashesBefore']==r['stateHashesAfter']==p['stateHashes']
    events=[d.read(d.bind(f)) for f in sorted((run/'events').glob('*.json'))];assert [e['sequence'] for e in events]==list(range(1,len(events)+1)) and events[-1]==d.read(d.bind(run/'terminal.json')) and events[-1]['phase']=='closed'
    for kind in ['cuda','cpuOrt']:
        for phase in ['model_input_started','model_input_confirmed']:assert [e['ordinal'] for e in events if e['phase']==phase and e['kind']==kind]==list(range(1,n+1))
    for c,row in zip(p['cases'],r['records'],strict=True):
        assert row['ordinal']==c['ordinal'] and row['input']==c['input'];reference=h.read_heads(row['cuda'],c['h'],c['w']);actual=h.read_heads(row['cpuOrt'],c['h'],c['w'])
        assert row['parity']==h.compare(reference,actual,c['h'],c['w']) and row['headMaxAbsoluteDifference']=={k:float(np.abs(a-b).max()) for k,a,b in zip(['mask','presence'],reference,actual,strict=True)}
        for kind,key in [('cuda','cuda'),('cpuOrt','cpuOrt')]:
            event=next(e for e in events if e['phase']=='model_input_confirmed' and e['kind']==kind and e['ordinal']==c['ordinal']);assert event['raw']==row[key]
    assert r['cpuFullGatePassed']==all(h.passed(row['parity']) for row in r['records'])
    return p,r


def prepare_browser(root):
    p,r=reconstruct_cpu(root);assert r['cpuFullGatePassed'],'CPU full gate failed; browser budget not admitted'
    prior=d.read(p['browserPolicy']['priorBrowserPlan']);server=d.load(HERE/'serve-native-two-head-controls.py','real_input_browser_server');page=server.HTML.replace('完整图两头独立控制','真实训练域部署保真').replace('仅合成数组；不展示预测图，产品保持HOLD。','仅现有训练域输入；不展示图片，不能作为新来源质量，产品保持HOLD。')
    b=root/'browser';b.mkdir();(b/'browser.html').write_bytes(page.encode('utf8'));(b/'syntax-check.js').write_bytes(page.split('<script>')[1].split('</script>')[0].encode('utf8'));subprocess.run(['node.exe','--check',str(b/'syntax-check.js')],check=True)
    assets={'model':p['model'],**{f"input-{c['ordinal']}":c['input'] for c in p['cases']}};schedule=[dict(backend=backend,ordinal=c['ordinal'],h=c['h'],w=c['w'],input=dict(url=f"/assets/input-{c['ordinal']}",sha256=c['input']['sha256'])) for backend in ['wasm','webgpu'] for c in p['cases']]
    bp={**prior,'operatorPlan':d.bind(root/'plan.json'),'server':d.bind(HERE/'serve-native-two-head-controls.py'),'html':d.bind(b/'browser.html'),'assets':assets,'schedule':schedule,'outputs':p['outputs'],'runtimeFiles':prior['runtimeFiles']}
    for ref in [*assets.values(),*bp['runtimeFiles'].values()]:d.checked(ref)
    d.new(b/'plan.json',bp);d.new(b/'config.json',dict(planSha256=d.bind(b/'plan.json')['sha256'],model=dict(url='/assets/model',sha256=p['model']['sha256']),schedule=schedule,outputs=p['outputs'],expectedUserAgent=bp['expectedUserAgent'],expectedAdapter=bp['expectedAdapter'],requiredDeviceLimits=bp['requiredDeviceLimits']))
    for name in ['capture','started','metadata','http-events']:(b/name).mkdir()
    d.new(root/'cpu-replay.json',dict(ok=True,reader=d.bind(__file__),plan=d.bind(root/'plan.json'),report=d.bind(root/'cpu/report.json'),allCpuAndCudaInputsAndRawCompleteFinite=True,cpuFullGatePassed=True,newInputs=0,productHold=True))
    print(json.dumps(dict(ok=True,cpuFullGatePassed=True,browserInputs=len(schedule),browserRawHeads=2*len(schedule))),flush=True)


def verify_all(root):
    p,cr=reconstruct_cpu(root);b=root/'browser';bp=d.read(d.bind(b/'plan.json'));live=d.read(d.bind(b/'capture/live-browser.json'));claim=d.read(d.bind(b/'claim.json'));n=len(p['cases'])
    assert bp['operatorPlan']==d.bind(root/'plan.json') and bp['assets']['model']==p['model'] and bp['html']==d.bind(b/'browser.html') and bp['server']==d.bind(HERE/'serve-native-two-head-controls.py')
    for ref in [*bp['assets'].values(),*bp['runtimeFiles'].values()]:d.checked(ref)
    assert live['phase']=='closed' and not live['errors'] and live['crossOriginIsolated'] and not live['virtualTime'] and live['claim']==claim['claim'] and live['planSha256']==d.bind(b/'plan.json')['sha256']
    assert live['userAgent']==bp['expectedUserAgent'] and live['adapterInfo']==bp['expectedAdapter'] and live['webgpuDevice']['grantedLimits']==bp['requiredDeviceLimits']
    expected=[(backend,c['ordinal']) for backend in ['wasm','webgpu'] for c in p['cases']];assert expected==[(v['backend'],v['ordinal']) for v in live['started']]==[(v['backend'],v['ordinal']) for v in live['records']]
    assert len(list((b/'started').glob('*.json')))==2*n and len(list((b/'capture').glob('*.bin')))==4*n
    rows=[dict(backend='cpuOrt',ordinal=v['ordinal'],input=v['input'],raw=v['cpuOrt'],parity=v['parity'],headMaxAbsoluteDifference=v['headMaxAbsoluteDifference']) for v in cr['records']]
    for v in live['records']:
        backend,i=v['backend'],v['ordinal'];c=p['cases'][i-1];rid=claim['claim']+'-'+backend+'-'+str(i);assert v['requestId']==rid
        assert d.read(d.bind(b/'started'/f'{backend}-{i}.json'))==dict(claim=claim['claim'],requestId=rid,backend=backend,ordinal=i,h=c['h'],w=c['w'],inputSha256=c['input']['sha256'])
        raw={}
        for key,shape in [('mask',[1,1,c['h'],c['w']]),('presence',[1,1])]:
            f=b/'capture'/f'{backend}-{i}-{key}.bin';ref=dict(binding=d.bind(f),shape=shape,dtype='float32',bytes=f.stat().st_size);raw[key]=ref
            assert v['outputs'][key]==dict(shape=shape,dtype='float32',bytes=ref['bytes'],sha256=ref['binding']['sha256'])
        reference=h.read_heads(cr['records'][i-1]['cuda'],c['h'],c['w']);actual=h.read_heads(raw,c['h'],c['w']);rows.append(dict(backend=backend,ordinal=i,input=c['input'],raw=raw,parity=h.compare(reference,actual,c['h'],c['w']),headMaxAbsoluteDifference={k:float(np.abs(a-b).max()) for k,a,b in zip(['mask','presence'],reference,actual,strict=True)}))
    files=[b/'claim.json',*sorted((b/'started').glob('*.json')),*sorted((b/'capture').glob('*'))];events=[d.read(d.bind(f)) for f in (b/'http-events').glob('*.json')];ids=set()
    for f in files:
        meta=d.read(d.bind(b/'metadata'/f'{f.parent.name}-{f.name}.json'));hits=[e for e in events if e['requestId']==meta['requestId']];route='/claim' if f.name=='claim.json' else '/started/'+f.stem.replace('-','/') if f.parent.name=='started' else '/capture/'+f.name
        assert 1<=len(hits)<=2 and meta['sha256']==d.bind(f)['sha256'] and meta['bytes']==f.stat().st_size and all(e['path']==route and e['declaredSha256']==meta['sha256'] and e['declaredBytes']==meta['bytes'] for e in hits);ids.add(meta['requestId'])
    assert len(files)==6*n+2 and ids=={e['requestId'] for e in events}
    summary={backend:dict(inputs=n,passed=sum(h.passed(v['parity']) for v in rows if v['backend']==backend),maxAbsoluteDifference=max(v['parity']['maxAbsoluteDifference'] for v in rows if v['backend']==backend),decodedPixelDifferences=sum(v['parity']['decodedMaskPixelDifference'] for v in rows if v['backend']==backend),presenceDecisionMismatches=sum(not v['parity']['presenceDecisionMatched'] for v in rows if v['backend']==backend)) for backend in ['cpuOrt','wasm','webgpu']}
    gate=all(v['passed']==n for v in summary.values());value=dict(ok=True,reader=d.bind(__file__),plan=d.bind(root/'plan.json'),cpuReport=d.bind(root/'cpu/report.json'),records=rows,summary=summary,allBackendInputsAndRawCompleteFinite=True,realInputDeploymentFidelityPassed=gate,
          decision=f'real_training_domain_full{n}_deployment_pass' if gate else f'real_training_domain_full{n}_deployment_failed',qualityQualificationAllowed=False,sourceIndependentQualificationAllowed=False,fullProcessPeakQualified=False,formalReleaseAllowed=False,productHold=True)
    f=root/'report.json'
    if f.exists():assert d.read(d.bind(f))==value
    else:d.new(f,value)
    print(json.dumps(dict(ok=True,decision=value['decision'],summary=summary)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','cpu','verify-cpu','browser','verify']);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--requirements',type=Path);args=parser.parse_args();root=args.root.resolve()
    if args.mode=='prepare':prepare(args.requirements.resolve(),root)
    elif args.mode=='cpu':execute_cpu(root)
    elif args.mode=='verify-cpu':
        p,r=reconstruct_cpu(root);print(json.dumps(dict(ok=True,cpuFullGatePassed=r['cpuFullGatePassed'],inputs=len(r['records']),newInputs=0)))
    elif args.mode=='browser':prepare_browser(root)
    else:verify_all(root)
