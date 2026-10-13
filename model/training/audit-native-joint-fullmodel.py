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

def validate_scope(p):
    values={'purpose':'joint_fullmodel_nonzero_controls_then_learned_full68_three_backend_gate','fullCandidateCount':68,'requiredBackends':['cpu','wasm','webgpu'],
            'controlInputsPerBackendAllowed':68,'learnedInputsPerBackendAllowedOnlyAfterAllThreeControlGates':68,'requiredNumericDifference':1e-4,'requiredDecodedPixelDifferences':0,'requiredPresenceDecisionDifferences':0,'graphOptimizationLevel':'disabled','wasmNumThreads':1,
            'newTorchInputsAllowed':0,'optimizerStepsAllowed':0,'valInputsAllowed':0,'protectedInputsAllowed':0,'newChatImageInputsAllowed':0,'formalReleaseAllowed':False,'productHold':True}
    if any(p[k]!=v for k,v in values.items()):raise ValueError('full68 fixed budgets / quality')
    for k in ('all204NonzeroControlsMustPassBeforeAnyLearnedInput','allBothHeadsNativeShapeFloat32Finite','implementationExecutionMustBeFrozenBeforeAnyModelBudget','controlsReferenceOriginalDeterministicNonzeroUntrainedTorchOnly','controlCannotSelectQuality','learnedReferenceOriginalStrictCudaOnly','oldFailuresAndConsumedBudgetsPreserved','internalValStillProhibitedUntilNewFullGateAndSeparateScope','productionManifestAndReleaseIdentityUnchanged'):
        if p[k] is not True:raise ValueError('required stage guard '+k)
    if p['newInput']!={'name':'resizeRatios','shape':[4],'dtype':'float32','order':'resize_e3_to_e2 y,x; resize_d2_to_e1 y,x','fromOriginalDimensionsOnly':True,'actualBrowserFullVectorMustMatchFrozenBytesBeforeEveryInput':True}:raise ValueError('host vector semantics')
    if p['patch']!={'replaceOnlyFourRatioDivWithGather':True,'onlyLastGroupNormAdditionalSumChunk':128,'originalFirstChunk':128,'groupNormEpsilon':1e-5,'otherNineGroupNormAndAllLearningParametersUnchanged':True,'reversePatchMustRestoreEachOriginalGraphByteForByte':True}:raise ValueError('limited math patch')

def tensor(ref):
    path=d.checked({k:ref[k] for k in ('path','sha256')})
    if ref['dtype']!='float32' or path.stat().st_size!=math.prod(ref['shape'])*4:raise ValueError('float32 exact native cardinality')
    a=np.fromfile(path,np.float32).reshape(ref['shape'])
    if not np.isfinite(a).all():raise ValueError('all tensor elements finite')
    return a

def save(path,a):
    if a.dtype!=np.float32 or not np.isfinite(a).all():raise ValueError('captured float32 finite')
    with path.open('xb') as f:f.write(a.tobytes());f.flush();os.fsync(f.fileno())
    return d.bind(path)|{'shape':list(a.shape),'dtype':'float32'}

def compare(c,kind,outputs,comparator):
    refs=c['references'][kind]
    return comparator.compare_outputs(tensor(refs['mask']).reshape(-1),tensor(refs['presence']).reshape(-1),tensor(outputs['mask']).reshape(-1),tensor(outputs['presence']).reshape(-1),c['h'],c['w'])

def passed(stats):return all(stats[k] for k in ('numericGatePassed','decodedPixelGatePassed','presenceDecisionMatched','allReferenceAndCapturedHeadsFinite'))

