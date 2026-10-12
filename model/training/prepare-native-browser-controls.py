"""为冻结动态非零ONNX生成完整四尺寸合成张量控制；无素材图片。"""
import argparse,importlib.util,json,os
from pathlib import Path
import torch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('native_browser_prepare_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def prepare(root):
 report=d.read(d.bind(root/'report.json'));plan=d.read(report['plan'])
 for ref in plan['inputs'].values():d.checked(ref)
 shapes=[[16,16],[31,37],[128,128],[333,341]]
 if not report['ok'] or not report['allReferenceAndOrtOutputTensorsFinite'] or [c['shape'] for c in report['controls']]!=shapes:raise ValueError('static four controls')
 if (root/'controls.json').exists() or (root/'browser.html').exists():raise ValueError('control package exists; no writer replay')
 net=d.load(d.checked(plan['inputs']['modelSource']),'browser_nonzero_control');torch.manual_seed(plan['seed']);torch.set_num_threads(4);model=net.NativeConditionalMaskRefiner().eval()
 with torch.no_grad():
  model.delta.weight.copy_(torch.linspace(-.25,.25,model.delta.weight.numel()).reshape_as(model.delta.weight));model.delta.bias.fill_(.1)
  model.presence.weight.copy_(torch.linspace(-.15,.15,model.presence.weight.numel()).reshape_as(model.presence.weight))
 controls=[]
 for h,w in shapes:
  torch.manual_seed(h*1000+w);x=torch.rand(1,4,h,w);x[:,3]=(x[:,3]>.6).float()
  with torch.inference_mode():mask,presence=model(x)
  if not torch.isfinite(mask).all() or not torch.isfinite(presence).all() or torch.equal(mask,x[:,3:4]*8-4):raise ValueError('nonzero finite control')
  paths={}
  for name,value in (('input',x),('mask',mask),('presence',presence)):
   p=root/f'{h}x{w}-{name}.bin'
   with p.open('xb') as f:f.write(value.numpy().tobytes());f.flush();os.fsync(f.fileno())
   paths[name]={'file':p.name,**d.bind(p)}
  controls.append({'h':h,'w':w,'paths':paths})
 d.new(root/'controls.json',{'model':report['onnx'],'controls':controls,'preparerSource':d.bind(__file__),
  'meaning':'untrained nonzero interface controls never training weights or model quality'})
 html='''<!doctype html><meta charset="utf-8"><title>Native model controls</title><button id="run">Run native model controls</button><pre id="status">ready</pre><script src="/ort/ort.all.min.js"></script><script>
ort.env.wasm.numThreads=1;ort.env.wasm.wasmPaths='/ort/';
async function bytes(name){const r=await fetch(name);if(!r.ok)throw Error('read '+r.status);return await r.arrayBuffer();}
async function capture(name,data){const r=await fetch('/capture/'+name,{method:'POST',body:data});if(!r.ok)throw Error('capture '+r.status);}
document.getElementById('run').onclick=async()=>{document.getElementById('run').disabled=true;document.getElementById('status').textContent='running';
const meta=await(await fetch('controls.json')).json();const model=await bytes(meta.model.path.split(/[\\\\/]/).pop());const results={userAgent:navigator.userAgent,webgpuAvailable:!!navigator.gpu,controls:[],errors:[]};
for(const backend of ['wasm','webgpu']){try{const session=await ort.InferenceSession.create(model,{executionProviders:[backend]});
for(const c of meta.controls){const input=new Float32Array(await bytes(c.paths.input.file));const started=performance.now();const out=await session.run({candidate:new ort.Tensor('float32',input,[1,4,c.h,c.w])});const elapsedMs=performance.now()-started;
let error=0;for(const [name,key]of [['mask','mask_logits'],['presence','presence_logit']]){const expected=new Float32Array(await bytes(c.paths[name].file));const actual=out[key].data;if(out[key].type!=='float32'||actual.length!==expected.length)throw Error('float32 cardinality');
for(let i=0;i<actual.length;i++){if(!Number.isFinite(actual[i])||!Number.isFinite(expected[i]))throw Error('nonfinite head');error=Math.max(error,Math.abs(actual[i]-expected[i]));}
await capture(backend+'-'+c.h+'x'+c.w+'-'+name+'.bin',new Uint8Array(actual.buffer,actual.byteOffset,actual.byteLength).slice());}
results.controls.push({backend,shape:[c.h,c.w],maxAbsoluteDifference:error,elapsedMs,dims:out.mask_logits.dims,presenceDims:out.presence_logit.dims});}await session.release();}catch(e){results.errors.push({backend,message:String(e)});}}
await capture('live-browser.json',new TextEncoder().encode(JSON.stringify(results)));document.getElementById('status').textContent=JSON.stringify(results);};
</script>'''
 with (root/'browser.html').open('xb') as f:f.write(html.encode('utf-8'));f.flush();os.fsync(f.fileno())
 print(json.dumps({'ok':True,'controlShapes':4,'browserPage':d.bind(root/'browser.html')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--export-dir',type=Path,required=True);a=p.parse_args();prepare(a.export_dir.resolve())
