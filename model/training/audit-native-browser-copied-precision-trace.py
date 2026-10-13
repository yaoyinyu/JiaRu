"""全68副本坐标与归一化统计追踪，先验证全部原算子结果逐字节不变。"""
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
    if p['purpose']!='full68_resize_coordinate_and_groupnorm_statistics_trace_only' or len(p['cases'])!=68 or p['traceOperatorInputsPerBackendAllowed']!={'cpu':136,'wasm':136,'webgpu':136} or p['newAnalyticalFp64StatisticsAllowed']!=68:raise ValueError('full68 trace budget')
    if any(p[k]!=0 for k in ('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed')):raise ValueError('trace only roles')
    if p['groupNorm']!={'groups':4,'channels':16,'epsilon':1e-5} or p['graphOptimizationLevel']!='disabled' or p['fullModelRequiredNumericDifference']!=1e-4 or p['fullModelRequiredDecodedPixelDifferences']!=0:raise ValueError('frozen numerical gate')
    if [(x['operationIndex'],x['operation'],len(x['additionalOutputs'])) for x in p['traceOperations']]!=[(0,'resize_d2_to_e1_repaired',10),(1,'dec1.4_group_norm',6)]:raise ValueError('trace output schema')
    for k in ('onlyResizeIdentityCopiesAndAdditionalOutputsAllowed','identityCopiesNeverFeedOriginalNodes','originalNodesInitializersInputsAndFinalOutputsUnchanged','syntheticControlPassDoesNotProveLearnedTraceFidelity','oldFailedTraceCapturesMayNotBeReinterpreted','allFinalOperatorOutputsMustMatchSameBackendUninstrumentedCapturesBitwiseBeforeAnyConclusion','finalReferenceMustComeFromOriginalOperatorReport','freezeNativeShapesFloat32FiniteAndStableIdentities','fp64StatisticsDiagnosticOnlyNotReplacementCudaReference','webgpuOnlyResizeRepairCannotCloseExistingWasmFailure','newFull68NonzeroControlsAndAllBackendModelGatesRequiredAfterRepair','allOldFailuresAndMissingWasm22LayerOutputsPreserved','productHold'):
        if p[k] is not True:raise ValueError('guard '+k)
    if p['addOutputsOnly'] is not False or p['fullCandidateCount']!=68:raise ValueError('explicit copies / full denominator')
    if p['formalReleaseAllowed'] is not False:raise ValueError('release prohibited')


def graph_guard(spec):
    original=onnx.load(d.checked(spec['originalGraph']));model=onnx.load(d.checked(spec['instrumentedGraph']));onnx.checker.check_model(model)
    if [x.name for x in model.graph.output]!=[spec['originalFinalOutput'],*spec['additionalOutputs']]:raise ValueError('ordered output names')
    if any(x.type.tensor_type.elem_type!=onnx.TensorProto.FLOAT for x in model.graph.output):raise ValueError('float32 outputs')
    copies=spec['diagnosticCopies']
    expected_sources=['native_bilinear_0_y_shifted','native_bilinear_0_y_lambda1','native_bilinear_0_x_shifted','native_bilinear_0_x_lambda1'] if spec['operationIndex']==0 else []
    if [(c['source'],c['output'],c['op']) for c in copies]!=[(n,'observation_'+n,'Identity') for n in expected_sources]:raise ValueError('four declared Identity copies / GN output only')
    if len(model.graph.node)!=len(original.graph.node)+len(copies):raise ValueError('only observation nodes')
    for node,copy in zip(model.graph.node[len(original.graph.node):],copies,strict=True):
        expected=onnx.helper.make_node('Identity',[copy['source']],[copy['output']],name=copy['output']+'_copy')
        if node.SerializeToString()!=expected.SerializeToString():raise ValueError('exact independent Identity node')
    if any(name in {c['output'] for c in copies} for node in original.graph.node for name in node.input):raise ValueError('observation must not feed original graph')
    stripped=onnx.ModelProto();stripped.CopyFrom(model);del stripped.graph.output[1:];del stripped.graph.node[len(original.graph.node):]
    if stripped.SerializeToString()!=original.SerializeToString() or not spec['originalNodesAndInitializersUnchanged']:raise ValueError('original graph / weights / inputs / final unchanged')
    return {'name':spec['operation'],'graph':spec['instrumentedGraph'],'inputNames':[x.name for x in model.graph.input],'outputNames':[x.name for x in model.graph.output],'hasSizes':spec['operationIndex']==0}