def resources(execution):
    e=d.read(d.bind(execution))
    for ref in [e['auditor'],e['rewriter'],e['isolatedRewriter'],e['comparator'],e['dataHelper']]:d.checked(ref)
    if e['auditor']!=d.bind(__file__):raise ValueError('frozen full-model auditor')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    gate=d.read(p['inputs']['operatorGate']);ratio=d.read(p['inputs']['hostRatioGate'])
    if not gate['allOperatorNumericGatesPassed'] or len(gate['records'])!=612 or not ratio['ok'] or ratio['ratioRecords']!=136:raise ValueError('whole operator / host gate')
    original=d.read(p['inputs']['originalBrowserPreparation']);operator=d.read(p['inputs']['originalOperatorScope'])
    if len(p['cases'])!=68 or [c['ordinal'] for c in p['cases']]!=list(range(1,69)) or [c['candidateIdentity'] for c in p['cases']]!=p['candidateIdentities']:raise ValueError('all68 stable order')
    for c,old,ops in zip(p['cases'],original['caseReferences'],operator['cases'],strict=True):
        if c['candidateIdentity']!=old['candidateIdentity'] or c['candidateIdentity']!=ops['candidateIdentity'] or c['candidateIdentity']['identity']['split']!='train' or (c['h'],c['w'])!=(old['h'],old['w']):raise ValueError('original train-only input')
        if {k:c['input'][k] for k in ('path','sha256')}!={k:old['refs']['input'][k] for k in ('path','sha256')} or c['input']['shape']!=[1,4,c['h'],c['w']]:raise ValueError('frozen native input')
        tensor(c['input']);v=tensor(c['resizeRatios'])
        dims=[(c['h']//4,c['h']//2),(c['w']//4,c['w']//2),(c['h']//2,c['h']),(c['w']//2,c['w'])]
        derived=np.array([np.float32(a)/np.float32(b) for a,b in dims],np.float32)
        if v.shape!=(4,) or v.tobytes()!=derived.tobytes() or v.tobytes()!=b''.join(tensor(r).tobytes() for r in c['ratioParents']):raise ValueError('four dimension-derived ratio bytes')
        if c['ratioParents']!=[ops['operations'][i]['hostRatios'] for i in range(2)]:raise ValueError('proven ratio parents')
        for kind in ('control','learned'):
            for head in ('mask','presence'):
                ref=c['references'][kind][head]
                if {k:ref[k] for k in ('path','sha256')}!={k:old['refs'][kind+'-'+head][k] for k in ('path','sha256')} or ref['shape']!=([1,1,c['h'],c['w']] if head=='mask' else [1,1]):raise ValueError('original two-head reference')
                tensor(ref)
        if not np.any(tensor(c['references']['control']['mask'])) or not np.any(tensor(c['references']['control']['presence'])):raise ValueError('deterministic control must be nonzero')
    rewriter=d.load(d.checked(e['rewriter']),'joint_full_rewriter');isolated=d.load(d.checked(e['isolatedRewriter']),'joint_full_isolated');models={}
    for kind,key in [('control','originalNonzeroControlOnnx'),('learned','originalLearnedOnnx')]:
        old=onnx.load(d.checked(p['inputs'][key]));expected=rewriter.rewrite_model(copy.deepcopy(old),isolated,e['graphTargets'][kind]);actual=onnx.load(d.checked(e['models'][kind]))
        if actual.SerializeToString()!=expected.SerializeToString():raise ValueError('only frozen joint graph patch')
        rewriter.verify_patch(old,actual,e['graphTargets'][kind])
        if [x.name for x in actual.graph.input]!=['candidate','resizeRatios'] or [x.name for x in actual.graph.output]!=['mask_logits','presence_logit']:raise ValueError('actual full two-head IO names')
        models[kind]=e['models'][kind]
    for ref in e['runtimeFiles'].values():d.checked(ref)
    return e,p,models,d.load(d.checked(e['comparator']),'joint_full_comparator')

def event(kind,b,c,page=None):
    r={'kind':kind,'backend':b,'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'inputSha256':c['input']['sha256'],'resizeRatiosSha256':c['resizeRatios']['sha256'],'targetShape':[1,1,c['h'],c['w']]}
    return r if page is None else r|{'pageRequestId':page}

def validate_event(r,kind,b,c,page):
    if {k:v for k,v in r.items() if k!='inputRequestId'}!=event(kind,b,c,page) or str(uuid.UUID(r['inputRequestId']))!=r['inputRequestId']:raise ValueError('ordered original input / ratios / unique UUID')

def control_gate(e):
    root=Path(e['controlRoot']);r=reconstruct(root)
    if r!=d.read(d.bind(root/'report.json')) or r['kind']!='control' or not r['allThreeBackendStageGatesPassed'] or r['modelInputsConsumedPerBackend']!={'cpu':68,'wasm':68,'webgpu':68}:raise ValueError('all204 controls before any learned input')
    return d.bind(root/'report.json')

HTML=r'''<!doctype html><meta charset="utf-8"><title>完整候选单阶段核验</title><link rel="icon" href="data:,"><h1>完整模型两头核验</h1><button id="run">执行本阶段WASM/WebGPU各68输入</button><pre id="result">未执行；产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
const verified=async(path,sha)=>{const r=await fetch(path),b=await r.arrayBuffer();if(!r.ok||hex(await crypto.subtle.digest('SHA-256',b))!==sha)throw Error('GET/SHA '+path);return b;};
async function post(path,body,log){const bytes=typeof body==='string'?new TextEncoder().encode(body):body,sha=hex(await crypto.subtle.digest('SHA-256',bytes));for(let attempt=0;attempt<3;attempt++){try{const r=await fetch(path,{method:'POST',body:bytes}),text=await r.text();if(!r.ok)throw Error('HTTP '+r.status);const a=JSON.parse(text);if(a.sha256!==sha||a.bytes!==bytes.length)throw Error('ACK');return;}catch(error){log.transportErrors.push({path,attempt,error:String(error)});const r=await fetch('/status'+path),text=await r.text();if(r.ok){const a=JSON.parse(text);if(a.sha256!==sha||a.bytes!==bytes.length)throw Error('persisted conflict');log.persistedAckRecoveries++;return;}if(r.status!==404)throw Error('status');log.uploadOnlyRetries++;}}throw Error('bounded upload attempts');}
document.querySelector('#run').onclick=async()=>{document.querySelector('#run').disabled=true;const c=await(await fetch('/config.json')).json(),r={executionSha256:c.executionSha256,configSha256:c.configSha256,kind:c.kind,pageRequestId:crypto.randomUUID(),userAgent:navigator.userAgent,crossOriginIsolated,records:[],startedInputs:[],errors:[],transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0,phase:'starting'};try{
await post('/claim',JSON.stringify({pageRequestId:r.pageRequestId,executionSha256:c.executionSha256}),r);if(!crossOriginIsolated)throw Error('isolation');ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;
const adapter=await navigator.gpu?.requestAdapter();r.adapterInfo=adapter?{vendor:adapter.info?.vendor,architecture:adapter.info?.architecture,device:adapter.info?.device,description:adapter.info?.description}:null;
for(const backend of ['wasm','webgpu']){let session;try{session=await ort.InferenceSession.create(await verified('/model.onnx',c.model.sha256),{executionProviders:[backend],graphOptimizationLevel:'disabled'});if(session.inputNames.join(',')!=='candidate,resizeRatios'||session.outputNames.join(',')!=='mask_logits,presence_logit')throw Error('actual IO');
for(const row of c.cases){r.phase=c.kind+'/'+backend+' '+row.ordinal+'/68';document.querySelector('#result').textContent=r.phase;const input=new Float32Array(await verified('/input/'+row.ordinal+'.bin',row.input.sha256));if(input.length!==4*row.h*row.w)throw Error('input cardinality');for(const v of input)if(!Number.isFinite(v))throw Error('input finite');const ratios=new Float32Array([Math.fround(Math.floor(row.h/4)/Math.floor(row.h/2)),Math.fround(Math.floor(row.w/4)/Math.floor(row.w/2)),Math.fround(Math.floor(row.h/2)/row.h),Math.fround(Math.floor(row.w/2)/row.w)]);if(hex(await crypto.subtle.digest('SHA-256',ratios.buffer))!==row.resizeRatios.sha256)throw Error('full host vector');
const e={kind:c.kind,backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity,inputSha256:row.input.sha256,resizeRatiosSha256:row.resizeRatios.sha256,targetShape:[1,1,row.h,row.w],pageRequestId:r.pageRequestId,inputRequestId:crypto.randomUUID()};await post('/start/'+backend+'/'+row.ordinal,JSON.stringify(e),r);r.startedInputs.push(e);
const y=await session.run({candidate:new ort.Tensor('float32',input,row.input.shape),resizeRatios:new ort.Tensor('float32',ratios,[4])}),shapes={};for(const [head,name] of [['mask','mask_logits'],['presence','presence_logit']]){const t=y[name],a=new Float32Array(await t.getData()),shape=head==='mask'?[1,1,row.h,row.w]:[1,1];if(t.type!=='float32'||Array.from(t.dims).join(',')!==shape.join(',')||a.length!==shape.reduce((x,y)=>x*y,1))throw Error('two-head native shape / float32');for(const v of a)if(!Number.isFinite(v))throw Error('two-head finite');await post('/capture/'+backend+'-'+row.ordinal+'-'+head+'.bin',new Uint8Array(a.buffer),r);shapes[head]=shape;}r.records.push({...e,shapes,dtype:'float32'});}
}finally{if(session)await session.release();}}
r.captureComplete=r.records.length===136;r.phase='terminal';}catch(error){r.captureComplete=false;r.errors.push(String(error));r.phase='terminal-failure';}await post('/terminal',JSON.stringify(r),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});document.querySelector('#result').textContent=JSON.stringify(r);};</script>'''

def prepare(execution,root,kind):
    if root.exists():raise ValueError('stage consumed; read-only replay only')
    e,p,models,comparator=resources(execution);gate=control_gate(e) if kind=='learned' else None
    root.mkdir(parents=True,exist_ok=False)
    for name in ('cpu','started-inputs','browser-capture','upload-events'):(root/name).mkdir()
    captures=[];starts=0
    try:
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;options.log_severity_level=3
        session=ort.InferenceSession(str(d.checked(models[kind])),sess_options=options,providers=['CPUExecutionProvider'])
        if [v.name for v in session.get_inputs()]!=['candidate','resizeRatios'] or [v.name for v in session.get_outputs()]!=['mask_logits','presence_logit']:raise ValueError('CPU full IO')
        for c in p['cases']:
            feeds={'candidate':tensor(c['input']),'resizeRatios':tensor(c['resizeRatios'])};ev=event(kind,'cpu',c)
            d.new(root/'cpu'/f'{c["ordinal"]}-start.json',ev|{'startedAtUnixNs':time.time_ns()});starts+=1;ys=session.run(None,feeds);outputs={}
            for head,a in zip(('mask','presence'),ys,strict=True):
                if list(a.shape)!=c['references'][kind][head]['shape']:raise ValueError('CPU two-head native shape')
                outputs[head]=save(root/'cpu'/f'{c["ordinal"]}-{head}.bin',a)
            captures.append(ev|{'outputs':outputs,'parity':compare(c,kind,outputs,comparator)})
        d.new(root/'cpu-captures.json',captures)
        config={'executionSha256':d.bind(execution)['sha256'],'kind':kind,'model':models[kind],'cases':p['cases']};d.new(root/'config-base.json',config);config['configSha256']=d.bind(root/'config-base.json')['sha256'];d.new(root/'config.json',config)
        with (root/'browser.html').open('xb') as f:f.write(HTML.encode());f.flush();os.fsync(f.fileno())
        d.new(root/'preparation.json',{'execution':d.bind(execution),'auditor':d.bind(__file__),'kind':kind,'controlGate':gate,'html':d.bind(root/'browser.html'),'config':d.bind(root/'config.json'),'cpuCaptures':d.bind(root/'cpu-captures.json')})
        if not all(passed(r['parity']) for r in captures):raise ValueError('CPU stage gate failed; browser budget remains zero')
        print(json.dumps({'ok':True,'kind':kind,'cpuCaptured':len(captures),'maxAbs':max(r['parity']['maxAbsoluteDifference'] for r in captures),'browserStarted':0}),flush=True)
    except BaseException as error:
        d.new(root/'execution-failure.json',{'ok':False,'error':str(error),'kind':kind,'cpuStarted':starts,'cpuCaptured':len(captures),'browserStarted':0,'optimizerSteps':0,'productHold':True});raise

def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'))
    for ref in prep.values():
        if isinstance(ref,dict) and 'path' in ref:d.checked(ref)
    e,p,models,comparator=resources(d.checked(prep['execution']));kind=prep['kind'];config=d.read(prep['config'])
    if kind=='learned' and prep['controlGate']!=control_gate(e):raise ValueError('learned control gate')
    if (root/'claim.json').exists() or any((root/'started-inputs').iterdir()) or not all(passed(r['parity']) for r in d.read(prep['cpuCaptures'])):raise ValueError('single stage / CPU gate')
    cases={c['ordinal']:c for c in p['cases']};order=[(b,c['ordinal']) for b in ('wasm','webgpu') for c in p['cases']]
    routes={'/browser.html':prep['html'],'/config.json':prep['config'],'/model.onnx':models[kind]};routes.update({'/ort/'+n:r for n,r in e['runtimeFiles'].items()});routes.update({f'/input/{o}.bin':{k:c['input'][k] for k in ('path','sha256')} for o,c in cases.items()})
    allowed={f'{b}-{o}-{h}.bin':(cases[o]['h']*cases[o]['w'] if h=='mask' else 1)*4 for b,o in order for h in ('mask','presence')};starts=[];captured=set();ids=set();lock=threading.Lock();claim=None;uploads=0
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
                        if not claim or len(starts)>=136:raise ValueError('stage limit')
                        b,o=order[len(starts)]
                        if self.path!=f'/start/{b}/{o}' or (starts and any(f'{starts[-1][0]}-{starts[-1][1]}-{h}.bin' not in captured for h in ('mask','presence'))):raise ValueError('ordered complete two heads')
                        value=json.loads(body);validate_event(value,kind,b,cases[o],claim)
                        if value['inputRequestId'] in ids:raise ValueError('unique UUID')
                        d.new(path,{'value':value,'startedAtUnixNs':time.time_ns(),'requestBinding':ack});starts.append((b,o));ids.add(value['inputRequestId'])
                    elif self.path.startswith('/capture/'):
                        if not starts:raise ValueError('start required')
                        b,o=starts[-1];name=self.path.removeprefix('/capture/')
                        if name not in (f'{b}-{o}-mask.bin',f'{b}-{o}-presence.bin') or (name.endswith('-presence.bin') and f'{b}-{o}-mask.bin' not in captured):raise ValueError('active two heads')
                        with path.open('xb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                        captured.add(name)
                    else:
                        value=json.loads(body)
                        if value['pageRequestId']!=claim:raise ValueError('terminal claim')
                        d.new(path,{'value':value,'requestBinding':ack})
                    uploads+=1;d.new(root/'upload-events'/f'{uploads:04d}.json',{'route':self.path,'requestBinding':ack});self.reply(201,ack)
                except (ValueError,KeyError,FileExistsError):self.reply(409,{'error':'full stage contract'})
        def log_message(self,*args):pass
    print(f'JOINT_FULL_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'));e,p,models,comparator=resources(d.checked(prep['execution']));kind=prep['kind']
    for ref in (prep['auditor'],prep['html'],prep['config'],prep['cpuCaptures']):d.checked(ref)
    if kind=='learned' and prep['controlGate']!=control_gate(e):raise ValueError('all controls gate binding')
    base={'executionSha256':prep['execution']['sha256'],'kind':kind,'model':models[kind],'cases':p['cases']};config=d.read(prep['config'])
    if d.read(d.bind(root/'config-base.json'))!=base or config!=base|{'configSha256':d.bind(root/'config-base.json')['sha256']}:raise ValueError('frozen config')
    live=d.read(d.bind(root/'live-browser.json'))['value'];claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId']
    if not live['captureComplete'] or live['errors'] or live['phase']!='terminal' or live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['pageRequestId']!=claim or live['kind']!=kind or not live['crossOriginIsolated']:raise ValueError('complete136 browser stage')
    if live['userAgent']!=e['expectedEnvironment']['userAgent'] or live['adapterInfo']!=e['expectedEnvironment']['adapterInfo']:raise ValueError('same actual browser environment')
    if len(live['records'])!=136 or len(live['startedInputs'])!=136 or len(list((root/'started-inputs').glob('*.json')))!=136 or len(list((root/'browser-capture').glob('*.bin')))!=272:raise ValueError('whole starts and both heads')
    cases={c['ordinal']:c for c in p['cases']};records=[];captures={'cpu':d.read(prep['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];ids=[];times=[]
    for index,(ev,record) in enumerate(zip(live['startedInputs'],live['records'],strict=True)):
        b='wasm' if index<68 else 'webgpu';o=index%68+1;c=cases[o];validate_event(ev,kind,b,c,claim);path=root/'started-inputs'/f'{b}-{o}.json';st=d.read(d.bind(path))
        if st['value']!=ev or (times and st['startedAtUnixNs']<=times[-1]):raise ValueError('persisted start order')
        if {k:record[k] for k in ev}!=ev or record['dtype']!='float32' or record['shapes']!={h:c['references'][kind][h]['shape'] for h in ('mask','presence')}:raise ValueError('two-head actual shape/dtype')
        outputs={h:d.bind(root/'browser-capture'/f'{b}-{o}-{h}.bin')|{'shape':record['shapes'][h],'dtype':'float32'} for h in ('mask','presence')}
        captures[b].append(ev|{'outputs':outputs});events.append(d.bind(path));ids.append(ev['inputRequestId']);times.append(st['startedAtUnixNs'])
    if len(set(ids))!=136 or len(list((root/'cpu').glob('*-start.json')))!=68:raise ValueError('unique actual starts')
    for b,rows in captures.items():
        if len(rows)!=68 or [r['ordinal'] for r in rows]!=list(range(1,69)):raise ValueError('all68 per backend')
        for cap in rows:
            c=cases[cap['ordinal']]
            if {k:cap[k] for k in event(kind,b,c)}!=event(kind,b,c):raise ValueError('same stage input/ratio')
            if b=='cpu':
                st=d.read(d.bind(root/'cpu'/f'{c["ordinal"]}-start.json'))
                if {k:st[k] for k in event(kind,b,c)}!=event(kind,b,c):raise ValueError('CPU started identity')
            stats=compare(c,kind,cap['outputs'],comparator)
            if b=='cpu' and stats!=cap['parity']:raise ValueError('CPU parity reconstruction')
            records.append({'backend':b,'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'parity':stats,'gatePassed':passed(stats)})
    summary={b:{'candidateCount':68,'maxAbs':max(r['parity']['maxAbsoluteDifference'] for r in records if r['backend']==b),'failedOrdinals':[r['ordinal'] for r in records if r['backend']==b and not r['gatePassed']],'decodedPixelDifferences':sum(r['parity']['decodedMaskPixelDifference'] for r in records if r['backend']==b),'presenceFailed':sum(not r['parity']['presenceDecisionMatched'] for r in records if r['backend']==b)} for b in captures}
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))];expected=['/claim']+[route for b in ('wasm','webgpu') for o in range(1,69) for route in (f'/start/{b}/{o}',f'/capture/{b}-{o}-mask.bin',f'/capture/{b}-{o}-presence.bin')]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected:raise ValueError('complete persisted upload order')
    stage_pass=all(r['gatePassed'] for r in records)
    return {'schemaVersion':1,'ok':True,'decision':'joint_fullmodel_stage_reconstructed','kind':kind,'inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json')},'controlGate':prep['controlGate'],'captures':captures,'browserStartEvents':events,'uploadEvents':uploads,'records':records,'summary':summary,'allThreeBackendStageGatesPassed':stage_pass,'fullModelLearnedGatePassed':kind=='learned' and stage_pass,'modelInputsConsumedPerBackend':{'cpu':68,'wasm':68,'webgpu':68},'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'newChatImageInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'oldFailuresAndConsumedBudgetsPreserved':True,'formalReleaseAllowed':False,'productHold':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',choices=['control','learned']);p.add_argument('--serve',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',action='store_true');p.add_argument('--port',type=int,default=8840);a=p.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        try:
            r=reconstruct(root)
            if a.verify_report:
                if r!=d.read(d.bind(root/'report.json')):raise ValueError('stage reconstruction_mismatch')
            else:d.new(root/'report.json',r)
            print(json.dumps({k:r[k] for k in ('ok','kind','allThreeBackendStageGatesPassed','summary')}))
        except BaseException as error:
            if not a.verify_report:d.new(root/'audit-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'productHold':True})
            raise
    else:prepare(a.execution.resolve(),root,a.stage)
