"""两处Resize表达修复按算子、非零控制、全候选CPU门串行验真。"""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('resize_repair_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)


def validate(scope):
    expected = {'purpose': 'same_weights_resize_expression_repair_then_full68_cpu_gate', 'fullCandidateCount': 68,
        'targetResizeNodes': ['/Resize', '/Resize_1'], 'operatorRepairInputsAllowed': 136,
        'operatorDiagnosticMaximumDifference': 2e-5, 'learnedCpuOrtInputsAllowedAfterControls': 68,
        'newLearnedTorchInputsAllowed': 0, 'nonzeroUntrainedTorchControlsAllowed': 68,
        'nonzeroUntrainedOrtControlsAllowed': 68, 'requiredFullModelNumericDifference': 1e-4,
        'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
        'optimizerStepsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'browserInputsAllowed': 0,
        'allOriginalNativeShapesRequired': True, 'nonzeroControlMayNotSelectModelQuality': True,
        'oldFailedOnnxAndAllFailuresPreserved': True, 'formalReleaseAllowed': False, 'productHold': True}
    if any(scope[k] != value for k, value in expected.items()):
        raise ValueError('frozen full68 repair/budget/quality contract')
    if scope['semanticContract'] != {'mode': 'bilinear', 'alignCorners': False, 'size': 'frozen native target feature dimensions',
        'coordinateOrder': 'float32 input/output ratio then ratio*(destination+0.5)-0.5 then clamp below zero',
        'sameBoundaryClamping': True, 'sameNormalizationEpsilonAndLearnedAffine': True, 'sameConvAndPresenceParameters': True}:
        raise ValueError('frozen Resize semantics')


def resources(plan_path):
    execution = d.read(d.bind(plan_path))
    if execution['purpose'] != 'execute_frozen_resize_repair_with_deterministic_nonzero_control' or execution['controlProtocol'] != {'seed': 20261013, 'deltaWeight': 'sin(arange+1)*0.125', 'deltaBias': 0.125, 'presenceWeight': 'cos(arange+1)*0.025', 'presenceBias': 2.0, 'strictCudaTf32': False, 'exportTraceShape': [1, 4, 128, 128]}:
        raise ValueError('frozen nonzero control protocol')
    for ref in execution['inputs'].values(): d.checked(ref)
    scope = d.read(execution['inputs']['scope']); validate(scope)
    for ref in scope['inputs'].values(): d.checked(ref)
    strict = d.read(scope['inputs']['strictReference'])
    helper = d.load(d.checked(strict['inputs']['auditor']), 'resize_repair_precision')
    if strict != helper.reconstruct(d.checked(strict['inputs']['plan']), strict['captures']) or not strict['strictFp32CapacityPassed']:
        raise ValueError('strict full68 reference reconstruction_mismatch')
    _, old, _, prior_scope, _, rows, net, _, guard, native = helper.resources(d.checked(strict['inputs']['plan']))
    try:
        layers = d.read(scope['inputs']['layerReport']); operators = d.read(scope['inputs']['operatorReport'])
        if not layers['ok'] or not operators['ok'] or not layers['instrumentationFinalHeadsBitwiseIdenticalAllBackends']:
            raise ValueError('layerwise diagnostic scope')
        if scope['candidateIdentities'] != [r['candidateIdentity'] for r in old['records']] or len(rows) != 68 or any(r['candidateIdentity']['identity']['split'] != 'train' for r in rows):
            raise ValueError('all68 train-only identities')
        if scope['inputs']['trainedWeights'] != strict['sameWeights'] or scope['inputs']['oldOnnx'] != old['inputs']['onnx'] or prior_scope['candidateIdentities'] != scope['candidateIdentities']:
            raise ValueError('same learned weights/ONNX')
        if any([r['candidateIdentity'] for r in report['captures']] != scope['candidateIdentities'] for report in (layers, operators)):
            raise ValueError('frozen tensor identities')
        rewriter = d.load(d.checked(execution['inputs']['rewriter']), 'resize_repair_rewriter')
        layer_helper = d.load(d.checked(layers['inputs']['auditor']), 'resize_repair_layer_helper')
        return execution, scope, helper, old, strict, layers, operators, net, guard, native, rewriter, layer_helper
    except BaseException:
        cleanup(guard, native); raise


def cleanup(guard, native):
    for path in native['cacheCleanupRoots']: guard.remove_ultralytics_label_caches(Path(path))


def session(ref):
    options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL; options.log_severity_level = 3
    return ort.InferenceSession(str(d.checked(ref)), sess_options=options, providers=['CPUExecutionProvider'])


def control_model(net, protocol):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(protocol['seed'])
        model = net.NativeConditionalMaskRefiner().cpu().eval().requires_grad_(False)
        with torch.no_grad():
            model.delta.weight.copy_(torch.sin(torch.arange(model.delta.weight.numel(), dtype=torch.float32) + 1).reshape_as(model.delta.weight)*.125)
            model.delta.bias.fill_(.125)
            model.presence.weight.copy_(torch.cos(torch.arange(model.presence.weight.numel(), dtype=torch.float32) + 1).reshape_as(model.presence.weight)*.025)
            model.presence.bias.fill_(2.)
    return model


def compare_heads(helper, actual, reference_mask, reference_presence, h, w):
    mask = helper.buffer(actual['mask'], h*w); presence = helper.buffer(actual['presence'], 1)
    return helper.compare.compare_outputs(reference_mask, reference_presence, mask, presence, h, w)


def heads_pass(stats):
    return all(stats[k] for k in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched'))


def reconstruct(plan_path, artifacts, captures):
    execution, scope, helper, old, strict, layers, operators, net, guard, native, rewrite, layer_helper = resources(plan_path)
    try:
        if len(captures['operators']) != 68 or [c['candidateIdentity'] for c in captures['operators']] != scope['candidateIdentities']:
            raise ValueError('complete operator captures')
        expected = onnx.load(d.checked(scope['inputs']['oldOnnx'])); rewrite.rewrite_model(expected)
        if expected.SerializeToString() != onnx.load(d.checked(artifacts['learnedOnnx'])).SerializeToString():
            raise ValueError('only targeted learned Resize expressions may change')
        for i, ref in enumerate(artifacts['operatorOnnx']):
            expected = onnx.load(d.checked(operators['graphs'][i])); rewrite.rewrite_model(expected, (scope['targetResizeNodes'][i],))
            if expected.SerializeToString() != onnx.load(d.checked(ref)).SerializeToString(): raise ValueError('isolated rewritten graph mismatch')
        operator_stats = []
        for c, previous in zip(captures['operators'], operators['captures'], strict=True):
            if c['ordinal'] != previous['ordinal'] or len(c['outputs']) != 2: raise ValueError('operator ordinals')
            stats = []
            for i, name in enumerate(('resize_e3_to_e2', 'resize_d2_to_e1')):
                expected = layer_helper.read_tensor(helper, previous['operations'][name]['strictCuda'])
                actual = layer_helper.read_tensor(helper, c['outputs'][i])
                stats.append(layer_helper.differences(expected, actual))
            operator_stats.append({'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'operators': stats})
        operator_pass = all(s['maxAbs'] <= 2e-5 for c in operator_stats for s in c['operators'])
        operator_max = [max(c['operators'][i]['maxAbs'] for c in operator_stats) for i in range(2)]
        control_stats = []; learned_stats = []
        if captures['controls']:
            if not operator_pass or len(captures['controls']) != 68 or [c['candidateIdentity'] for c in captures['controls']] != scope['candidateIdentities']:
                raise ValueError('controls require full operator gate')
            control_expected = onnx.load(d.checked(artifacts['controlBaseOnnx']))
            rewrite.rewrite_model(control_expected)
            if control_expected.SerializeToString() != onnx.load(d.checked(artifacts['controlOnnx'])).SerializeToString():
                raise ValueError('nonzero control graph expression binding')
            model = control_model(net, execution['controlProtocol'])
            saved = torch.load(d.checked(artifacts['controlWeights']), map_location='cpu', weights_only=True)
            if set(saved) != set(model.state_dict()) or any(not torch.equal(v, saved[k]) for k, v in model.state_dict().items()):
                raise ValueError('deterministic nonzero untrained control weights')
            if not saved['delta.weight'].any() or not saved['presence.weight'].any(): raise ValueError('nonzero branches required')
            for c, previous in zip(captures['controls'], old['records'], strict=True):
                h, w = previous['h'], previous['w']
                if c['ordinal'] != previous['ordinal']: raise ValueError('control ordinals')
                reference_mask = helper.buffer(c['torch']['mask'], h*w)
                reference_presence = helper.buffer(c['torch']['presence'], 1)
                stats = compare_heads(helper, c['ort'], reference_mask, reference_presence, h, w)
                x = helper.buffer(previous['paths']['input'], 4*h*w).reshape(1, 4, h, w)
                delta_max = float(np.max(np.abs(reference_mask - (x[:, 3:4]*8-4).reshape(-1))))
                control_stats.append({'candidateIdentity': c['candidateIdentity'], 'ordinal': c['ordinal'], 'parity': stats, 'nonzeroDeltaMaxAbs': delta_max})
        control_pass = len(control_stats) == 68 and all(heads_pass(c['parity']) and c['nonzeroDeltaMaxAbs'] > 0 for c in control_stats)
        if captures['learned']:
            if not control_pass or len(captures['learned']) != 68 or [c['candidateIdentity'] for c in captures['learned']] != scope['candidateIdentities']:
                raise ValueError('learned inference requires nonzero control gate')
            for c, r, previous in zip(captures['learned'], strict['captures'], old['records'], strict=True):
                h, w = previous['h'], previous['w']
                if c['ordinal'] != previous['ordinal']: raise ValueError('learned ordinals')
                stats = compare_heads(helper, c, helper.buffer(r['paths']['strict-mask'], h*w), helper.buffer(r['paths']['strict-presence'], 1), h, w)
                learned_stats.append({'candidateIdentity': c['candidateIdentity'], 'ordinal': c['ordinal'], 'parity': stats})
        learned_pass = len(learned_stats) == 68 and all(heads_pass(c['parity']) for c in learned_stats)
        summaries = {label: {'count': len(records), 'maxAbs': max((r['parity']['maxAbsoluteDifference'] for r in records), default=None),
            'numericFailed': sum(not r['parity']['numericGatePassed'] for r in records),
            'pixelDifferences': sum(r['parity']['decodedMaskPixelDifference'] for r in records),
            'presenceFailed': sum(not r['parity']['presenceDecisionMatched'] for r in records)} for label, records in (('control', control_stats), ('learned', learned_stats))}
        return {'schemaVersion': 1, 'ok': True, 'decision': 'resize_repaired_cpu68_pass_browser_pending' if learned_pass else 'resize_repair_reconstructed_gate_failed',
            'inputs': {'execution': d.bind(plan_path), 'auditor': d.bind(__file__)}, 'artifacts': artifacts, 'captures': captures,
            'operatorRecords': operator_stats, 'controlRecords': control_stats, 'learnedRecords': learned_stats, 'summary': summaries,
            'operatorMaxAbs': operator_max, 'operatorStagePassed': operator_pass, 'nonzeroControlGatePassed': control_pass,
            'learnedCpuGatePassed': learned_pass, 'newOperatorOrtInputs': len(captures['operators'])*2,
            'newControlTorchInputs': len(captures['controls']), 'newControlOrtInputs': len(captures['controls']),
            'exportTraceInputs': 1 if captures['controls'] else 0,
            'newLearnedOrtInputs': len(captures['learned']), 'newLearnedTorchInputs': 0, 'optimizerSteps': 0,
            'valModelInputs': 0, 'protectedModelInputs': 0, 'browserInputs': 0, 'oldFailuresPreserved': True,
            'browserEligibleForNewScope': learned_pass, 'formalReleaseAllowed': False, 'productHold': True}
    finally:
        cleanup(guard, native)


def run(plan_path, root):
    if root.exists(): raise ValueError('output exists; use read-only replay')
    execution, scope, helper, old, strict, layers, operators, net, guard, native, rewrite, layer_helper = resources(plan_path)
    policy = (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32)
    captures = {'operators': [], 'controls': [], 'learned': []}; artifacts = {}
    calls = {'operatorOrt': 0, 'controlTorch': 0, 'controlOrt': 0, 'learnedOrt': 0, 'exportTrace': 0}
    try:
        root.mkdir(exist_ok=False, parents=True)
        learned_graph = onnx.load(d.checked(scope['inputs']['oldOnnx'])); rewrite.rewrite_model(learned_graph)
        path = root / 'learned-resize-repaired.onnx'; onnx.save(learned_graph, path); artifacts['learnedOnnx'] = d.bind(path)
        artifacts['operatorOnnx'] = []
        for i in range(2):
            graph = onnx.load(d.checked(operators['graphs'][i])); rewrite.rewrite_model(graph, (scope['targetResizeNodes'][i],))
            path = root / f'operator-{i}.onnx'; onnx.save(graph, path); artifacts['operatorOnnx'].append(d.bind(path))
        sessions = [session(ref) for ref in artifacts['operatorOnnx']]
        for c, previous in zip(layers['captures'], operators['captures'], strict=True):
            folder = root / f'{c["ordinal"]:03d}'; folder.mkdir()
            outputs = []
            for i, (name, incoming, target) in enumerate(zip(('resize_e3_to_e2', 'resize_d2_to_e1'), ('enc3.5', 'dec2.5'), ('enc2.5', 'enc1.5'), strict=True)):
                x = layer_helper.read_tensor(helper, c['strictCuda']['layers'][incoming])
                sizes = np.array([*x.shape[:2], *c['strictCuda']['layers'][target]['shape'][-2:]], np.int64)
                calls['operatorOrt'] += 1
                actual = sessions[i].run(None, {'x': x, 'sizes': sizes})[0]
                outputs.append(layer_helper.save(folder / f'operator-{i}.bin', actual))
            record = {'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'outputs': outputs}
            captures['operators'].append(record); d.new(folder / 'operators.json', record)
            if len(captures['operators']) % 16 == 0: print(json.dumps({'phase': 'operators', 'completedCandidates': len(captures['operators'])}), flush=True)
        preliminary = reconstruct(plan_path, artifacts, captures)
        d.new(root / 'operator-report.json', preliminary)
        if not preliminary['operatorStagePassed']:
            d.new(root / 'report.json', preliminary); return preliminary
        torch.set_num_threads(4); torch.backends.cudnn.allow_tf32 = False; torch.backends.cuda.matmul.allow_tf32 = False
        model = control_model(net, execution['controlProtocol'])
        control_weights = root / 'nonzero-untrained-control.pt'; torch.save(model.state_dict(), control_weights)
        artifacts['controlWeights'] = d.bind(control_weights)
        control_path = root / 'nonzero-untrained-control.onnx'; calls['exportTrace'] += 1
        torch.onnx.export(model, torch.zeros(1, 4, 128, 128), str(control_path), input_names=['candidate'], output_names=['mask_logits', 'presence_logit'],
            dynamic_axes={'candidate': {2: 'height', 3: 'width'}, 'mask_logits': {2: 'height', 3: 'width'}}, opset_version=18, dynamo=False)
        normalization = d.load(d.checked(scope['inputs']['normalizationRewrite']), 'resize_control_normalization')
        normalization.rewrite(control_path)
        graph = onnx.load(control_path)
        base_path = root / 'nonzero-untrained-control-base.onnx'; onnx.save(graph, base_path); artifacts['controlBaseOnnx'] = d.bind(base_path)
        rewrite.rewrite_model(graph); onnx.save(graph, control_path)
        artifacts['controlOnnx'] = d.bind(control_path)
        control_session = session(artifacts['controlOnnx']); model.cuda().eval()
        for previous in old['records']:
            h, w = previous['h'], previous['w']; x = helper.buffer(previous['paths']['input'], 4*h*w).reshape(1, 4, h, w)
            folder = root / f'{previous["ordinal"]:03d}'
            calls['controlTorch'] += 1
            with torch.inference_mode(): torch_mask, torch_presence = model(torch.from_numpy(x).cuda())
            calls['controlOrt'] += 1
            ort_mask, ort_presence = control_session.run(None, {'candidate': x})
            record = {'candidateIdentity': previous['candidateIdentity'], 'ordinal': previous['ordinal']}
            for backend, values in (('torch', (torch_mask.cpu().numpy(), torch_presence.cpu().numpy())), ('ort', (ort_mask, ort_presence))):
                if values[0].shape != (1, 1, h, w) or values[1].shape != (1, 1): raise ValueError('native control heads shape')
                record[backend] = {name: layer_helper.save(folder / f'control-{backend}-{name}.bin', value) for name, value in zip(('mask', 'presence'), values, strict=True)}
            captures['controls'].append(record); d.new(folder / 'controls.json', record)
            if len(captures['controls']) % 16 == 0: print(json.dumps({'phase': 'nonzeroControl', 'completedCandidates': len(captures['controls'])}), flush=True)
        saved = torch.load(d.checked(artifacts['controlWeights']), map_location='cpu', weights_only=True)
        if any(not torch.equal(v.cpu(), saved[k]) for k, v in model.state_dict().items()): raise ValueError('control weights changed')
        control_result = reconstruct(plan_path, artifacts, captures); d.new(root / 'control-report.json', control_result)
        if not control_result['nonzeroControlGatePassed']:
            d.new(root / 'report.json', control_result); return control_result
        learned_session = session(artifacts['learnedOnnx'])
        for previous in old['records']:
            h, w = previous['h'], previous['w']; x = helper.buffer(previous['paths']['input'], 4*h*w).reshape(1, 4, h, w)
            calls['learnedOrt'] += 1
            mask, presence = learned_session.run(None, {'candidate': x})
            if mask.shape != (1, 1, h, w) or presence.shape != (1, 1): raise ValueError('native learned heads shape')
            folder = root / f'{previous["ordinal"]:03d}'
            record = {'candidateIdentity': previous['candidateIdentity'], 'ordinal': previous['ordinal'],
                'mask': layer_helper.save(folder / 'learned-mask.bin', mask), 'presence': layer_helper.save(folder / 'learned-presence.bin', presence)}
            captures['learned'].append(record); d.new(folder / 'learned.json', record)
            if len(captures['learned']) % 16 == 0: print(json.dumps({'phase': 'learnedCpu', 'completedCandidates': len(captures['learned'])}), flush=True)
        result = reconstruct(plan_path, artifacts, captures); d.new(root / 'report.json', result); return result
    except BaseException as error:
        if root.exists(): d.new(root / 'failure.json', {'ok': False, 'type': type(error).__name__, 'message': str(error),
            'startedCalls': calls, 'completedCounts': {k: len(v) for k, v in captures.items()}, 'optimizerSteps': 0, 'productHold': True})
        raise
    finally:
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = policy
        cleanup(guard, native)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--plan', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); a = p.parse_args()
    if a.verify_report:
        old = d.read(d.bind(a.verify_report)); d.checked(old['inputs']['auditor'])
        result = reconstruct(d.checked(old['inputs']['execution']), old['artifacts'], old['captures'])
        if result != old: raise ValueError('resize repair reconstruction_mismatch')
    else: result = run(a.plan.resolve(), a.output.resolve())
    print(json.dumps({k: result[k] for k in ('ok', 'decision', 'operatorMaxAbs', 'nonzeroControlGatePassed', 'learnedCpuGatePassed', 'summary', 'optimizerSteps')}))
