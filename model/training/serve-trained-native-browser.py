"""已通过CPU门的同候选双浏览器后端核验；回环资源与一次性输入事件。"""
import argparse
import importlib.util
import json
import os
import time
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('trained_browser_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)


def resources(plan_path):
    plan = d.read(d.bind(plan_path))
    if plan['purpose'] != 'repaired_same_weights_full68_real_wasm_webgpu_gate' or plan['requiredBackends'] != ['wasm', 'webgpu'] or plan['fullCandidateCount'] != 68:
        raise ValueError('full68 two-backend contract')
    if any(plan[k] != 0 for k in ('optimizerStepsAllowed', 'newTorchInputsAllowed', 'valInputsAllowed', 'protectedInputsAllowed')) or plan['controlInputsPerBackendAllowed'] != 68 or plan['learnedInputsPerBackendAllowedAfterAllControls'] != 68:
        raise ValueError('browser-only full68 scope')
    if plan['requiredNumericDifference'] != 1e-4 or plan['requiredDecodedPixelDifferences'] != 0 or plan['requiredPresenceDecisionDifferences'] != 0 or plan['graphOptimizationLevel'] != 'disabled':
        raise ValueError('frozen numeric contract')
    for ref in plan['inputs'].values(): d.checked(ref)
    for ref in plan['runtimeFiles'].values(): d.checked(ref)
    repair = d.read(plan['inputs']['cpuReport'])
    helper = d.load(d.checked(repair['inputs']['auditor']), 'trained_browser_cpu_helper')
    if not repair['learnedCpuGatePassed'] or not repair['nonzeroControlGatePassed'] or repair != helper.reconstruct(d.checked(repair['inputs']['execution']), repair['artifacts'], repair['captures']):
        raise ValueError('CPU and nonzero control gate')
    execution = d.read(repair['inputs']['execution']); scope = d.read(execution['inputs']['scope'])
    strict = d.read(scope['inputs']['strictReference']); precision = d.load(d.checked(strict['inputs']['auditor']), 'trained_browser_buffer')
    old = d.read(d.read(strict['inputs']['plan'])['inputs']['cpuFailure'])
    if plan['candidateIdentities'] != scope['candidateIdentities'] or len(old['records']) != 68:
        raise ValueError('all68 frozen candidate identities')
    if plan['inputs']['learnedOnnx'] != repair['artifacts']['learnedOnnx'] or plan['inputs']['controlOnnx'] != repair['artifacts']['controlOnnx']:
        raise ValueError('same CPU-qualified ONNX')
    cases = []
    for previous, learned, control, strict_row in zip(old['records'], repair['captures']['learned'], repair['captures']['controls'], strict['captures'], strict=True):
        h, w = previous['h'], previous['w']
        if any(c['candidateIdentity'] != previous['candidateIdentity'] for c in (learned, control, strict_row)) or previous['candidateIdentity']['identity']['split'] != 'train':
            raise ValueError('train-only identity binding')
        refs = {'input': previous['paths']['input'], 'control-mask': control['torch']['mask'], 'control-presence': control['torch']['presence'],
                'learned-mask': strict_row['paths']['strict-mask'], 'learned-presence': strict_row['paths']['strict-presence']}
        for name, ref in refs.items(): precision.buffer(ref, 4*h*w if name == 'input' else 1 if name.endswith('presence') else h*w)
        cases.append({'ordinal': previous['ordinal'], 'candidateIdentity': previous['candidateIdentity'], 'h': h, 'w': w, 'refs': refs})
    return plan, cases, precision


HTML = r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>同候选双后端数值核验</title><link rel="icon" href="data:,"><h1>开发候选浏览器数值核验</h1><button id="run">执行全68非零控制及全68学得输出</button><pre id="result">尚未执行；正式产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>
const load=async path=>{const r=await fetch(path);if(!r.ok)throw Error('GET '+path+' '+r.status);return await r.arrayBuffer();};
const hex=bytes=>Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,'0')).join('');
const verified=async(path,sha)=>{const b=await load(path);if(hex(await crypto.subtle.digest('SHA-256',b))!==sha)throw Error('SHA '+path);return b;};
const post=async(path,body)=>{const r=await fetch(path,{method:'POST',body});if(!r.ok)throw Error('POST '+path+' '+r.status);};
const compare=(em,ep,am,ap)=>{if(em.length!==am.length||ep.length!==1||ap.length!==1)throw Error('head cardinality');let maxAbs=0,pixels=0;for(const a of [em,ep,am,ap])for(const v of a)if(!Number.isFinite(v))throw Error('head nonfinite');const e=ep[0]>=0,a=ap[0]>=0;maxAbs=Math.abs(ep[0]-ap[0]);for(let i=0;i<am.length;i++){maxAbs=Math.max(maxAbs,Math.abs(em[i]-am[i]));if(((em[i]>=0)&&e)!==((am[i]>=0)&&a))pixels++;}return {maxAbs,pixels,presenceMatched:e===a,ok:maxAbs<=1e-4&&pixels===0&&e===a};};
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;
 const config=await(await fetch('/config.json')).json();
 const report={schemaVersion:1,planSha256:config.planSha256,configSha256:config.configSha256,userAgent:navigator.userAgent,origin:location.origin,crossOriginIsolated,webgpuExposed:Boolean(navigator.gpu),records:[],startedInputs:[],errors:[],phase:'starting'};
 try{
  if(!crossOriginIsolated)throw Error('cross-origin isolation required');
  ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;
  let adapterInfo=null;if(navigator.gpu){const adapter=await navigator.gpu.requestAdapter();if(adapter)adapterInfo={vendor:adapter.info?.vendor,architecture:adapter.info?.architecture,device:adapter.info?.device,description:adapter.info?.description};}report.adapterInfo=adapterInfo;
  for(const kind of ['control','learned']){
   if(kind==='learned'&&(report.records.length!==136||!report.records.every(r=>r.parity.ok)))throw Error('all nonzero controls must pass first');
   for(const backend of ['wasm','webgpu']){
    report.phase=kind+'/'+backend;document.querySelector('#result').textContent=report.phase;
    let session;try{
     const model=await verified('/model/'+kind+'.onnx',config.models[kind].sha256);
     session=await ort.InferenceSession.create(model,{executionProviders:[backend],graphOptimizationLevel:'disabled'});
     if(session.inputNames.join(',')!=='candidate'||session.outputNames.join(',')!=='mask_logits,presence_logit')throw Error('actual names');
     for(const row of config.cases){
      document.querySelector('#result').textContent=report.phase+' '+row.ordinal+'/68';
      const input=new Float32Array(await verified('/case/'+row.ordinal+'/input.bin',row.hashes.input));if(input.length!==4*row.h*row.w)throw Error('input size');
      const event={kind,backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity};
      await post('/start/'+kind+'/'+backend+'/'+row.ordinal,JSON.stringify(event));report.startedInputs.push(event);
      const outputs=await session.run({candidate:new ort.Tensor('float32',input,[1,4,row.h,row.w])});
      const mask=new Float32Array(await outputs.mask_logits.getData()),presence=new Float32Array(await outputs.presence_logit.getData());
      const dims=Array.from(outputs.mask_logits.dims),presenceDims=Array.from(outputs.presence_logit.dims);
      if(dims.join(',')!==[1,1,row.h,row.w].join(',')||presenceDims.join(',')!=='1,1')throw Error('native two-head dims');
      const expectedMask=new Float32Array(await verified('/case/'+row.ordinal+'/'+kind+'-mask.bin',row.hashes[kind+'-mask']));
      const expectedPresence=new Float32Array(await verified('/case/'+row.ordinal+'/'+kind+'-presence.bin',row.hashes[kind+'-presence']));
      const parity=compare(expectedMask,expectedPresence,mask,presence);
      await post('/capture/'+kind+'-'+backend+'-'+row.ordinal+'-mask.bin',new Uint8Array(mask.buffer));
      await post('/capture/'+kind+'-'+backend+'-'+row.ordinal+'-presence.bin',new Uint8Array(presence.buffer));
      report.records.push({...event,dims,presenceDims,parity});
     }
    }finally{if(session)await session.release();}
   }
  }
  report.ok=report.records.length===272&&report.records.every(r=>r.parity.ok);report.phase='terminal';
 }catch(e){report.ok=false;report.errors.push(String(e));report.phase='terminal-failure';}
 await post('/capture/live-browser.json',JSON.stringify(report));
 document.querySelector('#result').textContent=JSON.stringify(report);
};
</script></html>'''


def prepare(plan_path, root):
    if root.exists(): raise ValueError('browser output exists; do not restart captured budget')
    plan, cases, _ = resources(plan_path)
    root.mkdir(parents=True, exist_ok=False)
    (root / 'browser-capture').mkdir(); (root / 'started-inputs').mkdir()
    config = {'planSha256': d.bind(plan_path)['sha256'], 'models': {kind: plan['inputs'][kind + 'Onnx'] for kind in ('control', 'learned')},
        'cases': [{k: c[k] for k in ('ordinal', 'candidateIdentity', 'h', 'w')} | {'hashes': {name: ref['sha256'] for name, ref in c['refs'].items()}} for c in cases]}
    d.new(root / 'config-base.json', config)
    config['configSha256'] = d.bind(root / 'config-base.json')['sha256']; d.new(root / 'config.json', config)
    with (root / 'browser.html').open('xb') as stream: stream.write(HTML.encode('utf-8')); stream.flush(); os.fsync(stream.fileno())
    d.new(root / 'preparation.json', {'plan': d.bind(plan_path), 'server': d.bind(__file__), 'html': d.bind(root / 'browser.html'),
        'config': d.bind(root / 'config.json'), 'caseReferences': cases})


def serve(root, port):
    preparation = d.read(d.bind(root / 'preparation.json')); d.checked(preparation['server']); d.checked(preparation['html']); d.checked(preparation['config'])
    plan = d.read(preparation['plan'])
    routes = {'/': preparation['html'], '/browser.html': preparation['html'], '/config.json': preparation['config']}
    routes.update({'/ort/' + name: ref for name, ref in plan['runtimeFiles'].items()})
    routes.update({'/model/' + kind + '.onnx': plan['inputs'][kind + 'Onnx'] for kind in ('control', 'learned')})
    case_map = {c['ordinal']: c for c in preparation['caseReferences']}
    for c in case_map.values():
        routes.update({f'/case/{c["ordinal"]}/{name}.bin': {k: ref[k] for k in ('path', 'sha256')} for name, ref in c['refs'].items()})
    capture_names = {f'{kind}-{backend}-{ordinal}-{head}.bin': (case_map[ordinal]['h']*case_map[ordinal]['w'] if head=='mask' else 1)*4
        for kind in ('control', 'learned') for backend in ('wasm', 'webgpu') for ordinal in case_map for head in ('mask', 'presence')}

    class Handler(BaseHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin'); self.send_header('Cross-Origin-Embedder-Policy', 'require-corp'); super().end_headers()

        def do_GET(self):
            route = urllib.parse.urlsplit(self.path).path
            if route not in routes: self.send_error(404); return
            path = d.checked(routes[route]); body = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html' if path.suffix=='.html' else 'application/json' if path.suffix=='.json' else 'text/javascript' if path.suffix in ('.js', '.mjs') else 'application/wasm' if path.suffix=='.wasm' else 'application/octet-stream')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            count = int(self.headers.get('Content-Length', '0'))
            if not 0 < count <= 16_000_000: self.send_error(400); return
            if self.path.startswith('/start/'):
                parts = self.path.split('/')
                if len(parts)!=5 or parts[2] not in ('control', 'learned') or parts[3] not in ('wasm', 'webgpu'): self.send_error(400); return
                kind, backend, ordinal = parts[2], parts[3], int(parts[4])
                if ordinal not in case_map: self.send_error(400); return
                value = json.loads(self.rfile.read(count))
                if value != {'kind': kind, 'backend': backend, 'ordinal': ordinal, 'candidateIdentity': case_map[ordinal]['candidateIdentity']}: self.send_error(400); return
                target = root / 'started-inputs' / f'{kind}-{backend}-{ordinal}.json'
                body = d.raw({**value, 'startedAtUnixNs': time.time_ns()})
            elif self.path.startswith('/capture/'):
                name = self.path.removeprefix('/capture/')
                if name not in capture_names and name!='live-browser.json': self.send_error(400); return
                if name in capture_names and count!=capture_names[name]: self.send_error(400); return
                target = root / 'browser-capture' / name; body = self.rfile.read(count)
            else: self.send_error(404); return
            try:
                with target.open('xb') as stream: stream.write(body); stream.flush(); os.fsync(stream.fileno())
            except FileExistsError: self.send_error(409); return
            self.send_response(201); self.end_headers(); self.wfile.write(b'captured')

        def log_message(self, *args): pass

    print(f'TRAINED_BROWSER_SERVER http://127.0.0.1:{port}/browser.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--plan', type=Path); p.add_argument('--output', type=Path, required=True); p.add_argument('--port', type=int, default=8827); p.add_argument('--serve', action='store_true'); a = p.parse_args()
    if a.serve: serve(a.output.resolve(), a.port)
    else: prepare(a.plan.resolve(), a.output.resolve()); print('frozen browser harness prepared; no browser model inputs yet')
