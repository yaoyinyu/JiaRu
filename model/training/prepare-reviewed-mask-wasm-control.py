"""冻结独立合成mask控制：完整原控制参数、原生尺寸、全阶段独立F64参考。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np
import onnx
from onnx import numpy_helper
from scipy.special import erf

ROOT = Path(__file__).resolve().parents[2]
BLOCKS = [('enc1', 4, 16), ('enc2', 16, 32), ('enc3', 32, 64), ('dec2', 96, 32), ('dec1', 48, 16)]


def bind(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def new(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return bind(path)


def tensor(path, value):
    value = np.ascontiguousarray(value)
    return new(path, value.tobytes()) | {'shape': list(value.shape), 'dtype': str(value.dtype)}


def parameters(graph):
    nodes = {n.name: n for n in graph.graph.node}
    outputs = {o: n for n in graph.graph.node for o in n.output}
    initial = {n.name: n for n in graph.graph.initializer}
    result, epsilon, gelus = {}, {}, []
    def param(name, source, shape):
        a = numpy_helper.to_array(initial[source])
        if a.dtype != np.float32 or a.size != int(np.prod(shape)) or not np.isfinite(a).all():
            raise ValueError('original complete finite F32 parameter')
        result[name] = np.ascontiguousarray(a.reshape(shape))
    attrs = lambda n: {a.name: onnx.helper.get_attribute_value(a) for a in n.attribute}
    for block, incoming, channels in BLOCKS:
        for suffix, count in [('0', incoming), ('3', channels)]:
            node = nodes[f'/{block}/{block}.{suffix}/Conv']
            if node.op_type != 'Conv' or len(node.input) != 2 or attrs(node) != {'dilations': [1, 1], 'group': 1, 'kernel_shape': [3, 3], 'pads': [1, 1, 1, 1], 'strides': [1, 1]}:
                raise ValueError('original no-bias convolution topology')
            param(f'{block}.conv{suffix}', node.input[1], (channels, count, 3, 3))
        for suffix in ['1', '4']:
            prefix = f'/{block}/{block}.{suffix}/'
            add = outputs[prefix + 'Add_output_0']; mul = outputs[add.input[0]]
            div = outputs[prefix + 'InstanceNormalization_output_0']
            sqrt = outputs[div.input[1]]; epsadd = outputs[sqrt.input[0]]
            reshape = nodes[prefix + 'Reshape']
            groups = numpy_helper.to_array(outputs[reshape.input[1]].attribute[0].t).tolist()
            if [add.op_type, mul.op_type, div.op_type, sqrt.op_type, epsadd.op_type] != ['Add', 'Mul', 'Div', 'Sqrt', 'Add'] or groups != [0, 4, -1]:
                raise ValueError('four-group centered normalization')
            param(f'{block}.gamma{suffix}', mul.input[1], (channels,))
            param(f'{block}.beta{suffix}', add.input[1], (channels,))
            eps = numpy_helper.to_array(initial[epsadd.input[1]])
            if eps.dtype != np.float32 or eps.size != 1 or float(eps.flat[0]) <= 0:
                raise ValueError('positive original F32 epsilon')
            epsilon[f'{block}.{suffix}'] = float(eps.flat[0])
        for suffix in ['2', '5']:
            values = [numpy_helper.to_array(nodes[f'/{block}/{block}.{suffix}/{name}'].attribute[0].t)
                      for name in ['Constant', 'Constant_1', 'Constant_2']]
            if any(a.dtype != np.float32 or a.size != 1 for a in values):
                raise ValueError('original GELU scalar domain')
            gelus.append([float(a.flat[0]) for a in values])
    if any(a != [float(np.float32(np.sqrt(2))), 1., .5] for a in gelus):
        raise ValueError('shared original GELU constant bits')
    param('delta.weight', 'delta.weight', (16,))
    param('delta.bias', 'delta.bias', (1,))
    ordered = {}
    for block, _, _ in BLOCKS:
        for suffix in ['conv0', 'gamma1', 'beta1', 'conv3', 'gamma4', 'beta4']:
            ordered[f'{block}.{suffix}'] = result[f'{block}.{suffix}']
    ordered.update({name: result[name] for name in ['delta.weight', 'delta.bias']})
    return ordered, epsilon, gelus[0]


def conv(x, weight):
    h, w = x.shape[2:]
    padded = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
    view = np.lib.stride_tricks.sliding_window_view(padded, (3, 3), axis=(2, 3))
    kernel = weight.astype(np.float64).reshape(weight.shape[0], -1)
    out = np.empty((weight.shape[0], h * w), np.float64)
    for start in range(0, h * w, 1024):
        indices = np.arange(start, min(start + 1024, h * w))
        patches = view[0, :, indices // w, indices % w, :, :].reshape(len(indices), -1)
        out[:, start:start + len(indices)] = (patches @ kernel.T).T
    return out.reshape(1, weight.shape[0], h, w)


def resize(x, shape, ry, rx):
    def coordinates(incoming, outgoing, ratio):
        pos = np.maximum((np.arange(outgoing, dtype=np.float32) + np.float32(.5)) * np.float32(ratio) - np.float32(.5), np.float32(0))
        lower = np.minimum(np.floor(pos).astype(np.int64), incoming - 1)
        upper = np.minimum(lower + 1, incoming - 1)
        w1 = (pos - lower.astype(np.float32)).astype(np.float32)
        return lower, upper, (np.float32(1) - w1).astype(np.float64), w1.astype(np.float64)
    yl, yh, wy0, wy1 = coordinates(x.shape[2], shape[0], ry)
    xl, xh, wx0, wx1 = coordinates(x.shape[3], shape[1], rx)
    top = wx0[None, None, None, :] * x[:, :, yl, :][:, :, :, xl] + wx1[None, None, None, :] * x[:, :, yl, :][:, :, :, xh]
    bottom = wx0[None, None, None, :] * x[:, :, yh, :][:, :, :, xl] + wx1[None, None, None, :] * x[:, :, yh, :][:, :, :, xh]
    return wy0[None, None, :, None] * top + wy1[None, None, :, None] * bottom


def reference(candidate, p, epsilon, gelu, ratios, observe):
    def stage(op, a, name=None, suffix=None):
        observe(op, a, name, suffix)
        return a
    def block(name, x):
        for conv_suffix, norm_suffix, gelu_suffix in [('0', '1', '2'), ('3', '4', '5')]:
            x = stage('conv3', conv(x, p[f'{name}.conv{conv_suffix}']), f'{name}.conv{conv_suffix}')
            flat = x.reshape(4, -1)
            centered = flat - flat.mean(axis=1, keepdims=True)
            x = (centered / np.sqrt(np.mean(centered * centered, axis=1, keepdims=True) + epsilon[f'{name}.{norm_suffix}'])).reshape(x.shape)
            x = x * p[f'{name}.gamma{norm_suffix}'].astype(np.float64)[None, :, None, None] + p[f'{name}.beta{norm_suffix}'].astype(np.float64)[None, :, None, None]
            x = stage('gn4', x, name, norm_suffix)
            x = stage('gelu', (x * (gelu[1] + erf(x / gelu[0]))) * gelu[2], name, gelu_suffix)
        return x
    def pool(x):
        h, w = x.shape[2] // 2, x.shape[3] // 2
        a = x[:, :, :h * 2, :w * 2]
        return stage('pool2', (((a[:, :, ::2, ::2] + a[:, :, ::2, 1::2]) + a[:, :, 1::2, ::2]) + a[:, :, 1::2, 1::2]) * .25)
    enc1 = block('enc1', stage('promote', candidate.astype(np.float64)))
    enc2 = block('enc2', pool(enc1))
    enc3 = block('enc3', pool(enc2))
    x = stage('resize64', resize(enc3, enc2.shape[2:], *ratios[:2]))
    x = block('dec2', np.concatenate([x, enc2], axis=1))
    x = stage('resize64', resize(x, enc1.shape[2:], *ratios[2:]))
    x = block('dec1', np.concatenate([x, enc1], axis=1))
    delta = np.einsum('nchw,c->nhw', x, p['delta.weight'].astype(np.float64), optimize=False)[:, None] + float(p['delta.bias'][0])
    seed = candidate[:, 3:4] * np.float32(8) - np.float32(4)
    return stage('final_mask', (seed.astype(np.float64) + delta).astype(np.float32))


def prepare(output):
    if any(os.environ.get(k) != '1' for k in ['OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS']):
        raise ValueError('single-thread independent reference required')
    output = output.resolve()
    if not output.is_relative_to(ROOT / 'model/reviews'):
        raise ValueError('isolated immutable output')
    graph_path = ROOT / 'model/reviews/cycle016-convex-native-assets-v1/control.onnx'
    if bind(graph_path)['sha256'] != '77a0fd3a3bb6898bb88b3ead519b6ac9a8001fb757199977d5a954c1a487cbd8':
        raise ValueError('untrained original control graph binding')
    build_path = ROOT / 'model/reviews/cycle016-mask-wasm-build-v2/report.json'
    build = json.loads(build_path.read_bytes())
    if not build['ok'] or build['projectModelInputs'] != 0:
        raise ValueError('actual isolated module compilation')
    p, eps, gelu = parameters(onnx.load(graph_path))
    output.mkdir(exist_ok=False); (output / 'buffers').mkdir(); (output / 'events').mkdir()
    config, values, offset = {'tensors': {}, 'epsilon': eps, 'gelu': gelu}, [], 0
    for name, a in p.items():
        config['tensors'][name] = {'offset': offset, 'shape': list(a.shape)}
        values.append(a.reshape(-1)); offset += a.size
    config_ref = new(output / 'config.json', config)
    weights_ref = tensor(output / 'buffers/weights.f32', np.concatenate(values))
    design_path = ROOT / 'model/reviews/cycle016-reviewed-full-mask-closeout-v1/next-scope.json'
    design = json.loads(design_path.read_bytes())
    if bind(design_path)['sha256'] != '547c0de0dc7835572a9b8b54ca4b136d136a0789c02bd90327117bd150d80f90':
        raise ValueError('existing complete74 scope exact binding')
    cases = [{'id': f'synthetic-{h}x{w}', 'h': h, 'w': w, 'allStageRaw': h <= 31}
             for h, w in [(7, 9), (31, 35), (96, 100), (628, 628)]]
    plan = {'purpose': 'independent_synthetic_full_mask_wasm_not_two_head_release',
        'sources': {name: bind(path) for name, path in [
            ('reference', __file__), ('runtime', ROOT / 'model/runtime/nail-mask-f64-v2.mjs'),
            ('oldRuntime', ROOT / 'model/runtime/nail-mask-f64.mjs'),
            ('cSource', ROOT / 'model/runtime/nail-mask-f64.c')]},
        'build': bind(build_path), 'wasm': build['module'], 'controlGraph': bind(graph_path),
        'config': config_ref, 'weights': weights_ref, 'cases': cases,
        'nativeShapeScope': bind(design_path),
        'all74Shapes': [{'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'shape': c['nativeInputShape']} for c in design['cases']],
        'analyticalFullMaskReferencesAllowed': 4, 'nodeSyntheticMaskInputsAllowed': 4,
        'browserSyntheticMaskInputsAllowed': 4, 'erfScalarGridPointsPerBackend': 20001,
        'maxErfAbsError': 1e-13, 'smallStageMaxAbsError': 1e-9,
        'finalMaskMaxAbsError': 1e-4, 'decodedPixelDifferencesAllowed': 0,
        'fixedWasmMemoryBytes': 268435456, 'projectModelInputsAllowed': 0,
        'learnedInputsAllowed': 0, 'presenceExecutionClaimed': False,
        'originalFailuresPreserved': True, 'productHold': True, 'formalReleaseAllowed': False,
        'referenceRuntime': {'python': platform.python_version(), 'numpy': np.__version__, 'pythonBinary': bind(sys.executable)}}
    new(output / 'plan.json', plan)
    records = []
    for ordinal, case in enumerate(cases, 1):
        new(output / 'events' / f'{ordinal:02d}-start.json', case)
        h, w = case['h'], case['w']
        rng = np.random.default_rng(2026101500 + ordinal)
        candidate = rng.normal(0, .5, (1, 4, h, w)).astype(np.float32)
        candidate[:, 3] = ((np.indices((h, w)).sum(axis=0) % 5) == 0).astype(np.float32)
        ratios = np.asarray([np.float32(a) / np.float32(b) for a, b in [(h // 4, h // 2), (w // 4, w // 2), (h // 2, h), (w // 2, w)]], np.float32)
        input_ref = tensor(output / 'buffers' / f'{ordinal:02d}-input.f32', candidate)
        stages = []
        def observe(op, value, name, suffix):
            if not np.isfinite(value).all():
                raise ValueError('finite whole reference stage')
            item = {'ordinal': len(stages), 'op': op, 'name': name, 'suffix': suffix,
                    'shape': list(value.shape), 'dtype': str(value.dtype), 'sha256': hashlib.sha256(value.tobytes()).hexdigest()}
            if case['allStageRaw'] or op == 'final_mask':
                item['raw'] = tensor(output / 'buffers' / f'{ordinal:02d}-stage{len(stages):02d}.bin', value)
            stages.append(item)
        result = reference(candidate, p, eps, gelu, ratios, observe)
        if len(stages) != 36 or np.array_equal(result, candidate[:, 3:4] * 8 - 4):
            raise ValueError('complete nonzero-control mask path')
        record = case | {'ordinal': ordinal, 'candidate': input_ref, 'ratios': ratios.tolist(), 'stages': stages}
        records.append(record); new(output / 'events' / f'{ordinal:02d}-done.json', record)
        print(json.dumps({'phase': 'synthetic_reference', 'ordinal': ordinal, 'shape': [h, w]}), flush=True)
    grid = np.linspace(-10, 10, 20001, dtype=np.float64)
    grid_ref = tensor(output / 'buffers/erf-input.f64', grid)
    expected_ref = tensor(output / 'buffers/erf-reference.f64', erf(grid))
    report = {'ok': True, 'plan': bind(output / 'plan.json'), 'records': records,
        'erfInput': grid_ref, 'erfReference': expected_ref, 'projectModelInputs': 0,
        'learnedInputs': 0, 'presenceExecuted': False, 'formalReleaseAllowed': False, 'productHold': True}
    new(output / 'report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({'ok': result['ok'], 'referenceCount': len(result['records'])}), flush=True)
