"""新候选完整原尺寸图分阶段验真；全部新非零控制通过前禁止学得输入。"""
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
HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('joint_full_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s)
s.loader.exec_module(d)

def validate_config(root, prep, p, models, e):
    base = {'executionSha256': prep['execution']['sha256'], 'kind': prep['kind'], 'model': models[prep['kind']], 'cases': p['cases'], 'expectedEnvironment': e['expectedEnvironment']}
    config = d.read(prep['config'])
    if d.read(d.bind(root / 'config-base.json')) != base or config != base | {'configSha256': d.bind(root / 'config-base.json')['sha256']} or d.checked(prep['html']).read_bytes() != HTML.encode('utf-8'):
        raise ValueError('exact frozen config/HTML')
    if root != Path(e['stageRoots'][prep['kind']]).resolve():
        raise ValueError('exact frozen stage root')
    return config

def tensor(ref):
    path = d.checked({k: ref[k] for k in ('path', 'sha256')})
    if ref['dtype'] != 'float32' or path.stat().st_size != math.prod(ref['shape']) * 4:
        raise ValueError('float32 exact native cardinality')
    a = np.fromfile(path, np.float32).reshape(ref['shape'])
    if not np.isfinite(a).all():
        raise ValueError('all tensor elements finite')
    return a

def save(path, a):
    if a.dtype != np.float32 or not np.isfinite(a).all():
        raise ValueError('captured float32 finite')
    with path.open('xb') as f:
        f.write(a.tobytes())
        f.flush()
        os.fsync(f.fileno())
    return d.bind(path) | {'shape': list(a.shape), 'dtype': 'float32'}

def compare(c, kind, outputs, comparator):
    refs = c['references'][kind]
    reference = {}
    actual = {}
    for head in ('mask', 'presence'):
        shape = [1, 1, c['h'], c['w']] if head == 'mask' else [1, 1]
        if refs[head]['shape'] != shape or outputs[head]['shape'] != shape or refs[head]['dtype'] != 'float32' or (outputs[head]['dtype'] != 'float32'):
            raise ValueError('both heads original native shape / F32 domain')
        reference[head] = tensor(refs[head])
        actual[head] = tensor(outputs[head])
    return comparator.compare_outputs(reference['mask'].reshape(-1), reference['presence'].reshape(-1), actual['mask'].reshape(-1), actual['presence'].reshape(-1), c['h'], c['w'])

def passed(stats):
    return all((stats[k] for k in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched', 'allReferenceAndCapturedHeadsFinite')))

def event(kind, b, c, page=None):
    r = {'kind': kind, 'backend': b, 'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'inputSha256': c['input']['sha256'], 'resizeRatiosSha256': c['resizeRatios']['sha256'], 'targetShape': [1, 1, c['h'], c['w']]}
    return r if page is None else r | {'pageRequestId': page}

def validate_event(r, kind, b, c, page):
    if {k: v for k, v in r.items() if k != 'inputRequestId'} != event(kind, b, c, page) or str(uuid.UUID(r['inputRequestId'])) != r['inputRequestId']:
        raise ValueError('ordered original input / ratios / unique UUID')

def control_gate(e):
    root = Path(e['controlRoot'])
    r = reconstruct(root)
    if r != d.read(d.bind(root / 'report.json')):
        raise ValueError('control frozen report reconstruction')
    require_control_gate(r)
    return d.bind(root / 'report.json')

def prepare(execution, root, kind):
    if root.exists():
        raise ValueError('stage consumed; read-only replay only')
    e, p, models, comparator = resources(execution)
    if kind not in ('control', 'learned') or root != Path(e['stageRoots'][kind]).resolve():
        raise ValueError('fixed stage root')
    gate = control_gate(e) if kind == 'learned' else None
    root.mkdir(parents=True, exist_ok=False)
    for name in ('cpu', 'started-inputs', 'browser-capture', 'upload-events'):
        (root / name).mkdir()
    captures = []
    starts = 0
    try:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.log_severity_level = 3
        session = ort.InferenceSession(str(d.checked(models[kind])), sess_options=options, providers=['CPUExecutionProvider'])
        if [v.name for v in session.get_inputs()] != ['candidate', 'resizeRatios'] or [v.name for v in session.get_outputs()] != ['mask_logits', 'presence_logit']:
            raise ValueError('CPU full IO')
        for c in p['cases']:
            feeds = {'candidate': tensor(c['input']), 'resizeRatios': tensor(c['resizeRatios'])}
            ev = event(kind, 'cpu', c)
            d.new(root / 'cpu' / f"{c['ordinal']}-start.json", ev | {'startedAtUnixNs': time.time_ns()})
            starts += 1
            ys = session.run(None, feeds)
            outputs = {}
            for head, a in zip(('mask', 'presence'), ys, strict=True):
                if list(a.shape) != c['references'][kind][head]['shape']:
                    raise ValueError('CPU two-head native shape')
                outputs[head] = save(root / 'cpu' / f"{c['ordinal']}-{head}.bin", a)
            captures.append(ev | {'outputs': outputs, 'parity': compare(c, kind, outputs, comparator)})
        d.new(root / 'cpu-captures.json', captures)
        config = {'executionSha256': d.bind(execution)['sha256'], 'kind': kind, 'model': models[kind], 'cases': p['cases'], 'expectedEnvironment': e['expectedEnvironment']}
        d.new(root / 'config-base.json', config)
        config['configSha256'] = d.bind(root / 'config-base.json')['sha256']
        d.new(root / 'config.json', config)
        with (root / 'browser.html').open('xb') as f:
            f.write(HTML.encode())
            f.flush()
            os.fsync(f.fileno())
        d.new(root / 'preparation.json', {'execution': d.bind(execution), 'auditor': d.bind(__file__), 'kind': kind, 'controlGate': gate, 'html': d.bind(root / 'browser.html'), 'config': d.bind(root / 'config.json'), 'cpuCaptures': d.bind(root / 'cpu-captures.json')})
        if not all((passed(r['parity']) for r in captures)):
            raise ValueError('CPU stage gate failed; browser budget remains zero')
        print(json.dumps({'ok': True, 'kind': kind, 'cpuCaptured': len(captures), 'maxAbs': max((r['parity']['maxAbsoluteDifference'] for r in captures)), 'browserStarted': 0}), flush=True)
    except BaseException as error:
        d.new(root / 'execution-failure.json', {'ok': False, 'error': str(error), 'kind': kind, 'cpuStarted': starts, 'cpuCaptured': len(captures), 'browserStarted': 0, 'newTorchInputs': 0, 'optimizerSteps': 0, 'valInputs': 0, 'protectedInputs': 0, 'productHold': True})
        raise

def serve(root, port):
    prep = d.read(d.bind(root / 'preparation.json'))
    for ref in prep.values():
        if isinstance(ref, dict) and 'path' in ref:
            d.checked(ref)
    e, p, models, comparator = resources(d.checked(prep['execution']))
    kind = prep['kind']
    config = validate_config(root, prep, p, models, e)
    if kind == 'learned' and prep['controlGate'] != control_gate(e):
        raise ValueError('learned control gate')
    if (root / 'claim.json').exists() or any((root / 'started-inputs').iterdir()) or (not all((passed(r['parity']) for r in d.read(prep['cpuCaptures'])))):
        raise ValueError('single stage / CPU gate')
    cases = {c['ordinal']: c for c in p['cases']}
    order = [(b, c['ordinal']) for b in ('wasm', 'webgpu') for c in p['cases']]
    routes = {'/browser.html': prep['html'], '/config.json': prep['config'], '/model.onnx': models[kind]}
    routes.update({'/ort/' + n: r for n, r in e['runtimeFiles'].items()})
    routes.update({f'/input/{o}.bin': {k: c['input'][k] for k in ('path', 'sha256')} for o, c in cases.items()})
    allowed = {f'{b}-{o}-{h}.bin': (cases[o]['h'] * cases[o]['w'] if h == 'mask' else 1) * 4 for b, o in order for h in ('mask', 'presence')}
    starts = []
    captured = set()
    ids = set()
    lock = threading.Lock()
    claim = None
    uploads = 0

    def stored(route):
        if route == '/claim':
            return root / 'claim.json'
        if route == '/terminal':
            return root / 'live-browser.json'
        if route.startswith('/capture/') and route.removeprefix('/capture/') in allowed:
            return root / 'browser-capture' / route.removeprefix('/capture/')
        parts = route.split('/')
        if len(parts) == 4 and parts[1] == 'start' and (parts[2] in ('wasm', 'webgpu')) and parts[3].isdigit() and ((parts[2], int(parts[3])) in order):
            return root / 'started-inputs' / f'{parts[2]}-{int(parts[3])}.json'
        raise ValueError('route whitelist')

    def ack_for(route):
        path = stored(route)
        if not path.exists():
            return None
        return {'sha256': d.bind(path)['sha256'], 'bytes': path.stat().st_size} if route.startswith('/capture/') else d.read(d.bind(path))['requestBinding']

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def reply(self, code, value, content='application/json'):
            b = value if isinstance(value, bytes) else d.raw(value)
            self.send_response(code)
            self.send_header('Content-Length', str(len(b)))
            self.send_header('Content-Type', content)
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.end_headers()
            self.wfile.write(b)
            self.wfile.flush()

        def do_GET(self):
            route = urllib.parse.urlsplit(self.path).path
            if route.startswith('/status/'):
                try:
                    a = ack_for(route.removeprefix('/status'))
                    self.reply(200 if a else 404, a or {})
                except ValueError:
                    self.reply(400, {})
            elif route in routes:
                path = d.checked(routes[route])
                mime = 'text/html' if path.suffix == '.html' else 'text/javascript' if path.suffix in ('.js', '.mjs') else 'application/wasm' if path.suffix == '.wasm' else 'application/octet-stream'
                self.reply(200, path.read_bytes(), mime)
            else:
                self.reply(404, {})

        def do_POST(self):
            nonlocal claim, uploads
            with lock:
                try:
                    path = stored(self.path)
                    n = int(self.headers.get('Content-Length', '0'))
                    if self.path.startswith('/capture/'):
                        if n != allowed[self.path.removeprefix('/capture/')]:
                            raise ValueError('capture bytes')
                    elif not 0 < n <= 4000000:
                        raise ValueError('event bytes')
                    body = self.rfile.read(n)
                    ack = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
                    if len(body) != n:
                        raise ValueError('truncated body')
                    if path.exists():
                        if ack_for(self.path) != ack:
                            raise ValueError('same request conflict')
                        self.reply(201, ack)
                        return
                    if self.path == '/claim':
                        value = json.loads(body)
                        if set(value) != {'pageRequestId', 'executionSha256'} or value['executionSha256'] != prep['execution']['sha256'] or str(uuid.UUID(value['pageRequestId'])) != value['pageRequestId']:
                            raise ValueError('claim')
                        claim = value['pageRequestId']
                        d.new(path, {'value': value, 'requestBinding': ack})
                    elif self.path.startswith('/start/'):
                        if not claim or len(starts) >= 2 * N:
                            raise ValueError('stage limit')
                        b, o = order[len(starts)]
                        if self.path != f'/start/{b}/{o}' or (starts and any((f'{starts[-1][0]}-{starts[-1][1]}-{h}.bin' not in captured for h in ('mask', 'presence')))):
                            raise ValueError('ordered complete two heads')
                        value = json.loads(body)
                        validate_event(value, kind, b, cases[o], claim)
                        if value['inputRequestId'] in ids:
                            raise ValueError('unique UUID')
                        d.new(path, {'value': value, 'startedAtUnixNs': time.time_ns(), 'requestBinding': ack})
                        starts.append((b, o))
                        ids.add(value['inputRequestId'])
                    elif self.path.startswith('/capture/'):
                        if not starts:
                            raise ValueError('start required')
                        b, o = starts[-1]
                        name = self.path.removeprefix('/capture/')
                        if name not in (f'{b}-{o}-mask.bin', f'{b}-{o}-presence.bin') or (name.endswith('-presence.bin') and f'{b}-{o}-mask.bin' not in captured):
                            raise ValueError('active two heads')
                        with path.open('xb') as f:
                            f.write(body)
                            f.flush()
                            os.fsync(f.fileno())
                        captured.add(name)
                    else:
                        value = json.loads(body)
                        if value['pageRequestId'] != claim:
                            raise ValueError('terminal claim')
                        d.new(path, {'value': value, 'requestBinding': ack})
                    uploads += 1
                    d.new(root / 'upload-events' / f'{uploads:04d}.json', {'route': self.path, 'requestBinding': ack})
                    self.reply(201, ack)
                except (ValueError, KeyError, FileExistsError):
                    self.reply(409, {'error': 'full stage contract'})

        def log_message(self, *args):
            pass
    print(f'FIRST_GN_FULL_SERVER http://127.0.0.1:{port}/browser.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()

def reconstruct(root):
    prep = d.read(d.bind(root / 'preparation.json'))
    e, p, models, comparator = resources(d.checked(prep['execution']))
    kind = prep['kind']
    for ref in (prep['auditor'], prep['html'], prep['config'], prep['cpuCaptures']):
        d.checked(ref)
    if kind == 'learned' and prep['controlGate'] != control_gate(e):
        raise ValueError('all controls gate binding')
    config = validate_config(root, prep, p, models, e)
    live = d.read(d.bind(root / 'live-browser.json'))['value']
    claim = d.read(d.bind(root / 'claim.json'))['value']['pageRequestId']
    if not live['captureComplete'] or live['errors'] or live['phase'] != 'terminal' or (live['executionSha256'] != prep['execution']['sha256']) or (live['configSha256'] != config['configSha256']) or (live['pageRequestId'] != claim) or (live['kind'] != kind) or (not live['crossOriginIsolated']):
        raise ValueError('complete136 browser stage')
    if live['userAgent'] != e['expectedEnvironment']['userAgent'] or live['adapterInfo'] != e['expectedEnvironment']['adapterInfo']:
        raise ValueError('same actual browser environment')
    if len(live['records']) != 2 * N or len(live['startedInputs']) != 2 * N or len(list((root / 'started-inputs').glob('*.json'))) != 2 * N or (len(list((root / 'browser-capture').glob('*.bin'))) != 4 * N):
        raise ValueError('whole starts and both heads')
    cases = {c['ordinal']: c for c in p['cases']}
    records = []
    captures = {'cpu': d.read(prep['cpuCaptures']), 'wasm': [], 'webgpu': []}
    events = []
    ids = []
    times = []
    for index, (ev, record) in enumerate(zip(live['startedInputs'], live['records'], strict=True)):
        b = 'wasm' if index < N else 'webgpu'
        o = index % N + 1
        c = cases[o]
        validate_event(ev, kind, b, c, claim)
        path = root / 'started-inputs' / f'{b}-{o}.json'
        st = d.read(d.bind(path))
        if st['value'] != ev or (times and st['startedAtUnixNs'] <= times[-1]):
            raise ValueError('persisted start order')
        if {k: record[k] for k in ev} != ev or record['dtype'] != 'float32' or record['shapes'] != {h: c['references'][kind][h]['shape'] for h in ('mask', 'presence')}:
            raise ValueError('two-head actual shape/dtype')
        outputs = {h: d.bind(root / 'browser-capture' / f'{b}-{o}-{h}.bin') | {'shape': record['shapes'][h], 'dtype': 'float32'} for h in ('mask', 'presence')}
        captures[b].append(ev | {'outputs': outputs})
        events.append(d.bind(path))
        ids.append(ev['inputRequestId'])
        times.append(st['startedAtUnixNs'])
    if len(set(ids)) != 2 * N or len(list((root / 'cpu').glob('*-start.json'))) != N or len(list((root / 'cpu').glob('*.bin'))) != 2 * N:
        raise ValueError('unique actual starts and full CPU two heads')
    cpu_times = [d.read(d.bind(root / 'cpu' / f'{o}-start.json'))['startedAtUnixNs'] for o in range(1, 69)]
    if any((a >= b for a, b in zip(cpu_times, cpu_times[1:]))):
        raise ValueError('CPU monotonic starts')
    for b, rows in captures.items():
        if len(rows) != N or [r['ordinal'] for r in rows] != list(range(1, 69)):
            raise ValueError('all68 per backend')
        for cap in rows:
            c = cases[cap['ordinal']]
            if {k: cap[k] for k in event(kind, b, c)} != event(kind, b, c):
                raise ValueError('same stage input/ratio')
            if b == 'cpu':
                st = d.read(d.bind(root / 'cpu' / f"{c['ordinal']}-start.json"))
                if {k: st[k] for k in event(kind, b, c)} != event(kind, b, c):
                    raise ValueError('CPU started identity')
            stats = compare(c, kind, cap['outputs'], comparator)
            if b == 'cpu' and stats != cap['parity']:
                raise ValueError('CPU parity reconstruction')
            records.append({'backend': b, 'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'parity': stats, 'gatePassed': passed(stats)})
    summary = {b: {'candidateCount': N, 'maxAbs': max((r['parity']['maxAbsoluteDifference'] for r in records if r['backend'] == b)), 'failedOrdinals': [r['ordinal'] for r in records if r['backend'] == b and (not r['gatePassed'])], 'decodedPixelDifferences': sum((r['parity']['decodedMaskPixelDifference'] for r in records if r['backend'] == b)), 'presenceFailed': sum((not r['parity']['presenceDecisionMatched'] for r in records if r['backend'] == b))} for b in captures}
    uploads = [d.bind(path) for path in sorted((root / 'upload-events').glob('*.json'))]
    expected = ['/claim'] + [route for b in ('wasm', 'webgpu') for o in range(1, 69) for route in (f'/start/{b}/{o}', f'/capture/{b}-{o}-mask.bin', f'/capture/{b}-{o}-presence.bin')] + ['/terminal']
    if [d.read(ref)['route'] for ref in uploads] != expected:
        raise ValueError('complete persisted upload order')
    stage_pass = all((r['gatePassed'] for r in records))
    return {'schemaVersion': 1, 'ok': True, 'decision': 'new_reviewed_native_candidate_stage_reconstructed', 'kind': kind, 'inputs': {'preparation': d.bind(root / 'preparation.json'), 'auditor': d.bind(__file__), 'liveBrowser': d.bind(root / 'live-browser.json')}, 'controlGate': prep['controlGate'], 'captures': captures, 'browserStartEvents': events, 'uploadEvents': uploads, 'records': records, 'summary': summary, 'allThreeBackendStageGatesPassed': stage_pass, 'fullModelLearnedGatePassed': kind == 'learned' and stage_pass, 'modelInputsConsumedPerBackend': {'cpu': N, 'wasm': N, 'webgpu': N}, 'modelInputsConsumed': 3 * N, 'newTorchInputs': 0, 'optimizerSteps': 0, 'valModelInputs': 0, 'protectedModelInputs': 0, 'newChatImageInputs': 0, 'transportErrors': live['transportErrors'], 'persistedAckRecoveries': live['persistedAckRecoveries'], 'uploadOnlyRetries': live['uploadOnlyRetries'], 'oldFailuresAndConsumedBudgetsPreserved': True, 'formalReleaseAllowed': False, 'productHold': True}


N = 0

def resources(execution):
    global N
    e=d.read(d.bind(execution))
    for ref in e['sources'].values(): d.checked(ref)
    for ref in list(e['runtimeFiles'].values())+list(e['pythonRuntimeFiles'].values()): d.checked(ref)
    if e['sources']['auditor']!=d.bind(__file__) or not e['executionImplementedAndFrozen']: raise ValueError('frozen new native executor')
    if e['runtimeVersions']!={'python':__import__('platform').python_version(),'numpy':np.__version__,'onnx':onnx.__version__,'onnxruntime':ort.__version__}: raise ValueError('actual frozen runtime')
    p=d.read(e['scope']); assets=d.read(p['inputs']['assets'])
    reader=d.load(d.checked(e['sources']['assetReader']),'new_native_asset_reader')
    if reader.verify(d.checked(p['inputs']['assets']))!=d.read(p['inputs']['assetsReplay']): raise ValueError('complete original native inputs and reversible graphs')
    control=d.load(d.checked(e['sources']['controlReader']),'new_native_control_reader')
    if control.verify(d.checked(p['inputs']['strictControl']))!=d.read(p['inputs']['strictControlReplay']): raise ValueError('all new nonzero CUDA controls')
    references=d.read(p['inputs']['strictControl'])['records']; N=len(p['cases'])
    if N!=74 or p['candidateIdentities']!=assets['candidateIdentities'] or p['models']!=assets['models'] or len(references)!=N: raise ValueError('full current train-only cohort')
    for i,(case,original,ref) in enumerate(zip(p['cases'],assets['cases'],references,strict=True),1):
        expected=copy.deepcopy(original); expected['references']['control']=ref['outputs']
        if case!=expected or case['ordinal']!=i or case['candidateIdentity']['identity']['split']!='train': raise ValueError('all native candidate/reference bytes')
    if p['budget']!={'maximumAttemptsPerStage':1,'controlInputsPerBackend':N,'learnedInputsPerBackend':N,'backends':['cpu','wasm','webgpu'],'totalBackendInputs':6*N,'learnedCudaNewInputs':0,'optimizerSteps':0,'internalValInputs':0,'protectedInputs':0,'newChatImageInputs':0,'restartAllowed':False}: raise ValueError('full new budgets')
    if p['quality']!={'maximumBothHeadDifference':1e-4,'decodedPixelDifferences':0,'presenceDecisionDifferences':0,'allFloat32ShapesAndElementsFinite':True}: raise ValueError('unchanged numeric quality')
    comparator=d.load(d.checked(e['sources']['comparator']),'new_native_two_head_comparator')
    return e,p,p['models'],comparator

def require_control_gate(r):
    if not r.get('ok') or r.get('kind')!='control' or not r.get('allThreeBackendStageGatesPassed') or r.get('modelInputsConsumedPerBackend')!={b:N for b in ('cpu','wasm','webgpu')} or len(r.get('records',[]))!=3*N: raise ValueError('all new controls before learned')
    if [(row.get('backend'),row.get('ordinal')) for row in r['records']]!=[(b,o) for b in ('cpu','wasm','webgpu') for o in range(1,N+1)] or not all(row.get('gatePassed') is True and passed(row['parity']) for row in r['records']): raise ValueError('actual each full two-head control gate')

HTML = '<!doctype html><meta charset="utf-8"><title>新开发候选完整模型核验</title><link rel="icon" href="data:,"><h1>完整模型两头核验</h1><button id="run">执行本阶段完整WASM/WebGPU输入</button><pre id="result">未执行；产品HOLD。</pre><script src="/ort/ort.all.min.js"></script><script>\nconst hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,\'0\')).join(\'\');\nconst verified=async(path,sha)=>{const r=await fetch(path),b=await r.arrayBuffer();if(!r.ok||hex(await crypto.subtle.digest(\'SHA-256\',b))!==sha)throw Error(\'GET/SHA \'+path);return b;};\nasync function post(path,body,log){const bytes=typeof body===\'string\'?new TextEncoder().encode(body):body,sha=hex(await crypto.subtle.digest(\'SHA-256\',bytes));for(let attempt=0;attempt<3;attempt++){try{const r=await fetch(path,{method:\'POST\',body:bytes}),text=await r.text();if(!r.ok)throw Error(\'HTTP \'+r.status);const a=JSON.parse(text);if(a.sha256!==sha||a.bytes!==bytes.length)throw Error(\'ACK\');return;}catch(error){log.transportErrors.push({path,attempt,error:String(error)});const r=await fetch(\'/status\'+path),text=await r.text();if(r.ok){const a=JSON.parse(text);if(a.sha256!==sha||a.bytes!==bytes.length)throw Error(\'persisted conflict\');log.persistedAckRecoveries++;return;}if(r.status!==404)throw Error(\'status\');log.uploadOnlyRetries++;}}throw Error(\'bounded upload attempts\');}\ndocument.querySelector(\'#run\').onclick=async()=>{document.querySelector(\'#run\').disabled=true;const c=await(await fetch(\'/config.json\')).json(),r={executionSha256:c.executionSha256,configSha256:c.configSha256,kind:c.kind,pageRequestId:crypto.randomUUID(),userAgent:navigator.userAgent,crossOriginIsolated,records:[],startedInputs:[],errors:[],transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0,phase:\'starting\'};try{\nawait post(\'/claim\',JSON.stringify({pageRequestId:r.pageRequestId,executionSha256:c.executionSha256}),r);if(!crossOriginIsolated)throw Error(\'isolation\');ort.env.wasm.wasmPaths=\'/ort/\';ort.env.wasm.numThreads=1;\nconst adapter=await navigator.gpu?.requestAdapter();r.adapterInfo=adapter?{vendor:adapter.info?.vendor,architecture:adapter.info?.architecture,device:adapter.info?.device,description:adapter.info?.description}:null;\nif(r.userAgent!==c.expectedEnvironment.userAgent||JSON.stringify(r.adapterInfo)!==JSON.stringify(c.expectedEnvironment.adapterInfo))throw Error(\'frozen actual browser environment\');\nfor(const backend of [\'wasm\',\'webgpu\']){let session;try{session=await ort.InferenceSession.create(await verified(\'/model.onnx\',c.model.sha256),{executionProviders:[backend],graphOptimizationLevel:\'disabled\'});if(session.inputNames.join(\',\')!==\'candidate,resizeRatios\'||session.outputNames.join(\',\')!==\'mask_logits,presence_logit\')throw Error(\'actual IO\');\nfor(const row of c.cases){r.phase=c.kind+\'/\'+backend+\' \'+row.ordinal+\'/\'+c.cases.length;document.querySelector(\'#result\').textContent=r.phase;const input=new Float32Array(await verified(\'/input/\'+row.ordinal+\'.bin\',row.input.sha256));if(input.length!==4*row.h*row.w)throw Error(\'input cardinality\');for(const v of input)if(!Number.isFinite(v))throw Error(\'input finite\');const ratios=new Float32Array([Math.fround(Math.floor(row.h/4)/Math.floor(row.h/2)),Math.fround(Math.floor(row.w/4)/Math.floor(row.w/2)),Math.fround(Math.floor(row.h/2)/row.h),Math.fround(Math.floor(row.w/2)/row.w)]);if(hex(await crypto.subtle.digest(\'SHA-256\',ratios.buffer))!==row.resizeRatios.sha256)throw Error(\'full host vector\');\nconst e={kind:c.kind,backend,ordinal:row.ordinal,candidateIdentity:row.candidateIdentity,inputSha256:row.input.sha256,resizeRatiosSha256:row.resizeRatios.sha256,targetShape:[1,1,row.h,row.w],pageRequestId:r.pageRequestId,inputRequestId:crypto.randomUUID()};await post(\'/start/\'+backend+\'/\'+row.ordinal,JSON.stringify(e),r);r.startedInputs.push(e);\nconst y=await session.run({candidate:new ort.Tensor(\'float32\',input,row.input.shape),resizeRatios:new ort.Tensor(\'float32\',ratios,[4])}),shapes={};for(const [head,name] of [[\'mask\',\'mask_logits\'],[\'presence\',\'presence_logit\']]){const t=y[name],a=new Float32Array(await t.getData()),shape=head===\'mask\'?[1,1,row.h,row.w]:[1,1];if(t.type!==\'float32\'||Array.from(t.dims).join(\',\')!==shape.join(\',\')||a.length!==shape.reduce((x,y)=>x*y,1))throw Error(\'two-head native shape / float32\');for(const v of a)if(!Number.isFinite(v))throw Error(\'two-head finite\');await post(\'/capture/\'+backend+\'-\'+row.ordinal+\'-\'+head+\'.bin\',new Uint8Array(a.buffer),r);shapes[head]=shape;}r.records.push({...e,shapes,dtype:\'float32\'});}\n}finally{if(session)await session.release();}}\nr.captureComplete=r.records.length===c.cases.length*2;r.phase=\'terminal\';}catch(error){r.captureComplete=false;r.errors.push(String(error));r.phase=\'terminal-failure\';}await post(\'/terminal\',JSON.stringify(r),{transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0});document.querySelector(\'#result\').textContent=JSON.stringify(r);};</script>'

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--execution', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--stage', choices=['control', 'learned'])
    p.add_argument('--serve', action='store_true')
    p.add_argument('--audit', action='store_true')
    p.add_argument('--verify-report', action='store_true')
    p.add_argument('--port', type=int, default=8840)
    a = p.parse_args()
    root = a.output.resolve()
    if a.serve:
        serve(root, a.port)
    elif a.audit or a.verify_report:
        try:
            r = reconstruct(root)
            if a.verify_report:
                if r != d.read(d.bind(root / 'report.json')):
                    raise ValueError('stage reconstruction_mismatch')
            else:
                d.new(root / 'report.json', r)
            print(json.dumps({k: r[k] for k in ('ok', 'kind', 'allThreeBackendStageGatesPassed', 'summary')}))
        except BaseException as error:
            if not a.verify_report:
                d.new(root / 'audit-failure.json', {'ok': False, 'decision': 'reconstruction_mismatch', 'error': str(error), 'productHold': True})
            raise
    else:
        prepare(a.execution.resolve(), root, a.stage)