def resources(execution):
    e=d.read(d.bind(execution))
    for ref in [e['auditor'],*e['helpers'].values()]:d.checked(ref)
    if e['auditor']!=d.bind(__file__):raise ValueError('auditor version')
    p=d.read(e['scope']);validate_scope(p)
    for ref in p['inputs'].values():d.checked(ref)
    prior=d.read(p['inputs']['operatorReport']);oldscope=d.read(p['inputs']['operatorScope'])
    helper=d.load(d.checked(e['helpers']['operators']),'precision_trace_prior')
    _,op,_,precision,layer,runtime,environment=helper.resources(d.checked(d.read(prior['inputs']['preparation'])['execution']))
    if oldscope!=op or p['cases']!=op['cases'] or p['candidateIdentities']!=op['candidateIdentities'] or len(prior['records'])!=612 or not prior['ok'] or prior['fullModelBrowserGatePassed']:raise ValueError('original full68 reference')
    if not d.read(p['inputs']['copyControl'])['allVariantsBitwiseIdenticalToOwnBackendBaseline'] or not d.read(p['inputs']['combinedControl'])['allVariantsBitwiseIdenticalToOwnBackendBaseline'] or d.read(p['inputs']['failedTraceFidelity'])['allFinalOperatorOutputsBitwiseIdenticalAllBackends']:raise ValueError('controls / old failure')
    p['operations']=op['operations'][:2]
    models=[graph_guard(spec) for spec in p['traceOperations']]
    for i,spec in enumerate(p['traceOperations']):
        if spec['originalGraph']!=p['operations'][i]['graph']:raise ValueError('same original graph')
    if [r['ordinal'] for r in p['cases']]!=list(range(1,69)) or any(c['candidateIdentity']['identity']['split']!='train' for c in p['cases']):raise ValueError('train-only identities')
    for case in p['cases']:case['traceOutputNames']=[m['outputNames'] for m in models]
    return e,p,models,precision,layer,runtime,environment,prior


def shapes(case,index):
    target=case['operations'][index]['expected']['shape']
    if index==0:return [target if name=='y' else [target[2 if '_y_' in name else 3]] if name.endswith(('_shifted','_lambda1')) else [] for name in case['traceOutputNames'][index]]
    return [target,[1],*[ [1,4,1] for _ in range(5) ]]


def sequence(p,backends):
    return [(b,index,c['ordinal']) for b in backends for index in range(2) for c in p['cases']]


def analytical(case,precision,layer):
    x=layer.read_tensor(precision,case['operations'][1]['input']).astype(np.float64).reshape(1,4,-1)
    mean=x.mean(axis=2,keepdims=True);variance=np.square(x-mean).mean(axis=2,keepdims=True)
    return {'ordinal':case['ordinal'],'candidateIdentity':case['candidateIdentity'],'input':case['operations'][1]['input'],'dtype':'float64','count':x.shape[2],'mean':mean.tolist(),'variance':variance.tolist(),'std':np.sqrt(variance+float(np.float32(1e-5))).tolist(),'diagnosticOnly':True,'notCudaReference':True}


def exact_final(layer,precision,reference,actual):
    layer.exact(layer.read_tensor(precision,reference),layer.read_tensor(precision,actual))


def validate_event(event,pair,case,spec,page):
    b,index,o=pair
    if set(event)!={'backend','operationIndex','operation','ordinal','candidateIdentity','inputSha256','targetShape','inputRequestId','pageRequestId'} or event['backend']!=b or event['operationIndex']!=index or event['operation']!=spec['name'] or event['ordinal']!=o or event['candidateIdentity']!=case['candidateIdentity'] or event['inputSha256']!=case['operations'][index]['input']['sha256'] or event['targetShape']!=case['operations'][index]['expected']['shape'] or event['pageRequestId']!=page:raise ValueError('ordered same-input event')
    if str(uuid.UUID(event['inputRequestId']))!=event['inputRequestId']:raise ValueError('unique request ID')


