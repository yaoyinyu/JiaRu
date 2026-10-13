"""全68主机比例与GN分层求和隔离，先核验真实浏览器比例，不执行完整模型或训练。"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('tail_operator_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def validate_scope(p):
    if p['purpose']!='joint_host_float32_resize_ratios_and_last_groupnorm_hierarchical_sum_operator_gate' or p['fullCandidateCount']!=68 or p['operatorInputsAllowedPerBackend']!={'cpu':204,'wasm':204,'webgpu':204}:raise ValueError('joint fixed budget')
    if p['repairOperations']!=['resize_e3_to_e2','resize_d2_to_e1','dec1.4_group_norm']:raise ValueError('three ordered operators')
    if any(p[k]!=0 for k in ('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newProjectImageInputsAllowed')):raise ValueError('operator-only scope')
    gate=p['readinessGate']
    if gate['allThreeBackendsAll68AllThreeOperatorsMaxAbs']!=2e-5 or gate['formalFullModelMaxAbsUnchanged']!=1e-4 or gate['formalDecodedPixelDifferencesUnchanged']!=0 or not gate['cpuResizeOutputsMustRemainBitwiseSameAsPriorCpuRepair']:raise ValueError('fixed numerical gates')
    if p['groupNormPolicy']['additionalTotalSumChunkLength']!=128 or p['groupNormPolicy']['originalFirstChunkLength']!=128 or p['groupNormPolicy']['epsilon']!=1e-5 or not p['groupNormPolicy']['otherNineGroupNormGraphsUnchanged']:raise ValueError('GN scope')
    if not p['resizePolicy']['fullModelInputNotImplementedOrApproved'] or not p['resizePolicy']['pythonAndBrowserHostRatioBytesMustMatchAll68'] or p['graphOptimizationLevel']!='disabled' or not p['productHold'] or p['formalReleaseAllowed']:raise ValueError('metadata / HOLD')
    if not p['sourceRolesWeightsEpsilonAndReferencesUnchanged'] or not p['allOldFailuresAndConsumedBudgetsPreserved'] or not gate['noFullModelBudgetUntilOperatorGateAndSeparateNonzeroControlScope']:raise ValueError('preserved evidence / full-model gate')


def resources(execution):
    e=d.read(d.bind(execution))
    for ref in [e['auditor'],e['hostRatioAuditor'],e['repairTool'],*e['helpers'].values()]:d.checked(ref)
    if e['auditor']!=d.bind(__file__):raise ValueError('frozen auditor')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    strict=d.read(p['inputs']['strictLayerReport']);saved=d.read(p['inputs']['savedOperatorReport']);cpu=d.read(p['inputs']['cpuRepairReport']);prior=d.read(p['inputs']['priorTailOperators'])
    precision=d.load(d.checked(e['helpers']['buffer']),'joint_buffer');layer=d.load(d.checked(e['helpers']['layer']),'joint_layers');repair=d.load(d.checked(e['repairTool']),'joint_repair')
    specs=[{'name':name,'inputLayer':inp,'outputLayer':out,'diagnosticMaxAbs':2e-5,'graph':ref} for name,inp,out,ref in zip(p['repairOperations'],['enc3.5','dec2.5','dec1.3'],['enc2.5','enc1.5','dec1.4'],e['graphs'],strict=True)]
    models=[]
    originals=[*cpu['artifacts']['operatorOnnx'],d.read(prior['inputs']['preparation'])['execution']]
    originals[2]=d.read(d.read(originals[2])['scope'])['operations'][1]['graph']
    for index,spec in enumerate(specs):
        original=onnx.load(d.checked(originals[index]));expected=repair.host_resize_ratios(original) if index<2 else repair.hierarchical_group_sum(original)
        model=onnx.load(d.checked(spec['graph']))
        if model.SerializeToString()!=expected.SerializeToString():raise ValueError('only frozen rewrite graph allowed')
        models.append({'name':spec['name'],'graph':spec['graph'],'inputNames':[x.name for x in model.graph.input],'outputName':model.graph.output[0].name,'hasSizes':index<2,'hasHostRatios':index<2})
    p['operations']=specs
    for rows in [p['cases'],strict['captures'],saved['captures']]:
        if len(rows)!=68 or [r['candidateIdentity'] for r in rows]!=p['candidateIdentities'] or [r['ordinal'] for r in rows]!=list(range(1,69)):raise ValueError('all68 identities / order')
    for case,st,old in zip(p['cases'],strict['captures'],saved['captures'],strict=True):
        if case['candidateIdentity']['identity']['split']!='train':raise ValueError('train-only')
        for index,(spec,op) in enumerate(zip(specs,case['operations'],strict=True)):
            if op['name']!=spec['name'] or op['input']!=st['strictCuda']['layers'][spec['inputLayer']] or op['expected']!=old['operations'][spec['name']]['strictCuda']:raise ValueError('original strict CUDA reference')
            x=layer.read_tensor(precision,op['input']);y=layer.read_tensor(precision,op['expected'])
            if x.ndim!=4 or y.ndim!=4 or x.shape[0]!=1 or y.shape[0]!=1:raise ValueError('native shape')
            if index<2:
                ratio=layer.read_tensor(precision,op['hostRatios']);derived=np.array([np.float32(x.shape[j])/np.float32(y.shape[j]) for j in (2,3)],np.float32)
                if ratio.shape!=(2,) or ratio.tobytes()!=derived.tobytes():raise ValueError('dimension-only frozen ratio')
    runtime=d.read(prior['inputs']['preparation'])
    for ref in runtime['runtimeFiles'].values():d.checked(ref)
    return e,p,models,precision,layer,runtime['runtimeFiles'],runtime['expectedEnvironment']


def ratio_gate(e):
    auditor=d.load(d.checked(e['hostRatioAuditor']),'joint_host_gate');root=Path(e['hostRatioRoot'])
    reconstructed=auditor.reconstruct(root)
    if reconstructed!=d.read(d.bind(root/'report.json')) or not reconstructed['ok'] or reconstructed['newModelCalls']!=0:raise ValueError('all136 actual browser ratios before model budget')
    return d.bind(root/'report.json')


def sequence(p,backends):
    return [(b,index,c['ordinal']) for b in backends for index in range(3) for c in p['cases']]


def validate_event(event,pair,case,spec,page):
    b,index,o=pair
    if set(event)!={'backend','operationIndex','operation','ordinal','candidateIdentity','inputSha256','targetShape','inputRequestId','pageRequestId'} or event['backend']!=b or event['operationIndex']!=index or event['operation']!=spec['name'] or event['ordinal']!=o or event['candidateIdentity']!=case['candidateIdentity'] or event['inputSha256']!=case['operations'][index]['input']['sha256'] or event['targetShape']!=case['operations'][index]['expected']['shape'] or event['pageRequestId']!=page:raise ValueError('ordered same-input event')
    if str(uuid.UUID(event['inputRequestId']))!=event['inputRequestId']:raise ValueError('unique request ID')


HTML=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>同输入三算子隔离</title><link rel="icon" href="data:,"><h1>开发算子数值诊断</h1><button id="run">执行WASM/WebGPU各204算子输入</button><pre id="result">未执行；完整模型输入0，产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
const verified=async(path,sha)=>{const r=await fetch(path);const b=await r.arrayBuffer();if(!r.ok||hex(await crypto.subtle.digest('SHA-256',b))!==sha)throw Error('GET/SHA '+path);return b;};
async function post(path,body,log){
 const bytes=typeof body==='string'?new TextEncoder().encode(body):body,sha=hex(await crypto.subtle.digest('SHA-256',bytes));
 for(let attempt=0;attempt<3;attempt++){
  try{const r=await fetch(path,{method:'POST',body:bytes}),text=await r.text();if(!r.ok)throw Error('HTTP '+r.status);const ack=JSON.parse(text);if(ack.sha256!==sha||ack.bytes!==bytes.length)throw Error('ACK');return;}
  catch(error){log.transportErrors.push({path,attempt,error:String(error)});const r=await fetch('/status'+path),text=await r.text();if(r.ok){const ack=JSON.parse(text);if(ack.sha256!==sha||ack.bytes!==bytes.length)throw Error('persisted conflict');log.persistedAckRecoveries++;return;}if(r.status!==404)throw Error('status '+r.status);log.uploadOnlyRetries++;}
 }throw Error('bounded upload attempts exhausted '+path);
}
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;const config=await(await fetch('/config.json')).json();
 const report={executionSha256:config.executionSha256,configSha256:config.configSha256,pageRequestId:crypto.randomUUID(),userAgent:navigator.userAgent,crossOriginIsolated,records:[],startedInputs:[],errors:[],transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0,phase:'starting'};
 try{
  await post('/claim',JSON.stringify({pageRequestId:report.pageRequestId,executionSha256:config.executionSha256}),report);if(!crossOriginIsolated)throw Error('isolation');ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;
  const adapter=await navigator.gpu?.requestAdapter();report.adapterInfo=adapter?{vendor:adapter.info?.vendor,architecture:adapter.info?.architecture,device:adapter.info?.device,description:adapter.info?.description}:null;
  for(const backend of ['wasm','webgpu'])for(let index=0;index<3;index++){
   const model=config.models[index];let session;
   try{
    session=await ort.InferenceSession.create(await verified('/model/'+index+'.onnx',model.graph.sha256),{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    if(session.inputNames.join(',')!==model.inputNames.join(',')||session.outputNames.join(',')!==model.outputName)throw Error('actual IO names');
    for(const row of config.cases){
     report.phase=backend+' '+model.name+' '+row.ordinal+'/68';document.querySelector('#result').textContent=report.phase;
     const op=row.operations[index],x=new Float32Array(await verified('/input/'+index+'/'+row.ordinal+'.bin',op.input.sha256));if(x.length!==op.input.shape.reduce((a,b)=>a*b,1))throw Error('input cardinality');for(const v of x)if(!Number.isFinite(v))throw Error('input finite');
     const feeds={[model.inputNames[0]]:new ort.Tensor('float32',x,op.input.shape)};if(model.hasSizes)feeds[model.inputNames[1]]=new ort.Tensor('int64',BigInt64Array.from(op.expected.shape.map(BigInt)),[4]);if(model.hasHostRatios){const ratios=new Float32Array([Math.fround(op.input.shape[2]/op.expected.shape[2]),Math.fround(op.input.shape[3]/op.expected.shape[3])]);if(hex(await crypto.subtle.digest('SHA-256',ratios.buffer))!==op.hostRatios.sha256)throw Error('host ratios');feeds[model.inputNames[2]]=new ort.Tensor('float32',ratios,[2]);}
     const event={backend,operationIndex:index,operation:model.name,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity,inputSha256:op.input.sha256,targetShape:op.expected.shape,inputRequestId:crypto.randomUUID(),pageRequestId:report.pageRequestId};
     await post('/start/'+backend+'/'+index+'/'+row.ordinal,JSON.stringify(event),report);report.startedInputs.push(event);
     const outputs=await session.run(feeds),t=outputs[model.outputName],a=new Float32Array(await t.getData());if(t.type!=='float32'||Array.from(t.dims).join(',')!==op.expected.shape.join(',')||a.length!==op.expected.shape.reduce((x,y)=>x*y,1))throw Error('output shape/dtype');for(const v of a)if(!Number.isFinite(v))throw Error('output finite');
     await post('/capture/'+backend+'-'+index+'-'+row.ordinal+'.bin',new Uint8Array(a.buffer),report);report.records.push({...event,shape:Array.from(t.dims),dtype:t.type});
    }
   }finally{if(session)await session.release();}
  }
  report.captureComplete=report.records.length===408;report.phase='terminal';
 }catch(e){report.captureComplete=false;report.errors.push(String(e));report.phase='terminal-failure';}
 await post('/terminal',JSON.stringify(report),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});document.querySelector('#result').textContent=JSON.stringify(report);
};</script></html>'''


def prepare(execution,root):
    if root.exists():raise ValueError('budget exists; read-only replay only')
    e,p,models,precision,layer,runtime,environment=resources(execution)
    host_gate=ratio_gate(e)
    root.mkdir(parents=True,exist_ok=False)
    for name in ('cpu','started-inputs','browser-capture','upload-events'):(root/name).mkdir()
    captures=[];started=0
    try:
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;options.log_severity_level=3
        for index,model in enumerate(models):
            session=ort.InferenceSession(str(d.checked(model['graph'])),sess_options=options,providers=['CPUExecutionProvider'])
            if [x.name for x in session.get_inputs()]!=model['inputNames'] or [x.name for x in session.get_outputs()]!=[model['outputName']]:raise ValueError('CPU IO names')
            for case in p['cases']:
                op=case['operations'][index];x=layer.read_tensor(precision,op['input']);feeds={model['inputNames'][0]:x}
                if model['hasSizes']:feeds[model['inputNames'][1]]=np.array(op['expected']['shape'],dtype=np.int64)
                if model['hasHostRatios']:feeds[model['inputNames'][2]]=layer.read_tensor(precision,op['hostRatios'])
                event={'backend':'cpu','operationIndex':index,'operation':model['name'],'ordinal':case['ordinal'],'candidateIdentity':case['candidateIdentity'],'inputSha256':op['input']['sha256'],'targetShape':op['expected']['shape']}
                d.new(root/'cpu'/f'{index}-{case["ordinal"]}-start.json',event|{'startedAtUnixNs':time.time_ns()});started+=1
                y=session.run(None,feeds)[0]
                if list(y.shape)!=op['expected']['shape']:raise ValueError('CPU native shape')
                if index<2:
                    prior=d.read(p['inputs']['cpuRepairReport'])['captures']['operators'][case['ordinal']-1]['outputs'][index]
                    if y.tobytes()!=layer.read_tensor(precision,prior).tobytes():raise ValueError('CPU Resize bitwise preservation before browser')
                ref=layer.save(root/'cpu'/f'{index}-{case["ordinal"]}.bin',y);captures.append(event|{'output':ref})
            print(json.dumps({'cpuStarted':started,'cpuCaptured':len(captures),'fullModelInputs':0}),flush=True)
        d.new(root/'cpu-captures.json',captures)
        config={'executionSha256':d.bind(execution)['sha256'],'models':models,'cases':p['cases']};d.new(root/'config-base.json',config);config['configSha256']=d.bind(root/'config-base.json')['sha256'];d.new(root/'config.json',config)
        with (root/'browser.html').open('xb') as f:f.write(HTML.encode('utf-8'));f.flush();os.fsync(f.fileno())
        d.new(root/'preparation.json',{'hostRatioGate':host_gate,'execution':d.bind(execution),'auditor':d.bind(__file__),'html':d.bind(root/'browser.html'),'config':d.bind(root/'config.json'),'cpuCaptures':d.bind(root/'cpu-captures.json'),'runtimeFiles':runtime,'expectedEnvironment':{'userAgent':environment['userAgent'],'adapterInfo':environment['adapterInfo']}})
    except BaseException as error:
        d.new(root/'failure.json',{'ok':False,'error':str(error),'cpuStarted':started,'cpuCaptured':len(captures),'browserStarted':0,'fullModelInputs':0,'productHold':True});raise


def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures'):d.checked(prep[key])
    if prep['auditor']!=d.bind(__file__) or (root/'claim.json').exists() or any((root/'started-inputs').iterdir()):raise ValueError('frozen source / budget may not restart')
    p=d.read(d.read(prep['execution'])['scope']);validate_scope(p);config=d.read(prep['config']);p['operations']=[{'name':name,'graph':ref} for name,ref in zip(p['repairOperations'],d.read(prep['execution'])['graphs'],strict=True)];cases={c['ordinal']:c for c in p['cases']};order=sequence(p,['wasm','webgpu'])
    routes={'/browser.html':prep['html'],'/config.json':prep['config']};routes.update({'/ort/'+k:v for k,v in prep['runtimeFiles'].items()})
    for index,spec in enumerate(p['operations']):routes[f'/model/{index}.onnx']=spec['graph']
    for c in cases.values():
        for index,op in enumerate(c['operations']):routes[f'/input/{index}/{c["ordinal"]}.bin']={k:op['input'][k] for k in ('path','sha256')}
    allowed={f'{b}-{i}-{o}.bin':math.prod(cases[o]['operations'][i]['expected']['shape'])*4 for b,i,o in order}
    starts=[];captured=set();ids=set();lock=threading.Lock();claim=None;upload_count=0

    def stored(route):
        if route=='/claim':return root/'claim.json'
        if route=='/terminal':return root/'live-browser.json'
        if route.startswith('/capture/') and route.removeprefix('/capture/') in allowed:return root/'browser-capture'/route.removeprefix('/capture/')
        if route.startswith('/start/'):
            parts=route.split('/')
            if len(parts)==5 and parts[2] in ('wasm','webgpu') and parts[3].isdigit() and parts[4].isdigit() and (parts[2],int(parts[3]),int(parts[4])) in order:return root/'started-inputs'/f'{parts[2]}-{int(parts[3])}-{int(parts[4])}.json'
        raise ValueError('whitelisted route')

    def ack_for(route):
        path=stored(route)
        if not path.exists():return None
        if route.startswith('/capture/'):return {'sha256':d.bind(path)['sha256'],'bytes':path.stat().st_size}
        return d.read(d.bind(path))['requestBinding']

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'

        def response(self,code,value,content='application/json'):
            body=value if isinstance(value,bytes) else d.raw(value);self.send_response(code);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)));self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.end_headers();self.wfile.write(body);self.wfile.flush()

        def do_GET(self):
            route=urllib.parse.urlsplit(self.path).path
            if route.startswith('/status/'):
                try:
                    value=ack_for(route.removeprefix('/status'));self.response(200 if value else 404,value or {'present':False})
                except ValueError:self.response(400,{'error':'status route'})
            elif route in routes:
                path=d.checked(routes[route]);body=path.read_bytes();content='text/html' if path.suffix=='.html' else 'application/json' if path.suffix=='.json' else 'text/javascript' if path.suffix in ('.js','.mjs') else 'application/wasm' if path.suffix=='.wasm' else 'application/octet-stream';self.response(200,body,content)
            else:self.response(404,{'error':'route'})

        def do_POST(self):
            nonlocal claim,upload_count
            with lock:
                try:
                    path=stored(self.path);count=int(self.headers.get('Content-Length','0'))
                    if self.path.startswith('/capture/'):
                        if count!=allowed[self.path.removeprefix('/capture/')]:raise ValueError('output byte count')
                    elif not 0<count<=4_000_000:raise ValueError('event byte count')
                    body=self.rfile.read(count)
                    if len(body)!=count:raise ValueError('truncated body')
                    ack={'sha256':hashlib.sha256(body).hexdigest(),'bytes':count}
                    if path.exists():
                        if ack_for(self.path)!=ack:raise ValueError('same request identity conflict')
                        self.response(201,ack);return
                    if self.path=='/claim':
                        value=json.loads(body)
                        if set(value)!={'pageRequestId','executionSha256'} or value['executionSha256']!=prep['execution']['sha256'] or str(uuid.UUID(value['pageRequestId']))!=value['pageRequestId']:raise ValueError('page claim')
                        claim=value['pageRequestId'];d.new(path,{'value':value,'requestBinding':ack})
                    elif self.path.startswith('/start/'):
                        if not claim or len(starts)>=408:raise ValueError('start limit')
                        b,i,o=order[len(starts)]
                        if self.path!=f'/start/{b}/{i}/{o}' or (starts and f'{starts[-1][0]}-{starts[-1][1]}-{starts[-1][2]}.bin' not in captured):raise ValueError('ordered full prior capture')
                        event=json.loads(body);validate_event(event,(b,i,o),cases[o],p['operations'][i],claim)
                        if event['inputRequestId'] in ids:raise ValueError('one request ID per input')
                        d.new(path,{'value':event,'startedAtUnixNs':time.time_ns(),'requestBinding':ack});starts.append((b,i,o));ids.add(event['inputRequestId'])
                    elif self.path.startswith('/capture/'):
                        if not starts:raise ValueError('start required')
                        b,i,o=starts[-1];name=self.path.removeprefix('/capture/')
                        if name!=f'{b}-{i}-{o}.bin':raise ValueError('active tensor identity')
                        with path.open('xb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                        captured.add(name)
                    else:
                        value=json.loads(body)
                        if value['pageRequestId']!=claim:raise ValueError('terminal claim')
                        d.new(path,{'value':value,'requestBinding':ack})
                    upload_count+=1;d.new(root/'upload-events'/f'{upload_count:04d}.json',{'route':self.path,'requestBinding':ack});self.response(201,ack)
                except (ValueError,KeyError,FileExistsError):self.response(409,{'error':'capture contract'})

        def log_message(self,*args):pass

    print(f'JOINT_OPERATOR_SERVER http://127.0.0.1:{port}/browser.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures'):d.checked(prep[key])
    e,p,models,precision,layer,runtime,environment=resources(d.checked(prep['execution']))
    if prep['hostRatioGate']!=ratio_gate(e):raise ValueError('host ratio gate source')
    if prep['runtimeFiles']!=runtime:raise ValueError('runtime assets')
    config=d.read(prep['config']);live=d.read(d.bind(root/'live-browser.json'))['value'];claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId']
    base={'executionSha256':prep['execution']['sha256'],'models':models,'cases':p['cases']}
    if d.read(d.bind(root/'config-base.json'))!=base or config!=base|{'configSha256':d.bind(root/'config-base.json')['sha256']}:raise ValueError('frozen graph and input config')
    if live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['pageRequestId']!=claim or live['errors'] or live['phase']!='terminal' or not live['captureComplete'] or not live['crossOriginIsolated']:raise ValueError('complete browser terminal')
    if live['userAgent']!=environment['userAgent'] or live['adapterInfo']!=environment['adapterInfo']:raise ValueError('same browser environment')
    pairs=sequence(p,['wasm','webgpu']);cases={c['ordinal']:c for c in p['cases']}
    if len(live['records'])!=408 or len(live['startedInputs'])!=408 or len(list((root/'started-inputs').glob('*.json')))!=408 or len(list((root/'browser-capture').glob('*.bin')))!=408:raise ValueError('full408 captures/starts')
    captured={'cpu':d.read(prep['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];ids=[]
    for pair,event,rec in zip(pairs,live['startedInputs'],live['records'],strict=True):
        b,i,o=pair;c=cases[o];validate_event(event,pair,c,p['operations'][i],claim);path=root/'started-inputs'/f'{b}-{i}-{o}.json';st=d.read(d.bind(path))
        if st['value']!=event or st['startedAtUnixNs']<=(events[-1]['time'] if events else 0):raise ValueError('start persistence/order')
        if {k:rec[k] for k in event}!=event or rec['shape']!=event['targetShape'] or rec['dtype']!='float32':raise ValueError('actual tensor schema')
        ref=d.bind(root/'browser-capture'/f'{b}-{i}-{o}.bin')|{'shape':event['targetShape'],'dtype':'float32'};captured[b].append(event|{'output':ref});events.append({'binding':d.bind(path),'time':st['startedAtUnixNs']});ids.append(event['inputRequestId'])
    if len(set(ids))!=408:raise ValueError('unique input IDs')
    records=[];cpu_events=[]
    for b in captured:
        if len(captured[b])!=204 or [(r['operationIndex'],r['ordinal']) for r in captured[b]]!=[(i,o) for _,i,o in sequence(p,[b])]:raise ValueError('per-backend full204 order')
        for cap in captured[b]:
            i,o=cap['operationIndex'],cap['ordinal'];op=cases[o]['operations'][i]
            if cap['candidateIdentity']!=cases[o]['candidateIdentity'] or cap['inputSha256']!=op['input']['sha256'] or cap['targetShape']!=op['expected']['shape']:raise ValueError('same backend input reference')
            if b=='cpu':
                path=root/'cpu'/f'{i}-{o}-start.json';start=d.read(d.bind(path))
                if {k:start[k] for k in cap if k!='output'}!={k:v for k,v in cap.items() if k!='output'}:raise ValueError('CPU started identity')
                cpu_events.append(d.bind(path))
            reference=layer.read_tensor(precision,op['expected']);actual=layer.read_tensor(precision,cap['output']);stats=layer.differences(reference,actual)
            if b=='cpu' and i<2:
                old=d.read(p['inputs']['cpuRepairReport'])['captures']['operators'][o-1]['outputs'][i]
                if actual.tobytes()!=layer.read_tensor(precision,old).tobytes():raise ValueError('CPU Resize bitwise preservation')
            records.append({'backend':b,'operationIndex':i,'operation':p['operations'][i]['name'],'ordinal':o,'candidateIdentity':cap['candidateIdentity'],'difference':stats,'requiredMaxAbs':p['operations'][i]['diagnosticMaxAbs'],'numericGatePassed':stats['maxAbs']<=p['operations'][i]['diagnosticMaxAbs']})
    summary={spec['name']:{b:{'candidateCount':68,'maxAbs':max(r['difference']['maxAbs'] for r in records if r['backend']==b and r['operationIndex']==i),'failedOrdinals':[r['ordinal'] for r in records if r['backend']==b and r['operationIndex']==i and not r['numericGatePassed']]} for b in captured} for i,spec in enumerate(p['operations'])}
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))];expected_routes=['/claim']+[route for b,i,o in pairs for route in (f'/start/{b}/{i}/{o}',f'/capture/{b}-{i}-{o}.bin')]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected_routes:raise ValueError('persisted upload order')
    return {'schemaVersion':1,'ok':True,'decision':'full68_joint_numeric_operator_repair_reconstructed','inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json')},'captures':captured,'cpuStartEvents':cpu_events,'browserStartEvents':events,'uploadEvents':uploads,'records':records,'summary':summary,'allOperatorNumericGatesPassed':all(r['numericGatePassed'] for r in records),'operatorInputsPerBackend':{'cpu':204,'wasm':204,'webgpu':204},'cpuResizeOutputsBitwiseSameAsPriorRepair':True,'hostRatioGate':prep['hostRatioGate'],'sameFrozenInputReferenceForAllBackends':True,'newFullModelInputs':0,'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'originalFullModelNumericalFailuresPreserved':True,'missingWasm22FullLayerOutputsPreserved':True,'isolatedOperatorPassDoesNotProveFullModelPass':True,'fullModelBrowserGatePassed':False,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--serve',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',action='store_true');p.add_argument('--port',type=int,default=8839);a=p.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        try:
            result=reconstruct(root)
            if a.verify_report:
                if result!=d.read(d.bind(root/'report.json')):raise ValueError('report reconstruction_mismatch')
            else:d.new(root/'report.json',result)
            print(json.dumps({k:result[k] for k in ('ok','decision','allOperatorNumericGatesPassed','newFullModelInputs')}))
        except BaseException as error:
            if not a.verify_report:d.new(root/'audit-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'productHold':True})
            raise
    else:prepare(a.execution.resolve(),root)
