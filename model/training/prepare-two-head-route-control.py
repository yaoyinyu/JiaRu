"""零神经输入预检：完整74身份/严格参考、原图坐标及可观测WASM资产。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import onnx

ROOT = Path(__file__).resolve().parents[2]


def bind(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest}


def checked(ref):
    path = Path(ref['path'])
    if bind(path)['sha256'] != ref['sha256']: raise ValueError('frozen SHA: ' + str(path))
    return path


def read(ref): return json.loads(checked(ref).read_bytes())
def new(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return bind(path)
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def tensor(ref):
    a = np.frombuffer(checked(ref).read_bytes(), np.dtype(ref['dtype'])).reshape(ref['shape'])
    if not np.isfinite(a).all(): raise ValueError('full finite tensor')
    return a


def prepare(design_path, output):
    design_ref = bind(design_path); design = read(design_ref)
    if design['purpose'] != 'complete74_real_two_head_route_control_design_only' or design['controlBudgetAllocatedNow'] or design['learnedBudgetAllocatedNow']:
        raise ValueError('new unallocated full control design')
    for ref in design['inputs'].values(): checked(ref)
    assets = read(design['inputs']['assets']); strict = read(design['inputs']['strictControl'])
    if len(design['cases']) != 74 or len(assets['cases']) != 74 or len(strict['records']) != 74:
        raise ValueError('full74 denominator')
    output = output.resolve(); assert output.is_relative_to(ROOT / 'model/reviews')
    output.mkdir(exist_ok=False); (output / 'coordinates').mkdir()
    new(output / 'attempt.json', {'design': design_ref, 'projectModelInputsAllowed': 0, 'restartAllowed': False})
    try:
        env = os.environ.copy()
        env['TEMP'] = env['TMP'] = str(ROOT / 'model/reviews/resize-test-temp')
        for key in ['OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS']: env[key] = '1'
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'model/training/capture-reviewed-native-control.py'),
                   '--verify-report', design['inputs']['strictControl']['path']]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
        new(output / 'strict-reference.stdout', result.stdout); new(output / 'strict-reference.stderr', result.stderr)
        new(output / 'strict-reference-replay.json', {'command': command, 'exitCode': result.returncode,
            'stdout': bind(output / 'strict-reference.stdout'), 'stderr': bind(output / 'strict-reference.stderr')})
        if result.returncode: raise ValueError('full strict control reference replay failed')
        old_build = read(bind(ROOT / 'model/reviews/cycle016-mask-wasm-build-v2/report.json'))
        for ref in old_build['inputs'].values(): checked(ref)
        wrapper = ROOT / 'model/runtime/nail-mask-f64-coordinate-observer.c'
        module_path = output / 'mask-f64-coordinates.wasm'
        command = old_build['command'].copy()
        command[command.index(old_build['inputs']['cSource']['path'])] = str(wrapper)
        command[-1] = str(module_path)
        command.insert(-2, '-Wl,--export=capture_coordinates')
        built = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
        new(output / 'compiler.stdout', built.stdout); new(output / 'compiler.stderr', built.stderr)
        new(output / 'build.json', {'ok': built.returncode == 0, 'command': command, 'exitCode': built.returncode,
            'originalBuild': bind(ROOT / 'model/reviews/cycle016-mask-wasm-build-v2/report.json'),
            'includedFrozenKernel': old_build['inputs']['cSource'], 'observerSource': bind(wrapper),
            'module': bind(module_path) if built.returncode == 0 else None})
        if built.returncode: raise ValueError(built.stderr.decode(errors='replace'))
        graph = onnx.load(checked(assets['models']['control']))
        up = load(ROOT / 'model/training/analyze-reviewed-upstream-counterfactual.py', 'coordinate_graph_reader')
        param_reader = load(ROOT / 'model/training/prepare-reviewed-mask-wasm-control.py', 'route_control_params')
        parameters, epsilon, gelu = param_reader.parameters(graph)
        pack = np.concatenate([a.reshape(-1) for a in parameters.values()])
        if checked(design['controlParameterPack']).read_bytes() != pack.tobytes(): raise ValueError('complete exact control parameter bits')
        cfg = read(design['controlParameterConfig'])
        if cfg['epsilon'] != epsilon or cfg['gelu'] != gelu: raise ValueError('original constant bits')
        outputs = {o: n for n in graph.graph.node for o in n.output}; names = {n.name: n for n in graph.graph.node}
        topologies = []
        for block in ['dec2', 'dec1']:
            conv = names[f'/{block}/{block}.0/Conv']; concat = outputs[conv.input[0]]
            last = outputs[concat.input[0]]; prefix = last.name.removesuffix('output')
            if concat.op_type != 'Concat' or last.op_type != 'Add' or not prefix.startswith('native_bilinear_'):
                raise ValueError('original per-graph resize topology')
            deep = names[prefix + 'input_shape'].input[0]
            topologies.append({'block': block, 'prefix': prefix, 'deep': deep, 'skip': concat.input[1]})
        cases = []
        for ordinal, (case, asset, reference) in enumerate(zip(design['cases'], assets['cases'], strict['records'], strict=True), 1):
            if not (case['ordinal'] == asset['ordinal'] == reference['ordinal'] == ordinal and
                    case['candidateIdentity'] == asset['candidateIdentity'] == reference['candidateIdentity'] and
                    case['input'] == asset['input'] == reference['input'] and
                    case['references']['control'] == reference['outputs'] and case['candidateIdentity']['identity']['split'] == 'train'):
                raise ValueError('complete original stable identity and strict references')
            candidate = tensor(case['input']); ratios = tensor(case['resizeRatios']); h, w = case['h'], case['w']
            if candidate.shape != (1, 4, h, w) or ratios.dtype != np.float32 or ratios.shape != (4,): raise ValueError('original native inputs')
            for head, ref in reference['outputs'].items():
                a = tensor(ref)
                if a.dtype != np.float32 or list(a.shape) != ([1, 1, h, w] if head == 'mask' else [1, 1]): raise ValueError('strict both-head native shapes')
            axes = []
            for scale, top in enumerate(topologies):
                factor = 4 if scale == 0 else 2; target_factor = factor // 2
                ih, iw, oh, ow = h // factor, w // factor, h // target_factor, w // target_factor
                c, skipc = (64, 32) if scale == 0 else (32, 16)
                boundary = {top['deep']: np.broadcast_to(np.float32(0), (1, c, ih, iw)),
                            top['skip']: np.broadcast_to(np.float32(0), (1, skipc, oh, ow)), 'resizeRatios': ratios}
                for axis, incoming, outgoing, ratio in [('y', ih, oh, ratios[2 * scale]), ('x', iw, ow, ratios[2 * scale + 1])]:
                    fields = {}
                    for field in ['lower', 'upper', 'weight0', 'weight1']:
                        value = up.metadata_value(graph, boundary, top['prefix'] + axis + '_' + field)
                        if value.size != outgoing or value.dtype != (np.int64 if field in ['lower', 'upper'] else np.float32): raise ValueError('original coordinate complete storage domain')
                        path = output / 'coordinates' / f'{ordinal}-{len(axes)}-{field}.bin'
                        fields[field] = new(path, value.tobytes()) | {'shape': list(value.shape), 'dtype': str(value.dtype)}
                    axes.append({'incoming': incoming, 'outgoing': outgoing, 'ratio': float(ratio), 'fields': fields})
            cases.append(case | {'coordinateAxes': axes})
        report = {'ok': True, 'design': design_ref, 'model': assets['models']['control'],
            'wasm': bind(module_path), 'parameterPack': design['controlParameterPack'],
            'parameterConfig': design['controlParameterConfig'], 'cases': cases,
            'topologies': topologies, 'completeCoordinateArrays': 1184,
            'strictReferenceReplay': bind(output / 'strict-reference-replay.json'),
            'sources': {p.name: bind(p) for p in [Path(__file__), wrapper,
                ROOT / 'model/runtime/nail-mask-f64.c', ROOT / 'model/runtime/nail-mask-f64-v2.mjs',
                ROOT / 'model/runtime/nail-two-head-route.mjs', ROOT / 'model/runtime/verify-mask-wasm-coordinates.mjs',
                ROOT / 'model/training/analyze-reviewed-upstream-counterfactual.py']},
            'nativeRuntimeSources': read(bind(ROOT / 'model/reviews/cycle016-convex-native-backends-execution-v1.json'))['runtimeFiles'],
            'controlBudgetAllocatedNow': False, 'learnedBudgetAllocatedNow': False,
            'projectModelInputs': 0, 'formalReleaseAllowed': False, 'productHold': True}
        new(output / 'report.json', report)
        return report
    except BaseException as error:
        new(output / 'failure.json', {'ok': False, 'error': str(error), 'projectModelInputs': 0, 'restartAllowed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--design', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    value = prepare(args.design, args.output)
    print(json.dumps({'ok': value['ok'], 'cases': len(value['cases']), 'coordinateArrays': value['completeCoordinateArrays']}))
