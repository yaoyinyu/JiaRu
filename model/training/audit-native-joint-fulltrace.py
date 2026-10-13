"""完整候选分阶段验真；控制全204通过前禁止任何学得输入。"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import numpy as np
import onnx
import onnxruntime as ort

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('joint_full_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


HTML='<!doctype html><meta charset="utf-8"><title>完整候选逐层单阶段捕获</title><link rel="icon" href="data:,"><h1>完整模型双头保真与逐层捕获</h1><button id="run">执行本阶段WASM/WebGPU各68输入</button><pre id="result">未执行；产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>\nconst hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,\'0\')).join(\'\');\nconst verified=async(path,sha)=>{const r=await fetch(path),b=await r.arrayBuffer();if(!r.ok||hex(await crypto.subtle.digest(\'SHA-256\',b))!==sha)throw Error(\'GET/SHA \'+path);return b;};\nasync function post(path,body,log){const bytes=typeof body===\'string\'?new TextEncoder().encode(body):body,sha=hex(await crypto.subtle.digest(\'SHA-256\',bytes));for(let attempt=0;attempt<3;attempt++){try{const r=await fetch(path,{method:\'POST\',body:bytes}),text=await r.text();if(!r.ok)throw Error(\'HTTP \'+r.status);const a=JSON.parse(text);if(a.sha256!==sha||a.bytes!==bytes.length)throw Error(\'ACK\');return;}catch(error){log.transportErrors.push({path,attempt,error:String(error)});const r=await fetch(\'/status\'+path),text=await r.text();if(r.ok){const a=JSON.parse(text);if(a.sha256!==sha||a.bytes!==bytes.length)throw Error(\'persisted conflict\');log.persistedAckRecoveries++;return;}if(r.status!==404)throw Error(\'status\');log.uploadOnlyRetries++;}}throw Error(\'bounded upload attempts\');}\ndocument.querySelector(\'#run\').onclick=async()=>{document.querySelector(\'#run\').disabled=true;const c=await(await fetch(\'/config.json\')).json(),r={executionSha256:c.executionSha256,configSha256:c.configSha256,kind:c.kind,pageRequestId:crypto.randomUUID(),userAgent:navigator.userAgent,crossOriginIsolated,records:[],startedInputs:[],errors:[],transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0,phase:\'starting\'};try{\nawait post(\'/claim\',JSON.stringify({pageRequestId:r.pageRequestId,executionSha256:c.executionSha256}),r);if(!crossOriginIsolated)throw Error(\'isolation\');ort.env.wasm.wasmPaths=\'/ort/\';ort.env.wasm.numThreads=1;\nconst adapter=await navigator.gpu?.requestAdapter();r.adapterInfo=adapter?{vendor:adapter.info?.vendor,architecture:adapter.info?.architecture,device:adapter.info?.device,description:adapter.info?.description}:null;\nfor(const backend of c.backends){let session;try{session=await ort.InferenceSession.create(await verified(\'/model.onnx\',c.model.sha256),{executionProviders:[backend],graphOptimizationLevel:\'disabled\'});if(session.inputNames.join(\',\')!==\'candidate,resizeRatios\'||session.outputNames.join(\',\')!==c.outputs.map(x=>x.name).join(\',\'))throw Error(\'actual IO\');\nfor(const row of c.cases){r.phase=c.kind+\'/\'+backend+\' \'+row.ordinal+\'/68\';document.querySelector(\'#result\').textContent=r.phase;const input=new Float32Array(await verified(\'/input/\'+row.ordinal+\'.bin\',row.input.sha256));if(input.length!==4*row.h*row.w)throw Error(\'input cardinality\');for(const v of input)if(!Number.isFinite(v))throw Error(\'input finite\');const ratios=new Float32Array([Math.fround(Math.floor(row.h/4)/Math.floor(row.h/2)),Math.fround(Math.floor(row.w/4)/Math.floor(row.w/2)),Math.fround(Math.floor(row.h/2)/row.h),Math.fround(Math.floor(row.w/2)/row.w)]);if(hex(await crypto.subtle.digest(\'SHA-256\',ratios.buffer))!==row.resizeRatios.sha256)throw Error(\'full host vector\');\nconst e={kind:c.kind,backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity,inputSha256:row.input.sha256,resizeRatiosSha256:row.resizeRatios.sha256,targetShape:[1,1,row.h,row.w],pageRequestId:r.pageRequestId,inputRequestId:crypto.randomUUID()};await post(\'/start/\'+backend+\'/\'+row.ordinal,JSON.stringify(e),r);r.startedInputs.push(e);\nconst y=await session.run({candidate:new ort.Tensor(\'float32\',input,row.input.shape),resizeRatios:new ort.Tensor(\'float32\',ratios,[4])}),shapes={};for(const spec of c.outputs){const head=spec.key,name=spec.name,t=y[name],a=new Float32Array(await t.getData()),shape=row.outputShapes[head];if(t.type!==\'float32\'||Array.from(t.dims).join(\',\')!==shape.join(\',\')||a.length!==shape.reduce((x,y)=>x*y,1))throw Error(\'two-head native shape / float32\');for(const v of a)if(!Number.isFinite(v))throw Error(\'two-head finite\');await post(\'/capture/\'+backend+\'-\'+row.ordinal+\'-\'+head+\'.bin\',new Uint8Array(a.buffer),r);shapes[head]=shape;}r.records.push({...e,shapes,dtype:\'float32\'});}\n}finally{if(session)await session.release();}}\nr.captureComplete=r.records.length===c.cases.length*c.backends.length;r.phase=\'terminal\';}catch(error){r.captureComplete=false;r.errors.push(String(error));r.phase=\'terminal-failure\';}await post(\'/terminal\',JSON.stringify(r),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});document.querySelector(\'#result\').textContent=JSON.stringify(r);};</script>'


full=d.load(HERE/'audit-native-joint-fullmodel.py','joint_trace_full_helper')
tensor=full.tensor
save=full.save
event=full.event
validate_event=full.validate_event

def outputs_for(mapping):
    return [{'key':'mask','name':'mask_logits','shapeKey':'mask'}, {'key':'presence','name':'presence_logit','shapeKey':'presence'}]+[{'key':f'layer{i:02d}','name':r['tensor'],'shapeKey':r['module']} for i,r in enumerate(mapping)]

def validate_scope(p):
    if p['purpose']!='joint_graph_full68_nonzero_trace_controls_then_learned_layer_localization' or p['requiredBackends']!=['cpu','wasm','webgpu'] or p['fullCandidateCount']!=68:raise ValueError('full stage scope')
    for k in ('controlTraceInputsPerBackendAllowed','learnedTraceInputsPerBackendAllowedAfterAllControlFidelityGates'):
        if p[k]!=len(p['cases']):raise ValueError('full per-backend budget')
    for k in ('newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):
        if p[k]!=0:raise ValueError('forbidden inputs')
    for k in ('controlFidelityMustBeBitwiseOwnUninstrumentedBothHeadsAll204','learnedFidelityMustBeBitwiseOwnUninstrumentedBothHeadsAll204BeforeAnyLayerConclusions','layerFirstCrossingIsNotRootCauseProof','addOutputsOnlyOriginalGraphByteRestorationRequired','allActualOutputsFloat32FiniteNativeShapeRequired','independentExecutionAndTransportMustBeFrozenBeforeBudget','internalValStillProhibited','oldFailureAndBudgetPreserved','productHold'):
        if p[k] is not True:raise ValueError('required fidelity guard '+k)
    if p['graphOptimizationLevel']!='disabled' or p['requiredFullModelNumericDifference']!=1e-4 or p['requiredFullModelDecodedPixelDifferences']!=0 or p['formalReleaseAllowed']:raise ValueError('preserved quality')

def resources(execution):
    e=d.read(d.bind(execution))
    for ref in (e['auditor'],e['fullAuditor'],e['scope'],e['derivedPreflight']):d.checked(ref)
    if e['auditor']!=d.bind(__file__) or e['fullAuditor']!=d.bind(HERE/'audit-native-joint-fullmodel.py'):raise ValueError('frozen auditors')
    p=d.read(e['scope']);validate_scope(p);derived=d.read(e['derivedPreflight'])
    if not derived['ok'] or derived['scope']!=e['scope']:raise ValueError('independent denominator preflight')
    old_e,old_p,old_models,comparator=full.resources(d.checked(p['inputs']['execution']))
    for ref in p['inputs'].values():d.checked(ref)
    if e['runtimeFiles']!=old_e['runtimeFiles'] or e['expectedEnvironment']!=old_e['expectedEnvironment']:raise ValueError('same runtime/environment')
    control=d.read(p['inputs']['nonzeroControl204']);learned=d.read(p['inputs']['learnedFailure204'])
    if not control['allThreeBackendStageGatesPassed'] or learned['fullModelLearnedGatePassed']:raise ValueError('original current gates')
    specs=outputs_for(p['mapping']);actual_count=0;actual_bytes=0
    if [c['ordinal'] for c in p['cases']]!=list(range(1,len(p['cases'])+1)):raise ValueError('complete original order')
    for kind,ref in p['graphs'].items():
        model=onnx.load(d.checked(ref));original=onnx.load(d.checked(old_models[kind]));restored=copy.deepcopy(model);del restored.graph.output[len(original.graph.output):]
        if restored.SerializeToString()!=original.SerializeToString() or [o.name for o in model.graph.output]!=[r['name'] for r in specs]:raise ValueError('add outputs only / original graph')
        if any(o.type.tensor_type.elem_type!=onnx.TensorProto.FLOAT for o in model.graph.output):raise ValueError('float32 outputs')
        for c,original_case in zip(p['cases'],old_p['cases'],strict=True):
            if c['candidateIdentity']!=original_case['candidateIdentity'] or c['input']!=original_case['input'] or c['resizeRatios']!=original_case['resizeRatios']:raise ValueError('original train identity')
            if c['candidateIdentity']['identity']['split']!='train' or set(c['shapes'])!={r['shapeKey'] for r in specs}:raise ValueError('train shapes')
            for backend in p['requiredBackends']:
                report=control if kind=='control' else learned
                if c['ownUninstrumentedHeads'][kind][backend]!=report['captures'][backend][c['ordinal']-1]['outputs']:raise ValueError('own exact backend heads')
                actual_count+=len(specs);actual_bytes+=sum(math.prod(c['shapes'][r['shapeKey']])*4 for r in specs)
            for ref2 in c['strictCudaLayers'].values():d.checked({k:ref2[k] for k in ('path','sha256')})
    if actual_count!=p['captureCountDerivedFromActualOutputsAndCases'] or actual_bytes!=p['expectedRawCaptureBytes'] or actual_count!=derived['derivedCaptureCount']:raise ValueError('actual capture denominator')
    for c,original_case in zip(p['cases'],old_p['cases'],strict=True):
        c['h']=original_case['h'];c['w']=original_case['w'];c['references']=original_case['references'];c['outputShapes']={r['key']:c['shapes'][r['shapeKey']] for r in specs}
    p['outputs']=specs
    return e,p,p['graphs'],comparator

def fidelity(c,kind,backend,outputs):
    return all(d.checked({k:outputs[h][k] for k in ('path','sha256')}).read_bytes()==d.checked({k:c['ownUninstrumentedHeads'][kind][backend][h][k] for k in ('path','sha256')}).read_bytes() for h in ('mask','presence'))

def control_gate(e):
    root=Path(e['controlRoot']);r=reconstruct(root)
    if r!=d.read(d.bind(root/'report.json')) or r['kind']!='control' or not r['allOwnHeadsBitwiseIdenticalAllBackends'] or r['layerConclusionsAllowed']:raise ValueError('all204 nonzero trace fidelity before learned')
    return d.bind(root/'report.json')

def prepare(execution,root,kind):
    if root.exists():raise ValueError('trace stage consumed; readonly replay only')
    e,p,models,comparator=resources(execution);gate=control_gate(e) if kind=='learned' else None
    import shutil
    expected=p['expectedRawCaptureBytes']//len(models)
    if shutil.disk_usage(root.parent).free<expected*2:raise ValueError('current full stage RAW disk margin')
    root.mkdir(parents=True,exist_ok=False)
    for name in ('cpu','started-inputs','browser-capture','upload-events'):(root/name).mkdir()
    captures=[];starts=0
    try:
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;options.log_severity_level=3
        session=ort.InferenceSession(str(d.checked(models[kind])),sess_options=options,providers=['CPUExecutionProvider'])
        if [v.name for v in session.get_inputs()]!=['candidate','resizeRatios'] or [v.name for v in session.get_outputs()]!=[r['name'] for r in p['outputs']]:raise ValueError('actual CPU IO')
        for c in p['cases']:
            feeds={'candidate':tensor(c['input']),'resizeRatios':tensor(c['resizeRatios'])};ev=event(kind,'cpu',c)
            d.new(root/'cpu'/f'{c["ordinal"]}-start.json',ev|{'startedAtUnixNs':time.time_ns()});starts+=1;ys=session.run(None,feeds);outputs={}
            for spec,a in zip(p['outputs'],ys,strict=True):
                key=spec['key']
                if list(a.shape)!=c['outputShapes'][key]:raise ValueError('CPU actual output shape')
                outputs[key]=save(root/'cpu'/f'{c["ordinal"]}-{key}.bin',a)
            cap=ev|{'outputs':outputs,'ownHeadsBitwiseIdentical':fidelity(c,kind,'cpu',outputs)};captures.append(cap)
            d.new(root/'cpu'/f'{c["ordinal"]}-capture.json',cap)
        d.new(root/'cpu-captures.json',captures)
        config={'executionSha256':d.bind(execution)['sha256'],'kind':kind,'model':models[kind],'cases':p['cases'],'outputs':p['outputs'],'backends':['wasm','webgpu']};d.new(root/'config-base.json',config);config['configSha256']=d.bind(root/'config-base.json')['sha256'];d.new(root/'config.json',config)
        with (root/'browser.html').open('xb') as f:f.write(HTML.encode());f.flush();os.fsync(f.fileno())
        d.new(root/'preparation.json',{'execution':d.bind(execution),'auditor':d.bind(__file__),'kind':kind,'controlGate':gate,'html':d.bind(root/'browser.html'),'config':d.bind(root/'config.json'),'cpuCaptures':d.bind(root/'cpu-captures.json')})
        if not all(r['ownHeadsBitwiseIdentical'] for r in captures):raise ValueError('CPU trace fidelity failed; browser budget zero')
        print(json.dumps({'ok':True,'kind':kind,'cpuCaptured':len(captures),'actualOutputCount':len(p['outputs']),'allCpuOwnHeadsBitwiseIdentical':True,'browserStarted':0}),flush=True)
    except BaseException as error:
        d.new(root/'execution-failure.json',{'ok':False,'error':str(error),'kind':kind,'cpuStarted':starts,'cpuCaptured':len(captures),'browserStarted':0,'optimizerSteps':0,'productHold':True});raise

def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'));e,p,models,comparator=resources(d.checked(prep['execution']));kind=prep['kind'];specs=p['outputs'];keys=[r['key'] for r in specs]
    for ref in (prep['auditor'],prep['html'],prep['config'],prep['cpuCaptures']):d.checked(ref)
    if kind=='learned' and prep['controlGate']!=control_gate(e):raise ValueError('learned control proof')
    config=d.read(prep['config']);base={'executionSha256':prep['execution']['sha256'],'kind':kind,'model':models[kind],'cases':p['cases'],'outputs':specs,'backends':['wasm','webgpu']}
    if d.read(d.bind(root/'config-base.json'))!=base or config!=base|{'configSha256':d.bind(root/'config-base.json')['sha256']}:raise ValueError('frozen actual config')
    live=d.read(d.bind(root/'live-browser.json'))['value'];claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId'];count=len(p['cases']);order=[(b,c) for b in config['backends'] for c in p['cases']]
    if not live['captureComplete'] or live['errors'] or live['phase']!='terminal' or live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['pageRequestId']!=claim or live['kind']!=kind or not live['crossOriginIsolated']:raise ValueError('complete terminal')
    if live['userAgent']!=e['expectedEnvironment']['userAgent'] or live['adapterInfo']!=e['expectedEnvironment']['adapterInfo']:raise ValueError('actual environment')
    if len(live['records'])!=len(order) or len(live['startedInputs'])!=len(order) or len(list((root/'started-inputs').glob('*.json')))!=len(order) or len(list((root/'browser-capture').glob('*.bin')))!=len(order)*len(specs):raise ValueError('whole actual denominator')
    captures={'cpu':d.read(prep['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];ids=[];times=[]
    for ev,record,(backend,c) in zip(live['startedInputs'],live['records'],order,strict=True):
        o=c['ordinal'];validate_event(ev,kind,backend,c,claim);path=root/'started-inputs'/f'{backend}-{o}.json';start=d.read(d.bind(path))
        if start['value']!=ev or (times and start['startedAtUnixNs']<=times[-1]):raise ValueError('start binding/order')
        if {k:record[k] for k in ev}!=ev or record['dtype']!='float32' or record['shapes']!=c['outputShapes']:raise ValueError('all actual output metadata')
        outputs={key:d.bind(root/'browser-capture'/f'{backend}-{o}-{key}.bin')|{'shape':c['outputShapes'][key],'dtype':'float32'} for key in keys}
        captures[backend].append(ev|{'outputs':outputs});events.append(d.bind(path));ids.append(ev['inputRequestId']);times.append(start['startedAtUnixNs'])
    if len(set(ids))!=len(order) or len(list((root/'cpu').glob('*-start.json')))!=count:raise ValueError('unique starts')
    records=[];raw_count=0;raw_bytes=0
    for backend,rows in captures.items():
        if len(rows)!=count or [r['ordinal'] for r in rows]!=list(range(1,count+1)):raise ValueError('full backend denominator')
        for cap,c in zip(rows,p['cases'],strict=True):
            if {k:cap[k] for k in event(kind,backend,c)}!=event(kind,backend,c) or set(cap['outputs'])!=set(keys):raise ValueError('capture identity/cardinality')
            if backend=='cpu':
                start=d.read(d.bind(root/'cpu'/f'{c["ordinal"]}-start.json'))
                if {k:start[k] for k in event(kind,backend,c)}!=event(kind,backend,c) or cap!=d.read(d.bind(root/'cpu'/f'{c["ordinal"]}-capture.json')):raise ValueError('CPU persisted identity')
            for spec in specs:
                ref=cap['outputs'][spec['key']]
                if ref['shape']!=c['outputShapes'][spec['key']]:raise ValueError('native shapes')
                tensor(ref);raw_count+=1;raw_bytes+=math.prod(ref['shape'])*4
            same=fidelity(c,kind,backend,cap['outputs'])
            if backend=='cpu' and cap['ownHeadsBitwiseIdentical']!=same:raise ValueError('CPU fidelity reconstruction')
            records.append({'backend':backend,'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'ownHeadsBitwiseIdentical':same,'originalCudaParity':full.compare(c,kind,cap['outputs'],comparator)})
    expected_count=p['captureCountDerivedFromActualOutputsAndCases']//len(models);expected_bytes=p['expectedRawCaptureBytes']//len(models)
    if raw_count!=expected_count or raw_bytes!=expected_bytes or len(list((root/'cpu').glob('*.bin')))!=count*len(specs):raise ValueError('actual full RAW count/bytes')
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))];expected=['/claim']+[route for b,c in order for route in [f'/start/{b}/{c["ordinal"]}']+[f'/capture/{b}-{c["ordinal"]}-{h}.bin' for h in keys]]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected:raise ValueError('persisted complete upload order')
    all_same=all(r['ownHeadsBitwiseIdentical'] for r in records);conclusions=kind=='learned' and all_same;layer_records=[]
    if conclusions:
        for backend,rows in captures.items():
            for cap,c in zip(rows,p['cases'],strict=True):
                errors=[]
                for spec in specs[2:]:
                    name=spec['shapeKey'];ref=c['strictCudaLayers'][name];a=tensor(ref);b=tensor(cap['outputs'][spec['key']])
                    if a.shape!=b.shape:raise ValueError('strict CUDA layer shape')
                    delta=np.abs(a.astype(np.float64)-b.astype(np.float64));errors.append({'module':name,'shape':list(a.shape),'maxAbs':float(delta.max()),'requiredMaxAbs':1e-4,'aboveGate':bool(delta.max()>1e-4)})
                layer_records.append({'backend':backend,'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'layers':errors,'firstCrossing':next((r['module'] for r in errors if r['aboveGate']),None),'notRootCauseProof':True})
    summary={b:{'candidateCount':count,'fidelityFailedOrdinals':[r['ordinal'] for r in records if r['backend']==b and not r['ownHeadsBitwiseIdentical']]} for b in captures}
    return {'schemaVersion':1,'ok':True,'decision':'joint_fulltrace_stage_reconstructed','kind':kind,'inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json')},'controlGate':prep['controlGate'],'captures':captures,'browserStartEvents':events,'uploadEvents':uploads,'records':records,'summary':summary,'actualRawTensorCount':raw_count,'actualRawBytes':raw_bytes,'allOwnHeadsBitwiseIdenticalAllBackends':all_same,'layerConclusionsAllowed':conclusions,'layerRecords':layer_records,'firstCrossingIsNotRootCauseProof':True,'fullModelLearnedGatePassed':False,'modelInputsConsumedPerBackend':{b:count for b in captures},'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'newChatImageInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'oldFailuresAndConsumedBudgetsPreserved':True,'formalReleaseAllowed':False,'productHold':True}



def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'))
    for ref in prep.values():
        if isinstance(ref,dict) and 'path' in ref:d.checked(ref)
    e,p,models,comparator=resources(d.checked(prep['execution']));kind=prep['kind'];config=d.read(prep['config'])
    if kind=='learned' and prep['controlGate']!=control_gate(e):raise ValueError('learned control gate')
    if (root/'claim.json').exists() or any((root/'started-inputs').iterdir()) or not all(r['ownHeadsBitwiseIdentical'] for r in d.read(prep['cpuCaptures'])):raise ValueError('single stage / CPU gate')
    cases={c['ordinal']:c for c in p['cases']};order=[(b,c['ordinal']) for b in ('wasm','webgpu') for c in p['cases']]
    routes={'/browser.html':prep['html'],'/config.json':prep['config'],'/model.onnx':models[kind]};routes.update({'/ort/'+n:r for n,r in e['runtimeFiles'].items()});routes.update({f'/input/{o}.bin':{k:c['input'][k] for k in ('path','sha256')} for o,c in cases.items()})
    keys=[r['key'] for r in p['outputs']];allowed={f'{b}-{o}-{h}.bin':math.prod(cases[o]['outputShapes'][h])*4 for b,o in order for h in keys};starts=[];captured=set();ids=set();lock=threading.Lock();claim=None;uploads=0
    def stored(route):
        if route=='/claim':return root/'claim.json'
        if route=='/terminal':return root/'live-browser.json'
        if route.startswith('/capture/') and route.removeprefix('/capture/') in allowed:return root/'browser-capture'/route.removeprefix('/capture/')
        parts=route.split('/')
        if len(parts)==4 and parts[1]=='start' and parts[2] in ('wasm','webgpu') and parts[3].isdigit() and (parts[2],int(parts[3])) in order:return root/'started-inputs'/f'{parts[2]}-{int(parts[3])}.json'
        raise ValueError('route whitelist')
    def ack_for(route):
        path=stored(route)
        if not path.exists():return None
        return {'sha256':d.bind(path)['sha256'],'bytes':path.stat().st_size} if route.startswith('/capture/') else d.read(d.bind(path))['requestBinding']
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def reply(self,code,value,content='application/json'):
            b=value if isinstance(value,bytes) else d.raw(value);self.send_response(code);self.send_header('Content-Length',str(len(b)));self.send_header('Content-Type',content);self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.end_headers();self.wfile.write(b);self.wfile.flush()
        def do_GET(self):
            route=urllib.parse.urlsplit(self.path).path
            if route.startswith('/status/'):
                try:a=ack_for(route.removeprefix('/status'));self.reply(200 if a else 404,a or {})
                except ValueError:self.reply(400,{})
            elif route in routes:
                path=d.checked(routes[route]);mime='text/html' if path.suffix=='.html' else 'text/javascript' if path.suffix in ('.js','.mjs') else 'application/wasm' if path.suffix=='.wasm' else 'application/octet-stream';self.reply(200,path.read_bytes(),mime)
            else:self.reply(404,{})
        def do_POST(self):
            nonlocal claim,uploads
            with lock:
                try:
                    path=stored(self.path);n=int(self.headers.get('Content-Length','0'))
                    if self.path.startswith('/capture/'):
                        if n!=allowed[self.path.removeprefix('/capture/')]:raise ValueError('capture bytes')
                    elif not 0<n<=4_000_000:raise ValueError('event bytes')
                    body=self.rfile.read(n);ack={'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
                    if len(body)!=n:raise ValueError('truncated body')
                    if path.exists():
                        if ack_for(self.path)!=ack:raise ValueError('same request conflict')
                        self.reply(201,ack);return
                    if self.path=='/claim':
                        value=json.loads(body)
                        if set(value)!={'pageRequestId','executionSha256'} or value['executionSha256']!=prep['execution']['sha256'] or str(uuid.UUID(value['pageRequestId']))!=value['pageRequestId']:raise ValueError('claim')
                        claim=value['pageRequestId'];d.new(path,{'value':value,'requestBinding':ack})
                    elif self.path.startswith('/start/'):
                        if not claim or len(starts)>=len(order):raise ValueError('stage limit')
                        b,o=order[len(starts)]
                        if self.path!=f'/start/{b}/{o}' or (starts and any(f'{starts[-1][0]}-{starts[-1][1]}-{h}.bin' not in captured for h in keys)):raise ValueError('ordered complete two heads')
                        value=json.loads(body);validate_event(value,kind,b,cases[o],claim)
                        if value['inputRequestId'] in ids:raise ValueError('unique UUID')
                        d.new(path,{'value':value,'startedAtUnixNs':time.time_ns(),'requestBinding':ack});starts.append((b,o));ids.add(value['inputRequestId'])
                    elif self.path.startswith('/capture/'):
                        if not starts:raise ValueError('start required')
                        b,o=starts[-1];name=self.path.removeprefix('/capture/')
                        pending=[f'{b}-{o}-{h}.bin' for h in keys if f'{b}-{o}-{h}.bin' not in captured]
                        if not pending or name!=pending[0]:raise ValueError('all actual outputs in order')
                        with path.open('xb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                        captured.add(name)
                    else:
                        value=json.loads(body)
                        if value['pageRequestId']!=claim:raise ValueError('terminal claim')
                        d.new(path,{'value':value,'requestBinding':ack})
                    uploads+=1;d.new(root/'upload-events'/f'{uploads:04d}.json',{'route':self.path,'requestBinding':ack});self.reply(201,ack)
                except (ValueError,KeyError,FileExistsError):self.reply(409,{'error':'full stage contract'})
        def log_message(self,*args):pass
    print(f'JOINT_FULL_TRACE_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execution',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--stage',choices=['control','learned']);parser.add_argument('--serve',action='store_true');parser.add_argument('--audit',action='store_true');parser.add_argument('--verify-report',action='store_true');parser.add_argument('--port',type=int,default=8842);a=parser.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        try:
            report=reconstruct(root)
            if a.verify_report:
                if report!=d.read(d.bind(root/'report.json')):raise ValueError('fulltrace reconstruction_mismatch')
            else:d.new(root/'report.json',report)
            print(json.dumps({k:report[k] for k in ('ok','kind','allOwnHeadsBitwiseIdenticalAllBackends','layerConclusionsAllowed','summary','actualRawTensorCount')}))
        except BaseException as error:
            if not a.verify_report:d.new(root/'audit-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'productHold':True})
            raise
    else:prepare(a.execution.resolve(),root,a.stage)
