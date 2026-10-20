"""完整图汇合观测：先重建原两头字节，再允许分析中间层；不调用CUDA。"""
import argparse
import copy
import importlib.util
import json
import os
import traceback
from pathlib import Path

import numpy as np
import onnx

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('junction_io', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
heads = d.load(HERE / 'export-pretrained-native-candidate-v2.py', 'junction_heads')
boundary = d.load(HERE / 'audit-pretrained-native-boundary.py', 'junction_tensor')


def resources(path):
    p = d.read(d.bind(path))
    assert p['purpose'] == 'full9_partitioned_junction_capture_fidelity'
    assert p['runner'] == d.bind(__file__)
    for ref in [*p['inputs'].values(), p['browserServer'], p['headReader'], p['tensorReader']]:
        d.checked(ref)
    assert p['headReader'] == d.bind(HERE / 'export-pretrained-native-candidate-v2.py')
    assert p['tensorReader'] == d.bind(HERE / 'audit-pretrained-native-boundary.py')
    required = d.read(p['inputs']['requirements'])
    old = d.read(p['inputs']['currentFullReport'])
    oldplan = d.read(old['plan'])
    cuda = d.read(p['inputs']['strictBoundary'])
    isolated = d.read(p['inputs']['isolatedReport'])
    proof = d.read(p['inputs']['observerProof'])
    assert p['cases'] == required['cases'] == oldplan['cases'] == proof['cases']
    assert len(p['cases']) == 9 and [r['ordinal'] for r in p['cases']] == list(range(1, 10))
    assert p['target'] == required['target'] == proof['target']
    assert p['budget'] == {'cpuOrt': 9, 'wasm': 9, 'webgpu': 9, 'cuda': 0, 'exportTrace': 0, 'learned': 0, 'optimizerSteps': 0, 'val': 0, 'protected': 0, 'newChatImages': 0}
    assert p['outputs'] == {'mask': 'mask_logits', 'presence': 'presence_logit', 'boundary': p['target']['output']}
    assert old['all27Inputs54HeadsCompleteFinite'] and not old['independentFullGraphGatePassed']
    assert isolated['partitionOperatorGatePassed'] and isolated['all27CompleteFinite']
    assert p['deviceProbeGrantedLimits'] == oldplan['deviceProbeGrantedLimits']
    graph = onnx.load(d.checked(p['inputs']['onnx']))
    assert [v.name for v in graph.graph.output] == list(p['outputs'].values())
    original = copy.deepcopy(graph)
    del original.graph.output[-1:]
    assert original.SerializeToString() == d.checked(proof['originalFullGraph']).read_bytes()
    assert proof['observerGraph'] == p['inputs']['onnx'] and proof['originalGraphStrippedByteExact']
    assert len(old['records']) == 27 and len(cuda['records']) == 9 and len(isolated['records']) == 27
    oldidx = {(r['backend'], r['ordinal']): r for r in old['records']}
    iso = {(('cpuOrt' if r['backend'] == 'cpu-ort' else r['backend']), r['ordinal']): r for r in isolated['records']}
    expected = {(b, i) for b in ['cpuOrt', 'wasm', 'webgpu'] for i in range(1, 10)}
    assert set(oldidx) == set(iso) == expected
    for c, reference in zip(p['cases'], cuda['records'], strict=True):
        i, h, w = c['ordinal'], c['h'], c['w']
        assert reference['ordinal'] == i and reference['input'] == c['input']
        heads.input_array(c['input'], h, w)
        boundary.tensor(reference['raw']['boundary'], [1, 16, h, w])
        for backend in ['cpuOrt', 'wasm', 'webgpu']:
            assert oldidx[backend, i]['input'] == c['input']
            heads.read_heads(oldidx[backend, i]['raw'], h, w)
            boundary.tensor(iso[backend, i]['raw'], [1, 16, h, w])
    return p, oldidx, cuda, iso


def fidelity(raw, prior):
    return {name: raw[name]['binding']['sha256'] == prior[name]['binding']['sha256'] for name in ['mask', 'presence']}


def cpu(path, root):
    import onnxruntime as ort
    p, prior, _, _ = resources(path)
    ready = d.read(d.bind(path.with_name('readiness.json')))
    assert ready['ok'] and ready['plan'] == d.bind(path)
    root.mkdir(exist_ok=False)
    (root / 'raw').mkdir()
    (root / 'events').mkdir()
    d.new(root / 'attempt.json', {'plan': d.bind(path), 'pid': os.getpid(), 'automaticResumeAllowed': False})
    rows, count = [], 0
    try:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(str(d.checked(p['inputs']['onnx'])), sess_options=options, providers=['CPUExecutionProvider'])
        assert [v.name for v in session.get_outputs()] == list(p['outputs'].values())
        d.new(root / 'environment.json', {'onnxruntime': ort.__version__, 'providers': session.get_providers(), 'intraThreads': 4, 'interThreads': 1, 'graphOptimization': 'disabled'})
        for c in p['cases']:
            i, h, w = c['ordinal'], c['h'], c['w']
            x = heads.input_array(c['input'], h, w)
            d.new(root / 'events' / f'{i:03d}-started.json', {'ordinal': i, 'input': c['input'], 'plan': d.bind(path)})
            count += 1
            out = session.run(list(p['outputs'].values()), {'candidate': x})
            assert len(out) == 3
            raw = heads.save_heads(root / 'raw', f'{i:03d}', out[0], out[1], h, w)
            raw['boundary'] = boundary.save(root / 'raw' / f'{i:03d}-boundary.bin', out[2])
            boundary.tensor(raw['boundary'], [1, 16, h, w])
            row = {'backend': 'cpuOrt', 'ordinal': i, 'input': c['input'], 'raw': raw, 'finalHeadsByteExact': fidelity(raw, prior['cpuOrt', i]['raw'])}
            d.new(root / 'events' / f'{i:03d}-confirmed.json', row)
            rows.append(row)
            del x, out
            print(json.dumps({'cpuJunction': i, 'finalHeadsByteExact': all(row['finalHeadsByteExact'].values())}), flush=True)
        gate = all(all(r['finalHeadsByteExact'].values()) for r in rows)
        d.new(root / 'report.json', {'ok': True, 'plan': d.bind(path), 'records': rows, 'actualInputs': count, 'full9CpuFidelityPassed': gate, 'decision': 'cpu_fidelity_pass_browser_pending' if gate else 'reconstruction_mismatch', 'boundaryAttributionAllowed': False, 'formalReleaseAllowed': False, 'productHold': True})
        d.new(root / 'terminal.json', {'phase': 'closed', 'report': d.bind(root / 'report.json'), 'actualInputs': count})
    except BaseException as error:
        d.new(root / 'failure.json', {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc(), 'startedInputs': count, 'automaticResumeAllowed': False})
        raise


def reconstruct_cpu(path, root):
    p, prior, cuda, iso = resources(path)
    r = d.read(d.bind(root / 'report.json'))
    assert r['plan'] == d.bind(path) and len(r['records']) == r['actualInputs'] == 9
    assert d.read(d.bind(root / 'terminal.json')) == {'phase': 'closed', 'report': d.bind(root / 'report.json'), 'actualInputs': 9}
    assert len(list((root / 'raw').glob('*.bin'))) == 27 and len(list((root / 'events').glob('*.json'))) == 18
    for c, row in zip(p['cases'], r['records'], strict=True):
        i, h, w = c['ordinal'], c['h'], c['w']
        assert row['backend'] == 'cpuOrt' and row['ordinal'] == i and row['input'] == c['input']
        heads.read_heads(row['raw'], h, w)
        boundary.tensor(row['raw']['boundary'], [1, 16, h, w])
        assert row['finalHeadsByteExact'] == fidelity(row['raw'], prior['cpuOrt', i]['raw'])
        assert d.read(d.bind(root / 'events' / f'{i:03d}-confirmed.json')) == row
        assert d.read(d.bind(root / 'events' / f'{i:03d}-started.json')) == {'ordinal': i, 'input': c['input'], 'plan': d.bind(path)}
    assert r['full9CpuFidelityPassed'] == all(all(row['finalHeadsByteExact'].values()) for row in r['records'])
    return p, prior, cuda, iso, r


def write(path, value):
    if path.exists():
        assert d.read(d.bind(path)) == value, 'immutable replay drift'
    else:
        d.new(path, value)


def verify_cpu(path, root, output):
    p, _, _, _, r = reconstruct_cpu(path, root)
    write(output, {'ok': True, 'reader': d.bind(__file__), 'plan': d.bind(path), 'cpuReport': d.bind(root / 'report.json'), 'full9CpuFidelityPassed': r['full9CpuFidelityPassed'], 'all27CpuArraysAnd18EventsReplayed': True, 'newModelInputs': 0, 'boundaryAttributionAllowed': False, 'productHold': True})
    print(json.dumps({'ok': True, 'full9CpuFidelityPassed': r['full9CpuFidelityPassed'], 'newModelInputs': 0}), flush=True)


def verify(path, root, output):
    p, prior, cuda, iso, cr = reconstruct_cpu(path, root / 'cpu')
    br = root / 'browser'
    bp = d.read(d.bind(br / 'plan.json'))
    live = d.read(d.bind(br / 'capture/live-browser.json'))
    claim = d.read(d.bind(br / 'claim.json'))
    expected = [(b, i) for b in ['wasm', 'webgpu'] for i in range(1, 10)]
    assert bp['operatorPlan'] == d.bind(path) and bp['server'] == p['browserServer'] and bp['scope'] == 'main'
    assert live['phase'] == 'closed' and not live['errors'] and not live['virtualTime'] and live['crossOriginIsolated']
    assert live['planSha256'] == d.bind(br / 'plan.json')['sha256'] and live['claim'] == claim['claim']
    assert live['userAgent'] == bp['expectedUserAgent'] and live['adapterInfo'] == bp['expectedAdapter']
    assert live['webgpuDevice']['grantedLimits'] == p['deviceProbeGrantedLimits']
    assert [(r['backend'], r['ordinal']) for r in live['records']] == expected
    assert [(r['backend'], r['ordinal']) for r in live['started']] == expected
    assert len(list((br / 'started').glob('*.json'))) == 18 and len(list((br / 'capture').glob('*.bin'))) == 54
    rows = list(cr['records'])
    for row in live['records']:
        b, i = row['backend'], row['ordinal']
        c = p['cases'][i-1]
        h, w = c['h'], c['w']
        rid = claim['claim']+'-'+b+'-'+str(i)
        assert row['requestId'] == rid
        assert d.read(d.bind(br / 'started' / f'{b}-{i}.json')) == {'claim': claim['claim'], 'requestId': rid, 'backend': b, 'ordinal': i, 'h': h, 'w': w, 'inputSha256': c['input']['sha256']}
        raw = {}
        for name, shape in [('mask', [1, 1, h, w]), ('presence', [1, 1]), ('boundary', [1, 16, h, w])]:
            file = br / 'capture' / f'{b}-{i}-{name}.bin'
            ref = {'binding': d.bind(file), 'shape': shape, 'dtype': 'float32', 'bytes': file.stat().st_size}
            assert row['outputs'][name] == {'shape': shape, 'dtype': 'float32', 'sha256': ref['binding']['sha256'], 'bytes': ref['bytes']}
            boundary.tensor(ref, shape)
            raw[name] = ref
        rows.append({'backend': b, 'ordinal': i, 'input': c['input'], 'raw': raw, 'finalHeadsByteExact': fidelity(raw, prior[b, i]['raw'])})
    files = [br / 'claim.json', *sorted((br / 'started').glob('*.json')), *sorted((br / 'capture').glob('*'))]
    events = [d.read(d.bind(f)) for f in (br / 'http-events').glob('*.json')]
    ids = set()
    for file in files:
        meta = d.read(d.bind(br / 'metadata' / f'{file.parent.name}-{file.name}.json'))
        hits = [e for e in events if e['requestId'] == meta['requestId']]
        route = '/claim' if file.name == 'claim.json' else '/started/'+file.stem.replace('-', '/') if file.parent.name == 'started' else '/capture/'+file.name
        assert 1 <= len(hits) <= 2 and meta['sha256'] == d.bind(file)['sha256'] and meta['bytes'] == file.stat().st_size
        assert all(e['declaredSha256'] == meta['sha256'] and e['declaredBytes'] == meta['bytes'] and e['path'] == route for e in hits)
        ids.add(meta['requestId'])
    assert len(files) == 74 and ids == {e['requestId'] for e in events} and len(rows) == 27
    gate = all(all(r['finalHeadsByteExact'].values()) for r in rows)
    # 全27输入、81 RAW与原54最终头通过后才计算层差；失败报告不泄露局部归因。
    comparison = []
    if gate:
        for row in rows:
            b, i = row['backend'], row['ordinal']
            c = p['cases'][i-1]
            shape = [1, 16, c['h'], c['w']]
            actual = boundary.tensor(row['raw']['boundary'], shape)
            strict = boundary.tensor(cuda['records'][i-1]['raw']['boundary'], shape)
            isolated = boundary.tensor(iso[b, i]['raw'], shape)
            delta = np.abs(actual-strict)
            comparison.append({'backend': b, 'ordinal': i, 'maxAbsoluteDifferenceFromStrictCuda': float(delta.max()), 'valuesAbove1e4': int((delta > 1e-4).sum()), 'values': int(delta.size), 'maxAbsoluteDifferenceFromIsolatedSameBackend': float(np.abs(actual-isolated).max()), 'sameBackendIsolatedByteExact': row['raw']['boundary']['binding']['sha256'] == iso[b, i]['raw']['binding']['sha256']})
    summary = {b: {'inputs': len(rr), 'finalHeadFidelityPassed': sum(all(r['finalHeadsByteExact'].values()) for r in rr)} for b in ['cpuOrt', 'wasm', 'webgpu'] for rr in [[r for r in rows if r['backend'] == b]]}
    result = {'ok': True, 'decision': 'full27_fidelity_pass_boundary_observable' if gate else 'reconstruction_mismatch', 'reader': d.bind(__file__), 'plan': d.bind(path), 'cpuReport': d.bind(root / 'cpu/report.json'), 'browserPlan': d.bind(br / 'plan.json'), 'browserLive': d.bind(br / 'capture/live-browser.json'), 'records': rows, 'summary': summary, 'all27Inputs81TensorsFiniteComplete': True, 'all54OriginalFinalHeadsByteExact': gate, 'boundaryAttributionAllowed': gate, 'boundaryComparisons': comparison, 'httpAttempts': len(events), 'uniquePayloads': len(files), 'actualNetworkBytes': None, 'newModelInputs': 0, 'learnedInputs': 0, 'formalReleaseAllowed': False, 'productHold': True}
    write(output, result)
    print(json.dumps({'ok': True, 'decision': result['decision'], 'summary': summary, 'boundaryComparisons': comparison}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['cpu', 'verify-cpu', 'verify'])
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'cpu':
        cpu(args.plan.resolve(), args.root.resolve())
    elif args.mode == 'verify-cpu':
        verify_cpu(args.plan.resolve(), args.root.resolve(), args.output.resolve())
    else:
        verify(args.plan.resolve(), args.root.resolve(), args.output.resolve())
