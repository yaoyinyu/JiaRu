"""只执行未消费输入并继承中断RAW；保留缺层分母和旧失败。"""
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

import onnx

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('continue_layer_data', HERE/'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)


def validate_scope(p):
    if p['purpose'] != 'continue_only_unconsumed_layerwise_inputs_after_transport_failure' or p['fullCandidateCount'] != 68:
        raise ValueError('scope purpose/full68')
    if p['newWasmOrdinalsAllowed'] != list(range(23,69)) or p['newWebgpuOrdinalsAllowed'] != list(range(1,69)) or p['newBrowserInputsAllowed'] != 114:
        raise ValueError('exact unconsumed114')
    if any(p[k] != 0 for k in ('newCpuInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed')):
        raise ValueError('zero CPU/Torch/optimization/protected scope')
    if p['graphOptimizationLevel'] != 'disabled' or p['requiredNumericDifference'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0 or p['maximumUploadAttemptsPerTensor'] != 3:
        raise ValueError('frozen quality/transport limits')
    if p['missingWasm22Outputs'] != ['dec1.4','dec1.5','delta'] or p['lastThreeLayerDenominatorAfterCompletion'] != {'cpu':68,'wasm':67,'webgpu':68}:
        raise ValueError('missing layers preserved')
    if p['inheritedCpuOrdinals'] != list(range(1,69)) or p['inheritedWasmFinalHeadOrdinals'] != list(range(1,23)) or p['inheritedWasmCompleteLayerOrdinals'] != list(range(1,22)) or p['inheritedWasmPartialOrdinal'] != 22:
        raise ValueError('exact inheritance')
    for k in ('requireFull68FinalHeadBitwiseParityBeforeAnyLayerConclusion','full31AllBackendConclusionProhibited','firstCrossingNotRootCauseProof','allOriginalFailuresAndConsumedBudgetsPreserved','failedBrowserBudgetMayNotRestart','inheritedNonzeroControls','uploadRetryMustNotReexecuteModel','uploadAcknowledgmentsMustBindSha256AndByteCount','consumeResponseBodies','strictGetStatusBeforeUploadOnlyRetry','productHold'):
        if p[k] is not True: raise ValueError('guard '+k)
    if p['formalReleaseAllowed'] is not False: raise ValueError('release prohibited')


def resources(execution):
    e=d.read(d.bind(execution)); d.checked(e['auditor'])
    if e['auditor'] != d.bind(__file__): raise ValueError('auditor version')
    p=d.read(e['scope']); validate_scope(p)
    for ref in p['inputs'].values(): d.checked(ref)
    inv=d.read(p['inputs']['interruptionInventory']); prep=d.read(p['inputs']['originalPreparation'])
    old=d.load(d.checked(prep['server']),'continue_layer_original')
    original=old.resources(d.checked(prep['execution']))
    cases, mapping=original[9], original[8]
    if p['candidateIdentities'] != [c['candidateIdentity'] for c in cases] or prep['cases'] != cases or p['inputs']['originalScope'] != d.read(prep['execution'])['scope']:
        raise ValueError('all68 input identities')
    if p['full68CommonLayerModules'] != [m['module'] for m in mapping[:-3]] or p['outlierFull31LayerOrdinals'] != {'wasm':[40],'webgpu':[42]}:
        raise ValueError('layer membership/outliers')
    for key in ('server','html','config','cpuCaptures','model'): d.checked(prep[key])
    if onnx.load(d.checked(prep['model'])).SerializeToString() != original[7].SerializeToString(): raise ValueError('same instrumented model bytes')
    probe=d.read(p['inputs']['transportRecovery']); probe_helper=d.load(d.checked(probe['inputs']['auditor']),'continue_layer_probe')
    probe_root=d.checked(probe['inputs']['preparation']).parent
    if probe != probe_helper.reconstruct(probe_root): raise ValueError('zero-input transport recovery replay')
    if not inv['ok'] or inv['startedInputs'] != {'cpu':68,'wasm':22,'webgpu':0} or inv['fullThreeBackendFinalGatePassed'] or inv['full31LayerConclusionsAllowed'] or inv['unconsumedOrdinals'] != {'wasm':list(range(23,69)),'webgpu':list(range(1,69))}:
        raise ValueError('frozen interruption inventory')
    precision, layer=original[5], original[6]
    # 在任何新开始事件前核验全部继承RAW；不把几何或缺失报告当作捕获。
    for c in inv['captures']: layer.read_tensor(precision,c['tensor'])
    for ref in inv['cpuEvents']+inv['browserEvents']: d.checked(ref)
    return e,p,inv,prep,old,original


def ordered_pairs(p):
    return [('wasm',i) for i in p['newWasmOrdinalsAllowed']]+[('webgpu',i) for i in p['newWebgpuOrdinalsAllowed']]


def validate_event(event,pair,case,claim):
    b,o=pair
    if set(event) != {'backend','ordinal','candidateIdentity','inputRequestId','pageRequestId'} or event['backend'] != b or event['ordinal'] != o or event['candidateIdentity'] != case['candidateIdentity'] or event['pageRequestId'] != claim:
        raise ValueError('ordered stable input event')
    if str(uuid.UUID(event['inputRequestId'])) != event['inputRequestId']: raise ValueError('unique UUID')


def write_exact(path,body):
    if path.exists():
        if path.read_bytes() != body: raise ValueError('capture conflict')
        return False
    with path.open('xb') as f: f.write(body); f.flush(); os.fsync(f.fileno())
    return True


def make_html(old):
    html=old.HTML
    a=html.index('const post='); b=html.index('\nconst equal=',a)
    transport=r'''const post=async(path,body,report)=>{
 const bytes=typeof body==='string'?new TextEncoder().encode(body):body;
 const sha=hex(await crypto.subtle.digest('SHA-256',bytes));
 for(let attempt=0;attempt<3;attempt++){
  try{const r=await fetch(path,{method:'POST',body:bytes});const text=await r.text();if(!r.ok)throw Error('HTTP '+r.status+' '+path);const ack=JSON.parse(text);if(ack.sha256!==sha||ack.bytes!==bytes.length)throw Error('ACK binding '+path);return;}
  catch(error){report.transportErrors.push({path,attempt,error:String(error)});const r=await fetch('/status'+path);const text=await r.text();
   if(r.ok){const ack=JSON.parse(text);if(ack.sha256!==sha||ack.bytes!==bytes.length)throw Error('persisted identity conflict '+path);report.persistedAckRecoveries++;return;}
   if(r.status!==404)throw Error('status '+r.status+' '+path);report.uploadOnlyRetries++;
  }
 }throw Error('upload attempts exhausted '+path);
};'''
    html=html[:a]+transport+html[b:]
    html=html.replace('三后端逐层保真核验','未消费输入逐层续接').replace('执行全68 WASM及WebGPU逐层捕获','执行剩余114个浏览器输入')
    html=html.replace("phase:'starting'","phase:'starting',transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0,pageRequestId:crypto.randomUUID()")
    html=html.replace("if(!crossOriginIsolated)throw Error('isolation');", "await post('/claim',JSON.stringify({pageRequestId:report.pageRequestId,executionSha256:config.executionSha256}),report);if(!crossOriginIsolated)throw Error('isolation');")
    html=html.replace('for(const row of config.cases){','for(const row of config.cases.filter(r=>config.pendingOrdinals[backend].includes(r.ordinal))){')
    html=html.replace('const event={backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity};', 'const event={backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity,inputRequestId:crypto.randomUUID(),pageRequestId:report.pageRequestId};')
    html=html.replace("JSON.stringify(event));report.startedInputs", "JSON.stringify(event),report);report.startedInputs")
    html=html.replace("new Uint8Array(a.buffer));rec.outputs", "new Uint8Array(a.buffer),report);rec.outputs")
    html=html.replace('report.records.length===136','report.records.length===114')
    html=html.replace("await post('/terminal',JSON.stringify(report));", "await post('/terminal',JSON.stringify(report),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});")
    return html


def prepare(execution,root):
    if root.exists(): raise ValueError('output exists; do not restart input budget')
    e,p,inv,previous,old,original=resources(execution)
    root.mkdir(parents=True,exist_ok=False)
    for name in ('started-inputs','browser-capture','upload-events'): (root/name).mkdir()
    config=d.read(previous['config']); config.pop('configSha256')
    config['executionSha256']=d.bind(execution)['sha256'];config['pendingOrdinals']={'wasm':p['newWasmOrdinalsAllowed'],'webgpu':p['newWebgpuOrdinalsAllowed']}
    d.new(root/'config-base.json',config);config['configSha256']=d.bind(root/'config-base.json')['sha256'];d.new(root/'config.json',config)
    write_exact(root/'browser.html',make_html(old).encode('utf-8'))
    d.new(root/'preparation.json',{'execution':d.bind(execution),'auditor':d.bind(__file__),'html':d.bind(root/'browser.html'),'config':d.bind(root/'config.json'),'originalPreparation':p['inputs']['originalPreparation'],'interruptionInventory':p['inputs']['interruptionInventory']})
    print(json.dumps({'prepared':True,'modelInputs':0,'pendingInputs':114}))


def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'))
    for ref in prep.values():d.checked(ref)
    if prep['auditor']!=d.bind(__file__) or (root/'claim.json').exists() or any((root/'started-inputs').iterdir()):raise ValueError('frozen server / budget may not restart')
    p=d.read(d.read(prep['execution'])['scope']);validate_scope(p);previous=d.read(prep['originalPreparation']);cases={c['ordinal']:c for c in previous['cases']};order=ordered_pairs(p)
    routes={'/browser.html':prep['html'],'/config.json':prep['config'],'/model.onnx':previous['model']}
    routes.update({'/ort/'+k:v for k,v in previous['runtimeFiles'].items()})
    for c in cases.values():routes.update({f'/case/{c["ordinal"]}/{k}.bin':{n:v[n] for n in ('path','sha256')} for k,v in c['refs'].items()})
    allowed={f'{b}-{o}-{k}.bin':math.prod(shape)*4 for b,o in order for k,shape in cases[o]['shapes'].items()}
    starts=[];captured=set();attempts={};lock=threading.Lock();claim=None

    def stored(route):
        if route=='/claim':return root/'claim.json'
        if route=='/terminal':return root/'live-browser.json'
        if route.startswith('/start/'):
            parts=route.split('/')
            if len(parts)==4 and parts[2] in ('wasm','webgpu') and parts[3].isdigit() and (parts[2],int(parts[3])) in order:return root/'started-inputs'/f'{parts[2]}-{int(parts[3])}.json'
        if route.startswith('/capture/') and route.removeprefix('/capture/') in allowed:return root/'browser-capture'/route.removeprefix('/capture/')
        raise ValueError('route whitelist')

    def acknowledgment(route):
        path=stored(route)
        if not path.exists():return None
        if route.startswith('/capture/'):return {'sha256':d.bind(path)['sha256'],'bytes':path.stat().st_size}
        record=d.read(d.bind(path));return record['requestBinding']

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'

        def response(self,code,value,content='application/json'):
            body=value if isinstance(value,bytes) else d.raw(value)
            self.send_response(code);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)));self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.end_headers();self.wfile.write(body);self.wfile.flush()

        def do_GET(self):
            route=urllib.parse.urlsplit(self.path).path
            if route.startswith('/status/'):
                try:
                    value=acknowledgment(route.removeprefix('/status'));self.response(200 if value else 404,value or {'present':False})
                except ValueError:self.response(400,{'error':'status route'})
            elif route in routes:
                path=d.checked(routes[route]);body=path.read_bytes();content='text/html' if path.suffix=='.html' else 'application/json' if path.suffix=='.json' else 'text/javascript' if path.suffix in ('.js','.mjs') else 'application/wasm' if path.suffix=='.wasm' else 'application/octet-stream';self.response(200,body,content)
            else:self.response(404,{'error':'route'})

        def do_POST(self):
            nonlocal claim
            with lock:
                try:
                    target=stored(self.path);count=int(self.headers.get('Content-Length','0'))
                    if self.path.startswith('/capture/'):
                        if count!=allowed[self.path.removeprefix('/capture/')]:raise ValueError('tensor byte cardinality')
                    elif not 0<count<=4_000_000:raise ValueError('event size')
                    body=self.rfile.read(count)
                    if len(body)!=count:raise ValueError('truncated body')
                    ack={'sha256':hashlib.sha256(body).hexdigest(),'bytes':count}
                    if target.exists():
                        if acknowledgment(self.path)!=ack:raise ValueError('persisted identity conflict')
                        self.response(201,ack);return
                    if self.path=='/claim':
                        value=json.loads(body)
                        if set(value)!={'pageRequestId','executionSha256'} or value['executionSha256']!=prep['execution']['sha256'] or str(uuid.UUID(value['pageRequestId']))!=value['pageRequestId']:raise ValueError('page claim')
                        claim=value['pageRequestId'];d.new(target,{'value':value,'requestBinding':ack})
                    elif self.path.startswith('/start/'):
                        if not claim or len(starts)>=114:raise ValueError('start limit')
                        b,o=order[len(starts)]
                        if self.path!=f'/start/{b}/{o}':raise ValueError('start order')
                        if starts:
                            pb,po=starts[-1]
                            if any(f'{pb}-{po}-{k}.bin' not in captured for k in cases[po]['shapes']):raise ValueError('previous full capture required')
                        event=json.loads(body);validate_event(event,(b,o),cases[o],claim)
                        if any(d.read(d.bind(root/'started-inputs'/f'{pb}-{po}.json'))['value']['inputRequestId']==event['inputRequestId'] for pb,po in starts):raise ValueError('duplicate input request ID')
                        d.new(target,{'value':event,'startedAtUnixNs':time.time_ns(),'requestBinding':ack});starts.append((b,o))
                    elif self.path.startswith('/capture/'):
                        if not starts:raise ValueError('start required')
                        b,o=starts[-1];name=self.path.removeprefix('/capture/')
                        if name not in {f'{b}-{o}-{k}.bin' for k in cases[o]['shapes']}:raise ValueError('active capture identity')
                        write_exact(target,body);captured.add(name)
                    else:
                        value=json.loads(body)
                        if value['pageRequestId']!=claim:raise ValueError('terminal claim')
                        d.new(target,{'value':value,'requestBinding':ack})
                    key=target.name;attempt=attempts.get(key,0)+1;attempts[key]=attempt
                    d.new(root/'upload-events'/f'{len(list((root/"upload-events").iterdir()))+1:05d}.json',{'route':self.path,'requestBinding':ack,'attempt':attempt})
                    self.response(201,ack)
                except (ValueError,KeyError,FileExistsError):self.response(409,{'error':'capture contract'})

        def log_message(self,*args):pass

    print(f'CONTINUE_LAYER_SERVER http://127.0.0.1:{port}/browser.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


def captured_outputs(root,backend,case):
    return {'ordinal':case['ordinal'],'candidateIdentity':case['candidateIdentity'],'outputs':{k:d.bind(root/'browser-capture'/f'{backend}-{case["ordinal"]}-{k}.bin')|{'shape':shape,'dtype':'float32'} for k,shape in case['shapes'].items()}}


def check_final_heads(cases,captured,precision,layer):
    for backend,rows in captured.items():
        if len(rows)!=68 or [r['ordinal'] for r in rows]!=list(range(1,69)) or [r['candidateIdentity'] for r in rows]!=[c['candidateIdentity'] for c in cases]:raise ValueError('all68 final identities')
        for case,out in zip(cases,rows,strict=True):
            keys=list(case['shapes'])
            if backend=='wasm' and case['ordinal']==22:keys=keys[:-3]
            if list(out['outputs'])!=keys:raise ValueError('exact available output membership')
            for head in ('mask','presence'):
                actual=layer.read_tensor(precision,out['outputs'][head]);expected=precision.buffer(case['refs'][backend+'-'+head],math.prod(case['shapes'][head])).reshape(case['shapes'][head]);layer.exact(expected,actual)


def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'))
    for ref in prep.values():d.checked(ref)
    e,p,inv,previous,old,original=resources(d.checked(prep['execution']))
    cases,mapping,precision,layer=original[9],original[8],original[5],original[6];cm={c['ordinal']:c for c in cases};order=ordered_pairs(p)
    config=d.read(prep['config']);claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId'];live=d.read(d.bind(root/'live-browser.json'))['value']
    if live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['errors'] or live['phase']!='terminal' or not live['crossOriginIsolated'] or live['pageRequestId']!=claim:
        raise ValueError('terminal reconstruction_mismatch')
    if live['userAgent']!=original[3]['actualBrowserUserAgent'] or live['adapterInfo']!=original[3]['adapterInfo']:raise ValueError('same browser/control environment')
    if len(live['records'])!=114 or len(live['startedInputs'])!=114 or len(list((root/'started-inputs').glob('*.json')))!=114 or len(list((root/'browser-capture').glob('*.bin')))!=114*33:raise ValueError('114 full capture/start denominator')
    captured={'cpu':d.read(previous['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];request_ids=[]
    for c in cases[:22]:
        refs={r['output']:r['tensor'] for r in inv['captures'] if r['backend']=='wasm' and r['ordinal']==c['ordinal']}
        captured['wasm'].append({'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'outputs':{k:refs[k] for k in c['shapes'] if k in refs}})
    for pair,event,rec in zip(order,live['startedInputs'],live['records'],strict=True):
        b,o=pair;c=cm[o];validate_event(event,pair,c,claim);path=root/'started-inputs'/f'{b}-{o}.json';stored=d.read(d.bind(path))
        if stored['value']!=event or stored['startedAtUnixNs']<=(events[-1]['time'] if events else 0):raise ValueError('immutable start order')
        if {k:rec[k] for k in event}!=event or rec['outputs']!=[{'key':k,'shape':v,'dtype':'float32'} for k,v in c['shapes'].items()]:raise ValueError('actual output schema')
        events.append({'binding':d.bind(path),'time':stored['startedAtUnixNs']});request_ids.append(event['inputRequestId']);captured[b].append(captured_outputs(root,b,c))
    if len(set(request_ids))!=114:raise ValueError('one start ID per model input')
    # 仅最终两头全68、全部后端逐字节相同后才计算中间层误差。
    check_final_heads(cases,captured,precision,layer)
    if not live['ok'] or not all(r['finalHeadsBitwiseIdentical'] for r in live['records']):raise ValueError('live final byte gate disagrees')
    records=[]
    for i,c in enumerate(cases):
        row={'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'layers':[]}
        for item in mapping:
            key=item['module'];reference=layer.read_tensor(precision,original[4]['captures'][i]['strictCuda']['layers'][key]);values={b:layer.read_tensor(precision,captured[b][i]['outputs'][key]) for b in captured if key in captured[b][i]['outputs']}
            row['layers'].append(item|{'shape':list(reference.shape),'strictCudaVsBackend':{b:layer.differences(reference,v) for b,v in values.items()},'cpuVsBrowser':{b:layer.differences(values['cpu'],v) for b,v in values.items() if b!='cpu'},'missingBackends':[b for b in captured if b not in values]})
        row['firstAvailableLayerAbove1e4']={b:next((l['module'] for l in row['layers'] if b in l['strictCudaVsBackend'] and l['strictCudaVsBackend'][b]['maxAbs']>1e-4),None) for b in captured};records.append(row)
        print(json.dumps({'replayedCandidates':len(records)}),flush=True)
    summary=[]
    for i,item in enumerate(mapping):
        stats={}
        for b in captured:
            available=[r['layers'][i]['strictCudaVsBackend'][b] for r in records if b in r['layers'][i]['strictCudaVsBackend']]
            expected=67 if b=='wasm' and i>=28 else 68
            if len(available)!=expected:raise ValueError('explicit layer denominator')
            stats[b]={'candidateCount':len(available),'maxAbs':max(r['maxAbs'] for r in available),'candidateCountAbove1e4':sum(r['maxAbs']>1e-4 for r in available)}
        summary.append(item|{'strictCudaVsBackend':stats})
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))]
    expected_routes=['/claim']+[route for b,o in order for route in [f'/start/{b}/{o}']+[f'/capture/{b}-{o}-{k}.bin' for k in cm[o]['shapes']]]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected_routes:raise ValueError('one persisted event per acknowledged upload')
    return {'schemaVersion':2,'ok':True,'decision':'unconsumed_layerwise_inputs_and_explicit_missing_layers_reconstructed','inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json'),'claim':d.bind(root/'claim.json')},'captures':captured,'newInputEvents':events,'uploadEvents':uploads,'records':records,'layerSummary':summary,'fullCandidateCount':68,'finalHeadsBitwiseIdenticalAllBackends':True,'full28LayerDiagnosticReconstructed':True,'outlierFull31LayerOrdinals':p['outlierFull31LayerOrdinals'],'missingWasm22Outputs':p['missingWasm22Outputs'],'full31AllBackendConclusionAllowed':False,'newBrowserInputs':114,'newCpuInputs':0,'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'originalLayerwiseFailurePreserved':True,'browserLearnedGatePassed':False,'rootCauseEstablished':False,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--serve',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',action='store_true');p.add_argument('--port',type=int,default=8831);a=p.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        try:
            result=reconstruct(root)
            if a.verify_report:
                if result!=d.read(d.bind(root/'report.json')):raise ValueError('report reconstruction_mismatch')
            else:d.new(root/'report.json',result)
            print(json.dumps({k:result[k] for k in ('ok','decision','finalHeadsBitwiseIdenticalAllBackends','newBrowserInputs')}))
        except BaseException as error:
            if not a.verify_report:d.new(root/'audit-failure.json',{'ok':False,'decision':'reconstruction_mismatch','error':str(error),'layerConclusionsAllowed':False,'productHold':True})
            raise
    else:prepare(a.execution.resolve(),root)
