"""首编码块五输出捕获；完整最终头保真门先于层差解释。"""
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
s = importlib.util.spec_from_file_location('firstblock_io', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s)
s.loader.exec_module(d)
heads = d.load(HERE / 'export-pretrained-native-candidate-v2.py', 'firstblock_heads')
tensor = d.load(HERE / 'audit-pretrained-native-boundary.py', 'firstblock_tensor')
LABELS = ['encoder1', 'encoder2', 'encoder3']


def resources(path):
    p = d.read(d.bind(path))
    assert p['purpose'] == 'full9_encoder_five_outputs_fidelity'
    assert p['runner'] == d.bind(__file__)
    for ref in [*p['inputs'].values(), *p['modelSources'].values(), p['browserServer'], p['headReader'], p['tensorReader']]:
        d.checked(ref)
    assert p['headReader'] == d.bind(HERE / 'export-pretrained-native-candidate-v2.py')
    assert p['tensorReader'] == d.bind(HERE / 'audit-pretrained-native-boundary.py')
    req = d.read(p['inputs']['requirements'])
    proof = d.read(p['inputs']['observerProof'])
    old = d.read(p['inputs']['currentFullReport'])
    oldplan = d.read(old['plan'])
    strict = d.read(p['inputs']['originalCuda'])
    assert p['cases'] == req['cases'] == oldplan['cases']
    assert len(p['cases']) == 9 and [c['ordinal'] for c in p['cases']] == list(range(1, 10))
    assert p['targets'] == req['targets'] == proof['targets']
    assert [t['label'] for t in p['targets']] == LABELS
    assert p['outputs'] == {'mask': 'mask_logits', 'presence': 'presence_logit', **{t['label']: t['output'] for t in p['targets']}}
    assert p['budget'] == dict(cuda=9, cpuOrt=9, wasm=9, webgpu=9, exportTrace=0, learned=0, optimizerSteps=0, val=0, protected=0, newChatImages=0)
    assert p['deviceProbeGrantedLimits'] == oldplan['deviceProbeGrantedLimits']
    g = onnx.load(d.checked(p['inputs']['onnx']))
    assert [v.name for v in g.graph.output] == list(p['outputs'].values())
    original = copy.deepcopy(g)
    del original.graph.output[-3:]
    assert original.SerializeToString() == d.checked(proof['originalGraph']).read_bytes()
    assert proof['allThreeOutputsStripRestoresOriginalGraphBytes'] and p['inputs']['onnx'] == proof['observerGraph']
    assert old['all27Inputs54HeadsCompleteFinite'] and not old['independentFullGraphGatePassed']
    prior = {(r['backend'], r['ordinal']): r for r in old['records']}
    assert len(prior) == 27 and set(prior) == {(b, i) for b in ['cpuOrt', 'wasm', 'webgpu'] for i in range(1, 10)}
    assert len(strict['records']) == 9
    for c, r in zip(p['cases'], strict['records'], strict=True):
        i, h, w = c['ordinal'], c['h'], c['w']
        assert r['ordinal'] == i and r['input'] == c['input']
        heads.input_array(c['input'], h, w)
        heads.read_heads(r['captures']['cuda'], h, w)
        for b in ['cpuOrt', 'wasm', 'webgpu']:
            assert prior[b, i]['input'] == c['input']
            heads.read_heads(prior[b, i]['raw'], h, w)
    return p, prior, strict


def fidelity(raw, prior):
    return {k: raw[k]['binding']['sha256'] == prior[k]['binding']['sha256'] for k in ['mask', 'presence']}


