"""修复图全候选三后端逐层诊断；最终头逐字节保真是解释前置门。"""
import argparse
import importlib.util
import json
import math
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('repaired_layer_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)


def validate_scope(p):
    if p['purpose'] != 'repaired_graph_full68_cpu_wasm_webgpu_layerwise_localization_only':
        raise ValueError('scope purpose')
    if any(p[k] != 68 for k in ('fullCandidateCount', 'instrumentedCpuInputsAllowed', 'instrumentedWasmInputsAllowed', 'instrumentedWebgpuInputsAllowed')):
        raise ValueError('full68 denominator')
    if any(p[k] != 0 for k in ('newTorchInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed')):
        raise ValueError('zero Torch/optimizer/val/protected scope')
    if p['graphOptimizationLevel'] != 'disabled' or p['requiredNumericDifference'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0:
        raise ValueError('fixed numeric gate')
    for k in ('allFinalHeadsMustBeBitwiseIdenticalToSameBackendUninstrumentedCapturesBeforeLayerConclusions', 'addOutputsOnly', 'sameRepairedGraphAndAllLearnedParameters', 'inheritedFull68NonzeroControls', 'failedBrowserBudgetMayNotRestart', 'productHold'):
        if p[k] is not True: raise ValueError('required guard ' + k)
    if p['formalReleaseAllowed'] is not False: raise ValueError('release prohibited')


def resources(execution):
    e = d.read(d.bind(execution)); d.checked(e['auditor'])
    if e['auditor'] != d.bind(__file__): raise ValueError('auditor version')
    p = d.read(e['scope']); validate_scope(p)
    for ref in p['inputs'].values(): d.checked(ref)
    cpu = d.read(p['inputs']['cpuReport']); browser = d.read(p['inputs']['browserFailure'])
    strict = d.read(p['inputs']['strictReference']); layers = d.read(p['inputs']['strictLayerReport'])
    bs = d.read(p['inputs']['browserScope'])
    for ref in bs['runtimeFiles'].values(): d.checked(ref)
    if not cpu['learnedCpuGatePassed'] or not cpu['nonzeroControlGatePassed'] or not browser['bothBackendNonzeroControlGatePassed'] or browser['learnedBrowserGatePassed']:
        raise ValueError('inherited CPU/control/failure gates')
    if p['inputs']['learnedOnnx'] != cpu['artifacts']['learnedOnnx'] or p['inputs']['trainedWeights'] != strict['sameWeights']:
        raise ValueError('same learned model')
    precision = d.load(d.checked(strict['inputs']['auditor']), 'repaired_layer_precision')
    layer = d.load(d.checked(p['inputs']['layerInstrumentation']), 'repaired_layer_instrumentation')
    old = d.read(d.read(strict['inputs']['plan'])['inputs']['cpuFailure'])
    groups = [old['records'], cpu['captures']['learned'], strict['captures'], layers['captures']]
    for group in groups:
        if len(group) != 68 or [r['candidateIdentity'] for r in group] != p['candidateIdentities'] or [r['ordinal'] for r in group] != list(range(1, 69)):
            raise ValueError('full ordered stable identities')
    if any(r['identity']['split'] != 'train' for r in p['candidateIdentities']): raise ValueError('train only')
    bindings = {Path(r['path']).name: r for r in browser['captureBindings']}
    if len(bindings) != len(browser['captureBindings']): raise ValueError('duplicate browser captures')
    model = onnx.load(d.checked(p['inputs']['learnedOnnx'])); mapping = layer.instrument(model)
    cases = []
    for o, c, st, l in zip(*groups, strict=True):
        ordinal, h, w = o['ordinal'], o['h'], o['w']
        if list(l['strictCuda']['layers']) != [m['module'] for m in mapping]: raise ValueError('strict layer map')
        heads = {'mask': [1, 1, h, w], 'presence': [1, 1]}
        shapes = heads | {m['module']: l['strictCuda']['layers'][m['module']]['shape'] for m in mapping}
        refs = {'input': o['paths']['input']}
        for backend in ('cpu', 'wasm', 'webgpu'):
            for head in heads:
                ref = c[head] if backend == 'cpu' else bindings[f'learned-{backend}-{ordinal}-{head}.bin']
                refs[backend + '-' + head] = ref
                precision.buffer(ref, math.prod(heads[head]))
        precision.buffer(refs['input'], 4*h*w)
        for head, key in (('mask', 'strict-mask'), ('presence', 'strict-presence')):
            if precision.buffer(st['paths'][key], math.prod(heads[head])).tobytes() != layer.read_tensor(precision, l['strictCuda'][head]).tobytes():
                raise ValueError('strict layer final reference changed')
        cases.append({'ordinal': ordinal, 'candidateIdentity': o['candidateIdentity'], 'h': h, 'w': w, 'refs': refs, 'shapes': shapes})
    return e, p, cpu, browser, layers, precision, layer, model, mapping, cases, bs


def terminal_heads(cases, captured, precision, layer, backend):
    if len(captured) != 68 or [c['candidateIdentity'] for c in captured] != [c['candidateIdentity'] for c in cases] or [c['ordinal'] for c in captured] != list(range(1, 69)):
        raise ValueError('full captured denominator/order')
    for c, out in zip(cases, captured, strict=True):
        if list(out['outputs']) != list(c['shapes']): raise ValueError('output map')
        for head in ('mask', 'presence'):
            actual = layer.read_tensor(precision, out['outputs'][head])
            expected = precision.buffer(c['refs'][backend + '-' + head], math.prod(c['shapes'][head])).reshape(c['shapes'][head])
            layer.exact(expected, actual)


HTML = r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>三后端逐层保真核验</title><link rel="icon" href="data:,"><h1>开发模型逐层数值诊断</h1><button id="run">执行全68 WASM及WebGPU逐层捕获</button><pre id="result">未执行；产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>
const load=async p=>{const r=await fetch(p);if(!r.ok)throw Error('GET '+p+' '+r.status);return r.arrayBuffer();};
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
const verified=async(p,sha)=>{const b=await load(p);if(hex(await crypto.subtle.digest('SHA-256',b))!==sha)throw Error('SHA '+p);return b;};
const post=async(p,b)=>{const r=await fetch(p,{method:'POST',body:b});if(!r.ok)throw Error('POST '+p+' '+r.status);};
const equal=(a,b)=>{const x=new Uint8Array(a),y=new Uint8Array(b);if(x.length!==y.length)return false;for(let i=0;i<x.length;i++)if(x[i]!==y[i])return false;return true;};
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;const config=await(await fetch('/config.json')).json();
 const report={executionSha256:config.executionSha256,configSha256:config.configSha256,userAgent:navigator.userAgent,crossOriginIsolated,startedInputs:[],records:[],errors:[],phase:'starting'};
 try{
  if(!crossOriginIsolated)throw Error('isolation');ort.env.wasm.wasmPaths='/ort/';ort.env.wasm.numThreads=1;
  const adapter=await navigator.gpu?.requestAdapter();report.adapterInfo=adapter?{vendor:adapter.info?.vendor,architecture:adapter.info?.architecture,device:adapter.info?.device,description:adapter.info?.description}:null;
  for(const backend of ['wasm','webgpu']){
   let session;try{
    session=await ort.InferenceSession.create(await verified('/model.onnx',config.model.sha256),{executionProviders:[backend],graphOptimizationLevel:'disabled'});
    if(session.inputNames.join(',')!=='candidate'||session.outputNames.join(',')!==config.outputNames.join(','))throw Error('actual IO names');
    for(const row of config.cases){
     report.phase=backend+' '+row.ordinal+'/68';document.querySelector('#result').textContent=report.phase;
     const x=new Float32Array(await verified('/case/'+row.ordinal+'/input.bin',row.hashes.input));if(x.length!==4*row.h*row.w)throw Error('native input size');
     const event={backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity};await post('/start/'+backend+'/'+row.ordinal,JSON.stringify(event));report.startedInputs.push(event);
     const out=await session.run({candidate:new ort.Tensor('float32',x,[1,4,row.h,row.w])});const rec={...event,finalHeadsBitwiseIdentical:true,outputs:[]};
     for(let i=0;i<config.outputNames.length;i++){
      const key=config.outputKeys[i],t=out[config.outputNames[i]],a=new Float32Array(await t.getData());
      if(t.type!=='float32'||Array.from(t.dims).join(',')!==row.shapes[key].join(',')||a.length!==row.shapes[key].reduce((x,y)=>x*y,1))throw Error('shape/dtype '+key);
      for(const v of a)if(!Number.isFinite(v))throw Error('nonfinite '+key);
      if(i<2){const b=await verified('/case/'+row.ordinal+'/'+backend+'-'+key+'.bin',row.hashes[backend+'-'+key]);rec.finalHeadsBitwiseIdentical&&=equal(a.buffer,b);}
      await post('/capture/'+backend+'-'+row.ordinal+'-'+key+'.bin',new Uint8Array(a.buffer));rec.outputs.push({key,shape:Array.from(t.dims),dtype:t.type});
     }
     report.records.push(rec);
    }
   }finally{if(session)await session.release();}
  }
  report.ok=report.records.length===136&&report.records.every(r=>r.finalHeadsBitwiseIdentical);report.phase='terminal';
 }catch(e){report.ok=false;report.phase='terminal-failure';report.errors.push(String(e));}
 await post('/terminal',JSON.stringify(report));document.querySelector('#result').textContent=JSON.stringify(report);
};</script></html>'''


def prepare(execution, root):
    if root.exists(): raise ValueError('budget output exists; read-only replay only')
    e, p, cpu, browser, layers, precision, layer, model, mapping, cases, bs = resources(execution)
    root.mkdir(parents=True, exist_ok=False)
    (root / 'cpu').mkdir(); (root / 'browser-capture').mkdir(); (root / 'started-inputs').mkdir()
    onnx.save(model, root / 'instrumented.onnx'); captures = []; started = 0
    try:
        options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(str(root / 'instrumented.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        names = ['mask_logits', 'presence_logit'] + [m['tensor'] for m in mapping]
        if [o.name for o in session.get_outputs()] != names: raise ValueError('CPU output names')
        for c in cases:
            folder = root / 'cpu' / str(c['ordinal']); folder.mkdir()
            d.new(folder / 'start.json', {'backend': 'cpu', 'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'startedAtUnixNs': time.time_ns()}); started += 1
            x = precision.buffer(c['refs']['input'], 4*c['h']*c['w']).reshape(1, 4, c['h'], c['w'])
            values = session.run(None, {'candidate': x})
            out = {'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'outputs': {k: layer.save(folder / (k + '.bin'), v) for k, v in zip(c['shapes'], values, strict=True)}}
            d.new(folder / 'capture.json', out); captures.append(out)
            print(json.dumps({'cpuCaptured': len(captures), 'cpuStarted': started, 'TorchInputs': 0}), flush=True)
        terminal_heads(cases, captures, precision, layer, 'cpu')
        d.new(root / 'cpu-captures.json', captures)
        config = {'executionSha256': d.bind(execution)['sha256'], 'model': d.bind(root / 'instrumented.onnx'), 'outputNames': names, 'outputKeys': list(cases[0]['shapes']),
                  'cases': [{k: c[k] for k in ('ordinal', 'candidateIdentity', 'h', 'w', 'shapes')} | {'hashes': {k: v['sha256'] for k, v in c['refs'].items()}} for c in cases]}
        d.new(root / 'config-base.json', config); config['configSha256'] = d.bind(root / 'config-base.json')['sha256']; d.new(root / 'config.json', config)
        with (root / 'browser.html').open('xb') as stream: stream.write(HTML.encode('utf-8')); stream.flush(); os.fsync(stream.fileno())
        d.new(root / 'preparation.json', {'execution': d.bind(execution), 'server': d.bind(__file__), 'html': d.bind(root / 'browser.html'), 'config': d.bind(root / 'config.json'), 'cpuCaptures': d.bind(root / 'cpu-captures.json'), 'model': config['model'], 'cases': cases, 'runtimeFiles': bs['runtimeFiles']})
    except BaseException as error:
        d.new(root / 'failure.json', {'ok': False, 'decision': 'reconstruction_mismatch', 'type': type(error).__name__, 'message': str(error), 'cpuStarted': started, 'cpuCaptured': len(captures), 'browserStarted': 0, 'layerConclusionsAllowed': False, 'productHold': True}); raise


def sequence(cases):
    return [(b, c['ordinal']) for b in ('wasm', 'webgpu') for c in cases]


def validate_event(actual, expected, case):
    b, ordinal = expected
    if actual != {'backend': b, 'ordinal': ordinal, 'candidateIdentity': case['candidateIdentity']}: raise ValueError('ordered start identity')


def serve(root, port):
    prep = d.read(d.bind(root / 'preparation.json'))
    for k in ('execution', 'server', 'html', 'config', 'cpuCaptures', 'model'): d.checked(prep[k])
    if prep['server'] != d.bind(__file__): raise ValueError('server version')
    if any((root / 'started-inputs').iterdir()) or (root / 'live-browser.json').exists(): raise ValueError('browser budget may not restart')
    cases = {c['ordinal']: c for c in prep['cases']}; order = sequence(prep['cases'])
    routes = {'/browser.html': prep['html'], '/config.json': prep['config'], '/model.onnx': prep['model']}
    routes.update({'/ort/' + k: v for k, v in prep['runtimeFiles'].items()})
    for c in cases.values(): routes.update({f'/case/{c["ordinal"]}/{k}.bin': {n: v[n] for n in ('path', 'sha256')} for k, v in c['refs'].items()})
    allowed = {f'{b}-{o}-{k}.bin': math.prod(shape)*4 for b, o in order for k, shape in cases[o]['shapes'].items()}
    starts = []; captured = set(); lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin'); self.send_header('Cross-Origin-Embedder-Policy', 'require-corp'); super().end_headers()

        def do_GET(self):
            route = urllib.parse.urlsplit(self.path).path
            if route not in routes: self.send_error(404); return
            path = d.checked(routes[route]); body = path.read_bytes(); self.send_response(200)
            self.send_header('Content-Type', 'text/html' if path.suffix == '.html' else 'application/json' if path.suffix == '.json' else 'text/javascript' if path.suffix in ('.js', '.mjs') else 'application/wasm' if path.suffix == '.wasm' else 'application/octet-stream')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            with lock:
                try:
                    count = int(self.headers.get('Content-Length', '0'))
                    if self.path.startswith('/start/'):
                        if not 0 < count <= 100_000 or len(starts) >= len(order): raise ValueError('start limit')
                        b, o = order[len(starts)]
                        if self.path != f'/start/{b}/{o}': raise ValueError('start order')
                        if starts:
                            pb, po = starts[-1]
                            if any(f'{pb}-{po}-{k}.bin' not in captured for k in cases[po]['shapes']): raise ValueError('previous full capture required')
                        event = json.loads(self.rfile.read(count)); validate_event(event, (b, o), cases[o])
                        d.new(root / 'started-inputs' / f'{b}-{o}.json', event | {'startedAtUnixNs': time.time_ns()}); starts.append((b, o))
                    elif self.path.startswith('/capture/'):
                        name = self.path.removeprefix('/capture/')
                        if name not in allowed or count != allowed[name] or not starts: raise ValueError('tensor byte cardinality')
                        b, o = starts[-1]
                        if name not in {f'{b}-{o}-{k}.bin' for k in cases[o]['shapes']}: raise ValueError('active identity capture')
                        body = self.rfile.read(count)
                        if len(body) != count: raise ValueError('truncated tensor')
                        with (root / 'browser-capture' / name).open('xb') as stream: stream.write(body); stream.flush(); os.fsync(stream.fileno())
                        captured.add(name)
                    elif self.path == '/terminal':
                        if not 0 < count <= 4_000_000: raise ValueError('terminal size')
                        d.new(root / 'live-browser.json', json.loads(self.rfile.read(count)))
                    else: self.send_error(404); return
                except FileExistsError: self.send_error(409); return
                except (ValueError, KeyError): self.send_error(400); return
            self.send_response(201); self.end_headers(); self.wfile.write(b'captured')

        def log_message(self, *args): pass

    print(f'REPAIRED_LAYER_SERVER http://127.0.0.1:{port}/browser.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def reconstruct(root):
    prep = d.read(d.bind(root / 'preparation.json'))
    for k in ('server', 'html', 'config', 'cpuCaptures', 'model'): d.checked(prep[k])
    e, p, cpu, browser, layers, precision, layer, model, mapping, cases, bs = resources(d.checked(prep['execution']))
    if model.SerializeToString() != onnx.load(d.checked(prep['model'])).SerializeToString() or prep['cases'] != cases or prep['runtimeFiles'] != bs['runtimeFiles']:
        raise ValueError('add outputs only / case reconstruction_mismatch')
    live = d.read(d.bind(root / 'live-browser.json')); config = d.read(prep['config'])
    if live['executionSha256'] != prep['execution']['sha256'] or live['configSha256'] != config['configSha256'] or live['errors'] or live['phase'] != 'terminal' or not live['crossOriginIsolated']:
        raise ValueError('browser terminal reconstruction_mismatch')
    order = sequence(cases); cm = {c['ordinal']: c for c in cases}
    if len(live['records']) != 136 or len(live['startedInputs']) != 136 or len(list((root / 'started-inputs').glob('*.json'))) != 136 or len(list((root / 'browser-capture').glob('*.bin'))) != 136*33:
        raise ValueError('browser full captures/starts denominator')
    events = []; captured = {'cpu': d.read(prep['cpuCaptures']), 'wasm': [], 'webgpu': []}
    for pair, event, rec in zip(order, live['startedInputs'], live['records'], strict=True):
        b, o = pair; c = cm[o]; validate_event(event, pair, c)
        frozen = d.read(d.bind(root / 'started-inputs' / f'{b}-{o}.json'))
        if {k: frozen[k] for k in event} != event or type(frozen['startedAtUnixNs']) != int: raise ValueError('start event binding')
        if frozen['startedAtUnixNs'] <= (events[-1]['time'] if events else 0): raise ValueError('start event time order')
        events.append({'binding': d.bind(root / 'started-inputs' / f'{b}-{o}.json'), 'time': frozen['startedAtUnixNs']})
        if {k: rec[k] for k in event} != event or rec['outputs'] != [{'key': k, 'shape': v, 'dtype': 'float32'} for k, v in c['shapes'].items()]: raise ValueError('browser actual shapes')
        captured[b].append({'ordinal': o, 'candidateIdentity': c['candidateIdentity'], 'outputs': {k: d.bind(root / 'browser-capture' / f'{b}-{o}-{k}.bin') | {'shape': shape, 'dtype': 'float32'} for k, shape in c['shapes'].items()}})
    # 所有后端的全68最终头保真通过前，禁止读取中间层并给出层结论。
    for backend in captured: terminal_heads(cases, captured[backend], precision, layer, backend)
    if not live['ok'] or not all(r['finalHeadsBitwiseIdentical'] for r in live['records']): raise ValueError('browser head report disagrees')
    cpu_events = []
    for c in cases:
        event_path = root / 'cpu' / str(c['ordinal']) / 'start.json'; event = d.read(d.bind(event_path)); validate_event({k: event[k] for k in ('backend', 'ordinal', 'candidateIdentity')}, ('cpu', c['ordinal']), c)
        if d.read(d.bind(root / 'cpu' / str(c['ordinal']) / 'capture.json')) != captured['cpu'][c['ordinal']-1]: raise ValueError('CPU capture persistence')
        cpu_events.append(d.bind(event_path))
    records = []
    for i, c in enumerate(cases):
        row = {'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'layers': []}
        for m in mapping:
            key = m['module']; reference = layer.read_tensor(precision, layers['captures'][i]['strictCuda']['layers'][key])
            values = {b: layer.read_tensor(precision, captured[b][i]['outputs'][key]) for b in captured}
            if any(list(v.shape) != c['shapes'][key] for v in values.values()): raise ValueError('native layer shape')
            row['layers'].append(m | {'shape': list(reference.shape), 'strictCudaVsBackend': {b: layer.differences(reference, v) for b, v in values.items()}, 'cpuVsBrowser': {b: layer.differences(values['cpu'], values[b]) for b in ('wasm', 'webgpu')}})
        row['firstLayerAbove1e4'] = {b: next((l['module'] for l in row['layers'] if l['strictCudaVsBackend'][b]['maxAbs'] > 1e-4), None) for b in captured}
        records.append(row)
        print(json.dumps({'replayedCandidates': len(records)}), flush=True)
    summary = [{**m, 'strictCudaVsBackend': {b: {'maxAbs': max(r['layers'][i]['strictCudaVsBackend'][b]['maxAbs'] for r in records), 'candidateCountAbove1e4': sum(r['layers'][i]['strictCudaVsBackend'][b]['maxAbs'] > 1e-4 for r in records)} for b in captured}} for i, m in enumerate(mapping)]
    return {'schemaVersion': 1, 'ok': True, 'decision': 'repaired_three_backend_layerwise_diagnostic_reconstructed', 'inputs': {'preparation': d.bind(root / 'preparation.json'), 'auditor': d.bind(__file__), 'liveBrowser': d.bind(root / 'live-browser.json')}, 'captures': captured, 'inputStartEvents': {'cpu': cpu_events, 'browser': events}, 'records': records, 'layerSummary': summary, 'fullCandidateCount': 68, 'finalHeadsBitwiseIdenticalAllBackends': True, 'newInstrumentedInputs': {'cpu': 68, 'wasm': 68, 'webgpu': 68}, 'newTorchInputs': 0, 'optimizerSteps': 0, 'valModelInputs': 0, 'protectedModelInputs': 0, 'browserLearnedGatePassed': False, 'inheritedNonzeroControlsPassed': True, 'firstCrossingIsNotRootCauseProof': True, 'formalReleaseAllowed': False, 'productHold': True, 'actualBrowserUserAgent': live['userAgent'], 'adapterInfo': live['adapterInfo']}


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--execution', type=Path); a.add_argument('--output', type=Path, required=True); a.add_argument('--serve', action='store_true'); a.add_argument('--audit', action='store_true'); a.add_argument('--verify-report', action='store_true'); a.add_argument('--port', type=int, default=8828); args = a.parse_args(); root = args.output.resolve()
    if args.serve: serve(root, args.port)
    elif args.audit or args.verify_report:
        try:
            result = reconstruct(root)
            if args.verify_report:
                if result != d.read(d.bind(root / 'report.json')): raise ValueError('report reconstruction_mismatch')
            else: d.new(root / 'report.json', result)
            print(json.dumps({k: result[k] for k in ('ok', 'decision', 'finalHeadsBitwiseIdenticalAllBackends')}))
        except BaseException as error:
            if not args.verify_report: d.new(root / 'audit-failure.json', {'ok': False, 'decision': 'reconstruction_mismatch', 'error': str(error), 'layerConclusionsAllowed': False, 'productHold': True})
            raise
    else: prepare(args.execution.resolve(), root)
