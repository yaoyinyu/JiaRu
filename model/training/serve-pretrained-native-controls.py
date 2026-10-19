"""完整非零独立新图的真实WASM/WebGPU控制，回环捕获和只读验真。"""
import argparse
import hashlib
import importlib.util
import json
import os
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
HERE=Path(__file__).resolve().parent;R=HERE.parents[1]
s=importlib.util.spec_from_file_location('pretrained_browser_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)

HTML=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>完整新图独立控制</title><link rel="icon" href="data:,"><h1>完整新图端侧控制</h1><p>仅合成控制；正式产品保持HOLD。此页无图片预览。</p><button id="run">执行冻结的18项控制</button><pre id="result">尚未执行</pre><script src="/ort/ort.all.min.js"></script><script>
const post=async(path,body)=>{const r=await fetch(path,{method:'POST',body});if(!r.ok)throw Error(path+' '+r.status);};
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
const load=async(ref)=>{const r=await fetch(ref.url);if(!r.ok)throw Error(ref.url+' '+r.status);const b=await r.arrayBuffer();if(hex(await crypto.subtle.digest('SHA-256',b))!==ref.sha256)throw Error('SHA '+ref.url);return b;};
const cmp=(em,ep,am,ap)=>{if(em.length!==am.length||ep.length!==1||ap.length!==1)throw Error('head cardinality');for(const v of [em,ep,am,ap])for(const f of v)if(!Number.isFinite(f))throw Error('nonfinite head');let error=Math.abs(ep[0]-ap[0]),pixels=0;const e=ep[0]>=0,a=ap[0]>=0;for(let i=0;i<em.length;i++){error=Math.max(error,Math.abs(em[i]-am[i]));if(((em[i]>=0)&&e)!==((am[i]>=0)&&a))pixels++;}return {maxAbs:error,pixels,presenceMatched:e===a,ok:error<=1e-4&&pixels===0&&e===a};};
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;
 const config=await(await fetch('/config.json')).json();
 const result={planSha256:config.planSha256,userAgent:navigator.userAgent,crossOriginIsolated,webgpuExposed:Boolean(navigator.gpu),adapterInfo:null,records:[],errors:[],started:[],phase:'starting',virtualTime:false,formalReleaseAllowed:false,productHold:true};
 try{
  await post('/attempt',JSON.stringify({planSha256:config.planSha256}));
  if(!crossOriginIsolated)throw Error('cross-origin isolation required');
  ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;ort.env.logLevel='error';
  if(navigator.gpu){const a=await navigator.gpu.requestAdapter();if(a)result.adapterInfo={vendor:a.info?.vendor,architecture:a.info?.architecture,device:a.info?.device,description:a.info?.description};}
  const model=await load(config.model);
  for(const backend of ['wasm','webgpu']){
   let session;
   try{
    if(backend==='webgpu'&&!result.adapterInfo)throw Error('WebGPU adapter unavailable');
    session=await ort.InferenceSession.create(model,{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    for(const c of config.cases){
     const x=new Float32Array(await load(c.input));const em=new Float32Array(await load(c.mask));const ep=new Float32Array(await load(c.presence));
     await post('/started/'+backend+'/'+c.ordinal,JSON.stringify({backend,ordinal:c.ordinal,h:c.h,w:c.w,inputSha256:c.input.sha256}));result.started.push({backend,ordinal:c.ordinal});
     const start=performance.now();const output=await session.run({candidate:new ort.Tensor('float32',x,[1,4,c.h,c.w])});const elapsed=performance.now()-start;
     const am=output.mask_logits.data,ap=output.presence_logit.data;
     await post('/capture/'+backend+'-'+c.ordinal+'-mask.bin',am.buffer.slice(am.byteOffset,am.byteOffset+am.byteLength));
     await post('/capture/'+backend+'-'+c.ordinal+'-presence.bin',ap.buffer.slice(ap.byteOffset,ap.byteOffset+ap.byteLength));
     const row={backend,ordinal:c.ordinal,h:c.h,w:c.w,maskDims:output.mask_logits.dims,presenceDims:output.presence_logit.dims,maskType:output.mask_logits.type,presenceType:output.presence_logit.type,parity:cmp(em,ep,am,ap),sessionRunMonotonicMs:elapsed};
     result.records.push(row);document.querySelector('#result').textContent=JSON.stringify({phase:'running',backend,confirmed:result.records.length,total:18},null,2);
     for(const t of Object.values(output))t.dispose();
    }
   }catch(e){result.errors.push({backend,message:String(e)});}
   finally{if(session)await session.release();}
  }
  result.phase='closed';
 }catch(e){result.errors.push({phase:'outer',message:String(e)});result.phase='failed';}
 result.all18Passed=result.records.length===18&&result.errors.length===0&&result.records.every(r=>r.parity.ok);
 await post('/capture/live-browser.json',JSON.stringify(result));document.querySelector('#result').textContent=JSON.stringify(result,null,2);
};</script></html>'''


def prepare(scope,root):
 parent=d.read(d.bind(scope));assert parent['purpose']=='same_full9_independent_controls_blocked_gn_repair'
 scope_dir=Path(scope).parent;report=d.read(d.bind(scope_dir/'run/report.json'));replay=d.read(d.bind(scope_dir/'replay.json'))
 assert report['independentCpuGatePassed'] and replay['ok'] and replay['independentCpuGatePassed']
 root.mkdir(exist_ok=False);runtime=R/'node_modules/onnxruntime-web/dist';assets={'model':parent['inputs']['onnx']}
 cases=[]
 for c,row in zip(parent['cases'],report['records'],strict=True):
  assert c['ordinal']==row['ordinal'];refs={'input':c['input'],'mask':row['reference']['mask']['binding'],'presence':row['reference']['presence']['binding']};cases.append({'ordinal':c['ordinal'],'h':c['h'],'w':c['w'],**{k:{'url':f'/assets/{c["ordinal"]}-{k}','sha256':v['sha256']} for k,v in refs.items()}});assets.update({f'{c["ordinal"]}-{k}':v for k,v in refs.items()})
 runtime_files={p.name:d.bind(p) for p in runtime.iterdir() if p.is_file() and p.name.endswith(('.mjs','.wasm')) and 'ort-wasm-simd-threaded' in p.name};runtime_files['ort.all.min.js']=d.bind(runtime/'ort.all.min.js')
 for ref in [*assets.values(),*runtime_files.values()]:d.checked(ref)
 with (root/'browser.html').open('xb') as stream:stream.write(HTML.encode('utf8'))
 plan={'purpose':'full9_independent_pretrained_browser_controls_per_backend','server':d.bind(__file__),'cpuPlan':d.bind(scope),'cpuReport':d.bind(scope_dir/'run/report.json'),'cpuReplay':d.bind(scope_dir/'replay.json'),'html':d.bind(root/'browser.html'),'assets':assets,'runtimeFiles':runtime_files,'cases':cases,'backends':['wasm','webgpu'],'budget':{'wasm':9,'webgpu':9,'learned':0,'optimizerSteps':0,'newChatImages':0},'requiredAbsoluteDifference':1e-4,'requiredDecodedPixelDifference':0,'requiredPresenceDecisionDifference':0,'graphOptimization':'disabled','threadCount':1,'oneAttempt':True,'costQualification':'只捕获session.run浏览器单调时钟；无虚拟时钟；没有完整端到端/进程峰值/P95资格。','formalReleaseAllowed':False,'productHold':True}
 d.new(root/'plan.json',plan);config={'planSha256':d.bind(root/'plan.json')['sha256'],'model':{'url':'/assets/model','sha256':assets['model']['sha256']},'cases':cases};d.new(root/'config.json',config);(root/'capture').mkdir();(root/'started').mkdir();print(json.dumps({'ok':True,'browserBudget':18,'browserInputsConsumed':0}),flush=True)


def serve(root,port):
 p=d.read(d.bind(root/'plan.json'));assert p['server']==d.bind(__file__) and p['html']==d.bind(root/'browser.html')
 for ref in [*p['assets'].values(),*p['runtimeFiles'].values()]:d.checked(ref)
 captures={f'{b}-{c["ordinal"]}-{head}.bin':(c['h']*c['w']*4 if head=='mask' else 4) for b in p['backends'] for c in p['cases'] for head in ['mask','presence']}
 class Handler(BaseHTTPRequestHandler):
  def end_headers(self):
   self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.send_header('Cache-Control','no-store');super().end_headers()
  def do_GET(self):
   if self.path in ['/','/browser.html']:path=root/'browser.html'
   elif self.path=='/config.json':path=root/'config.json'
   elif self.path.startswith('/assets/') and self.path[8:] in p['assets']:path=d.checked(p['assets'][self.path[8:]])
   elif self.path.startswith('/ort/') and self.path[5:] in p['runtimeFiles']:path=d.checked(p['runtimeFiles'][self.path[5:]])
   else:self.send_error(404);return
   mime='application/wasm' if path.suffix=='.wasm' else 'text/javascript' if path.suffix in ['.js','.mjs'] else 'text/html; charset=utf-8' if path.suffix=='.html' else 'application/json' if path.suffix=='.json' else 'application/octet-stream';body=path.read_bytes();self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def do_POST(self):
   n=int(self.headers.get('Content-Length',0))
   if self.path=='/attempt':
    body=self.rfile.read(n);value=json.loads(body)
    if value!={'planSha256':d.bind(root/'plan.json')['sha256']}:self.send_error(400);return
    target=root/'attempt.json';body=d.raw({**value,'startedUnixNs':time.time_ns()})
   elif self.path.startswith('/started/'):
    parts=self.path.split('/')
    if len(parts)!=4 or parts[2] not in p['backends'] or not parts[3].isdigit():self.send_error(400);return
    b,i=parts[2],int(parts[3]);matching=[c for c in p['cases'] if c['ordinal']==i]
    if len(matching)!=1:self.send_error(400);return
    c=matching[0];body=self.rfile.read(n);value=json.loads(body)
    if value!={'backend':b,'ordinal':i,'h':c['h'],'w':c['w'],'inputSha256':c['input']['sha256']}:self.send_error(400);return
    target=root/'started'/f'{b}-{i}.json';body=d.raw({**value,'startedUnixNs':time.time_ns()})
   elif self.path.startswith('/capture/'):
    name=self.path[9:]
    if name!='live-browser.json' and (name not in captures or n!=captures[name]):self.send_error(400);return
    if name=='live-browser.json' and n>1048576:self.send_error(400);return
    target=root/'capture'/name;body=self.rfile.read(n)
   else:self.send_error(404);return
   try:
    with target.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
   except FileExistsError:self.send_error(409);return
   self.send_response(201);self.end_headers();self.wfile.write(b'captured')
  def log_message(self,*args):pass
 print(f'PRETRAINED_BROWSER_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


def verify(root,output):
 p=d.read(d.bind(root/'plan.json'));live=d.read(d.bind(root/'capture/live-browser.json'));scope=d.read(p['cpuPlan']);helper=d.load(d.checked(scope['inputs']['exporter']),'pretrained_browser_compare')
 assert live['planSha256']==d.bind(root/'plan.json')['sha256'] and live['crossOriginIsolated'] and not live['virtualTime']
 rows=[]
 for r in live['records']:
  b,i=r['backend'],r['ordinal'];c=next(c for c in p['cases'] if c['ordinal']==i);h,w=c['h'],c['w'];assert b in p['backends'] and r['h']==h and r['w']==w and r['maskDims']==[1,1,h,w] and r['presenceDims']==[1,1] and r['maskType']==r['presenceType']=='float32'
  event=d.read(d.bind(root/'started'/f'{b}-{i}.json'));assert event['backend']==b and event['ordinal']==i and event['inputSha256']==c['input']['sha256']
  refs={}
  for head,shape in [('mask',[1,1,h,w]),('presence',[1,1])]:
   path=root/'capture'/f'{b}-{i}-{head}.bin';refs[head]={'binding':d.bind(path),'shape':shape,'dtype':'float32','bytes':path.stat().st_size}
  prior=d.read(p['cpuReport'])['records'][i-1]['reference'];stats=helper.compare(helper.read_heads(prior,h,w),helper.read_heads(refs,h,w),h,w)
  assert abs(stats['maxAbsoluteDifference']-r['parity']['maxAbs'])<=1e-6 and stats['decodedMaskPixelDifference']==r['parity']['pixels'] and stats['presenceDecisionMatched']==r['parity']['presenceMatched'] and helper.passed(stats)==r['parity']['ok']
  rows.append({'backend':b,'ordinal':i,'raw':refs,'parity':stats})
 expected=[(b,c['ordinal']) for b in p['backends'] for c in p['cases']];actual=[(r['backend'],r['ordinal']) for r in rows];assert len(set(actual))==len(actual) and all(x in expected for x in actual)
 started=[(e['backend'],e['ordinal']) for e in live['started']];assert len(set(started))==len(started) and set(actual)<=set(started) and len(list((root/'started').glob('*.json')))==len(started)
 gate=actual==expected and not live['errors'] and all(helper.passed(r['parity']) for r in rows);assert gate==live['all18Passed']
 result={'ok':True,'plan':d.bind(root/'plan.json'),'reader':d.bind(__file__),'live':d.bind(root/'capture/live-browser.json'),'records':rows,'startedInputs':{b:sum(x[0]==b for x in started) for b in p['backends']},'confirmedInputs':{b:sum(x[0]==b for x in actual) for b in p['backends']},'errors':live['errors'],'independentBrowserGatePassed':gate,'newModelInputsByVerifier':0,'learnedInputs':0,'optimizerSteps':0,'costQualified':False,'formalReleaseAllowed':False,'productHold':True}
 if output.exists():assert result==d.read(d.bind(output))
 else:d.new(output,result)
 print(json.dumps({'ok':True,'independentBrowserGatePassed':gate,'started':result['startedInputs'],'confirmed':result['confirmedInputs'],'errors':result['errors']}),flush=True)


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','serve','verify']);a.add_argument('--scope',type=Path);a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path);a.add_argument('--port',type=int,default=8839);v=a.parse_args()
 if v.mode=='prepare':prepare(v.scope.resolve(),v.root.resolve())
 elif v.mode=='serve':serve(v.root.resolve(),v.port)
 else:verify(v.root.resolve(),v.output.resolve())
