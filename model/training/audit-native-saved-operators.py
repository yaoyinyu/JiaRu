"""用冻结同输入隔离插值与归一化，不消费完整模型、训练或留出预算。"""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('saved_operator_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)


def resources(plan_path):
    plan = d.read(d.bind(plan_path))
    if plan['purpose'] != 'full68_same_saved_input_operator_localization' or plan['fullCandidateCount'] != 68:
        raise ValueError('operator full68 contract')
    if any(plan[k] != 0 for k in ('optimizerStepsAllowed', 'fullModelInputsAllowed', 'valInputsAllowed', 'protectedInputsAllowed')) or plan['operatorInputsPerBackendAllowed'] != 204:
        raise ValueError('operator-only budget')
    if plan['operations'] != ['resize_e3_to_e2', 'resize_d2_to_e1', 'dec1.4_group_norm']:
        raise ValueError('frozen operation order')
    if plan['inferencePolicy'] != {'cudnnAllowTf32': False, 'matmulAllowTf32': False} or plan['groupNorm'] != {'groups': 4, 'channels': 16, 'epsilon': 1e-5}:
        raise ValueError('frozen precision/normalization')
    for ref in plan['inputs'].values(): d.checked(ref)
    layers = d.read(plan['inputs']['layerReport'])
    helper = d.load(d.checked(layers['inputs']['auditor']), 'saved_operator_layer_helper')
    prior_scope = d.read(layers['inputs']['plan'])
    if plan['inputs']['instrumentedOnnx'] != layers['inputs']['instrumentedOnnx'] or plan['inputs']['trainedWeights'] != prior_scope['inputs']['trainedWeights']:
        raise ValueError('same graph and learned weights')
    if not layers['ok'] or not layers['instrumentationFinalHeadsBitwiseIdenticalAllBackends'] or plan['candidateIdentities'] != [c['candidateIdentity'] for c in layers['captures']]:
        raise ValueError('prior full68 instrumentation gate')
    if len(layers['captures']) != 68 or any(c['candidateIdentity']['identity']['split'] != 'train' for c in layers['captures']):
        raise ValueError('train-only denominator')
    buffer_helper = d.load(HERE / 'audit-trained-native-precision-v2.py', 'operator_preflight_buffer')
    for c in layers['captures']:
        for name in ('enc3.5', 'enc2.5', 'dec2.5', 'enc1.5', 'dec1.3', 'dec1.4'):
            helper.read_tensor(buffer_helper, c['strictCuda']['layers'][name])
    return plan, layers, helper


def graph_models(plan):
    source = onnx.load(d.checked(plan['inputs']['instrumentedOnnx']))
    nodes = {n.name: n for n in source.graph.node}
    models = []
    for name in ('/Resize', '/Resize_1'):
        node = onnx.NodeProto(); node.CopyFrom(nodes[name])
        node.input[:] = ['x', '', '', 'sizes']; node.output[:] = ['y']
        graph = onnx.helper.make_graph([node], name,
            [onnx.helper.make_tensor_value_info('x', onnx.TensorProto.FLOAT, ['n', 'c', 'h', 'w']),
             onnx.helper.make_tensor_value_info('sizes', onnx.TensorProto.INT64, [4])],
            [onnx.helper.make_tensor_value_info('y', onnx.TensorProto.FLOAT, ['n', 'c', 'oh', 'ow'])])
        model = onnx.helper.make_model(graph, opset_imports=list(source.opset_import)); model.ir_version = source.ir_version
        models.append(model)
    shaped = onnx.shape_inference.infer_shapes(source)
    models.append(onnx.utils.Extractor(shaped).extract_model(['/dec1/dec1.3/Conv_output_0'], ['/dec1/dec1.4/Add_output_0']))
    for model in models: onnx.checker.check_model(model)
    return models


def reconstruct(plan_path, graphs, captures):
    plan, layers, helper = resources(plan_path)
    buffer_helper = d.load(HERE / 'audit-trained-native-precision-v2.py', 'operator_replay_buffer')
    if len(graphs) != 3 or any(onnx.load(d.checked(ref)).SerializeToString() != m.SerializeToString() for ref, m in zip(graphs, graph_models(plan), strict=True)):
        raise ValueError('isolated operation graph reconstruction_mismatch')
    if len(captures) != 68 or [c['candidateIdentity'] for c in captures] != plan['candidateIdentities'] or [c['ordinal'] for c in captures] != [c['ordinal'] for c in layers['captures']]:
        raise ValueError('full68 operator captures')
    records = []
    for c, previous in zip(captures, layers['captures'], strict=True):
        if list(c['operations']) != plan['operations']: raise ValueError('operation order mismatch')
        statistics = {}
        for name, refs in c['operations'].items():
            values = {b: helper.read_tensor(buffer_helper, refs[b]) for b in ('cpuTorch', 'strictCuda', 'ort')}
            if name == 'dec1.4_group_norm':
                helper.exact(helper.read_tensor(buffer_helper, previous['strictCuda']['layers']['dec1.4']), values['strictCuda'])
            statistics[name] = {'shape': list(values['ort'].shape),
                'strictCudaVsOrt': helper.differences(values['strictCuda'], values['ort']),
                'cpuTorchVsOrt': helper.differences(values['cpuTorch'], values['ort']),
                'strictCudaVsCpuTorch': helper.differences(values['strictCuda'], values['cpuTorch'])}
        records.append({'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'operations': statistics})
    summary = {name: {label: {'maxAbs': max(r['operations'][name][label]['maxAbs'] for r in records),
                            'candidateCountAbove1e4': sum(r['operations'][name][label]['maxAbs'] > 1e-4 for r in records)}
                     for label in ('strictCudaVsOrt', 'cpuTorchVsOrt', 'strictCudaVsCpuTorch')} for name in plan['operations']}
    return {'schemaVersion': 1, 'ok': True, 'decision': 'same_input_operator_diagnostic_reconstructed',
        'inputs': {'plan': d.bind(plan_path), 'auditor': d.bind(__file__)}, 'graphs': graphs, 'captures': captures,
        'records': records, 'summary': summary, 'groupNormStrictSavedOutputBitwiseIdentical': True,
        'fullCandidateCount': 68, 'newOperatorInputsPerBackend': 204, 'newFullModelInputs': 0, 'optimizerSteps': 0,
        'valModelInputs': 0, 'protectedModelInputs': 0, 'fullModelCpuGatePassed': False,
        'formalReleaseAllowed': False, 'productHold': True}


def run(plan_path, root):
    if root.exists(): raise ValueError('output exists; read-only replay required')
    plan, layers, helper = resources(plan_path)
    buffer_helper = d.load(HERE / 'audit-trained-native-precision-v2.py', 'operator_capture_buffer')
    policy = (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32)
    captures = []; calls = {'cpuTorch': 0, 'strictCuda': 0, 'ort': 0}
    try:
        root.mkdir(parents=True, exist_ok=False)
        graphs = []
        for i, model in enumerate(graph_models(plan)):
            path = root / f'operator-{i}.onnx'; onnx.save(model, path); graphs.append(d.bind(path))
        options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.log_severity_level = 3
        sessions = [ort.InferenceSession(str(d.checked(ref)), sess_options=options, providers=['CPUExecutionProvider']) for ref in graphs]
        torch.set_num_threads(4); torch.backends.cudnn.allow_tf32 = False; torch.backends.cuda.matmul.allow_tf32 = False
        state = torch.load(d.checked(plan['inputs']['trainedWeights']), map_location='cpu', weights_only=True)
        normalizers = {}
        for b, device in (('cpuTorch', 'cpu'), ('strictCuda', 'cuda')):
            gn = torch.nn.GroupNorm(4, 16, eps=1e-5).to(device).eval().requires_grad_(False)
            gn.load_state_dict({'weight': state['dec1.4.weight'], 'bias': state['dec1.4.bias']}, strict=True)
            normalizers[b] = gn
        for previous in layers['captures']:
            c = {'ordinal': previous['ordinal'], 'candidateIdentity': previous['candidateIdentity'], 'operations': {}}
            folder = root / f'{c["ordinal"]:03d}'; folder.mkdir()
            for i, (name, incoming, target) in enumerate(zip(plan['operations'], ('enc3.5', 'dec2.5', 'dec1.3'), ('enc2.5', 'enc1.5', 'dec1.4'), strict=True)):
                x = helper.read_tensor(buffer_helper, previous['strictCuda']['layers'][incoming])
                shape = previous['strictCuda']['layers'][target]['shape'][-2:]
                outputs = {}
                for b, device in (('cpuTorch', 'cpu'), ('strictCuda', 'cuda')):
                    calls[b] += 1
                    with torch.inference_mode():
                        tensor = torch.from_numpy(x).to(device)
                        value = F.interpolate(tensor, size=shape, mode='bilinear', align_corners=False) if i < 2 else normalizers[b](tensor)
                    outputs[b] = value.cpu().numpy()
                calls['ort'] += 1
                feed = {'x': x, 'sizes': np.array([*x.shape[:2], *shape], np.int64)} if i < 2 else {'/dec1/dec1.3/Conv_output_0': x}
                outputs['ort'] = sessions[i].run(None, feed)[0]
                if i == 2: helper.exact(helper.read_tensor(buffer_helper, previous['strictCuda']['layers']['dec1.4']), outputs['strictCuda'])
                c['operations'][name] = {b: helper.save(folder / f'{i}-{b}.bin', v) for b, v in outputs.items()}
            captures.append(c); d.new(folder / 'capture.json', c)
            if len(captures) % 16 == 0: print(json.dumps({'completedCandidates': len(captures), 'startedOperatorInputs': calls}), flush=True)
        if any(not torch.equal(v.cpu(), state['dec1.4.' + k]) for gn in normalizers.values() for k, v in gn.state_dict().items()):
            raise ValueError('normalization weights changed')
        result = reconstruct(plan_path, graphs, captures); d.new(root / 'report.json', result); return result
    except BaseException as error:
        if root.exists(): d.new(root / 'failure.json', {'ok': False, 'type': type(error).__name__, 'message': str(error),
            'completedCandidates': len(captures), 'startedOperatorInputs': calls, 'newFullModelInputs': 0, 'optimizerSteps': 0, 'productHold': True})
        raise
    finally:
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = policy


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--plan', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); a = p.parse_args()
    if a.verify_report:
        old = d.read(d.bind(a.verify_report)); d.checked(old['inputs']['auditor'])
        result = reconstruct(d.checked(old['inputs']['plan']), old['graphs'], old['captures'])
        if result != old: raise ValueError('operator report reconstruction_mismatch')
    else: result = run(a.plan.resolve(), a.output.resolve())
    print(json.dumps({k: result[k] for k in ('ok', 'summary', 'newFullModelInputs', 'optimizerSteps')}))
