"""零推理绑定完整学得参数、严格参考及实际图坐标，继承同字节运行时控制。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import onnx

import importlib.util

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load(ROOT / 'model/training/prepare-two-head-route-control.py', 'learned_binding_primitives')


def prepare(design_path, output):
    design = p.read(p.bind(design_path))
    if design['purpose'] != 'complete74_learned_two_head_route_acceptance_design_only' or design['learnedBudgetAllocatedNow']:
        raise ValueError('unallocated complete learned design')
    control = p.read(design['controlGate'])
    if not control['fullNonzeroRouteControlPassed'] or control['learnedInputs'] != 0:
        raise ValueError('all complete current controls before learned inputs')
    old = p.read(design['preflight']); assets = p.read(design['assets'])
    for ref in [*design['runtimeSources'].values(), design['wasmModule'], design['kernel']]:
        p.checked(ref)
    if assets['models']['learned'] != design['learnedModel'] or assets['weights'] != design['weights']:
        raise ValueError('exact learned model and weights')
    output = output.resolve()
    if not output.is_relative_to(ROOT / 'model/reviews'):
        raise ValueError('isolated new output')
    output.mkdir(exist_ok=False)
    p.new(output / 'attempt.json', {'design': p.bind(design_path), 'modelInputsAllowed': 0})
    try:
        env = os.environ.copy()
        env['TEMP'] = env['TMP'] = str(ROOT / 'model/reviews/resize-test-temp')
        for name in ['OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS']:
            env[name] = '1'
        jobs = [
            ('control', 'audit-two-head-route-control-v2.py', ['verify', '--root', str(Path(design['controlGate']['path']).parent)]),
            ('strict-learned', 'verify-reviewed-convex-presence-head.py', ['--verify-report', str(ROOT / 'model/reviews/cycle016-convex-presence-fit-replay-v1.json')]),
            ('assets', 'materialize-reviewed-native-deployment.py', ['--verify-report', design['assets']['path']])]
        replays = []
        for name, source, args in jobs:
            command = [sys.executable, '-X', 'utf8', str(ROOT / 'model/training' / source), *args]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
            stdout = p.new(output / f'{name}.stdout', result.stdout)
            stderr = p.new(output / f'{name}.stderr', result.stderr)
            row = {'name': name, 'command': command, 'exitCode': result.returncode, 'stdout': stdout, 'stderr': stderr}
            p.new(output / f'{name}-replay.json', row); replays.append(row)
            print(json.dumps({'preflight': name, 'exitCode': result.returncode}), flush=True)
            if result.returncode:
                raise ValueError('read-only full reference replay failed: ' + name)
        ae = p.read(assets['execution']); training = p.read(ae['inputs']['training'])
        environment = p.read(training['environment'])
        if any(environment[k] for k in ['cudaMatmulAllowTf32', 'cudnnAllowTf32', 'autocastEnabled']) or environment['float32MatmulPrecision'] != 'highest':
            raise ValueError('strict original learned precision policy')
        graph = onnx.load(p.checked(design['learnedModel']))
        reader = load(ROOT / 'model/training/prepare-reviewed-mask-wasm-control.py', 'learned_parameter_reader')
        params, epsilon, gelu = reader.parameters(graph)
        cfg = {'tensors': {}, 'epsilon': epsilon, 'gelu': gelu}; values = []; offset = 0
        for name, a in params.items():
            cfg['tensors'][name] = {'offset': offset, 'shape': list(a.shape)}
            values.append(a.reshape(-1)); offset += a.size
        if cfg != p.read(old['parameterConfig']) or len(params) != 32 or offset != 118737:
            raise ValueError('unchanged complete runtime slots and original constants')
        pack = np.concatenate(values)
        pack_ref = p.new(output / 'learned-weights.f32', pack.tobytes())
        cfg_ref = p.new(output / 'config.json', cfg)
        up = load(ROOT / 'model/training/analyze-reviewed-upstream-counterfactual.py', 'learned_coordinate_graph')
        outputs = {o: n for n in graph.graph.node for o in n.output}; names = {n.name: n for n in graph.graph.node}
        topologies = []
        for block in ['dec2', 'dec1']:
            conv = names[f'/{block}/{block}.0/Conv']; concat = outputs[conv.input[0]]
            last = outputs[concat.input[0]]; prefix = last.name.removesuffix('output')
            if concat.op_type != 'Concat' or last.op_type != 'Add' or not prefix.startswith('native_bilinear_'):
                raise ValueError('actual learned graph topology')
            topologies.append({'block': block, 'prefix': prefix, 'deep': names[prefix + 'input_shape'].input[0], 'skip': concat.input[1]})
        cases = []
        if not len(design['cases']) == len(assets['cases']) == len(old['cases']) == 74:
            raise ValueError('full74 denominator')
        for i, (desired, case, original) in enumerate(zip(design['cases'], assets['cases'], old['cases'], strict=True), 1):
            for key in ['ordinal', 'candidateIdentity', 'h', 'w', 'input', 'resizeRatios']:
                if desired[key] != case[key] or case[key] != original[key]:
                    raise ValueError('stable complete candidate/input identity')
            if case['ordinal'] != i or case['candidateIdentity']['identity']['split'] != 'train' or desired['strictLearnedReference'] != case['references']['learned']:
                raise ValueError('full original train-only learned reference')
            h, w = case['h'], case['w']; x = p.tensor(case['input']); ratios = p.tensor(case['resizeRatios'])
            if x.shape != (1, 4, h, w) or ratios.shape != (4,) or ratios.dtype != np.float32:
                raise ValueError('native input and ratio storage')
            for head, shape in [('mask', (1, 1, h, w)), ('presence', (1, 1))]:
                a = p.tensor(case['references']['learned'][head])
                if a.dtype != np.float32 or a.shape != shape:
                    raise ValueError('all native strict learned head bytes')
            for scale, top in enumerate(topologies):
                factor = 4 if scale == 0 else 2; target_factor = factor // 2
                ih, iw, oh, ow = h // factor, w // factor, h // target_factor, w // target_factor
                c, skipc = (64, 32) if scale == 0 else (32, 16)
                boundary = {top['deep']: np.broadcast_to(np.float32(0), (1, c, ih, iw)),
                    top['skip']: np.broadcast_to(np.float32(0), (1, skipc, oh, ow)), 'resizeRatios': ratios}
                for axis_index, axis in enumerate(['y', 'x']):
                    expected = original['coordinateAxes'][scale * 2 + axis_index]
                    for field, ref in expected['fields'].items():
                        a = up.metadata_value(graph, boundary, top['prefix'] + axis + '_' + field)
                        b = p.tensor(ref)
                        if a.shape != b.shape or a.dtype != b.dtype or a.tobytes() != b.tobytes():
                            raise ValueError('all1184 actual learned coordinate array bytes differ')
            cases.append(case | {'coordinateAxes': original['coordinateAxes']})
        p.new(output / 'strict-reference-replay.json', {'ok': True, 'replays': replays, 'environment': training['environment'], 'newModelInputs': 0})
        report = {'ok': True, 'referenceKind': 'learned', 'design': p.bind(design_path),
            'controlGate': design['controlGate'], 'model': design['learnedModel'], 'weights': assets['weights']['learned'],
            'wasm': old['wasm'], 'parameterPack': pack_ref, 'parameterConfig': cfg_ref,
            'cases': cases, 'topologies': topologies, 'completeCoordinateArrays': 1184,
            'coordinateReferencesInheritedByAllArrayByteEquality': True,
            'strictReferenceReplay': p.bind(output / 'strict-reference-replay.json'),
            'sources': old['sources'] | {Path(__file__).name: p.bind(__file__), 'parameterReader': p.bind(ROOT / 'model/training/prepare-reviewed-mask-wasm-control.py')},
            'nativeRuntimeSources': old['nativeRuntimeSources'], 'projectModelInputs': 0,
            'learnedBudgetAllocatedNow': False, 'formalReleaseAllowed': False, 'productHold': True}
        p.new(output / 'report.json', report)
        return report
    except BaseException as error:
        p.new(output / 'failure.json', {'ok': False, 'error': str(error), 'newModelInputs': 0})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--design', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    report = prepare(args.design.resolve(), args.output)
    print(json.dumps({'ok': report['ok'], 'cases': len(report['cases']), 'newModelInputs': 0}), flush=True)
