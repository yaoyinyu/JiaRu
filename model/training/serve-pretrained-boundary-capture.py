"""完整观测图浏览器捕获；独占认领、稳定请求与同SHA应答继承。"""
import argparse
import hashlib
import importlib.util
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
HERE=Path(__file__).resolve().parent;R=HERE.parents[1]
s=importlib.util.spec_from_file_location('boundary_browser_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)

HTML=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>完整图只读边界验收</title><link rel="icon" href="data:,"><h1>完整图只读边界验收</h1><p>仅独立合成控制；无预测图片，正式产品保持HOLD。</p><button id="run">执行冻结的18项观测</button><pre id="status">尚未执行</pre><script src="/ort/ort.all.min.js"></script><script>
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
const sha=async b=>hex(await crypto.subtle.digest('SHA-256',b));
const post=async(path,body,id,hash)=>{
 let last;
 for(let attempt=0;attempt<2;attempt++){
  try{const r=await fetch(path,{method:'POST',headers:{'X-Request-Id':id,'X-Content-SHA256':hash},body});const text=await r.text();if(!r.ok)throw Error(path+' '+r.status+' '+text);return;}catch(e){last=e;}
 }
 throw last;
};
const sendJSON=async(path,v,id)=>{const b=new TextEncoder().encode(JSON.stringify(v));await post(path,b,id,await sha(b));};
const load=async(ref)=>{const r=await fetch(ref.url);if(!r.ok)throw Error(ref.url+' '+r.status);const b=await r.arrayBuffer();if(await sha(b)!==ref.sha256)throw Error('SHA '+ref.url);return b;};
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;
 const c=await(await fetch('/config.json')).json();const claim=crypto.randomUUID();
 const result={planSha256:c.planSha256,claim,userAgent:navigator.userAgent,crossOriginIsolated,webgpuExposed:Boolean(navigator.gpu),adapterInfo:null,started:[],records:[],errors:[],phase:'starting',virtualTime:false,formalReleaseAllowed:false,productHold:true};
 try{
  await sendJSON('/claim',{claim,planSha256:c.planSha256},claim+'-claim');
  if(!crossOriginIsolated||navigator.userAgent!==c.expectedUserAgent)throw Error('browser environment fidelity mismatch');
  ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;ort.env.logLevel='error';
  if(navigator.gpu){const a=await navigator.gpu.requestAdapter();if(a)result.adapterInfo={vendor:a.info?.vendor,architecture:a.info?.architecture,device:a.info?.device,description:a.info?.description};}
  if(JSON.stringify(result.adapterInfo)!==JSON.stringify(c.expectedAdapter))throw Error('adapter environment mismatch');
  const model=await load(c.model);
  for(const backend of ['wasm','webgpu']){
   let session;
   try{
    if(backend==='webgpu'&&!result.adapterInfo)throw Error('WebGPU unavailable');
    session=await ort.InferenceSession.create(model,{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    for(const row of c.cases){
     const input=new Float32Array(await load(row.input));const requestId=claim+'-'+backend+'-'+row.ordinal;
     await sendJSON('/started/'+backend+'/'+row.ordinal,{claim,requestId,backend,ordinal:row.ordinal,h:row.h,w:row.w,inputSha256:row.input.sha256},requestId+'-start');result.started.push({backend,ordinal:row.ordinal,requestId});
     const start=performance.now();const output=await session.run({candidate:new ort.Tensor('float32',input,[1,4,row.h,row.w])});const elapsed=performance.now()-start;
     if(Object.keys(output).length!==3)throw Error('three output denominator');
     const outputs={};
     for(const [label,key] of Object.entries(c.outputNames)){
      const t=output[key];const v=t.data;const bytes=new Uint8Array(v.buffer,v.byteOffset,v.byteLength);const hash=await sha(bytes);
      await post('/capture/'+backend+'-'+row.ordinal+'-'+label+'.bin',bytes,requestId+'-'+label,hash);
      outputs[label]={shape:t.dims,dtype:t.type,sha256:hash,bytes:bytes.byteLength};
     }
     result.records.push({backend,ordinal:row.ordinal,requestId,outputs,sessionRunMonotonicMs:elapsed});document.querySelector('#status').textContent=JSON.stringify({phase:'running',backend,confirmed:result.records.length,total:18},null,2);
     for(const t of Object.values(output))t.dispose();
    }
   }catch(e){result.errors.push({backend,message:String(e)});}
   finally{if(session)await session.release();}
  }
  result.phase='closed';
 }catch(e){result.errors.push({phase:'outer',message:String(e)});result.phase='failed';}
 await sendJSON('/capture/live-browser.json',result,claim+'-terminal');document.querySelector('#status').textContent=JSON.stringify({phase:result.phase,confirmed:result.records.length,total:18,errors:result.errors,layerAttribution:'只读核验完整保真后判定'},null,2);
};</script></html>'''


def prepare(capture_plan,root):
 p=d.read(d.bind(capture_plan));capture=d.load(d.checked(p['runner']),'prepare_browser_boundary');capture.resources(capture_plan);parent_root=Path(capture_plan).parent;replay=d.read(d.bind(parent_root/'cuda-replay.json'));assert replay['ok'] and replay['cudaFidelityPassed']
 prior=d.read(p['inputs']['originalBrowser']);prior_plan=d.read(prior['plan']);live=d.read(prior['live']);root.mkdir(exist_ok=False);assets={'model':p['inputs']['diagnosticOnnx']};cases=[]
 for c in p['cases']:
  key=f'{c["ordinal"]}-input';assets[key]=c['input'];cases.append({'ordinal':c['ordinal'],'h':c['h'],'w':c['w'],'input':{'url':'/assets/'+key,'sha256':c['input']['sha256']}})
 with (root/'browser.html').open('xb') as stream:stream.write(HTML.encode('utf8'))
 plan={'purpose':'full9_three_output_browser_fidelity_capture','server':d.bind(__file__),'capturePlan':d.bind(capture_plan),'cudaReplay':d.bind(parent_root/'cuda-replay.json'),'html':d.bind(root/'browser.html'),'assets':assets,'runtimeFiles':prior_plan['runtimeFiles'],'cases':cases,'outputNames':{'mask':'mask_logits','presence':'presence_logit','boundary':p['boundary']['outputs'][0]},'boundaryChannels':p['boundary']['channels'],'expectedUserAgent':live['userAgent'],'expectedAdapter':live['adapterInfo'],'budget':{'wasm':9,'webgpu':9,'learned':0,'optimizerSteps':0},'allOutputs':3,'rawTensors':54,'graphOptimization':'disabled','wasmThreads':1,'uploadAttemptsPerSameRequestMax':2,'oneExclusiveClaim':True,'formalReleaseAllowed':False,'productHold':True}
 for ref in [*assets.values(),*plan['runtimeFiles'].values()]:d.checked(ref)
 d.new(root/'plan.json',plan);d.new(root/'config.json',{'planSha256':d.bind(root/'plan.json')['sha256'],'model':{'url':'/assets/model','sha256':assets['model']['sha256']},'cases':cases,'outputNames':plan['outputNames'],'expectedUserAgent':plan['expectedUserAgent'],'expectedAdapter':plan['expectedAdapter']})
 for name in ['capture','started','metadata','http-events']:(root/name).mkdir()
 print(json.dumps({'ok':True,'browserInputs':18,'rawTensors':54,'newModelInputs':0}),flush=True)


def serve(root,port):
 p=d.read(d.bind(root/'plan.json'));assert p['server']==d.bind(__file__) and p['html']==d.bind(root/'browser.html')
 for ref in [*p['assets'].values(),*p['runtimeFiles'].values()]:d.checked(ref)
 expected={f'{b}-{c["ordinal"]}-{name}.bin':(c['h']*c['w']*4*(p['boundaryChannels'] if name=='boundary' else 1) if name!='presence' else 4) for b in ['wasm','webgpu'] for c in p['cases'] for name in ['mask','presence','boundary']}
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
   count=int(self.headers.get('Content-Length',0));request_id=self.headers.get('X-Request-Id','');sha=self.headers.get('X-Content-SHA256','')
   d.new(root/'http-events'/f'{uuid.uuid4().hex}.json',{'path':self.path,'requestId':request_id,'declaredSha256':sha,'declaredBytes':count,'startedUnixNs':time.time_ns()})
   if not request_id or len(request_id)>200 or len(sha)!=64:self.send_error(400);return
   if self.path=='/claim':target=root/'claim.json';limit=4096
   elif self.path.startswith('/started/'):
    parts=self.path.split('/')
    if len(parts)!=4 or parts[2] not in ['wasm','webgpu'] or not parts[3].isdigit() or not 1<=int(parts[3])<=9:self.send_error(400);return
    target=root/'started'/f'{parts[2]}-{parts[3]}.json';limit=4096
   elif self.path.startswith('/capture/'):
    name=self.path[9:]
    if name=='live-browser.json':limit=1048576
    elif name in expected:limit=expected[name]
    else:self.send_error(400);return
    if name!='live-browser.json' and count!=limit:self.send_error(400);return
    target=root/'capture'/name
   else:self.send_error(404);return
   if count>limit or count<=0:self.send_error(400);return
   body=self.rfile.read(count)
   if len(body)!=count or hashlib.sha256(body).hexdigest()!=sha:self.send_error(400);return
   if self.path=='/claim':
    value=json.loads(body)
    if value.get('planSha256')!=d.bind(root/'plan.json')['sha256'] or request_id!=value.get('claim','')+'-claim':self.send_error(400);return
   else:
    if not (root/'claim.json').exists():self.send_error(403);return
    claim=json.loads((root/'claim.json').read_bytes())['claim']
    if not request_id.startswith(claim+'-'):self.send_error(403);return
    if self.path.startswith('/started/'):
     value=json.loads(body);c=p['cases'][int(parts[3])-1]
     if value!={'claim':claim,'requestId':claim+'-'+parts[2]+'-'+parts[3],'backend':parts[2],'ordinal':int(parts[3]),'h':c['h'],'w':c['w'],'inputSha256':c['input']['sha256']}:self.send_error(400);return
   meta_path=root/'metadata'/f'{target.parent.name}-{target.name}.json'
   if target.exists():
    if not meta_path.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=sha or json.loads(meta_path.read_bytes())['requestId']!=request_id:self.send_error(409);return
    self.send_response(200);self.end_headers();self.wfile.write(b'inherited exact same request');return
   try:
    with target.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    d.new(meta_path,{'requestId':request_id,'sha256':sha,'bytes':count,'savedUnixNs':time.time_ns()})
   except FileExistsError:self.send_error(409);return
   self.send_response(201);self.end_headers();self.wfile.write(b'captured')
  def log_message(self,*args):pass
 print(f'BOUNDARY_BROWSER_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','serve']);a.add_argument('--capture-plan',type=Path);a.add_argument('--root',type=Path,required=True);a.add_argument('--port',type=int,default=8840);v=a.parse_args()
 if v.mode=='prepare':prepare(v.capture_plan.resolve(),v.root.resolve())
 else:serve(v.root.resolve(),v.port)
