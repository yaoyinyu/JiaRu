"""完整新路由控制：一次CPU及真实WASM/WebGPU双头，原始捕获独立重放。"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('route_control_primitives', Path(__file__).with_name('prepare-two-head-route-control.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
compare_spec = importlib.util.spec_from_file_location('route_original_comparator', Path(__file__).with_name('verify-native-multiscale-browser-v2.py'))
compare = importlib.util.module_from_spec(compare_spec); compare_spec.loader.exec_module(compare)
MODULES = ['nail-two-head-route.mjs', 'nail-mask-f64-v2.mjs', 'verify-mask-wasm-coordinates.mjs', 'browser-two-head-control.mjs']


def read(path): return json.loads(Path(path).read_bytes())
def passed(row): return all(row[k] for k in ['numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched', 'allReferenceAndCapturedHeadsFinite'])
def capture(path, a):
    assert a.dtype == np.float32 and np.isfinite(a).all()
    return p.new(path, a.tobytes()) | {'shape': list(a.shape), 'dtype': 'float32'}


def parity(case, outputs):
    expected, actual = {}, {}
    for head in ['mask', 'presence']:
        shape = [1, 1, case['h'], case['w']] if head == 'mask' else [1, 1]
        expected[head] = p.tensor(case['references']['control'][head]); actual[head] = p.tensor(outputs[head])
        if list(expected[head].shape) != shape or list(actual[head].shape) != shape: raise ValueError('complete two-head cardinality')
    return compare.compare_outputs(expected['mask'].reshape(-1), expected['presence'].reshape(-1),
        actual['mask'].reshape(-1), actual['presence'].reshape(-1), case['h'], case['w'])


def coordinates(root, pre, records):
    if not records['ok'] or len(records['records']) != 296: raise ValueError('complete actual coordinate calls')
    for i, row in enumerate(records['records']):
        case = pre['cases'][i // 4]; axis = case['coordinateAxes'][i % 4]
        if (row['ordinal'], row['index'], row['incoming'], row['outgoing']) != (case['ordinal'], i % 4, axis['incoming'], axis['outgoing']): raise ValueError('coordinate identity')
        for field, ref in axis['fields'].items():
            actual = root / f'{case["ordinal"]}-{i % 4}-{field}.bin'
            if p.bind(actual)['sha256'] != ref['sha256'] or row['fields'][field]['actualSha256'] != ref['sha256'] or row['fields'][field]['path'] != ref['path']:
                raise ValueError('all1184 actual original coordinate bytes')
    if len(list(root.glob('*.bin'))) != 1184: raise ValueError('coordinate RAW denominator')


def freeze(root, preflight, node_coordinates):
    if not root.is_relative_to(ROOT / 'model/reviews'): raise ValueError('isolated review root')
    pre = read(preflight); nr = read(node_coordinates / 'report.json')
    if nr['preflight'] != p.bind(preflight): raise ValueError('coordinate stage binding')
    coordinates(node_coordinates, pre, nr)
    root.mkdir(exist_ok=False)
    for name in ['cpu', 'events', 'browser', 'coordinates']: (root / name).mkdir()
    sources = {str(file.relative_to(ROOT)): p.bind(file) for file in [Path(__file__),
        Path(__file__).with_name('prepare-two-head-route-control.py'),
        Path(__file__).with_name('verify-native-multiscale-browser-v2.py'),
        *[ROOT / 'model/runtime' / name for name in MODULES]]}
    for ref in [*pre['sources'].values(), *pre['nativeRuntimeSources'].values(), pre['model'], pre['wasm'], pre['parameterPack'], pre['parameterConfig']]: p.checked(ref)
    old = read(ROOT / 'model/reviews/cycle016-convex-native-backends-execution-v1.json')
    runtime = old['pythonRuntimeFiles'].copy()
    for ref in runtime.values(): p.checked(ref)
    execution = {'purpose': 'complete74_fresh_three_backend_nonzero_two_head_route_control',
        'preflight': p.bind(preflight), 'nodeCoordinateReplay': p.bind(node_coordinates / 'report.json'),
        'sources': sources, 'pythonRuntimeFiles': runtime,
        'browserBinary': p.bind(Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')),
        'runtimeVersions': {'python': platform.python_version(), 'numpy': np.__version__, 'ort': ort.__version__},
        'controlBudget': {'onnxInputsPerBackend': 74, 'backends': ['cpu', 'wasm', 'webgpu'],
            'totalOnnxInputs': 222, 'extraF64WasmMaskInputs': 74, 'browserCoordinateCalls': 296,
            'learnedInputsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'restartAllowed': False},
        'quality': {'maxAbs': 1e-4, 'decodedPixelDifferences': 0, 'presenceDecisionDifferences': 0},
        'root': str(root), 'formalReleaseAllowed': False, 'productHold': True}
    p.new(root / 'execution.json', execution)
    print(json.dumps({'ok': True, 'stage': 'frozen', 'onnxBudget': 222, 'extraWasmMaskBudget': 74, 'learnedBudget': 0}), flush=True)


def resources(root):
    e = read(root / 'execution.json')
    if e['runtimeVersions'] != {'python': platform.python_version(), 'numpy': np.__version__, 'ort': ort.__version__}: raise ValueError('frozen actual runtime versions')
    if e['root'] != str(root) or e['sources']['model/training/audit-two-head-route-control.py'] != p.bind(__file__): raise ValueError('frozen route executor')
    for ref in list(e['sources'].values()) + list(e['pythonRuntimeFiles'].values()) + [e['browserBinary']]: p.checked(ref)
    pre = p.read(e['preflight'])
    for ref in [*pre['sources'].values(), *pre['nativeRuntimeSources'].values(), pre['model'], pre['wasm'], pre['parameterPack'], pre['parameterConfig']]: p.checked(ref)
    if len(pre['cases']) != 74 or e['controlBudget'] != {'onnxInputsPerBackend': 74, 'backends': ['cpu', 'wasm', 'webgpu'],
            'totalOnnxInputs': 222, 'extraF64WasmMaskInputs': 74, 'browserCoordinateCalls': 296,
            'learnedInputsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'restartAllowed': False}: raise ValueError('unchanged complete control budget')
    if e['quality'] != {'maxAbs': 1e-4, 'decodedPixelDifferences': 0, 'presenceDecisionDifferences': 0}: raise ValueError('original complete gates')
    return e, pre


def cpu(root):
    e, pre = resources(root); records = []
    p.new(root / 'cpu-attempt.json', {'execution': p.bind(root / 'execution.json'), 'restartAllowed': False})
    try:
        options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL; options.log_severity_level = 3
        session = ort.InferenceSession(str(p.checked(pre['model'])), sess_options=options, providers=['CPUExecutionProvider'])
        if [v.name for v in session.get_inputs()] != ['candidate', 'resizeRatios'] or [v.name for v in session.get_outputs()] != ['mask_logits', 'presence_logit']: raise ValueError('original full native IO')
        for case in pre['cases']:
            ordinal = case['ordinal']; x, ratios = p.tensor(case['input']), p.tensor(case['resizeRatios'])
            event = {'backend': 'cpu', 'ordinal': ordinal, 'candidateIdentity': case['candidateIdentity'],
                     'inputSha256': case['input']['sha256'], 'resizeRatiosSha256': case['resizeRatios']['sha256']}
            p.new(root / 'cpu' / f'{ordinal}-start.json', event | {'startedAtUnixNs': time.time_ns()})
            mask, presence = session.run(None, {'candidate': x, 'resizeRatios': ratios})
            outputs = {head: capture(root / 'cpu' / f'{ordinal}-{head}.bin', a) for head, a in [('mask', mask), ('presence', presence)]}
            correction = float(np.abs(mask - (x[:, 3:4] * np.float32(8) - np.float32(4))).max())
            if correction <= 0 or not np.any(presence != 0): raise ValueError('actual two-head nonzero control')
            row = event | {'outputs': outputs, 'parity': parity(case, outputs), 'actualPresenceExecuted': True,
                           'nonzeroMaskCorrectionMaxAbs': correction}
            p.new(root / 'cpu' / f'{ordinal}-done.json', row); records.append(row)
            if ordinal % 10 == 0: print(json.dumps({'phase': 'actual_cpu_control', 'confirmed': ordinal, 'total': 74}), flush=True)
        report = {'ok': True, 'records': records, 'allGatesPassed': all(passed(r['parity']) for r in records), 'learnedInputs': 0}
        p.new(root / 'cpu-report.json', report)
        print(json.dumps({'ok': True, 'cpuControlGatePassed': report['allGatesPassed'], 'count': len(records)}), flush=True)
    except BaseException as error:
        p.new(root / 'cpu-failure.json', {'error': str(error), 'confirmed': len(records), 'restartAllowed': False}); raise


def actual_output(root, backend, case, head):
    path = root / 'browser' / f'{backend}-{case["ordinal"]}-{head}.bin'
    shape = [1, 1] if head == 'presence' else [1, 1, case['h'], case['w']]
    ref = p.bind(path) | {'dtype': 'float32', 'shape': shape}
    p.tensor(ref)
    return ref


def reconstruct(root):
    e, pre = resources(root); records = []
    cp = read(root / 'cpu-report.json'); claim = read(root / 'claim.json')
    if not cp['ok'] or len(cp['records']) != 74: raise ValueError('complete CPU scope')
    if claim['adapterInfo']['vendor'] != 'nvidia' or claim['adapterInfo']['architecture'] != 'lovelace' or not claim['crossOriginIsolated'] or 'Chrome/155.' not in claim['userAgent']: raise ValueError('actual browser environment')
    coordinates(root / 'coordinates', pre, read(root / 'coordinates-complete.json'))
    for case, row in zip(pre['cases'], cp['records'], strict=True):
        if row != read(root / 'cpu' / f'{case["ordinal"]}-done.json') or row['candidateIdentity'] != case['candidateIdentity'] or row['parity'] != parity(case, row['outputs']): raise ValueError('CPU complete byte replay')
        start = read(root / 'cpu' / f'{case["ordinal"]}-start.json')
        for key in ['backend', 'ordinal', 'candidateIdentity', 'inputSha256', 'resizeRatiosSha256']:
            if start[key] != row[key]: raise ValueError('CPU start chain')
        x = p.tensor(case['input']); mask = p.tensor(row['outputs']['mask'])
        correction = float(np.abs(mask - (x[:, 3:4] * np.float32(8) - np.float32(4))).max())
        if not row['actualPresenceExecuted'] or correction <= 0 or correction != row['nonzeroMaskCorrectionMaxAbs']: raise ValueError('actual nonzero CPU heads')
        records.append({'backend': 'cpu', 'ordinal': case['ordinal'], 'parity': row['parity'], 'outputs': row['outputs']})
    request_ids = set()
    for backend in ['wasm', 'webgpu']:
        for case in pre['cases']:
            ordinal = case['ordinal']; row = read(root / 'events' / f'{backend}-{ordinal}-done.json')
            start = read(root / 'events' / f'{backend}-{ordinal}-start.json')
            if row['event'] != start or start['pageId'] != claim['pageId'] or start['ordinal'] != ordinal or start['candidateIdentity'] != case['candidateIdentity'] or start['inputSha256'] != case['input']['sha256'] or start['resizeRatiosSha256'] != case['resizeRatios']['sha256']:
                raise ValueError('full actual browser start identity')
            request = read(root / 'events' / f'{backend}-{ordinal}-done-request.json')
            if any(request[k] != v for k, v in start.items()) or any(request[k] != row[k] for k in ['actualPresenceExecuted', 'maskRoute', 'memory', 'elapsedMsWithCapture']): raise ValueError('actual done request and server record chain')
            if str(uuid.UUID(start['requestId'])) != start['requestId'] or start['requestId'] in request_ids: raise ValueError('unique request identity')
            request_ids.add(start['requestId'])
            outputs = {head: actual_output(root, backend, case, head) for head in ['mask', 'presence']}
            if outputs != row['outputs'] or parity(case, outputs) != row['parity'] or not row['actualPresenceExecuted']: raise ValueError('actual browser two-head RAW and gate')
            if backend == 'wasm':
                if read(root / 'events' / f'wasm-{ordinal}-mask-start.json') != start or row['maskRoute'] != 'f64_wasm': raise ValueError('new actual F64 mask execution')
                actual_output(root, backend, case, 'unused')
                if row['memory']['wasmMemoryBytes'] != 268435456 or row['memory']['workspaceHighWaterBytes'] > 268435456: raise ValueError('bounded actual mask memory')
            elif row['maskRoute'] != 'original_f32_webgpu' or row['memory'] is not None: raise ValueError('original actual WebGPU route')
            x = p.tensor(case['input']); a = p.tensor(outputs['mask']); b = p.tensor(outputs['presence'])
            if not np.any(b != 0) or not float(np.abs(a - (x[:, 3:4] * np.float32(8) - np.float32(4))).max()) > 0: raise ValueError('actual both-head nonzero control')
            records.append({'backend': backend, 'ordinal': ordinal, 'parity': row['parity'], 'outputs': outputs})
    if len(list((root / 'cpu').glob('*-start.json'))) != 74 or len(list((root / 'cpu').glob('*-done.json'))) != 74 or len(list((root / 'events').glob('*-start.json'))) != 222 or len(list((root / 'events').glob('*-done.json'))) != 148:
        raise ValueError('full immutable actual event cardinality')
    if len(list((root / 'browser').glob('*.bin'))) != 370: raise ValueError('all actual browser outputs including unused mask')
    terminal = read(root / 'live-browser.json')
    expected_order = [{'backend': b, 'ordinal': i} for b in ['wasm', 'webgpu'] for i in range(1, 75)]
    if terminal['records'] != expected_order or terminal['pageId'] != claim['pageId'] or not terminal['actualPresenceExecuted']: raise ValueError('complete browser terminal')
    summary = {}
    for backend in ['cpu', 'wasm', 'webgpu']:
        rows = [r for r in records if r['backend'] == backend]
        summary[backend] = {'count': len(rows), 'maxAbs': max(r['parity']['maxAbsoluteDifference'] for r in rows),
            'failedOrdinals': [r['ordinal'] for r in rows if not passed(r['parity'])],
            'decodedPixelDifferences': sum(r['parity']['decodedMaskPixelDifference'] for r in rows),
            'presenceDecisionDifferences': sum(not r['parity']['presenceDecisionMatched'] for r in rows)}
    return {'ok': True, 'decision': 'complete74_fresh_nonzero_route_control_reconstructed',
        'execution': p.bind(root / 'execution.json'), 'records': records, 'summary': summary,
        'fullNonzeroRouteControlPassed': all(not r['failedOrdinals'] for r in summary.values()),
        'actualPresenceExecuted': True, 'onnxInputsConsumed': 222, 'extraF64WasmMaskInputsConsumed': 74,
        'wholeBrowserPeakMemoryClaimed': False, 'learnedInputs': 0, 'formalReleaseAllowed': False, 'productHold': True}


def serve(root, port):
    e, pre = resources(root)
    if (root / 'claim.json').exists() or list((root / 'events').iterdir()): raise ValueError('already claimed or consumed browser stage')
    allowed = {}
    def collect(obj):
        if isinstance(obj, dict):
            if 'path' in obj and 'sha256' in obj: allowed[str(p.checked(obj))] = obj['sha256']
            for value in obj.values(): collect(value)
        elif isinstance(obj, list):
            for value in obj: collect(value)
    collect({k: pre[k] for k in ['wasm', 'model', 'parameterPack', 'parameterConfig', 'nativeRuntimeSources']})
    for case in pre['cases']: collect([case['input'], case['resizeRatios'], case['coordinateAxes']])
    modules = {name: ROOT / 'model/runtime' / name for name in MODULES}
    for path in modules.values(): allowed[str(path)] = p.bind(path)['sha256']
    config = {'executionSha256': p.bind(root / 'execution.json')['sha256'], 'preflight': pre}
    html = '<!doctype html><meta charset="utf-8"><title>全74新双头路由控制</title><link rel="icon" href="data:,"><button id="run" disabled>执行全74新双头控制</button><pre id="status">准备坐标与实际环境</pre><script src="/ort/ort.all.min.js"></script><script type="module" src="/module/browser-two-head-control.mjs"></script>'.encode('utf-8')
    lock = threading.Lock(); order = [(b, i) for b in ['wasm', 'webgpu'] for i in range(1, 75)]
    starts = []; cases = {c['ordinal']: c for c in pre['cases']}
    field_expected = {f'{c["ordinal"]}-{index}-{field}.bin': ref for c in pre['cases'] for index, axis in enumerate(c['coordinateAxes']) for field, ref in axis['fields'].items()}
    def response_raw(value): return value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False) + '\n').encode()
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args): return
        def reply(self, code, value, content='application/json'):
            raw = response_raw(value); self.send_response(code)
            for name, val in [('Content-Type', content), ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
                              ('Cross-Origin-Opener-Policy', 'same-origin'), ('Cross-Origin-Embedder-Policy', 'require-corp')]: self.send_header(name, val)
            self.end_headers(); self.wfile.write(raw); self.wfile.flush()
        def do_GET(self):
            target = urlsplit(self.path)
            try:
                if target.path == '/': return self.reply(200, html, 'text/html; charset=utf-8')
                if target.path == '/config': return self.reply(200, config)
                if target.path == '/ready':
                    ready = (root / 'coordinates-complete.json').is_file() and (root / 'cpu-report.json').is_file() and read(root / 'cpu-report.json')['allGatesPassed']
                    return self.reply(200, {'ready': ready})
                if target.path.startswith('/module/'): path = modules[target.path.removeprefix('/module/')]
                elif target.path.startswith('/ort/'): path = Path(pre['nativeRuntimeSources'][target.path.removeprefix('/ort/')]['path'])
                elif target.path == '/resource': path = Path(parse_qs(target.query)['path'][0])
                else: return self.reply(404, b'not found')
                if str(path) not in allowed: raise ValueError('read whitelist')
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != allowed[str(path)]: raise ValueError('frozen read bytes')
                return self.reply(200, raw, 'application/wasm' if path.suffix == '.wasm' else 'text/javascript' if path.suffix in ['.js', '.mjs'] else 'application/octet-stream')
            except Exception as error: return self.reply(409, {'error': str(error)})
        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', -1))
                if not 0 <= size <= 16 * 1024 * 1024: raise ValueError('bounded request')
                raw = self.rfile.read(size); digest = hashlib.sha256(raw).hexdigest()
                if len(raw) != size or digest != self.headers.get('X-Content-Sha256'): raise ValueError('actual request bytes')
                route = urlsplit(self.path).path; parts = route.strip('/').split('/')
                with lock:
                    page = self.headers.get('X-Page-Id'); request = self.headers.get('X-Request-Id')
                    if route == '/claim':
                        value = json.loads(raw)
                        if value['pageId'] != page or value['executionSha256'] != config['executionSha256'] or value['adapterInfo']['vendor'] != 'nvidia' or value['adapterInfo']['architecture'] != 'lovelace' or not value['crossOriginIsolated'] or 'Chrome/155.' not in value['userAgent']: raise ValueError('new real browser environment')
                        path = root / 'claim.json'
                    elif route == '/failure' and not (root / 'claim.json').exists():
                        path = root / 'browser-environment-failure.json'
                    else:
                        if read(root / 'claim.json')['pageId'] != page: raise ValueError('exclusive page claim')
                        if parts[0] == 'coordinate':
                            ref = field_expected[parts[1]]
                            if digest != ref['sha256']: raise ValueError('actual original coordinate SHA')
                            path = root / 'coordinates' / parts[1]
                        elif route == '/coordinates-complete':
                            coordinates(root / 'coordinates', pre, json.loads(raw)); path = root / 'coordinates-complete.json'
                        elif parts[0] in ['start', 'mask-start']:
                            backend, ordinal = (parts[1], int(parts[2])) if parts[0] == 'start' else ('wasm', int(parts[1]))
                            value = json.loads(raw); case = cases[ordinal]
                            expected = {'backend': backend, 'ordinal': ordinal, 'pageId': page, 'requestId': request,
                                'candidateIdentity': case['candidateIdentity'], 'inputSha256': case['input']['sha256'], 'resizeRatiosSha256': case['resizeRatios']['sha256']}
                            if value != expected or str(uuid.UUID(request)) != request: raise ValueError('complete unique start binding')
                            if not read(root / 'cpu-report.json')['allGatesPassed'] or not (root / 'coordinates-complete.json').exists(): raise ValueError('full preflight/CPU gates before browser inputs')
                            suffix = 'start' if parts[0] == 'start' else 'mask-start'
                            path = root / 'events' / f'{backend}-{ordinal}-{suffix}.json'
                            if not path.exists():
                                if parts[0] == 'start':
                                    if order[len(starts)] != (backend, ordinal): raise ValueError('full ordered control starts')
                                    if starts:
                                        b, i = starts[-1]
                                        if not (root / 'events' / f'{b}-{i}-done.json').exists(): raise ValueError('prior input not completed')
                                    starts.append((backend, ordinal))
                                elif read(root / 'events' / f'wasm-{ordinal}-start.json') != value: raise ValueError('actual ORT before mask')
                        elif parts[0] == 'capture':
                            backend, ordinal, head = parts[1], int(parts[2]), parts[3]; case = cases[ordinal]
                            start = read(root / 'events' / f'{backend}-{ordinal}-start.json')
                            if start['requestId'] != request or (backend, ordinal) != starts[-1]: raise ValueError('current request capture binding')
                            if head not in (['mask', 'presence', 'unused'] if backend == 'wasm' else ['mask', 'presence']): raise ValueError('actual output head')
                            count = 1 if head == 'presence' else case['h'] * case['w']
                            if size != count * 4 or not np.isfinite(np.frombuffer(raw, np.float32)).all(): raise ValueError('complete finite native output')
                            path = root / 'browser' / f'{backend}-{ordinal}-{head}.bin'
                        elif parts[0] == 'done':
                            backend, ordinal = parts[1], int(parts[2]); case = cases[ordinal]; value = json.loads(raw)
                            start = read(root / 'events' / f'{backend}-{ordinal}-start.json')
                            for key in start:
                                if value[key] != start[key]: raise ValueError('done actual start binding')
                            outputs = {head: actual_output(root, backend, case, head) for head in ['mask', 'presence']}
                            if backend == 'wasm':
                                actual_output(root, backend, case, 'unused')
                                if read(root / 'events' / f'wasm-{ordinal}-mask-start.json') != start: raise ValueError('F64 mask actual start')
                            row = {'event': start, 'outputs': outputs, 'parity': parity(case, outputs), 'actualPresenceExecuted': value['actualPresenceExecuted'],
                                'maskRoute': value['maskRoute'], 'memory': value['memory'], 'elapsedMsWithCapture': value['elapsedMsWithCapture']}
                            path = root / 'events' / f'{backend}-{ordinal}-done.json'
                            # 服务端构建的记录另存，客户端原应答字节绑定仍独立保留。
                            request_path = root / 'events' / f'{backend}-{ordinal}-done-request.json'
                            if request_path.exists():
                                if request_path.read_bytes() != raw: raise ValueError('done request changed')
                            else: p.new(request_path, raw)
                            raw = (json.dumps(row, ensure_ascii=False, indent=2) + '\n').encode()
                        elif route == '/terminal': path = root / 'live-browser.json'
                        elif route == '/failure': path = root / 'browser-failure.json'
                        else: raise ValueError('write whitelist')
                    if path.exists():
                        if path.read_bytes() != raw: raise ValueError('persisted output conflict')
                    else: p.new(path, raw)
                    self.reply(200, {'sha256': digest, 'bytes': size})
            except Exception as error: self.reply(409, {'error': str(error)})
    p.new(root / 'server-start.json', {'port': port, 'execution': p.bind(root / 'execution.json')})
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(json.dumps({'ready': True, 'url': f'http://127.0.0.1:{port}/'}), flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['freeze', 'cpu', 'serve', 'audit', 'verify'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--preflight', type=Path)
    parser.add_argument('--coordinates', type=Path); parser.add_argument('--port', type=int, default=8868)
    args = parser.parse_args(); root = args.root.resolve()
    if args.mode == 'freeze': freeze(root, args.preflight.resolve(), args.coordinates.resolve())
    elif args.mode == 'cpu': cpu(root)
    elif args.mode == 'serve': serve(root, args.port)
    else:
        result = reconstruct(root)
        if args.mode == 'verify':
            if result != read(root / 'report.json'): raise ValueError('whole control reconstruction mismatch')
        else: p.new(root / 'report.json', result)
        print(json.dumps({'ok': True, 'fullNonzeroRouteControlPassed': result['fullNonzeroRouteControlPassed'], 'summary': result['summary']}), flush=True)
