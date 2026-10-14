"""新图同74输入的确定性非零控制：一次严格CUDA参考捕获，不训练。"""
import argparse
import importlib.util
import json
import traceback
from pathlib import Path
import numpy as np
import torch
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('capture_new_control_assets', HERE/'materialize-reviewed-native-deployment.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
d, c, require = m.d, m.c, m.require


def resources(ref):
    e = d.read(ref)
    for bound in [*e['inputs'].values(), *e['sources'].values()]: d.checked(bound)
    require(e['purpose'] == 'full_native_new_nonzero_untrained_strict_cuda_control_reference' and e['sources']['runner'] == d.bind(__file__), 'control purpose/source')
    report = d.read(e['inputs']['assets']); proof = m.verify(d.checked(e['inputs']['assets']))
    require(e['budget'] == {'maximumAttempts': 1, 'strictCudaControlInputs': len(report['cases']), 'learnedModelInputs': 0,
            'optimizerSteps': 0, 'autogradEvaluations': 0, 'restartAllowed': False} and proof['candidateCount'] == 74, 'new control only complete budget')
    assets_e = d.read(report['execution']); training = d.read(assets_e['inputs']['training']); fit_e = d.read(training['execution'])
    _, data, rows, net, band, metric, guard, cleanup = c.resources(Path(d.read(fit_e['inputs']['failedControlTraining'])['inputs']['plan']['path']))
    return e, report, net, guard, cleanup


def execute(ref, root):
    e, assets, net, guard, cleanup = resources(ref); started = 0; records = []
    try:
        root.mkdir(exist_ok=False); (root/'events').mkdir(); (root/'buffers').mkdir()
        d.new(root/'attempt.json', {'execution': ref, 'restartAllowed': False})
        c.base.set_precision(); model = net.NativeConditionalMaskRefiner().cuda().float().eval(); model.requires_grad_(False)
        state = torch.load(d.checked(assets['weights']['control']), map_location='cpu', weights_only=True); model.load_state_dict(state, strict=True)
        before = c.tensors_sha(model); d.new(root/'environment.json', c.base.environment())
        for i, case in enumerate(assets['cases'], 1):
            path = d.checked({k: case['input'][k] for k in ('path', 'sha256')}); x = np.frombuffer(path.read_bytes(), np.float32).reshape(case['input']['shape']).copy()
            started = i; d.new(root/'events'/f'{2*i-1:03d}.json', {'phase': 'started', 'ordinal': i, 'candidateIdentity': case['candidateIdentity'], 'input': case['input']})
            with torch.inference_mode(): mask, presence = model(torch.from_numpy(x).cuda())
            a = mask.cpu().numpy().copy(); b = presence.cpu().numpy().copy()
            require(a.shape == (1, 1, case['h'], case['w']) and b.shape == (1, 1), 'full native two-head shape')
            delta = float(np.abs(a-(x[:, 3:4]*8-4)).max()); require(delta > 0 and np.any(b != 0), 'actual both-head nonzero untrained control')
            outputs = {'mask': m.save(root/'buffers'/f'{i:03d}-mask.bin', a), 'presence': m.save(root/'buffers'/f'{i:03d}-presence.bin', b)}
            record = {'ordinal': i, 'candidateIdentity': case['candidateIdentity'], 'input': case['input'], 'outputs': outputs, 'nonzeroControlDeltaMaxAbs': delta}
            records.append(record); d.new(root/'events'/f'{2*i:03d}.json', {'phase': 'confirmed', 'record': record})
        require(c.tensors_sha(model) == before, 'all untrained control weights unchanged')
        result = {'ok': True, 'execution': ref, 'records': records, 'strictCudaControlInputs': started, 'environment': d.bind(root/'environment.json'),
                  'weightTensorHashes': before, 'optimizerSteps': 0, 'autogradEvaluations': 0, 'formalReleaseAllowed': False, 'productHold': True}
        d.new(root/'report.json', result); d.new(root/'terminal.json', {'phase': 'closed', 'started': started, 'confirmed': len(records)})
        return result
    except BaseException as error:
        if root.exists():
            d.new(root/'failure.json', {'error': str(error), 'traceback': traceback.format_exc(), 'started': started, 'confirmed': len(records), 'restartAllowed': False})
        raise
    finally:
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


def verify(path):
    saved = d.read(d.bind(path)); e, assets, net, guard, cleanup = resources(saved['execution'])
    try:
        require(len(saved['records']) == saved['strictCudaControlInputs'] == len(assets['cases']) == 74, 'full control denominator')
        state = torch.load(d.checked(assets['weights']['control']), map_location='cpu', weights_only=True)
        require({k: m.fit.capture.sha(v.contiguous().numpy()) for k, v in state.items()} == saved['weightTensorHashes'], 'control state exact hashes')
        env = d.read(saved['environment']); require(not env['cudaMatmulAllowTf32'] and not env['cudnnAllowTf32'] and not env['autocastEnabled'] and env['float32MatmulPrecision'] == 'highest', 'strict actual policy')
        require(len(list((path.parent/'events').glob('*.json'))) == 148, 'all immutable starts/confirmations')
        for i, (case, record) in enumerate(zip(assets['cases'], saved['records'], strict=True), 1):
            require(record['ordinal'] == i and record['candidateIdentity'] == case['candidateIdentity'] and record['input'] == case['input'], 'control actual input binding')
            arrays = {}
            for head, shape in (('mask', [1, 1, case['h'], case['w']]), ('presence', [1, 1])):
                ref = record['outputs'][head]; raw = d.checked({k: ref[k] for k in ('path', 'sha256')}).read_bytes()
                require(ref['shape'] == shape and ref['dtype'] == 'float32' and len(raw) == int(np.prod(shape))*4, 'native finite two-head bytes')
                arrays[head] = np.frombuffer(raw, np.float32).reshape(shape); require(np.isfinite(arrays[head]).all(), 'all elements finite')
            x = np.frombuffer(d.checked({k: case['input'][k] for k in ('path', 'sha256')}).read_bytes(), np.float32).reshape(case['input']['shape'])
            delta = float(np.abs(arrays['mask']-(x[:, 3:4]*8-4)).max())
            require(delta > 0 and delta == record['nonzeroControlDeltaMaxAbs'] and np.any(arrays['presence'] != 0), 'full actual nonzero control')
            require(d.read(d.bind(path.parent/'events'/f'{2*i-1:03d}.json')) == {'phase': 'started', 'ordinal': i, 'candidateIdentity': case['candidateIdentity'], 'input': case['input']} and
                    d.read(d.bind(path.parent/'events'/f'{2*i:03d}.json')) == {'phase': 'confirmed', 'record': record}, 'unique actual ordered events')
        require(d.read(d.bind(path.parent/'terminal.json')) == {'phase': 'closed', 'started': 74, 'confirmed': 74} and
                d.read(d.bind(path.parent/'attempt.json')) == {'execution': saved['execution'], 'restartAllowed': False}, 'exclusive closed reference budget')
        return {'ok': True, 'controlReference': d.bind(path), 'full74NonzeroStrictCudaReferenceAnd148EventsReplayed': True, 'newModelCalls': 0}
    finally:
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execution', type=Path); parser.add_argument('--output', type=Path); parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args(); result = verify(args.verify_report.resolve()) if args.verify_report else execute(d.bind(args.execution), args.output.resolve())
    print(json.dumps({'ok': result['ok'], 'strictCudaControlInputs': result.get('strictCudaControlInputs'), 'newModelCalls': result.get('newModelCalls')}))
