"""完整原尺寸三输出保真：独占捕获、实际设备限制和有界同请求重试。"""
import argparse
import hashlib
import importlib.util
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('single_browser_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)

HTML=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>完整图三输出保真</title><link rel="icon" href="data:,"><h1>完整图三输出保真</h1><p>仅合成数组；不展示预测图，产品保持HOLD。</p><button id="run">执行冻结控制</button><pre id="status">尚未执行</pre><script src="/ort/ort.all.min.js"></script><script>
const sha=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b))).map(x=>x.toString(16).padStart(2,'0')).join('');
const post=async(path,body,id,hash)=>{let error;for(let attempt=0;attempt<2;attempt++){try{const r=await fetch(path,{method:'POST',headers:{'X-Request-Id':id,'X-Content-SHA256':hash},body});const t=await r.text();if(!r.ok)throw Error(path+' '+r.status+' '+t);return;}catch(e){error=e;}}throw error;};
const send=async(path,v,id)=>{const b=new TextEncoder().encode(JSON.stringify(v));await post(path,b,id,await sha(b));};
const load=async r=>{const v=await fetch(r.url);if(!v.ok)throw Error('HTTP '+v.status);const b=await v.arrayBuffer();if(await sha(b)!==r.sha256)throw Error('SHA '+r.url);return b;};
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;const c=await(await fetch('/config.json')).json();const claim=crypto.randomUUID();
 const result={planSha256:c.planSha256,claim,userAgent:navigator.userAgent,timeOrigin:performance.timeOrigin,crossOriginIsolated,adapterInfo:null,webgpuDevice:null,started:[],records:[],errors:[],phase:'starting',virtualTime:false,formalReleaseAllowed:false,productHold:true};
 try{
  await send('/claim',{claim,planSha256:c.planSha256},claim+'-claim');
  if(!crossOriginIsolated||navigator.userAgent!==c.expectedUserAgent)throw Error('browser environment mismatch');
  ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;ort.env.logLevel='error';
  if(navigator.gpu){const a=await navigator.gpu.requestAdapter();if(a)result.adapterInfo={vendor:a.info?.vendor,architecture:a.info?.architecture,device:a.info?.device,description:a.info?.description};}
  if(JSON.stringify(result.adapterInfo)!==JSON.stringify(c.expectedAdapter))throw Error('adapter mismatch');
  const model=await load(c.model);
  for(const backend of [...new Set(c.schedule.map(x=>x.backend))]){
   let session;
   try{
    session=await ort.InferenceSession.create(model,{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    if(backend==='webgpu'){
     const device=await ort.env.webgpu.device;const adapter=ort.env.webgpu.adapter;
     const keys=Object.keys(c.requiredDeviceLimits);const pick=v=>Object.fromEntries(keys.map(k=>[k,v[k]]));
     result.webgpuDevice={grantedLimits:pick(device.limits),adapterLimits:pick(adapter.limits),requestedLimitsFromLocalBackendPolicy:pick(adapter.limits),requestDescriptorIntercepted:false};
     for(const [key,value] of Object.entries(c.requiredDeviceLimits)){if(device.limits[key]!==value)throw Error('actual ORT device limits mismatch '+key);}
    }
    for(const row of c.schedule.filter(x=>x.backend===backend)){
     const input=new Float32Array(await load(row.input));const requestId=claim+'-'+backend+'-'+row.ordinal;
     await send('/started/'+backend+'/'+row.ordinal,{claim,requestId,backend,ordinal:row.ordinal,h:row.h,w:row.w,inputSha256:row.input.sha256},requestId+'-start');result.started.push({backend,ordinal:row.ordinal,requestId});
     const inputTensor=new ort.Tensor('float32',input,[1,4,row.h,row.w]);const start=performance.now();const out=await session.run({candidate:inputTensor});const elapsed=performance.now()-start;
     if(Object.keys(out).length!==3)throw Error('three complete outputs required');
     const outputs={};
     for(const [label,key] of Object.entries(c.outputs)){
      const t=out[key];if(!t)throw Error('missing head '+label);const v=t.data;const bytes=new Uint8Array(v.buffer,v.byteOffset,v.byteLength);const hash=await sha(bytes);
      await post('/capture/'+backend+'-'+row.ordinal+'-'+label+'.bin',bytes,requestId+'-'+label,hash);
      outputs[label]={shape:t.dims,dtype:t.type,sha256:hash,bytes:bytes.byteLength};
     }
     result.records.push({backend,ordinal:row.ordinal,requestId,outputs,sessionRunMonotonicMs:elapsed});for(const t of Object.values(out))t.dispose();inputTensor.dispose();
     document.querySelector('#status').textContent=JSON.stringify({phase:'running',confirmed:result.records.length,total:c.schedule.length},null,2);
    }
   }catch(e){result.errors.push({backend,message:String(e)});}finally{if(session)await session.release();}
  }
  result.phase='closed';
 }catch(e){result.errors.push({phase:'outer',message:String(e)});result.phase='failed';}
 await send('/capture/live-browser.json',result,claim+'-terminal');document.querySelector('#status').textContent=JSON.stringify({phase:result.phase,confirmed:result.records.length,total:c.schedule.length,errors:result.errors},null,2);
};</script></html>'''


def prepare(operator_plan,scope,root):
 if scope!='main':raise ValueError('full18 browser denominator required')
 p=d.read(d.bind(operator_plan));audit=d.load(d.checked(p['runner']),'single_output_operator');audit.resources(operator_plan);cpu_replay=d.read(d.bind(operator_plan.with_name('cpu-replay.json')));assert cpu_replay['ok'] and cpu_replay['full9CpuFidelityPassed'];ready=d.read(d.bind(operator_plan.with_name('readiness.json')))
 if not ready['ok'] or ready['plan']!=d.bind(operator_plan) or p['browserServer']!=d.bind(__file__):raise ValueError('operator readiness/server identity')
 prior=d.read(p['inputs']['priorBrowserPlan']);live=d.read(p['inputs']['priorBrowserLive']);root.mkdir(exist_ok=False);assets={'model':p['inputs']['onnx']};schedule=[]
 for b,i in ([ (b,c['ordinal']) for b in ['wasm','webgpu'] for c in p['cases']] if scope=='main' else [('webgpu',9)]):
  c=p['cases'][i-1];key=f'input-{i}';assets[key]=c['input'];schedule.append({'backend':b,'ordinal':i,'h':c['h'],'w':c['w'],'input':{'url':'/assets/'+key,'sha256':c['input']['sha256']}})
 with (root/'browser.html').open('xb') as stream:stream.write(HTML.encode('utf8'));stream.flush();os.fsync(stream.fileno())
 plan={'scope':scope,'server':d.bind(__file__),'operatorPlan':d.bind(operator_plan),'html':d.bind(root/'browser.html'),'assets':assets,'runtimeFiles':prior['runtimeFiles'],'schedule':schedule,'outputs':p['outputs'],'expectedUserAgent':live['userAgent'],'expectedAdapter':live['adapterInfo'],'requiredDeviceLimits':p['deviceProbeGrantedLimits'],'singleNewSessionPerBackend':True,'graphOptimization':'disabled','wasmThreads':1,'uploadAttemptsPerSameRequestMax':2,'formalReleaseAllowed':False,'productHold':True}
 for ref in [*assets.values(),*plan['runtimeFiles'].values()]:d.checked(ref)
 d.new(root/'plan.json',plan);d.new(root/'config.json',{'planSha256':d.bind(root/'plan.json')['sha256'],'model':{'url':'/assets/model','sha256':assets['model']['sha256']},'schedule':schedule,'outputs':plan['outputs'],'expectedUserAgent':plan['expectedUserAgent'],'expectedAdapter':plan['expectedAdapter'],'requiredDeviceLimits':plan['requiredDeviceLimits']})
 for name in ['capture','started','metadata','http-events']:(root/name).mkdir()
 print(json.dumps({'ok':True,'scope':scope,'plannedOperatorInputs':len(schedule),'newModelInputs':0}),flush=True)


def serve(root,port):
 p=d.read(d.bind(root/'plan.json'));assert p['server']==d.bind(__file__) and p['html']==d.bind(root/'browser.html')
 for ref in [*p['assets'].values(),*p['runtimeFiles'].values()]:d.checked(ref)
 cases={(c['backend'],str(c['ordinal'])):c for c in p['schedule']};expected={f'{b}-{i}-{head}.bin':(4 if head=='presence' else c['h']*c['w']*4*(16 if head=='boundary' else 1)) for (b,i),c in cases.items() for head in p['outputs']}
 class Handler(BaseHTTPRequestHandler):
  def end_headers(self):
   self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.send_header('Cache-Control','no-store');super().end_headers()
  def do_GET(self):
   if self.path in ['/','/browser.html']:path=root/'browser.html'
   elif self.path=='/config.json':path=root/'config.json'
   elif self.path.startswith('/assets/') and self.path[8:] in p['assets']:path=d.checked(p['assets'][self.path[8:]])
   elif self.path.startswith('/ort/') and self.path[5:] in p['runtimeFiles']:path=d.checked(p['runtimeFiles'][self.path[5:]])
   else:self.send_error(404);return
   content=path.read_bytes();mime='application/wasm' if path.suffix=='.wasm' else 'text/javascript' if path.suffix in ['.mjs','.js'] else 'text/html; charset=utf8' if path.suffix=='.html' else 'application/json' if path.suffix=='.json' else 'application/octet-stream';self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
  def do_POST(self):
   count=int(self.headers.get('Content-Length',0));rid=self.headers.get('X-Request-Id','');sha=self.headers.get('X-Content-SHA256','');d.new(root/'http-events'/f'{uuid.uuid4().hex}.json',{'path':self.path,'requestId':rid,'declaredSha256':sha,'declaredBytes':count,'startedUnixNs':time.time_ns()})
   if not rid or len(rid)>200 or len(sha)!=64:self.send_error(400);return
   if self.path=='/claim':target=root/'claim.json';limit=4096
   elif self.path.startswith('/started/'):
    parts=self.path.split('/')
    if len(parts)!=4 or (parts[2],parts[3]) not in cases:self.send_error(400);return
    target=root/'started'/f'{parts[2]}-{parts[3]}.json';limit=4096
   elif self.path.startswith('/capture/'):
    name=self.path[9:]
    if name=='live-browser.json':limit=1048576
    elif name in expected:limit=expected[name]
    else:self.send_error(400);return
    if name!='live-browser.json' and count!=limit:self.send_error(400);return
    target=root/'capture'/name
   else:self.send_error(404);return
   if count<=0 or count>limit:self.send_error(400);return
   body=self.rfile.read(count)
   if len(body)!=count or hashlib.sha256(body).hexdigest()!=sha:self.send_error(400);return
   if self.path=='/claim':
    value=json.loads(body)
    if value.get('planSha256')!=d.bind(root/'plan.json')['sha256'] or rid!=value.get('claim','')+'-claim':self.send_error(400);return
   else:
    if not (root/'claim.json').exists():self.send_error(403);return
    claim=json.loads((root/'claim.json').read_bytes())['claim']
    if not rid.startswith(claim+'-'):self.send_error(403);return
    if self.path.startswith('/started/'):
     value=json.loads(body);c=cases[(parts[2],parts[3])]
     if value!={'claim':claim,'requestId':claim+'-'+parts[2]+'-'+parts[3],'backend':parts[2],'ordinal':int(parts[3]),'h':c['h'],'w':c['w'],'inputSha256':c['input']['sha256']}:self.send_error(400);return
   metadata=root/'metadata'/f'{target.parent.name}-{target.name}.json'
   if target.exists():
    if not metadata.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=sha or json.loads(metadata.read_bytes())['requestId']!=rid:self.send_error(409);return
    self.send_response(200);self.end_headers();self.wfile.write(b'inherited exact same request');return
   try:
    with target.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    d.new(metadata,{'requestId':rid,'sha256':sha,'bytes':count,'savedUnixNs':time.time_ns()})
   except FileExistsError:self.send_error(409);return
   self.send_response(201);self.end_headers();self.wfile.write(b'captured')
  def log_message(self,*args):pass
 print(f'FULL_JUNCTION_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','serve']);a.add_argument('--operator-plan',type=Path);a.add_argument('--scope',choices=['main','fresh']);a.add_argument('--root',type=Path,required=True);a.add_argument('--port',type=int,default=8841);v=a.parse_args()
 if v.mode=='prepare':prepare(v.operator_plan.resolve(),v.scope,v.root.resolve())
 else:serve(v.root.resolve(),v.port)
