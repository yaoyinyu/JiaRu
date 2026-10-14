"""按实际语义映射全部新参数到稳定原尺寸图；逐字节逆变换与完整输入重放。"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper
import torch

HERE = Path(__file__).resolve().parent
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
fit = load(HERE/'fit-reviewed-convex-presence-head.py', 'native_deployment_fit')
d, c, require = fit.d, fit.c, fit.require


def save(path, value):
    require(value.dtype == np.float32 and np.isfinite(value).all(), 'finite float32 artifact')
    with path.open('xb') as stream: stream.write(value.tobytes()); stream.flush(); os.fsync(stream.fileno())
    return d.bind(path)|{'shape': list(value.shape), 'dtype': 'float32'}


def parameter_map(model, state):
    initializers = {x.name: x for x in model.graph.initializer}; nodes = {x.name: x for x in model.graph.node}; result = {}
    require(len(initializers) == len(model.graph.initializer) and len(nodes) == len(model.graph.node), 'unique graph names')
    for name, value in state.items():
        if name in initializers:
            target = name
        else:
            block, index, kind = name.split('.')
            require(index in ('1', '4') and kind in ('weight', 'bias'), 'only named GN affine mapping')
            op = 'Mul' if kind == 'weight' else 'Add'; node = nodes[f'/{block}/{block}.{index}/{op}']
            require(node.op_type == op and len(node.input) == 2, 'actual semantic affine node')
            target = node.input[1]
        stored = numpy_helper.to_array(initializers[target]); expected = value.detach().cpu().numpy()
        require(stored.dtype == expected.dtype == np.float32 and stored.size == expected.size and
                list(stored.shape) in [list(expected.shape), [len(expected), 1, 1]], 'each actual parameter shape and storage')
        result[name] = {'initializer': target, 'shape': list(stored.shape)}
    require(len({x['initializer'] for x in result.values()}) == len(state), 'complete bijective parameter mapping')
    return result


def graft(parent, state, mapping):
    require(mapping == parameter_map(parent, state), 'actual semantic map')
    result = copy.deepcopy(parent); by_name = {x.name: x for x in result.graph.initializer}
    for name, target in mapping.items():
        value = state[name].detach().cpu().contiguous().numpy().reshape(target['shape'])
        by_name[target['initializer']].CopyFrom(numpy_helper.from_array(value, name=target['initializer']))
    verify_graft(parent, result, state, mapping)
    return result


def verify_graft(parent, result, state, mapping):
    require(mapping == parameter_map(parent, state), 'all parameters mapped from actual graph')
    original = {x.name: x for x in parent.graph.initializer}; actual = {x.name: x for x in result.graph.initializer}
    require(original.keys() == actual.keys(), 'no new initializer')
    restored = copy.deepcopy(result); old = {x.name: x for x in restored.graph.initializer}
    for name, target in mapping.items():
        key = target['initializer']; expected = state[name].detach().cpu().contiguous().numpy().reshape(target['shape'])
        require(numpy_helper.to_array(actual[key]).tobytes() == expected.tobytes(), 'new exact learned/control parameter bytes')
        old[key].CopyFrom(original[key])
    require(restored.SerializeToString() == parent.SerializeToString(), 'reverse all weight substitutions restores exact parent graph')
    require([v.name for v in result.graph.input] == ['candidate', 'resizeRatios'] and
            [v.name for v in result.graph.output] == ['mask_logits', 'presence_logit'], 'stable original native two-input two-head interface')
    onnx.checker.check_model(result, full_check=True)


def ratios(h, w):
    require(h >= 4 and w >= 4, 'native pooling dimensions')
    return np.array([np.float32(a)/np.float32(b) for a, b in ((h//4, h//2), (w//4, w//2), (h//2, h), (w//2, w))], np.float32)


def control_state(net):
    torch.manual_seed(2026101402)
    model = net.NativeConditionalMaskRefiner().cpu().float().eval()
    with torch.no_grad():
        model.delta.weight.copy_(torch.linspace(-.25, .25, model.delta.weight.numel()).reshape_as(model.delta.weight))
        model.delta.bias.fill_(.125)
        model.presence.weight.copy_(torch.linspace(-.1, .1, 128).reshape(1, 128)); model.presence.bias.fill_(.25)
    return {name: value.detach().clone() for name, value in model.state_dict().items()}


def resources(execution):
    e = d.read(execution)
    for bound in [*e['inputs'].values(), *e['sources'].values()]: d.checked(bound)
    require(e['purpose'] == 'new_convex_candidate_zero_forward_graph_and_native_input_materialization' and
            e['sources']['runner'] == d.bind(__file__) and e['modelInputsAllowed'] == 0, 'materialization only no forward')
    training = d.read(e['inputs']['training']); audit = d.read(e['inputs']['replay']); scope = d.read(e['inputs']['scope'])
    require(training['trainQualityGatePassed'] and audit['ok'] and audit['trainQualityGatePassed'] and
            scope['inputs']['training'] == e['inputs']['training'] == audit['training'] and scope['inputs']['weights'] == training['weights'], 'current complete developer candidate')
    template_runner = load(d.checked(e['sources']['templateRunner']), 'materialization_old_fullgraph')
    old_e, old_p, old_models, _ = template_runner.resources(d.checked(e['inputs']['templateExecution']))
    require(e['inputs']['template'] == old_models['learned'], 'frozen stable learned graph expression')
    candidate_e, prior, data, rows, net, metric, guard, cleanup, features, flags = fit.resources(training['execution'])
    require(scope['candidateIdentities'] == candidate_e['candidateIdentities'] == [r['candidateIdentity'] for r in rows], 'entire current train identities')
    return e, training, data, rows, net, guard, cleanup


def build(execution, root):
    e, training, data, rows, net, guard, cleanup = resources(execution)
    try:
        root.mkdir(exist_ok=False); (root/'buffers').mkdir()
        parent = onnx.load(d.checked(e['inputs']['template']))
        learned = torch.load(d.checked(training['weights']), map_location='cpu', weights_only=True)
        model = net.NativeConditionalMaskRefiner(); require(model.load_state_dict(learned, strict=True) is not None, 'exact architecture keys')
        controls = control_state(net); mapping = parameter_map(parent, learned); models = {}; weights = {'learned': training['weights']}
        for kind, state in (('control', controls), ('learned', learned)):
            graph = graft(parent, state, mapping); path = root/f'{kind}.onnx'
            with path.open('xb') as stream: stream.write(graph.SerializeToString()); stream.flush(); os.fsync(stream.fileno())
            models[kind] = d.bind(path)
        with (root/'control-weights.pt').open('xb') as stream: torch.save(controls, stream); stream.flush(); os.fsync(stream.fileno())
        weights['control'] = d.bind(root/'control-weights.pt'); cases = []
        for i, (row, sample, output) in enumerate(zip(rows, c.base.load_samples(rows), training['native'], strict=True), 1):
            rgb, coarse, target, positive = sample; h, w = coarse.shape
            case = {'ordinal': i, 'candidateIdentity': row['candidateIdentity'], 'h': h, 'w': w, 'positive': positive,
                    'input': save(root/'buffers'/f'{i:03d}-input.bin', net.pack(rgb, coarse)[None]),
                    'resizeRatios': save(root/'buffers'/f'{i:03d}-ratios.bin', ratios(h, w)), 'references': {}}
            with np.load(d.checked(output), allow_pickle=False) as archive:
                case['references']['learned'] = {'mask': save(root/'buffers'/f'{i:03d}-learned-mask.bin', archive['logits'][None, None]),
                    'presence': save(root/'buffers'/f'{i:03d}-learned-presence.bin', archive['presenceLogit'].reshape(1, 1))}
            cases.append(case)
        result = {'ok': True, 'execution': execution, 'models': models, 'weights': weights, 'parameterMap': mapping,
                  'cases': cases, 'counts': data['counts'], 'candidateIdentities': [r['candidateIdentity'] for r in rows],
                  'allGraphConstantsAndNodesUnchanged': True, 'allWeightSubstitutionsExactlyReversible': True,
                  'newModelCalls': 0, 'formalReleaseAllowed': False, 'productHold': True}
        d.new(root/'report.json', result); return result
    finally:
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


def verify(path):
    report = d.read(d.bind(path)); e, training, data, rows, net, guard, cleanup = resources(report['execution'])
    try:
        parent = onnx.load(d.checked(e['inputs']['template'])); original = torch.load(d.checked(training['weights']), map_location='cpu', weights_only=True)
        control = control_state(net); saved_control = torch.load(d.checked(report['weights']['control']), map_location='cpu', weights_only=True)
        require(control.keys() == saved_control.keys() and all(control[k].numpy().tobytes() == saved_control[k].numpy().tobytes() for k in control), 'new deterministic nonzero control weights')
        for kind, state in (('control', control), ('learned', original)):
            verify_graft(parent, onnx.load(d.checked(report['models'][kind])), state, report['parameterMap'])
        require(len(report['cases']) == len(rows) and report['counts'] == data['counts'] and
                report['candidateIdentities'] == [r['candidateIdentity'] for r in rows], 'full candidate cardinality')
        for i, (case, row, sample, output) in enumerate(zip(report['cases'], rows, c.base.load_samples(rows), training['native'], strict=True), 1):
            rgb, coarse, target, positive = sample; h, w = coarse.shape
            require(case['ordinal'] == i and case['candidateIdentity'] == row['candidateIdentity'] and
                    case['h'] == h and case['w'] == w and case['positive'] == positive, 'source native identity/order')
            independent = np.concatenate([((rgb.astype(np.float64)/255-np.array([.485, .456, .406]))/np.array([.229, .224, .225])).transpose(2, 0, 1).astype(np.float32), (coarse.astype(np.float32)/255)[None]], axis=0)[None]
            for key, expected in (('input', independent), ('resizeRatios', ratios(h, w))):
                ref = case[key]; require(ref['shape'] == list(expected.shape) and ref['dtype'] == 'float32' and d.checked({k: ref[k] for k in ('path', 'sha256')}).read_bytes() == expected.tobytes(), 'complete native normalization and host ratio exact bytes')
            with np.load(d.checked(output), allow_pickle=False) as archive:
                for head, value in (('mask', archive['logits'][None, None]), ('presence', archive['presenceLogit'].reshape(1, 1))):
                    ref = case['references']['learned'][head]
                    require(ref['shape'] == list(value.shape) and ref['dtype'] == 'float32' and d.checked({k: ref[k] for k in ('path', 'sha256')}).read_bytes() == value.tobytes(), 'actual strict CUDA inherited new weight two-head bytes')
        return {'ok': True, 'materialization': d.bind(path), 'allParameterGraphReverseAndNativeInputBytesReplayed': True,
                'candidateCount': len(rows), 'newModelCalls': 0, 'formalReleaseAllowed': False, 'productHold': True}
    finally:
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execution', type=Path); parser.add_argument('--output', type=Path); parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args(); result = verify(args.verify_report.resolve()) if args.verify_report else build(d.bind(args.execution), args.output.resolve())
    print(json.dumps({'ok': result['ok'], 'newModelCalls': 0, 'candidateCount': result.get('candidateCount', len(result.get('cases', [])))}))