HTML=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>坐标与归一化统计追踪</title><link rel="icon" href="data:,"><h1>开发算子数值诊断</h1><button id="run">执行WASM/WebGPU各136追踪算子输入</button><pre id="result">未执行；完整模型输入0，产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>
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
  for(const backend of ['wasm','webgpu'])for(let index=0;index<2;index++){
   const model=config.models[index];let session;
   try{
    session=await ort.InferenceSession.create(await verified('/model/'+index+'.onnx',model.graph.sha256),{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    if(session.inputNames.join(',')!==model.inputNames.join(',')||session.outputNames.join(',')!==model.outputNames.join(','))throw Error('actual IO names');
    for(const row of config.cases){
     report.phase=backend+' '+model.name+' '+row.ordinal+'/68';document.querySelector('#result').textContent=report.phase;
     const op=row.operations[index],x=new Float32Array(await verified('/input/'+index+'/'+row.ordinal+'.bin',op.input.sha256));if(x.length!==op.input.shape.reduce((a,b)=>a*b,1))throw Error('input cardinality');for(const v of x)if(!Number.isFinite(v))throw Error('input finite');
     const feeds={[model.inputNames[0]]:new ort.Tensor('float32',x,op.input.shape)};if(model.hasSizes)feeds[model.inputNames[1]]=new ort.Tensor('int64',BigInt64Array.from(op.expected.shape.map(BigInt)),[4]);
     const event={backend,operationIndex:index,operation:model.name,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity,inputSha256:op.input.sha256,targetShape:op.expected.shape,inputRequestId:crypto.randomUUID(),pageRequestId:report.pageRequestId};
     await post('/start/'+backend+'/'+index+'/'+row.ordinal,JSON.stringify(event),report);report.startedInputs.push(event);
     const outputs=await session.run(feeds),records=[];
     const target=op.expected.shape,expected=index===0?model.outputNames.map(name=>name==='y'?target:name.endsWith('_shifted')||name.endsWith('_lambda1')?[target[name.includes('_y_')?2:3]]:[]):[target,[1],...Array.from({length:5},()=>[1,4,1])];
     for(let j=0;j<model.outputNames.length;j++){
      const t=outputs[model.outputNames[j]],a=new Float32Array(await t.getData());if(t.type!=='float32'||Array.from(t.dims).join(',')!==expected[j].join(',')||a.length!==expected[j].reduce((x,y)=>x*y,1))throw Error('output shape/dtype');for(const v of a)if(!Number.isFinite(v))throw Error('output finite');
      await post('/capture/'+backend+'-'+index+'-'+row.ordinal+'-'+j+'.bin',new Uint8Array(a.buffer),report);records.push({name:model.outputNames[j],shape:Array.from(t.dims),dtype:t.type});
     }
     report.records.push({...event,outputs:records});
    }
   }finally{if(session)await session.release();}
  }
  report.captureComplete=report.records.length===272;report.phase='terminal';
 }catch(e){report.captureComplete=false;report.errors.push(String(e));report.phase='terminal-failure';}
 await post('/terminal',JSON.stringify(report),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});document.querySelector('#result').textContent=JSON.stringify(report);
};</script></html>'''


def prepare(execution,root):
    if root.exists():raise ValueError('budget exists; replay only')
    e,p,models,precision,layer,runtime,environment,prior=resources(execution)
    root.mkdir(parents=True,exist_ok=False)
    for name in ('cpu','started-inputs','browser-capture','upload-events'):(root/name).mkdir()
    captures=[];started=0
    try:
        stats=[analytical(case,precision,layer) for case in p['cases']];d.new(root/'analytical-fp64.json',stats)
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;options.log_severity_level=3
        for index,model in enumerate(models):
            session=ort.InferenceSession(str(d.checked(model['graph'])),sess_options=options,providers=['CPUExecutionProvider'])
            if [x.name for x in session.get_inputs()]!=model['inputNames'] or [x.name for x in session.get_outputs()]!=model['outputNames']:raise ValueError('CPU IO names')
            for case in p['cases']:
                op=case['operations'][index];x=layer.read_tensor(precision,op['input']);feeds={model['inputNames'][0]:x}
                if model['hasSizes']:feeds[model['inputNames'][1]]=np.array(op['expected']['shape'],dtype=np.int64)
                event={'backend':'cpu','operationIndex':index,'operation':model['name'],'ordinal':case['ordinal'],'candidateIdentity':case['candidateIdentity'],'inputSha256':op['input']['sha256'],'targetShape':op['expected']['shape']}
                d.new(root/'cpu'/f'{index}-{case["ordinal"]}-start.json',event|{'startedAtUnixNs':time.time_ns()});started+=1
                ys=session.run(None,feeds);outputs=[]
                for j,(name,y,shape) in enumerate(zip(model['outputNames'],ys,shapes(case,index),strict=True)):
                    if list(y.shape)!=shape:raise ValueError('CPU trace shape')
                    outputs.append({'name':name,'tensor':layer.save(root/'cpu'/f'{index}-{case["ordinal"]}-{j}.bin',y)})
                original=next(c for c in prior['captures']['cpu'] if c['operationIndex']==index and c['ordinal']==case['ordinal'])
                exact_final(layer,precision,original['output'],outputs[0]['tensor']);captures.append(event|{'outputs':outputs})
            print(json.dumps({'cpuStarted':started,'cpuCaptured':len(captures),'fullModelInputs':0}),flush=True)
        d.new(root/'cpu-captures.json',captures)
        config={'executionSha256':d.bind(execution)['sha256'],'models':models,'cases':p['cases']};d.new(root/'config-base.json',config);config['configSha256']=d.bind(root/'config-base.json')['sha256'];d.new(root/'config.json',config)
        with (root/'browser.html').open('xb') as f:f.write(HTML.encode('utf-8'));f.flush();os.fsync(f.fileno())
        d.new(root/'preparation.json',{'execution':d.bind(execution),'auditor':d.bind(__file__),'html':d.bind(root/'browser.html'),'config':d.bind(root/'config.json'),'cpuCaptures':d.bind(root/'cpu-captures.json'),'analyticalStatistics':d.bind(root/'analytical-fp64.json'),'runtimeFiles':runtime,'expectedEnvironment':{'userAgent':environment['userAgent'],'adapterInfo':environment['adapterInfo']}})
    except BaseException as error:
        d.new(root/'failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'cpuStarted':started,'cpuCaptured':len(captures),'browserStarted':0,'fullModelInputs':0,'productHold':True});raise


def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures','analyticalStatistics'):d.checked(prep[key])
    if prep['auditor']!=d.bind(__file__) or (root/'claim.json').exists() or any((root/'started-inputs').iterdir()):raise ValueError('frozen source / budget may not restart')
    _,p,_,_,_,_,_,_=resources(d.checked(prep['execution']));config=d.read(prep['config']);cases={c['ordinal']:c for c in p['cases']};order=sequence(p,['wasm','webgpu'])
    routes={'/browser.html':prep['html'],'/config.json':prep['config']};routes.update({'/ort/'+k:v for k,v in prep['runtimeFiles'].items()})
    for index,spec in enumerate(p['operations']):routes[f'/model/{index}.onnx']=p['traceOperations'][index]['instrumentedGraph']
    for c in cases.values():
        for index,op in enumerate(c['operations'][:2]):routes[f'/input/{index}/{c["ordinal"]}.bin']={k:op['input'][k] for k in ('path','sha256')}
    allowed={f'{b}-{i}-{o}-{j}.bin':math.prod(shape)*4 for b,i,o in order for j,shape in enumerate(shapes(cases[o],i))}
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
                        if not claim or len(starts)>=272:raise ValueError('start limit')
                        b,i,o=order[len(starts)]
                        if self.path!=f'/start/{b}/{i}/{o}' or (starts and any(f'{starts[-1][0]}-{starts[-1][1]}-{starts[-1][2]}-{j}.bin' not in captured for j in range(len(config['models'][starts[-1][1]]['outputNames'])))):raise ValueError('ordered full prior capture')
                        event=json.loads(body);validate_event(event,(b,i,o),cases[o],p['operations'][i],claim)
                        if event['inputRequestId'] in ids:raise ValueError('one request ID per input')
                        d.new(path,{'value':event,'startedAtUnixNs':time.time_ns(),'requestBinding':ack});starts.append((b,i,o));ids.add(event['inputRequestId'])
                    elif self.path.startswith('/capture/'):
                        if not starts:raise ValueError('start required')
                        b,i,o=starts[-1];name=self.path.removeprefix('/capture/')
                        if name not in [f'{b}-{i}-{o}-{j}.bin' for j in range(len(config['models'][i]['outputNames']))]:raise ValueError('active tensor identity')
                        with path.open('xb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                        captured.add(name)
                    else:
                        value=json.loads(body)
                        if value['pageRequestId']!=claim:raise ValueError('terminal claim')
                        d.new(path,{'value':value,'requestBinding':ack})
                    upload_count+=1;d.new(root/'upload-events'/f'{upload_count:04d}.json',{'route':self.path,'requestBinding':ack});self.response(201,ack)
                except (ValueError,KeyError,FileExistsError):self.response(409,{'error':'capture contract'})

        def log_message(self,*args):pass

    print(f'PRECISION_TRACE_SERVER http://127.0.0.1:{port}/browser.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures','analyticalStatistics'):d.checked(prep[key])
    e,p,models,precision,layer,runtime,environment,prior=resources(d.checked(prep['execution']))
    if prep['runtimeFiles']!=runtime:raise ValueError('runtime assets')
    config=d.read(prep['config']);live=d.read(d.bind(root/'live-browser.json'))['value'];claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId']
    if live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['pageRequestId']!=claim or live['errors'] or live['phase']!='terminal' or not live['captureComplete'] or not live['crossOriginIsolated']:raise ValueError('complete browser terminal')
    if live['userAgent']!=environment['userAgent'] or live['adapterInfo']!=environment['adapterInfo']:raise ValueError('same browser environment')
    pairs=sequence(p,['wasm','webgpu']);cases={c['ordinal']:c for c in p['cases']}
    if len(live['records'])!=272 or len(live['startedInputs'])!=272 or len(list((root/'started-inputs').glob('*.json')))!=272 or len(list((root/'browser-capture').glob('*.bin')))!=sum(len(m['outputNames']) for m in models)*len(p['cases'])*2:raise ValueError('full272 starts /2448 tensors')
    captured={'cpu':d.read(prep['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];ids=[]
    for pair,event,rec in zip(pairs,live['startedInputs'],live['records'],strict=True):
        b,i,o=pair;c=cases[o];validate_event(event,pair,c,p['operations'][i],claim);path=root/'started-inputs'/f'{b}-{i}-{o}.json';st=d.read(d.bind(path))
        if st['value']!=event or st['startedAtUnixNs']<=(events[-1]['time'] if events else 0):raise ValueError('start persistence/order')
        if {k:rec[k] for k in event}!=event or len(rec['outputs'])!=len(models[i]['outputNames']):raise ValueError('actual trace schema')
        outputs=[]
        for j,(schema,name,shape) in enumerate(zip(rec['outputs'],models[i]['outputNames'],shapes(c,i),strict=True)):
            if schema!={'name':name,'shape':shape,'dtype':'float32'}:raise ValueError('actual output shape/name/dtype')
            outputs.append({'name':name,'tensor':d.bind(root/'browser-capture'/f'{b}-{i}-{o}-{j}.bin')|{'shape':shape,'dtype':'float32'}})
        captured[b].append(event|{'outputs':outputs});events.append({'binding':d.bind(path),'time':st['startedAtUnixNs']});ids.append(event['inputRequestId'])
    if len(set(ids))!=272:raise ValueError('unique inputs')
    cpu_events=[]
    # 先核验全部后端原结果；任何失败均禁止返回统计结论。
    for b,rows in captured.items():
        if len(rows)!=136 or [(r['operationIndex'],r['ordinal']) for r in rows]!=[(i,o) for _,i,o in sequence(p,[b])]:raise ValueError('full136 order')
        for cap in rows:
            i,o=cap['operationIndex'],cap['ordinal'];op=cases[o]['operations'][i]
            if cap['candidateIdentity']!=cases[o]['candidateIdentity'] or cap['inputSha256']!=op['input']['sha256'] or cap['targetShape']!=op['expected']['shape']:raise ValueError('same frozen input')
            if b=='cpu':
                path=root/'cpu'/f'{i}-{o}-start.json';st=d.read(d.bind(path))
                if {k:st[k] for k in cap if k!='outputs'}!={k:v for k,v in cap.items() if k!='outputs'}:raise ValueError('CPU event')
                cpu_events.append(d.bind(path))
            for out,name,shape in zip(cap['outputs'],models[i]['outputNames'],shapes(cases[o],i),strict=True):
                if out['name']!=name or out['tensor']['shape']!=shape:raise ValueError('stored trace shape/name')
                layer.read_tensor(precision,out['tensor'])
            original=next(c for c in prior['captures'][b] if c['operationIndex']==i and c['ordinal']==o)
            exact_final(layer,precision,original['output'],cap['outputs'][0]['tensor'])
    analytical_stats=[analytical(c,precision,layer) for c in p['cases']]
    if analytical_stats!=d.read(prep['analyticalStatistics']):raise ValueError('FP64 diagnostic replay')
    traces=[]
    for b in ('wasm','webgpu'):
        for cap,cpu in zip(captured[b],captured['cpu'],strict=True):
            i,o=cap['operationIndex'],cap['ordinal'];outs={x['name']:layer.read_tensor(precision,x['tensor']) for x in cap['outputs']};refs={x['name']:layer.read_tensor(precision,x['tensor']) for x in cpu['outputs']}
            differences={name:layer.differences(refs[name],outs[name])|{'bitwiseEqual':refs[name].tobytes()==outs[name].tobytes()} for name in models[i]['outputNames'][1:]}
            row={'backend':b,'operationIndex':i,'ordinal':o,'candidateIdentity':cap['candidateIdentity'],'differenceFromCpu':differences}
            if i==1:
                fp64=analytical_stats[o-1];row['diagnosticFp64Errors']={name:float(np.max(np.abs(outs[f'stable_gn_209_{name}'].astype(np.float64)-np.asarray(fp64[name])))) for name in ('mean','variance','std')}
                count=outs['stable_gn_209_count'];row['divisionFromOwnSumErrors']={name:float(np.max(np.abs(np.float32(outs[f'stable_gn_209_{name}_total_sum']/count)-outs[f'stable_gn_209_{name}']))) for name in ('mean','variance')}
            traces.append(row)
    summary={str(i):{b:{'candidateCount':68,'differentOutputOrdinals':{name:[r['ordinal'] for r in traces if r['backend']==b and r['operationIndex']==i and not r['differenceFromCpu'][name]['bitwiseEqual']] for name in models[i]['outputNames'][1:]},'maxAbsFromCpu':{name:max(r['differenceFromCpu'][name]['maxAbs'] for r in traces if r['backend']==b and r['operationIndex']==i) for name in models[i]['outputNames'][1:]}} for b in ('wasm','webgpu')} for i in range(2)}
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))];expected_routes=['/claim']+[route for b,i,o in pairs for route in [f'/start/{b}/{i}/{o}',*[f'/capture/{b}-{i}-{o}-{j}.bin' for j in range(len(models[i]['outputNames']))]]]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected_routes:raise ValueError('upload order')
    return {'schemaVersion':1,'ok':True,'decision':'full68_copied_precision_trace_reconstructed_original_outputs_unchanged','inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json')},'captures':captured,'cpuStartEvents':cpu_events,'browserStartEvents':events,'uploadEvents':uploads,'traces':traces,'summary':summary,'allFinalOperatorOutputsBitwiseIdenticalAllBackends':True,'traceOperatorInputsPerBackend':{'cpu':136,'wasm':136,'webgpu':136},'analyticalFp64Statistics':68,'fp64DiagnosticOnly':True,'newFullModelInputs':0,'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'originalFailuresAndMissingWasm22Preserved':True,'traceDoesNotProveFullModelPass':True,'fullModelBrowserGatePassed':False,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--serve',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',action='store_true');p.add_argument('--port',type=int,default=8837);a=p.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        try:
            result=reconstruct(root)
            if a.verify_report:
                if result!=d.read(d.bind(root/'report.json')):raise ValueError('report reconstruction_mismatch')
            else:d.new(root/'report.json',result)
            print(json.dumps({k:result[k] for k in ('ok','decision','allFinalOperatorOutputsBitwiseIdenticalAllBackends','newFullModelInputs')}))
        except BaseException as error:
            if not a.verify_report:d.new(root/'audit-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'productHold':True})
            raise
    else:prepare(a.execution.resolve(),root)