def shapes(c):
    return {'mask': [1, 1, c['h'], c['w']], 'presence': [1, 1], **{k: [1, 16*(2**i), c['h']//(2**i), c['w']//(2**i)] for i,k in enumerate(LABELS)}}


def capture(path, root, backend):
    p, prior, strict = resources(path)
    ready = d.read(d.bind(path.with_name('readiness.json')))
    assert ready['ok'] and ready['plan'] == d.bind(path)
    root.mkdir(exist_ok=False)
    (root / 'raw').mkdir()
    (root / 'events').mkdir()
    d.new(root / 'attempt.json', dict(plan=d.bind(path), backend=backend, pid=os.getpid(), automaticResumeAllowed=False))
    count, rows, handles, held = 0, [], [], {}
    try:
        if backend == 'cuda':
            import torch
            model, _, state = heads.model_from_plan(d.read(p['inputs']['constructorPlan']), p['inputs']['independentWeights'])
            model = model.cuda().eval().requires_grad_(False)
            torch.set_num_threads(4)
            torch.set_float32_matmul_precision('highest')
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.cuda.reset_peak_memory_stats()
            before = heads.digest(state)
            def hook(label):
                def store(module, args, output):
                    if label in held:
                        raise ValueError('duplicate boundary invocation')
                    held[label] = output.detach()
                return store
            for t in p['targets']:
                handles.append(model.get_submodule(t['cudaModule']).register_forward_hook(hook(t['label'])))
            environment = dict(torch=torch.__version__, threadsAfterDevice=torch.get_num_threads(), float32Matmul=torch.get_float32_matmul_precision(), cudaTF32=False, cudnnTF32=False, autocast=False)
        else:
            import onnxruntime as ort
            o = ort.SessionOptions()
            o.intra_op_num_threads = 4
            o.inter_op_num_threads = 1
            o.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
            o.log_severity_level = 3
            session = ort.InferenceSession(str(d.checked(p['inputs']['onnx'])), sess_options=o, providers=['CPUExecutionProvider'])
            assert [v.name for v in session.get_outputs()] == list(p['outputs'].values())
            environment = dict(onnxruntime=ort.__version__, providers=session.get_providers(), intraThreads=session.get_session_options().intra_op_num_threads, interThreads=session.get_session_options().inter_op_num_threads, graphOptimization='disabled')
        d.new(root / 'environment.json', environment)
        for c in p['cases']:
            i, h, w = c['ordinal'], c['h'], c['w']
            x = heads.input_array(c['input'], h, w)
            if backend == 'cuda':
                x = torch.from_numpy(x).cuda()
                held.clear()
            d.new(root / 'events' / f'{i:03d}-started.json', dict(backend=backend, ordinal=i, input=c['input'], plan=d.bind(path)))
            count += 1
            if backend == 'cuda':
                with torch.inference_mode(), torch.autocast('cuda', enabled=False):
                    a, b = model(x)
                raw = heads.save_heads(root / 'raw', f'{i:03d}', a, b, h, w)
                assert set(held) == set(LABELS)
                for label in LABELS:
                    raw[label] = tensor.save(root / 'raw' / f'{i:03d}-{label}.bin', held[label].cpu().numpy())
                baseline = strict['records'][i-1]['captures']['cuda']
            else:
                out = session.run(list(p['outputs'].values()), {'candidate': x})
                assert len(out) == 5
                raw = heads.save_heads(root / 'raw', f'{i:03d}', out[0], out[1], h, w)
                for label, value in zip(LABELS, out[2:], strict=True):
                    raw[label] = tensor.save(root / 'raw' / f'{i:03d}-{label}.bin', value)
                baseline = prior[backend, i]['raw']
            for label, shape in shapes(c).items():
                tensor.tensor(raw[label], shape)
            row = dict(backend=backend, ordinal=i, input=c['input'], raw=raw, finalHeadsByteExact=fidelity(raw, baseline))
            d.new(root / 'events' / f'{i:03d}-confirmed.json', row)
            rows.append(row)
            if backend == 'cuda' and torch.cuda.max_memory_allocated() > p['resources']['maxCudaAllocatedBytes']:
                raise MemoryError('fixed CUDA allocated guard')
            print(json.dumps(dict(backend=backend, confirmed=i, finalHeadsByteExact=all(row['finalHeadsByteExact'].values()))), flush=True)
            del x
            if backend == 'cuda':
                held.clear()
                del a, b
            else:
                del out
        extra = {}
        if backend == 'cuda':
            assert heads.digest(model.state_dict()) == before
            extra = dict(stateTensorHashes=before, allStateUnchanged=True, peakCudaAllocatedBytes=torch.cuda.max_memory_allocated())
        gate = all(all(r['finalHeadsByteExact'].values()) for r in rows)
        result = dict(ok=True, plan=d.bind(path), records=rows, actualInputs=count, full9FidelityPassed=gate, decision='full9_fidelity_pass' if gate else 'reconstruction_mismatch', boundaryAttributionAllowed=False, formalReleaseAllowed=False, productHold=True, **extra)
        d.new(root / 'report.json', result)
        d.new(root / 'terminal.json', dict(phase='closed', report=d.bind(root / 'report.json'), actualInputs=count))
    except BaseException as error:
        d.new(root / 'failure.json', dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc(), startedInputs=count, automaticResumeAllowed=False))
        d.new(root / 'terminal.json', dict(phase='failed', failure=d.bind(root / 'failure.json'), startedInputs=count))
        raise
    finally:
        for handle in handles:
            handle.remove()


def reconstruct(path, root, backend):
    p, prior, strict = resources(path)
    r = d.read(d.bind(root / 'report.json'))
    assert r['plan'] == d.bind(path) and len(r['records']) == r['actualInputs'] == 9
    assert d.read(d.bind(root / 'terminal.json')) == dict(phase='closed', report=d.bind(root / 'report.json'), actualInputs=9)
    assert len(list((root / 'raw').glob('*.bin'))) == 45 and len(list((root / 'events').glob('*.json'))) == 18
    for c, row in zip(p['cases'], r['records'], strict=True):
        i = c['ordinal']
        assert row['backend'] == backend and row['ordinal'] == i and row['input'] == c['input']
        assert list(row['raw']) == list(p['outputs'])
        for label, shape in shapes(c).items():
            tensor.tensor(row['raw'][label], shape)
        baseline = strict['records'][i-1]['captures']['cuda'] if backend == 'cuda' else prior[backend, i]['raw']
        assert row['finalHeadsByteExact'] == fidelity(row['raw'], baseline)
        assert d.read(d.bind(root / 'events' / f'{i:03d}-confirmed.json')) == row
        assert d.read(d.bind(root / 'events' / f'{i:03d}-started.json')) == dict(backend=backend, ordinal=i, input=c['input'], plan=d.bind(path))
    assert r['full9FidelityPassed'] == all(all(row['finalHeadsByteExact'].values()) for row in r['records'])
    env = d.read(d.bind(root / 'environment.json'))
    if backend == 'cuda':
        assert env['threadsAfterDevice'] == 4 and env['float32Matmul'] == 'highest' and not env['cudaTF32'] and not env['cudnnTF32'] and not env['autocast']
        assert r['allStateUnchanged'] and len(r['stateTensorHashes']) == 300 and r['peakCudaAllocatedBytes'] <= p['resources']['maxCudaAllocatedBytes']
    else:
        assert env['intraThreads'] == 4 and env['interThreads'] == 1 and env['providers'] == ['CPUExecutionProvider']
    return p, prior, r


def write(path, value):
    if path.exists():
        assert d.read(d.bind(path)) == value, 'immutable replay drift'
    else:
        d.new(path, value)


def verify_single(path, root, backend, output):
    _, _, r = reconstruct(path, root, backend)
    result = dict(ok=True, reader=d.bind(__file__), plan=d.bind(path), report=d.bind(root / 'report.json'), full9FidelityPassed=r['full9FidelityPassed'], all45Raw18EventsReplayed=True, newModelInputs=0, formalReleaseAllowed=False, productHold=True)
    if backend == 'cpuOrt':
        result['full9CpuFidelityPassed'] = r['full9FidelityPassed']
    write(output, result)
    print(json.dumps(result), flush=True)


def verify(path, root, output):
    p, prior, cr = reconstruct(path, root / 'cpu', 'cpuOrt')
    _, _, cu = reconstruct(path, root / 'cuda', 'cuda')
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
    assert len(list((br / 'started').glob('*.json'))) == 18 and len(list((br / 'capture').glob('*.bin'))) == 90
    rows = list(cu['records']) + list(cr['records'])
    for row in live['records']:
        b, i = row['backend'], row['ordinal']
        c = p['cases'][i-1]
        rid = claim['claim']+'-'+b+'-'+str(i)
        assert row['requestId'] == rid
        assert d.read(d.bind(br / 'started' / f'{b}-{i}.json')) == dict(claim=claim['claim'], requestId=rid, backend=b, ordinal=i, h=c['h'], w=c['w'], inputSha256=c['input']['sha256'])
        raw = {}
        for name, shape in shapes(c).items():
            file = br / 'capture' / f'{b}-{i}-{name}.bin'
            ref = dict(binding=d.bind(file), shape=shape, dtype='float32', bytes=file.stat().st_size)
            assert row['outputs'][name] == dict(shape=shape, dtype='float32', sha256=ref['binding']['sha256'], bytes=ref['bytes'])
            tensor.tensor(ref, shape)
            raw[name] = ref
        rows.append(dict(backend=b, ordinal=i, input=c['input'], raw=raw, finalHeadsByteExact=fidelity(raw, prior[b, i]['raw'])))
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
    assert len(files) == 110 and ids == {e['requestId'] for e in events} and len(rows) == 36
    gate = all(all(r['finalHeadsByteExact'].values()) for r in rows)
    comparisons = []
    # 完整36输入、180张量、72原最终头保真后，才允许输出108层差。
    if gate:
        for row in rows:
            c = p['cases'][row['ordinal']-1]
            for label in LABELS:
                a = tensor.tensor(row['raw'][label], shapes(c)[label])
                b = tensor.tensor(cu['records'][row['ordinal']-1]['raw'][label], shapes(c)[label])
                delta = np.abs(a-b)
                comparisons.append(dict(backend=row['backend'], ordinal=row['ordinal'], label=label, maxAbsoluteDifference=float(delta.max()), valuesAbove1e4=int((delta > 1e-4).sum()), values=int(delta.size)))
    result = dict(ok=True, decision='full36_fidelity_pass_firstblock_observable' if gate else 'reconstruction_mismatch', reader=d.bind(__file__), plan=d.bind(path), cudaReport=d.bind(root / 'cuda/report.json'), cpuReport=d.bind(root / 'cpu/report.json'), browserPlan=d.bind(br / 'plan.json'), browserLive=d.bind(br / 'capture/live-browser.json'), records=rows, all36Inputs180TensorsCompleteFinite=True, all72OriginalFinalHeadsByteExact=gate, boundaryAttributionAllowed=gate, boundaryComparisons=comparisons, httpAttempts=len(events), uniquePayloads=len(files), actualNetworkBytes=None, newModelInputs=0, learnedInputs=0, formalReleaseAllowed=False, productHold=True)
    write(output, result)
    print(json.dumps(dict(ok=True, decision=result['decision'], finalHeadsByteExact=gate, boundaryComparisons=[r for r in comparisons if r['backend'] != 'cuda'])), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['cuda', 'cpu', 'verify-cuda', 'verify-cpu', 'verify'])
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--output', type=Path)
    v = ap.parse_args()
    if v.mode in ['cuda', 'cpu']:
        capture(v.plan.resolve(), v.root.resolve(), 'cuda' if v.mode == 'cuda' else 'cpuOrt')
    elif v.mode.startswith('verify-'):
        verify_single(v.plan.resolve(), v.root.resolve(), 'cuda' if v.mode == 'verify-cuda' else 'cpuOrt', v.output.resolve())
    else:
        verify(v.plan.resolve(), v.root.resolve(), v.output.resolve())
