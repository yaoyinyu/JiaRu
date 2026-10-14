"""全68双来源首GN原始/候选分阶段隔离；完整模型与训练预算为零。"""
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('tail_operator_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)



def validate_scope(p):
    fixed={'purpose':'first_decoder_gn_original_then_hierarchical_patch_full68_two_origins_three_backend_isolation',
           'candidateCount':68,'contextsPerModelPerBackend':136,'requiredBackends':['cpu','wasm','webgpu'],
           'modelsInOrder':['original','patched'],'originalOperatorInputsAllowed':408,
           'patchedOperatorInputsAllowedOnlyAfterAllOriginalGates':408,'newOnnxOperatorInputsAllowed':816,
           'graphOptimizationLevel':'disabled','wasmNumThreads':1,'requiredOwnInputFp64NumericDifference':1e-4,
           'fullModelNumericDifferenceUnchanged':1e-4,'fullModelDecodedPixelDifferencesUnchanged':0,
           'fullModelPresenceDecisionDifferencesUnchanged':0,'newFullModelInputsAllowed':0,'newTorchInputsAllowed':0,
           'optimizerStepsAllowed':0,'valInputsAllowed':0,'protectedInputsAllowed':0,'newChatImageInputsAllowed':0,
           'formalReleaseAllowed':False,'fullModelLearnedGatePassed':False,'productHold':True}
    if any(p.get(k)!=v for k,v in fixed.items()):raise ValueError('full68 fixed scope / budgets / gates')
    for key in ('originalAll408OwnInputGatesRequiredBeforePatchedStage','allNativeFloat32FiniteOutputsRequired','oldFailuresAndConsumedBudgetsPreserved'):
        if p.get(key) is not True:raise ValueError('required guard '+key)
    if p['patch']!={'onlyFirstGnMeanAndVarianceTotalSum':True,'originalFirstChunk':128,'additionalSecondChunk':128,'originalGroupCount':4,'originalChannelCount':16,'originalParametersEpsilonAndGeluUnchanged':True,'originalLastGnAndHostRatiosNotModified':True,'reversePatchRestoresOriginalIsolatedModelBytes':True,'isolationDoesNotProveFullGraphFidelity':True}:raise ValueError('limited first GN repair')
    cases=p['cases']
    if len(cases)!=136 or [c['contextOrdinal'] for c in cases]!=list(range(1,137)) or [c['candidateOrdinal'] for c in cases]!=[i for i in range(1,69) for _ in range(2)] or [c['inputOrigin'] for c in cases]!=['wasm_dec1_0','cuda_dec1_0']*68:raise ValueError('full ordered two-origin denominator')
    for first,second in zip(cases[::2],cases[1::2],strict=True):
        if first['candidateIdentity']!=second['candidateIdentity'] or first['candidateIdentity']['identity']['split']!='train':raise ValueError('train-only stable paired identities')


def isolated_original(parent,boundary,output):
    producers={value:node for node in parent.graph.node for value in node.output};inits={i.name:i for i in parent.graph.initializer}
    wanted=set();used=set()
    def visit(value):
        if value==boundary:return
        if value in inits:used.add(value);return
        if value not in producers:raise ValueError('unexpected upstream boundary')
        node=producers[value]
        if node.name in wanted:return
        wanted.add(node.name)
        for inp in node.input:
            if inp:visit(inp)
    visit(output);result=copy.deepcopy(parent);graph=result.graph
    nodes=[n for n in parent.graph.node if n.name in wanted];initializers=[i for i in parent.graph.initializer if i.name in used]
    del graph.node[:];graph.node.extend(nodes);del graph.initializer[:];graph.initializer.extend(initializers)
    del graph.input[:];graph.input.append(onnx.helper.make_tensor_value_info(boundary,onnx.TensorProto.FLOAT,[1,16,'height','width']))
    del graph.output[:];graph.output.append(onnx.helper.make_tensor_value_info(output,onnx.TensorProto.FLOAT,[1,16,'height','width']))
    del graph.value_info[:];graph.name='first_decoder_gn_only_original_boundary'
    onnx.checker.check_model(result,full_check=True)
    return result


def save(path,a):
    if a.dtype!=np.float32 or not np.isfinite(a).all():raise ValueError('actual F32 finite output')
    with path.open('xb') as f:f.write(a.astype('<f4',copy=False).tobytes());f.flush();os.fsync(f.fileno())
    return d.bind(path)|{'shape':list(a.shape),'dtype':'float32'}


def differences(reference,actual):
    if reference.dtype!=np.float64 or actual.dtype!=np.float32 or reference.shape!=actual.shape or any(not np.isfinite(a).all() for a in (reference,actual)):raise ValueError('same native shape FP64 reference / actual FP32')
    delta=actual.astype(np.float64)-reference
    return {'maxAbs':float(np.max(np.abs(delta))),'meanAbs':float(np.mean(np.abs(delta))),'rootMeanSquare':float(np.sqrt(np.mean(delta*delta))),'comparisonDomain':'float64_reference_minus_promoted_actual_float32_no_reference_rounding'}


def require_original_gate(report):
    if not report.get('ok') or report.get('stage')!='original' or report.get('operatorInputsPerBackend')!={'cpu':136,'wasm':136,'webgpu':136} or len(report.get('records',[]))!=408 or not report.get('allOperatorNumericGatesPassed') or not all(r.get('numericGatePassed') is True for r in report['records']):raise ValueError('all original408 must pass before patched inputs')
    if [(r.get('backend'),r.get('ordinal')) for r in report['records']]!=[(b,o) for b in ('cpu','wasm','webgpu') for o in range(1,137)]:raise ValueError('original full backend/context order')
    if any(r.get('requiredMaxAbs')!=1e-4 or r['difference']['maxAbs']>1e-4 for r in report['records']):raise ValueError('original actual fixed numeric gate')


def original_gate(e):
    root=Path(e['stageRoots']['original']);result=reconstruct(root)
    if result!=d.read(d.bind(root/'report.json')):raise ValueError('original frozen report reconstruction')
    require_original_gate(result)
    return d.bind(root/'report.json')


def resources(execution,stage):
    if stage not in ('original','patched'):raise ValueError('stage')
    e=d.read(d.bind(execution))
    for ref in e['sources'].values():d.checked(ref)
    if e['sources']['auditor']!=d.bind(__file__) or e['executionImplementedAndFrozen'] is not True:raise ValueError('frozen executor')
    if e['runtimeVersions']!={'python':__import__('platform').python_version(),'numpy':np.__version__,'onnx':onnx.__version__,'onnxruntime':ort.__version__}:raise ValueError('frozen runtime versions')
    for ref in e['runtimeFiles'].values():d.checked(ref)
    for ref in e['pythonRuntimeFiles'].values():d.checked(ref)
    raw=d.read(e['scope']);validate_scope(raw)
    for ref in raw['inputs'].values():d.checked(ref)
    buffer=d.load(d.checked(e['sources']['tensorReader']),'first_gn_tensor_reader')
    decoder=d.read(raw['inputs']['decoderCounterfactual']);previous=d.read(raw['inputs']['decoderScope']);trace=d.read(raw['inputs']['trace']);parent_scope=d.read(raw['inputs']['parentScope']);old=d.read(raw['inputs']['originalFullFailure'])
    if not decoder['ok'] or not decoder['originalFinalHeadByteFidelityPreserved'] or decoder['actualFp32RepairOrWholeModelUnreachableProven'] or not trace['allOwnHeadsBitwiseIdenticalAllBackends'] or not trace['layerConclusionsAllowed'] or old['fullModelLearnedGatePassed'] or old['summary']['wasm']['failedOrdinals']!=[40]:raise ValueError('prior fidelity / failures retained')
    if any(row['failedOrdinals'] or row['decodedPixelDifferences'] or row['presenceFailed'] for row in decoder['summary'].values()):raise ValueError('full decoder diagnostic prerequisite')
    if raw['parentModel']!=previous['model'] or raw['inputs']['trace']!=previous['inputs']['trace'] or raw['inputs']['parentScope']!=previous['inputs']['parentScope']:raise ValueError('exact parent bindings')
    parent=onnx.load(d.checked(raw['parentModel']));boundary=raw['operatorInputName'];output=raw['operatorOutputName']
    normalized=[n for n in parent.graph.node if list(n.output)==['/dec1/dec1.1/InstanceNormalization_output_0']]
    if len(normalized)!=1 or normalized[0].op_type!='Div' or normalized[0].name!=raw['actualGroupNormPrefix']+'normalized' or boundary!='/dec1/dec1.0/Conv_output_0' or output!='/dec1/dec1.1/Add_output_0':raise ValueError('actual first GN semantic target')
    original=isolated_original(parent,boundary,output);actual=onnx.load(d.checked(raw['models']['original']))
    if original.SerializeToString()!=actual.SerializeToString():raise ValueError('exact original parent dependency cone')
    repair=d.load(d.checked(raw['inputs']['graphRepair']),'first_gn_repair');expected=repair.hierarchical_group_sum(copy.deepcopy(original),raw['actualGroupNormPrefix']);patched=onnx.load(d.checked(raw['models']['patched']))
    if patched.SerializeToString()!=expected.SerializeToString():raise ValueError('only frozen hierarchical sum patch')
    for name,m in [('original',actual),('patched',patched)]:
        onnx.checker.check_model(m,full_check=True)
        if [(x.name,x.type.tensor_type.elem_type) for x in m.graph.input]!=[(boundary,onnx.TensorProto.FLOAT)] or [(x.name,x.type.tensor_type.elem_type) for x in m.graph.output]!=[(output,onnx.TensorProto.FLOAT)]:raise ValueError('one native FP32 input and output')
        bindings=[{'name':i.name,'sha256':hashlib.sha256(i.SerializeToString()).hexdigest()} for i in m.graph.initializer if not i.name.startswith('hierarchical_'+raw['actualGroupNormPrefix'])]
        if bindings!=raw['originalInitializerTensorProtoBindings']:raise ValueError('original affine epsilon initializer bytes')
    if any(len(rows)!=68 for rows in (previous['cases'],decoder['records'],parent_scope['cases'],trace['captures']['wasm'])):raise ValueError('all68 authoritative records')
    for index,(c,record,parentcase,cap) in enumerate(zip(previous['cases'],decoder['records'],parent_scope['cases'],trace['captures']['wasm'],strict=True)):
        if c['ordinal']!=index+1 or any(c['candidateIdentity']!=r['candidateIdentity'] for r in (record,parentcase,cap)):raise ValueError('stable ordered original identity')
        for branch_index,branch in enumerate(['wasm_dec1_0','cuda_dec1_0']):
            case=raw['cases'][index*2+branch_index];reference=next(r for r in record['branches'] if r['branch']==branch)['firstGn64'];stored=cap['outputs']['layer25'] if branch_index==0 else parentcase['strictCudaLayers']['dec1.1']
            if case['candidateIdentity']!=c['candidateIdentity'] or case['input']!=c['branches'][branch]['firstGnInput'] or case['ownInputFp64Reference']!=reference or case['originalFullGraphFirstGnOutput']!=stored:raise ValueError('own actual input and FP64/full-graph references')
            x=buffer.read_tensor(case['input']);y=buffer.read_tensor(reference);z=buffer.read_tensor(stored)
            if x.dtype!=np.float32 or y.dtype!=np.float64 or z.dtype!=np.float32 or x.ndim!=4 or x.shape[:2]!=(1,16) or x.shape!=y.shape or x.shape!=z.shape:raise ValueError('native full-size storage domains')
    if stage=='patched':original_gate(e)
    p=copy.deepcopy(raw);p['stage']=stage
    p['operations']=[{'name':'first_decoder_gn_'+stage,'graph':raw['models'][stage],'diagnosticMaxAbs':raw['requiredOwnInputFp64NumericDifference']}]
    p['cases']=[c|{'ordinal':c['contextOrdinal'],'operations':[{'input':c['input'],'expected':c['ownInputFp64Reference']}]} for c in raw['cases']]
    models=[{'name':p['operations'][0]['name'],'graph':raw['models'][stage],'inputNames':[boundary],'outputName':output,'hasSizes':False}]
    return e,p,models,buffer,e['runtimeFiles'],e['expectedEnvironment']


def check_config(root,prep,p,models,environment):
    config=d.read(prep['config']);base=d.read(d.bind(root/'config-base.json'))
    expected={'stage':prep['stage'],'executionSha256':prep['execution']['sha256'],'models':models,'cases':p['cases'],'expectedEnvironment':environment}
    if base!=expected or config!=expected|{'configSha256':d.bind(root/'config-base.json')['sha256']} or prep['expectedEnvironment']!=environment or Path(d.checked(prep['html'])).read_bytes()!=HTML.encode('utf-8'):raise ValueError('frozen config / environment / exact HTML')
    return config


def sequence(p,backends):
    return [(b,index,c['ordinal']) for b in backends for index in range(len(p['operations'])) for c in p['cases']]


def validate_event(event,pair,case,spec,page):
    b,index,o=pair
    keys={'backend','operationIndex','operation','ordinal','candidateOrdinal','inputOrigin','candidateIdentity','inputSha256','targetShape','inputRequestId','pageRequestId'}
    if set(event)!=keys or event['backend']!=b or event['operationIndex']!=index or event['operation']!=spec['name'] or event['ordinal']!=o or event['candidateOrdinal']!=case['candidateOrdinal'] or event['inputOrigin']!=case['inputOrigin'] or event['candidateIdentity']!=case['candidateIdentity'] or event['inputSha256']!=case['input']['sha256'] or event['targetShape']!=case['ownInputFp64Reference']['shape'] or event['pageRequestId']!=page:raise ValueError('ordered own-input event')
    if str(uuid.UUID(event['inputRequestId']))!=event['inputRequestId']:raise ValueError('unique input UUID')


HTML=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>首GN分阶段双输入隔离</title><link rel="icon" href="data:,"><h1>开发算子数值诊断</h1><button id="run">执行本阶段WASM/WebGPU各136输入</button><pre id="result">未执行；完整模型输入0，产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>
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
  if(report.userAgent!==config.expectedEnvironment.userAgent||JSON.stringify(report.adapterInfo)!==JSON.stringify(config.expectedEnvironment.adapterInfo))throw Error('frozen actual browser environment');
  for(const backend of ['wasm','webgpu'])for(let index=0;index<1;index++){
   const model=config.models[index];let session;
   try{
    session=await ort.InferenceSession.create(await verified('/model/'+index+'.onnx',model.graph.sha256),{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    if(session.inputNames.join(',')!==model.inputNames.join(',')||session.outputNames.join(',')!==model.outputName)throw Error('actual IO names');
    for(const row of config.cases){
     report.phase=backend+' '+model.name+' '+row.ordinal+'/136';document.querySelector('#result').textContent=report.phase;
     const op=row.operations[index],x=new Float32Array(await verified('/input/'+index+'/'+row.ordinal+'.bin',op.input.sha256));if(x.length!==op.input.shape.reduce((a,b)=>a*b,1))throw Error('input cardinality');for(const v of x)if(!Number.isFinite(v))throw Error('input finite');
     const feeds={[model.inputNames[0]]:new ort.Tensor('float32',x,op.input.shape)};if(model.hasSizes)feeds[model.inputNames[1]]=new ort.Tensor('int64',BigInt64Array.from(op.expected.shape.map(BigInt)),[4]);
     const event={backend,operationIndex:index,operation:model.name,ordinal:row.ordinal,candidateOrdinal:row.candidateOrdinal,inputOrigin:row.inputOrigin,candidateIdentity:row.candidateIdentity,inputSha256:op.input.sha256,targetShape:op.expected.shape,inputRequestId:crypto.randomUUID(),pageRequestId:report.pageRequestId};
     await post('/start/'+backend+'/'+index+'/'+row.ordinal,JSON.stringify(event),report);report.startedInputs.push(event);
     const outputs=await session.run(feeds),t=outputs[model.outputName],a=new Float32Array(await t.getData());if(t.type!=='float32'||Array.from(t.dims).join(',')!==op.expected.shape.join(',')||a.length!==op.expected.shape.reduce((x,y)=>x*y,1))throw Error('output shape/dtype');for(const v of a)if(!Number.isFinite(v))throw Error('output finite');
     await post('/capture/'+backend+'-'+index+'-'+row.ordinal+'.bin',new Uint8Array(a.buffer),report);report.records.push({...event,shape:Array.from(t.dims),dtype:t.type});
    }
   }finally{if(session)await session.release();}
  }
  report.captureComplete=report.records.length===272;report.phase='terminal';
 }catch(e){report.captureComplete=false;report.errors.push(String(e));report.phase='terminal-failure';}
 await post('/terminal',JSON.stringify(report),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});document.querySelector('#result').textContent=JSON.stringify(report);
};</script></html>'''


def prepare(execution,root,stage):
    if root.exists():raise ValueError('budget exists; read-only replay only')
    e,p,models,buffer,runtime,environment=resources(execution,stage)
    if root!=Path(e['stageRoots'][stage]).resolve():raise ValueError('frozen stage root')
    root.mkdir(parents=True,exist_ok=False)
    for name in ('cpu','started-inputs','browser-capture','upload-events'):(root/name).mkdir()
    captures=[];started=0
    try:
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;options.log_severity_level=3
        for index,model in enumerate(models):
            session=ort.InferenceSession(str(d.checked(model['graph'])),sess_options=options,providers=['CPUExecutionProvider'])
            if [x.name for x in session.get_inputs()]!=model['inputNames'] or [x.name for x in session.get_outputs()]!=[model['outputName']]:raise ValueError('CPU IO names')
            for case in p['cases']:
                op=case['operations'][index];x=buffer.read_tensor(op['input']);feeds={model['inputNames'][0]:x}
                if model['hasSizes']:feeds[model['inputNames'][1]]=np.array(op['expected']['shape'],dtype=np.int64)
                event={'backend':'cpu','operationIndex':index,'operation':model['name'],'ordinal':case['ordinal'],'candidateOrdinal':case['candidateOrdinal'],'inputOrigin':case['inputOrigin'],'candidateIdentity':case['candidateIdentity'],'inputSha256':op['input']['sha256'],'targetShape':op['expected']['shape']}
                d.new(root/'cpu'/f'{index}-{case["ordinal"]}-start.json',event|{'startedAtUnixNs':time.time_ns()});started+=1
                y=session.run(None,feeds)[0]
                if list(y.shape)!=op['expected']['shape']:raise ValueError('CPU native shape')
                ref=save(root/'cpu'/f'{index}-{case["ordinal"]}.bin',y);captures.append(event|{'output':ref})
            print(json.dumps({'cpuStarted':started,'cpuCaptured':len(captures),'fullModelInputs':0}),flush=True)
        d.new(root/'cpu-captures.json',captures)
        config={'stage':stage,'executionSha256':d.bind(execution)['sha256'],'models':models,'cases':p['cases'],'expectedEnvironment':environment};d.new(root/'config-base.json',config);config['configSha256']=d.bind(root/'config-base.json')['sha256'];d.new(root/'config.json',config)
        with (root/'browser.html').open('xb') as f:f.write(HTML.encode('utf-8'));f.flush();os.fsync(f.fileno())
        d.new(root/'preparation.json',{'stage':stage,'originalGate':original_gate(e) if stage=='patched' else None,'execution':d.bind(execution),'auditor':d.bind(__file__),'html':d.bind(root/'browser.html'),'config':d.bind(root/'config.json'),'cpuCaptures':d.bind(root/'cpu-captures.json'),'runtimeFiles':runtime,'expectedEnvironment':{'userAgent':environment['userAgent'],'adapterInfo':environment['adapterInfo']}})
    except BaseException as error:
        d.new(root/'failure.json',{'ok':False,'error':str(error),'cpuStarted':started,'cpuCaptured':len(captures),'browserStarted':0,'fullModelInputs':0,'productHold':True});raise


def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures'):d.checked(prep[key])
    if prep['auditor']!=d.bind(__file__) or (root/'claim.json').exists() or any((root/'started-inputs').iterdir()):raise ValueError('frozen source / budget may not restart')
    e,p,models,buffer,runtime,environment=resources(d.checked(prep['execution']),prep['stage']);
    if root!=Path(e['stageRoots'][prep['stage']]).resolve() or prep['runtimeFiles']!=runtime:raise ValueError('frozen stage root / assets')
    config=check_config(root,prep,p,models,environment);cases={c['ordinal']:c for c in p['cases']};order=sequence(p,['wasm','webgpu'])
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
                        if not claim or len(starts)>=272:raise ValueError('start limit')
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

    print(f'FIRST_GN_OPERATOR_SERVER http://127.0.0.1:{port}/browser.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures'):d.checked(prep[key])
    e,p,models,buffer,runtime,environment=resources(d.checked(prep['execution']),prep['stage'])
    if root!=Path(e['stageRoots'][prep['stage']]).resolve():raise ValueError('frozen stage root')
    if prep['originalGate']!=(original_gate(e) if prep['stage']=='patched' else None):raise ValueError('exact prior original gate')
    if prep['runtimeFiles']!=runtime:raise ValueError('runtime assets')
    config=check_config(root,prep,p,models,environment);live=d.read(d.bind(root/'live-browser.json'))['value'];claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId']
    if live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['pageRequestId']!=claim or live['errors'] or live['phase']!='terminal' or not live['captureComplete'] or not live['crossOriginIsolated']:raise ValueError('complete browser terminal')
    if live['userAgent']!=environment['userAgent'] or live['adapterInfo']!=environment['adapterInfo']:raise ValueError('same browser environment')
    pairs=sequence(p,['wasm','webgpu']);cases={c['ordinal']:c for c in p['cases']}
    if len(live['records'])!=272 or len(live['startedInputs'])!=272 or len(list((root/'started-inputs').glob('*.json')))!=272 or len(list((root/'browser-capture').glob('*.bin')))!=272:raise ValueError('full272 browser captures/starts')
    captured={'cpu':d.read(prep['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];ids=[]
    for pair,event,rec in zip(pairs,live['startedInputs'],live['records'],strict=True):
        b,i,o=pair;c=cases[o];validate_event(event,pair,c,p['operations'][i],claim);path=root/'started-inputs'/f'{b}-{i}-{o}.json';st=d.read(d.bind(path))
        if st['value']!=event or st['startedAtUnixNs']<=(events[-1]['time'] if events else 0):raise ValueError('start persistence/order')
        if {k:rec[k] for k in event}!=event or rec['shape']!=event['targetShape'] or rec['dtype']!='float32':raise ValueError('actual tensor schema')
        ref=d.bind(root/'browser-capture'/f'{b}-{i}-{o}.bin')|{'shape':event['targetShape'],'dtype':'float32'};captured[b].append(event|{'output':ref});events.append({'binding':d.bind(path),'time':st['startedAtUnixNs']});ids.append(event['inputRequestId'])
    if len(set(ids))!=272:raise ValueError('unique input IDs')
    records=[];cpu_events=[]
    for b in captured:
        if len(captured[b])!=136 or [(r['operationIndex'],r['ordinal']) for r in captured[b]]!=[(i,o) for _,i,o in sequence(p,[b])]:raise ValueError('per-backend full136 order')
        for cap in captured[b]:
            i,o=cap['operationIndex'],cap['ordinal'];op=cases[o]['operations'][i]
            if cap['candidateIdentity']!=cases[o]['candidateIdentity'] or cap['candidateOrdinal']!=cases[o]['candidateOrdinal'] or cap['inputOrigin']!=cases[o]['inputOrigin'] or cap['inputSha256']!=op['input']['sha256'] or cap['targetShape']!=op['expected']['shape'] or cap['output']['dtype']!='float32':raise ValueError('same backend input reference / actual storage')
            if b=='cpu':
                path=root/'cpu'/f'{i}-{o}-start.json';start=d.read(d.bind(path))
                if {k:start[k] for k in cap if k!='output'}!={k:v for k,v in cap.items() if k!='output'}:raise ValueError('CPU started identity')
                cpu_events.append(d.bind(path))
            reference=buffer.read_tensor(op['expected']);actual=buffer.read_tensor(cap['output']);stats=differences(reference,actual)
            stored=buffer.read_tensor(cases[o]['originalFullGraphFirstGnOutput']);stored_difference=float(np.max(np.abs(actual.astype(np.float64)-stored.astype(np.float64))))
            records.append({'backend':b,'operationIndex':i,'operation':p['operations'][i]['name'],'ordinal':o,'candidateOrdinal':cases[o]['candidateOrdinal'],'inputOrigin':cases[o]['inputOrigin'],'candidateIdentity':cap['candidateIdentity'],'difference':stats,'originalFullGraphOwnOriginOutputMaxAbsDiagnostic':stored_difference,'requiredMaxAbs':p['operations'][i]['diagnosticMaxAbs'],'numericGatePassed':stats['maxAbs']<=p['operations'][i]['diagnosticMaxAbs']})
    summary={b:{'contextCount':136,'candidateCount':68,'maxAbs':max(r['difference']['maxAbs'] for r in records if r['backend']==b),'failedContexts':[{'contextOrdinal':r['ordinal'],'candidateOrdinal':r['candidateOrdinal'],'inputOrigin':r['inputOrigin']} for r in records if r['backend']==b and not r['numericGatePassed']], 'byInputOrigin':{origin:{'candidateCount':68,'maxAbs':max(r['difference']['maxAbs'] for r in records if r['backend']==b and r['inputOrigin']==origin)} for origin in ('wasm_dec1_0','cuda_dec1_0')}} for b in captured}
    if len(list((root/'cpu').glob('*-start.json')))!=136 or len(list((root/'cpu').glob('*.bin')))!=136:raise ValueError('full CPU start/capture cardinality')
    for a,b in zip(cpu_events,cpu_events[1:]):
        if d.read(a)['startedAtUnixNs']>=d.read(b)['startedAtUnixNs']:raise ValueError('CPU monotonic starts')
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))];expected_routes=['/claim']+[route for b,i,o in pairs for route in (f'/start/{b}/{i}/{o}',f'/capture/{b}-{i}-{o}.bin')]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected_routes:raise ValueError('persisted upload order')
    return {'schemaVersion':1,'ok':True,'decision':'full68_two_origin_first_gn_stage_reconstructed','stage':prep['stage'],'originalGate':prep['originalGate'],'inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json')},'captures':captured,'cpuStartEvents':cpu_events,'browserStartEvents':events,'uploadEvents':uploads,'records':records,'summary':summary,'allOperatorNumericGatesPassed':all(r['numericGatePassed'] for r in records),'operatorInputsPerBackend':{'cpu':136,'wasm':136,'webgpu':136},'operatorInputsConsumed':408,'sameFrozenInputReferenceForAllBackends':True,'ownInputReferenceStorageDomain':'float64','referenceNotRoundedToFloat32':True,'newFullModelInputs':0,'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'originalFullModelNumericalFailuresPreserved':True,'isolatedOperatorPassDoesNotProveFullModelPass':True,'fullModelBrowserGatePassed':False,'formalReleaseAllowed':False,'productHold':True}



if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--stage',choices=['original','patched']);p.add_argument('--output',type=Path,required=True);p.add_argument('--serve',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',action='store_true');p.add_argument('--port',type=int,default=8854);a=p.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        try:
            result=reconstruct(root)
            if a.verify_report:
                if result!=d.read(d.bind(root/'report.json')):raise ValueError('report reconstruction_mismatch')
            else:d.new(root/'report.json',result)
            print(json.dumps({k:result[k] for k in ('ok','decision','stage','allOperatorNumericGatesPassed','operatorInputsConsumed','summary','newFullModelInputs')}))
        except BaseException as error:
            if not a.verify_report:d.new(root/'audit-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'productHold':True})
            raise
    else:prepare(a.execution.resolve(),root,a.stage)
