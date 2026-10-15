"""保存头的原图整数逆映射：完整源真值、真实浏览器画布及无模型独立重放。"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


d = module(HERE / 'reviewed-role-development-data.py', 'canvas_data')


def require(ok, message):
    if not ok:
        raise ValueError('reconstruction_mismatch: ' + message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(ref):
    path = Path(ref['path'])
    require(digest(path.read_bytes()) == ref['sha256'], 'bound bytes ' + str(path))
    return path


def canvas(logits, presence, size, box):
    width, height = size
    x0, y0, x1, y1 = box
    require(all(type(v) is int for v in [width, height, x0, y0, x1, y1]) and
            0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, 'integer geometry')
    require(logits.dtype == np.float32 and logits.shape == (y1-y0, x1-x0) and
            np.isfinite(logits).all() and np.isfinite(presence), 'finite full native heads')
    output = np.zeros((height, width), bool)
    if presence >= 0:
        output[y0:y1, x0:x1] = logits >= 0
    return output


def pack(pixels):
    return np.packbits(pixels.reshape(-1), bitorder='little').tobytes()


def unpack(raw, size):
    count = size[0] * size[1]
    require(len(raw) == (count+7)//8, 'full packed canvas length')
    bits = np.unpackbits(np.frombuffer(raw, np.uint8), bitorder='little')
    require(not bits[count:].any(), 'zero unused tail bits')
    return bits[:count].astype(bool).reshape(size[1], size[0])


def heads(pair, shape):
    mask = np.fromfile(checked(pair['mask']), dtype='<f4')
    presence = np.fromfile(checked(pair['presence']), dtype='<f4')
    require(pair['mask']['dtype'] == pair['presence']['dtype'] == 'float32' and
            pair['mask']['shape'] == [1, 1, *shape] and pair['presence']['shape'] == [1, 1] and
            mask.size == shape[0]*shape[1] and presence.size == 1 and
            np.isfinite(mask).all() and np.isfinite(presence).all(), 'all head shapes and finite values')
    return mask.reshape(shape), float(presence[0])


def controls():
    # 独立字面量位置，不以逆映射实现生成控制真值；35/15像素覆盖非整字节尾部。
    return [
        {'key': 'control-right-nonsquare', 'control': True, 'sourceSize': [7, 5],
         'cropBox': [3, 1, 7, 4], 'nativeSize': [3, 4], 'presence': 0,
         'logits': [0, 0, -1, 1, -2, 2, -3, 3, 1, -1, 0, 0],
         'expectedIndices': [10, 11, 13, 18, 20, 24, 26, 27]},
        {'key': 'control-top-left', 'control': True, 'sourceSize': [5, 3],
         'cropBox': [0, 0, 2, 3], 'nativeSize': [3, 2], 'presence': 1,
         'logits': [1, -1, -1, 1, 0, -2], 'expectedIndices': [0, 6, 10]},
        {'key': 'control-reject-only-candidate', 'control': True, 'sourceSize': [7, 5],
         'cropBox': [3, 1, 7, 4], 'nativeSize': [3, 4], 'presence': -1e-30,
         'logits': [1]*12, 'expectedIndices': []}]


def quality(case, pixels, presence, truth, metric):
    base = {'candidateIdentity': case['candidateIdentity'], 'positive': case['positive'],
            'presenceAccepted': bool(presence >= 0)}
    if not case['positive']:
        return {**base, 'outputPixels': int(pixels.sum()), 'rejected': not pixels.any(),
                'meaning': 'same_candidate_not_empty_rgb'}
    iou = int((pixels & truth).sum()) / max(1, int((pixels | truth).sum()))
    b = metric.boundary_stats(truth, pixels, 2)
    return {**base, 'iou': iou, **b, 'originalSourceSize': case['sourceSize'],
            'jointPass': iou >= .75 and b['boundaryIoU'] >= .75 and b['boundaryF1'] >= .9}


def reconstruct(root, replay=False):
    execution = json.loads((root/'execution.json').read_bytes())
    for ref in execution['sources'].values():
        checked(ref)
    scope = d.read(execution['design'])
    require(scope['purpose'] == 'complete74_original_coordinate_quality_roundtrip_design_only' and
            len(scope['cases']) == 74 and all(scope[k] == 0 for k in
            ['modelInputsAllowed', 'trainingOrAutogradAllowed', 'internalValInputsAllowed', 'protectedInputsAllowed']), 'zero neural input full scope')
    require(d.read(scope['nativeLearnedGate'])['fullLearnedRouteGatePassed'], 'actual learned native gate')
    data = d.read(scope['materialization'])
    materializer = module(HERE/'materialize-reviewed-stage-b-train-inputs.py', 'canvas_materializer')
    e, plan, sources, _, cleanup = materializer.resources(data['execution'])
    guard = d.load(d.checked(plan['inputs']['readOnlyGuard']), 'canvas_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        # 原权威物化完整重建，不靠只读标记宣称源数据保真。
        materializer.build(data['execution'], Path(scope['materialization']['path']).parent, replay=True)
        reader = module(d.checked(e['sources']['truthReader']), 'canvas_truth_reader')
        metric = module(d.checked(plan['inputs']['roiHelper']), 'canvas_boundary_metric')
        normal = module(HERE/'train-reviewed-stage-b-normal-development.py', 'canvas_quality_summary')
        truth_index = {d.key(s['identity']): (s, reader.truths(s)) for s in sources}
        training = d.read(execution['training'])
        require(len(data['records']) == len(training['perCandidate']) == 74, 'all native/training rows')
        results = []; strict_quality = []; seen = set(); actual_quality = {b: [] for b in ['cpu', 'wasm', 'webgpu']}
        for case, row, old_quality in zip(scope['cases'], data['records'], training['perCandidate'], strict=True):
            require(case['ordinal'] == len(results)+1 and case['candidateIdentity'] == row['candidateIdentity'] and
                    case['candidateIdentity']['identity']['split'] == row['split'] == 'train' and
                    case['cropBox'] == row['cropBox'] and case['positive'] == row['presenceTarget'] and
                    case['sourceGroup'] == row['sourceGroup'] and case['target'] == row['target'] and
                    case['targetImage'] == row['paths']['nativeTarget'] and
                    case['nativeSize'] == row['nativeSize'][::-1], 'stable candidate/geometry/target/role')
            source, truths = truth_index[d.key(case['candidateIdentity']['identity'])]
            require(source['size'] == case['sourceSize'] and
                    all(hit['role'] == 'developmentTrain' for hit in source['parentRoleMatches']), 'source and parent protection')
            if case['positive']:
                key = (d.key(source['identity']), case['target']['truthIndex'])
                require(key not in seen, 'one-to-one full truth assignment'); seen.add(key)
                truth = truths[case['target']['truthIndex']-1]
                require(digest(truth.tobytes()) == case['target']['truthMaskSha256'], 'original full truth bytes')
            else:
                truth = np.zeros((source['size'][1], source['size'][0]), bool)
            native_truth = materializer.image_array(checked(case['targetImage']), 'L') > 0
            x0, y0, x1, y1 = case['cropBox']
            full_truth = np.zeros_like(truth); full_truth[y0:y1, x0:x1] = native_truth
            require(np.array_equal(full_truth, truth), 'complete original truth not truncated')
            a, p = heads(case['strictLearnedReference'], case['nativeSize'])
            strict = canvas(a, p, case['sourceSize'], case['cropBox'])
            q = quality(case, strict, p, truth, metric)
            require(q == old_quality, 'full original strict quality identical to frozen training')
            strict_quality.append(q)
            packed = pack(strict); path = root/'references'/f'{case["ordinal"]:03d}.bits'
            if replay:
                require(path.read_bytes() == packed, 'strict canvas reference bytes')
            else:
                with path.open('xb') as stream:
                    stream.write(packed); stream.flush(); os.fsync(stream.fileno())
            records = {}
            for backend, pair in case['actual'].items():
                a, p = heads(pair, case['nativeSize']); predicted = canvas(a, p, case['sourceSize'], case['cropBox'])
                require(np.array_equal(predicted, strict), 'all actual saved heads original pixel zero difference')
                bq = quality(case, predicted, p, truth, metric)
                require(bq == q, 'all backend original quality identical')
                actual_quality[backend].append(bq)
                records[backend] = {'quality': bq, 'pixelDifferences': 0}
            results.append({'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'],
                            'sourceSize': case['sourceSize'], 'strictQuality': q,
                            'reference': d.bind(path), 'pixelSha256': digest(strict.astype(np.uint8).tobytes()),
                            'outputPixels': int(strict.sum()), 'actual': records})
        require(len(seen) == sum(s['maskCount'] for s in sources) == data['fullTruthDenominator'] == 71,
                'entire source truth denominator no missing positives')
        metrics, passed = normal.summarize(strict_quality)
        require(metrics == training['metrics'] and passed == training['trainQualityGatePassed'], 'full frozen quality metrics')
        result = {'ok': True, 'execution': d.bind(root/'execution.json'), 'cases': results, 'metrics': metrics,
                  'trainQualityGatePassed': passed, 'sourceCount': len(sources),
                  'sourceGroups': len({s['sourceGroup'] for s in sources}), 'positiveTruthCount': len(seen),
                  'packing': 'row-major bool; little bitorder; exact ceil(W*H/8); unused tail bits zero',
                  'backends': {b: normal.summarize(q)[0] for b, q in actual_quality.items()},
                  'newModelCalls': 0, 'formalReleaseAllowed': False, 'productHold': True}
        if replay:
            require(d.raw(result) == (root/'python-report.json').read_bytes(), 'independent complete Python replay')
        else:
            d.new(root/'python-report.json', result)
        return result
    finally:
        for path in cleanup:
            guard.remove_ultralytics_label_caches(Path(path))


def prepare(design, training, root):
    require(root.is_relative_to(ROOT/'model/reviews'), 'new isolated output root')
    root.mkdir(exist_ok=False)
    for name in ['references', 'events', 'browser']:
        (root/name).mkdir()
    paths = [Path(__file__), HERE/'reviewed-role-development-data.py', HERE/'materialize-reviewed-stage-b-train-inputs.py',
             HERE/'train-reviewed-stage-b-normal-development.py', ROOT/'model/runtime/native-canvas-roundtrip.mjs',
             ROOT/'model/runtime/browser-native-canvas-roundtrip.mjs']
    execution = {'purpose': 'full_original_canvas_saved_heads_only', 'design': d.bind(design), 'training': d.bind(training),
                 'sources': {p.relative_to(ROOT).as_posix(): d.bind(p) for p in paths},
                 'controls': controls(), 'browserTransformations': 222, 'modelInputs': 0,
                 'trainingInputs': 0, 'internalValInputs': 0, 'protectedInputs': 0, 'restartAllowed': False}
    d.new(root/'execution.json', execution)
    try:
        result = reconstruct(root)
        print(json.dumps({'ok': True, 'pythonCandidates': len(result['cases']), 'metrics': result['metrics']}), flush=True)
    except BaseException as error:
        d.new(root/'prepare-failure.json', {'ok': False, 'error': repr(error), 'newModelCalls': 0})
        raise


def manifest(root):
    execution = json.loads((root/'execution.json').read_bytes())
    for ref in execution['sources'].values():
        checked(ref)
    scope = d.read(execution['design']); files = []; items = execution['controls'].copy()
    for backend in ['cpu', 'wasm', 'webgpu']:
        for case in scope['cases']:
            pair = {}
            for name, ref in case['actual'][backend].items():
                checked(ref); pair[name] = {**ref, 'id': len(files)}; files.append(ref)
            items.append({'key': f'{backend}-{case["ordinal"]}', 'control': False,
                          **{k: case[k] for k in ['sourceSize', 'cropBox', 'nativeSize']}, 'heads': pair})
    require(len(items) == 225, 'three independent controls before all 222 saved transforms')
    return {'items': items}, files


def expected(root, item):
    if item['control']:
        pixels = np.zeros(item['sourceSize'][0]*item['sourceSize'][1], bool)
        pixels[item['expectedIndices']] = True
        return pixels.reshape(item['sourceSize'][1], item['sourceSize'][0])
    ordinal = int(item['key'].split('-')[1])
    return unpack((root/'references'/f'{ordinal:03d}.bits').read_bytes(), item['sourceSize'])


def audit(root, write=False):
    python = reconstruct(root, replay=True)
    items = manifest(root)[0]['items']
    claim = json.loads((root/'claim.json').read_bytes())
    terminal = json.loads((root/'browser-complete.json').read_bytes())
    require(terminal == {'page': claim['page'], 'sequence': len(items)}, 'full terminal')
    require(len(list((root/'events').glob('*.json'))) == 2*len(items) and
            len(list((root/'browser').glob('*.bits'))) == len(items), 'complete event/capture denominator')
    results = []
    for sequence, item in enumerate(items, 1):
        start = json.loads((root/'events'/f'{sequence:03d}-start.json').read_bytes())
        done = json.loads((root/'events'/f'{sequence:03d}-done.json').read_bytes())
        require(start == {k: done[k] for k in ['sequence', 'key', 'page', 'requestId']} and
                start['sequence'] == sequence and start['key'] == item['key'] and start['page'] == claim['page'], 'exact event identity/order')
        raw = (root/'browser'/f'{sequence:03d}.bits').read_bytes()
        actual = unpack(raw, item['sourceSize']); reference = expected(root, item)
        require(np.array_equal(actual, reference) and raw == pack(reference), 'full canvas zero pixel differences')
        require(done['pixelSha256'] == digest(actual.astype(np.uint8).tobytes()) and
                done['packedSha256'] == digest(raw) and done['outputPixels'] == int(actual.sum()) and
                done['sourceSize'] == item['sourceSize'], 'actual full canvas/raw and metadata')
        if item['control']:
            presence = item['presence']
        else:
            presence = float(np.fromfile(checked(item['heads']['presence']), dtype='<f4')[0])
        require(done['presenceAccepted'] == (presence >= 0), 'original presence decision')
        results.append({'key': item['key'], 'pixelDifferences': 0,
                        'capture': d.bind(root/'browser'/f'{sequence:03d}.bits'), 'pixelSha256': done['pixelSha256']})
    result = {'ok': True, 'decision': 'train_only_original_canvas_roundtrip_complete',
              'pythonReplay': d.bind(root/'python-report.json'), 'browserClaim': d.bind(root/'claim.json'),
              'controlsPassed': 3, 'browserSavedOutputCases': 222, 'originalPixelDifferences': 0,
              'metrics': python['metrics'], 'results': results, 'newModelCalls': 0,
              'internalValInputs': 0, 'protectedInputs': 0, 'formalReleaseAllowed': False, 'productHold': True}
    if write:
        d.new(root/'report.json', result)
    else:
        require(d.raw(result) == (root/'report.json').read_bytes(), 'complete independent browser and quality report')
    return result


def serve(root, port):
    require(not (root/'claim.json').exists(), 'page already claimed; do not restart')
    data, files = manifest(root)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, raw, kind='application/json', code=200):
            self.send_response(code); self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(raw))); self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(raw)

        def do_GET(self):
            try:
                if self.path == '/':
                    self.send(b'<title>Original canvas saved-output replay</title><button>Run full saved-output canvas replay</button><p id="status">ready; model inputs 0</p><script type="module" src="/browser-native-canvas-roundtrip.mjs"></script>', 'text/html')
                elif self.path == '/manifest':
                    self.send(d.raw(data))
                elif self.path.startswith('/raw/'):
                    self.send(checked(files[int(self.path[5:])]).read_bytes(), 'application/octet-stream')
                elif self.path in ['/native-canvas-roundtrip.mjs', '/browser-native-canvas-roundtrip.mjs']:
                    name = 'model/runtime'+self.path
                    ref = json.loads((root/'execution.json').read_bytes())['sources'][name]
                    self.send(checked(ref).read_bytes(), 'text/javascript')
                else:
                    self.send(b'{}', code=404)
            except Exception as error:
                self.send(d.raw({'ok': False, 'error': str(error)}), code=400)

        def do_POST(self):
            try:
                length = int(self.headers['Content-Length'])
                require(0 < length < 4_000_000, 'bounded exact payload')
                body = json.loads(self.rfile.read(length))
                with lock:
                    if self.path == '/claim':
                        path = root/'claim.json'
                    elif self.path == '/finish':
                        require(body == {'page': json.loads((root/'claim.json').read_bytes())['page'], 'sequence': 225}, 'full finish')
                        require((root/'events/225-done.json').exists(), 'all actual cases captured')
                        path = root/'browser-complete.json'
                    else:
                        require(self.path in ['/start', '/done'], 'known action')
                        n = body['sequence']; require(type(n) is int and 1 <= n <= 225, 'ordered sequence')
                        require(body['key'] == data['items'][n-1]['key'] and body['page'] == json.loads((root/'claim.json').read_bytes())['page'], 'single page exact item')
                        if n > 1:
                            require((root/'events'/f'{n-1:03d}-done.json').exists(), 'previous complete before next start')
                        path = root/'events'/f'{n:03d}-{self.path[1:]}.json'
                        if self.path == '/done':
                            require(json.loads((root/'events'/f'{n:03d}-start.json').read_bytes()) ==
                                    {k: body[k] for k in ['sequence', 'key', 'page', 'requestId']}, 'same unique start before decode')
                            raw = base64.b64decode(body['packed'], validate=True)
                            require(digest(raw) == body['packedSha256'], 'captured packed SHA')
                            capture = root/'browser'/f'{n:03d}.bits'
                            if capture.exists():
                                require(capture.read_bytes() == raw, 'ACK retry exact saved bytes')
                            else:
                                with capture.open('xb') as stream:
                                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                            del body['packed']
                            item = data['items'][n-1]
                            actual = unpack(raw, item['sourceSize'])
                            require(np.array_equal(actual, expected(root, item)) and
                                    body['pixelSha256'] == digest(actual.astype(np.uint8).tobytes()) and
                                    body['sourceSize'] == item['sourceSize'] and body['outputPixels'] == int(actual.sum()),
                                    'independent full-pixel gate before next case')
                    if path.exists():
                        require(json.loads(path.read_bytes()) == body, 'same-body ACK only')
                    else:
                        d.new(path, body)
                self.send(d.raw({'ok': True}))
            except Exception as error:
                self.send(d.raw({'ok': False, 'error': str(error)}), code=400)

    print(json.dumps({'listening': port, 'modelInputs': 0, 'items': len(data['items'])}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'serve', 'audit', 'verify'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--design', type=Path)
    parser.add_argument('--training', type=Path)
    parser.add_argument('--port', type=int, default=8870)
    args = parser.parse_args(); root = args.root.resolve()
    if args.mode == 'prepare':
        prepare(args.design.resolve(), args.training.resolve(), root)
    elif args.mode == 'serve':
        serve(root, args.port)
    else:
        report = audit(root, write=args.mode == 'audit')
        print(json.dumps({k: report[k] for k in ['ok', 'decision', 'controlsPassed', 'browserSavedOutputCases', 'originalPixelDifferences', 'metrics', 'newModelCalls']}), flush=True)
