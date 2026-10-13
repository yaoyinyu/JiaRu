"""全候选两头保真后重放逐层误差；只增加ONNX输出，不改权重或发布门。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('layerwise_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s)
s.loader.exec_module(d)


def validate_scope(plan):
    if plan['purpose'] != 'full68_layerwise_numeric_localization_zero_optimizer':
        raise ValueError('layerwise purpose')
    if any(plan[k] != 68 for k in ('requiredFullCandidateDenominator', 'cpuTorchNativeInputsAllowed',
                                  'strictCudaNativeInputsAllowed', 'instrumentedOrtNativeInputsAllowed')):
        raise ValueError('complete denominator')
    if any(plan[k] != 0 for k in ('optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed')):
        raise ValueError('zero optimization train-only scope')
    if plan['inferencePolicy'] != {'cudnnAllowTf32': False, 'matmulAllowTf32': False}:
        raise ValueError('strict precision policy')
    if plan['ortGraphOptimizationLevel'] != 'ORT_DISABLE_ALL' or plan['requiredNumericDifference'] != 1e-4 or plan['requiredDecodedPixelDifferences'] != 0:
        raise ValueError('frozen numeric contract')
    for key in ('instrumentationMayAddOutputsOnly', 'allFinalOutputsMustMatchUninstrumentedBackendBeforeLayerConclusions',
                'mustBindLayerNamesShapesFloat32AndBothHeadsFinite', 'weightsThresholdsCandidatesTruthAndOriginalFailuresUnchanged',
                'revisedExportRequiresNonzeroUntrainedControlsAndFull68Parity', 'browserAndInternalValRequireNewIndependentDeploymentGatePass', 'productHold'):
        if plan[key] is not True:
            raise ValueError('required instrumentation/quality guard')
    if plan['formalReleaseAllowed'] is not False:
        raise ValueError('formal release prohibited')


def resources(plan_path):
    plan = d.read(d.bind(plan_path))
    validate_scope(plan)
    for ref in plan['inputs'].values():
        d.checked(ref)
    strict = d.read(plan['inputs']['strictReference'])
    helper = d.load(d.checked(strict['inputs']['auditor']), 'layerwise_precision')
    if strict != helper.reconstruct(d.checked(strict['inputs']['plan']), strict['captures']):
        raise ValueError('strict reference reconstruction_mismatch')
    old = d.read(plan['inputs']['oldExport'])
    ablation = d.read(plan['inputs']['optimizationAblation'])
    ablation_helper = d.load(d.checked(ablation['inputs']['auditor']), 'layerwise_ablation')
    if ablation != ablation_helper.reconstruct(d.checked(ablation['inputs']['plan']), ablation['captures']):
        raise ValueError('uninstrumented reference reconstruction_mismatch')
    _, _, _, scope, _, rows, net, _, guard, native = helper.resources(d.checked(strict['inputs']['plan']))
    try:
        if plan['candidateIdentities'] != [r['candidateIdentity'] for r in rows] or plan['inputs']['trainedWeights'] != strict['sameWeights'] or plan['inputs']['onnx'] != old['inputs']['onnx'] or d.bind(plan['inputs']['scope']['path']) != old['inputs']['scope']:
            raise ValueError('all68 scope/weights/ONNX reconstruction_mismatch')
        if any(r['candidateIdentity']['identity']['split'] != 'train' for r in rows):
            raise ValueError('train-only identities')
        return plan, helper, strict, old, ablation, net, guard, native
    except BaseException:
        cleanup(guard, native)
        raise


def cleanup(guard, native):
    for path in native['cacheCleanupRoots']:
        guard.remove_ultralytics_label_caches(Path(path))


def layer_map(graph):
    nodes = {n.name: n for n in graph.node}
    if len(nodes) != len(graph.node):
        raise ValueError('duplicate ONNX node names')
    mapping = []
    for block in ('enc1', 'enc2', 'enc3', 'dec2', 'dec1'):
        for index, operation in enumerate(('Conv', 'Add', 'Mul_1', 'Conv', 'Add', 'Mul_1')):
            module = f'{block}.{index}'
            node = nodes[f'/{block}/{module}/{operation}']
            mapping.append({'module': module, 'node': node.name, 'tensor': node.output[0],
                            'operation': ('Conv2d', 'GroupNorm', 'GELU')[index % 3]})
    mapping.append({'module': 'delta', 'node': '/delta/Conv', 'tensor': nodes['/delta/Conv'].output[0], 'operation': 'Conv2d'})
    return mapping


def instrument(model):
    original = onnx.ModelProto()
    original.CopyFrom(model)
    mapping = layer_map(model.graph)
    for item in mapping:
        model.graph.output.append(onnx.helper.make_tensor_value_info(item['tensor'], onnx.TensorProto.FLOAT, ['batch', 'channels', 'height', 'width']))
    stripped = onnx.ModelProto()
    stripped.CopyFrom(model)
    del stripped.graph.output[len(original.graph.output):]
    if stripped.SerializeToString() != original.SerializeToString():
        raise ValueError('instrumentation changed graph beyond added outputs')
    onnx.checker.check_model(model)
    return mapping


def finite(value):
    if value.dtype != np.float32 or not np.isfinite(value).all():
        raise ValueError('nonfinite or non-float32 layer')


def exact(reference, actual):
    finite(reference)
    finite(actual)
    if reference.shape != actual.shape or reference.tobytes() != actual.tobytes():
        raise ValueError('reconstruction_mismatch: instrumented final heads changed')


def save(path, value):
    finite(value)
    with path.open('xb') as stream:
        stream.write(value.tobytes()); stream.flush(); os.fsync(stream.fileno())
    return {**d.bind(path), 'shape': list(value.shape), 'dtype': 'float32'}


def read_tensor(helper, ref):
    if ref['dtype'] != 'float32' or any(type(n) != int or n <= 0 for n in ref['shape']):
        raise ValueError('invalid float32 tensor shape')
    return helper.buffer(ref, int(np.prod(ref['shape']))).reshape(ref['shape'])


def differences(a, b):
    finite(a); finite(b)
    if a.shape != b.shape:
        raise ValueError('layer shape reconstruction_mismatch')
    error = np.abs(a.astype(np.float64) - b.astype(np.float64))
    return {'maxAbs': float(error.max()), 'meanAbs': float(error.mean()),
            'valuesAbove1e4': int((error > 1e-4).sum()), 'valueCount': int(error.size)}


def final_check(helper, captured, strict, old, ablation):
    h, w = old['h'], old['w']
    refs = {'cpuTorch': (strict['paths']['cpu-mask'], strict['paths']['cpu-presence']),
            'strictCuda': (strict['paths']['strict-mask'], strict['paths']['strict-presence']),
            'ort': (ablation['mask'], ablation['presence'])}
    for backend, (mask, presence) in refs.items():
        exact(helper.buffer(mask, h*w).reshape(1, 1, h, w), read_tensor(helper, captured[backend]['mask']))
        exact(helper.buffer(presence, 1).reshape(1, 1), read_tensor(helper, captured[backend]['presence']))


def reconstruct(plan_path, instrumented_ref, captures):
    plan, helper, strict, old, ablation, _, guard, native = resources(plan_path)
    try:
        instrumented = onnx.load(d.checked(instrumented_ref))
        original = onnx.load(d.checked(plan['inputs']['onnx']))
        mapping = instrument(original)
        if original.SerializeToString() != instrumented.SerializeToString():
            raise ValueError('instrumented graph reconstruction_mismatch')
        if len(captures) != 68 or [c['candidateIdentity'] for c in captures] != plan['candidateIdentities'] or [c['ordinal'] for c in captures] != [r['ordinal'] for r in old['records']]:
            raise ValueError('full capture identities/ordinals reconstruction_mismatch')
        # 全68、所有后端的最终两头先逐字节保真，任何失败禁止解释中间层。
        for c, r, o, a in zip(captures, strict['captures'], old['records'], ablation['captures'], strict=True):
            final_check(helper, c, r, o, a)
        records = []
        for captured in captures:
            if any(list(captured[b]['layers']) != [m['module'] for m in mapping] for b in ('cpuTorch', 'strictCuda', 'ort')):
                raise ValueError('full ordered layer map')
            layers = []
            for item in mapping:
                values = {b: read_tensor(helper, captured[b]['layers'][item['module']]) for b in ('cpuTorch', 'strictCuda', 'ort')}
                layers.append({**item, 'shape': list(values['ort'].shape),
                               'strictCudaVsOrt': differences(values['strictCuda'], values['ort']),
                               'cpuTorchVsOrt': differences(values['cpuTorch'], values['ort']),
                               'strictCudaVsCpuTorch': differences(values['strictCuda'], values['cpuTorch'])})
            records.append({'candidateIdentity': captured['candidateIdentity'], 'ordinal': captured['ordinal'],
                            'firstStrictCudaLayerAbove1e4': next((l['module'] for l in layers if l['strictCudaVsOrt']['maxAbs'] > 1e-4), None), 'layers': layers})
        summary = [{**item, **{label: {'maxAbs': max(r['layers'][i][label]['maxAbs'] for r in records),
                                      'candidateCountAbove1e4': sum(r['layers'][i][label]['maxAbs'] > 1e-4 for r in records)}
                               for label in ('strictCudaVsOrt', 'cpuTorchVsOrt', 'strictCudaVsCpuTorch')}} for i, item in enumerate(mapping)]
        return {'schemaVersion': 1, 'ok': True, 'decision': 'layerwise_numeric_diagnostic_reconstructed',
                'inputs': {'plan': d.bind(plan_path), 'auditor': d.bind(__file__), 'instrumentedOnnx': instrumented_ref},
                'captures': captures, 'records': records, 'layerSummary': summary,
                'instrumentationFinalHeadsBitwiseIdenticalAllBackends': True, 'fullCandidateCount': 68,
                'newCpuTorchInputs': 68, 'newStrictCudaInputs': 68, 'newInstrumentedOrtInputs': 68,
                'optimizerSteps': 0, 'valModelInputs': 0, 'protectedModelInputs': 0,
                'oldNumericalFailuresPreserved': True, 'strictFp32CpuGatePassed': False,
                'browserAdmitted': False, 'formalReleaseAllowed': False, 'productHold': True}
    finally:
        cleanup(guard, native)


def run(plan_path, root):
    if root.exists():
        raise ValueError('output exists; use read-only replay')
    plan, helper, strict, old, ablation, net, guard, native = resources(plan_path)
    policy = (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32)
    captures = []
    calls = {'cpuTorch': 0, 'strictCuda': 0, 'ort': 0}
    handles = []
    try:
        root.mkdir(parents=True, exist_ok=False)
        graph = onnx.load(d.checked(plan['inputs']['onnx']))
        mapping = instrument(graph)
        instrumented_path = root / 'instrumented.onnx'
        onnx.save(graph, instrumented_path)
        options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(str(instrumented_path), sess_options=options, providers=['CPUExecutionProvider'])
        torch.set_num_threads(4)
        torch.backends.cudnn.allow_tf32 = False; torch.backends.cuda.matmul.allow_tf32 = False
        state = torch.load(d.checked(plan['inputs']['trainedWeights']), map_location='cpu', weights_only=True)
        models = {b: net.NativeConditionalMaskRefiner().to(device).eval().requires_grad_(False)
                  for b, device in (('cpuTorch', 'cpu'), ('strictCuda', 'cuda'))}
        hooked = {b: {} for b in models}
        for backend, model in models.items():
            model.load_state_dict(state, strict=True)
            for item in mapping:
                name = item['module']
                def hook(module, arguments, output, b=backend, n=name):
                    hooked[b][n] = output.detach().cpu().numpy().copy()
                handles.append(model.get_submodule(name).register_forward_hook(hook))
        for previous, reference, baseline in zip(old['records'], strict['captures'], ablation['captures'], strict=True):
            h, w = previous['h'], previous['w']
            x = helper.buffer(previous['paths']['input'], 4*h*w).reshape(1, 4, h, w)
            captured = {'candidateIdentity': previous['candidateIdentity'], 'ordinal': previous['ordinal']}
            folder = root / f'{previous["ordinal"]:03d}'; folder.mkdir()
            for backend, model in models.items():
                hooked[backend].clear(); calls[backend] += 1
                with torch.inference_mode():
                    mask, presence = model(torch.from_numpy(x).to(next(model.parameters()).device))
                captured[backend] = {name: save(folder / f'{backend}-{name}.bin', value.detach().cpu().numpy())
                                     for name, value in (('mask', mask), ('presence', presence))}
                captured[backend]['layers'] = {name: save(folder / f'{backend}-{name}.bin', value) for name, value in hooked[backend].items()}
            calls['ort'] += 1
            values = session.run(None, {'candidate': x})
            captured['ort'] = {'mask': save(folder / 'ort-mask.bin', values[0]), 'presence': save(folder / 'ort-presence.bin', values[1]),
                               'layers': {item['module']: save(folder / f'ort-{item["module"]}.bin', value) for item, value in zip(mapping, values[2:], strict=True)}}
            final_check(helper, captured, reference, previous, baseline)
            captures.append(captured)
            d.new(folder / 'capture.json', captured)
            print(json.dumps({'capturedCandidates': len(captures), 'startedModelInputs': calls, 'optimizerSteps': 0}), flush=True)
        for model in models.values():
            if any(not torch.equal(v.cpu(), state[k]) for k, v in model.state_dict().items()):
                raise ValueError('weights changed')
        result = reconstruct(plan_path, d.bind(instrumented_path), captures)
        d.new(root / 'report.json', result)
        return result
    except BaseException as error:
        if root.exists():
            d.new(root / 'failure.json', {'ok': False, 'type': type(error).__name__, 'message': str(error),
                                        'completedCandidates': len(captures), 'startedModelInputs': calls,
                                        'optimizerSteps': 0, 'layerConclusionsAllowed': False, 'productHold': True})
        raise
    finally:
        for handle in handles:
            handle.remove()
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = policy
        cleanup(guard, native)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path); parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = d.read(d.bind(args.verify_report)); d.checked(previous['inputs']['auditor'])
        result = reconstruct(d.checked(previous['inputs']['plan']), previous['inputs']['instrumentedOnnx'], previous['captures'])
        if result != previous:
            raise ValueError('layerwise reconstruction_mismatch')
    else:
        result = run(args.plan.resolve(), args.output.resolve())
    print(json.dumps({k: result[k] for k in ('ok', 'decision', 'instrumentationFinalHeadsBitwiseIdenticalAllBackends', 'optimizerSteps')}))
