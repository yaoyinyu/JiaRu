"""复用冻结原像素审计，仅替换已预注册的空间上下文构造器。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import onnx
import torch
import importlib.util


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


s = module('context_static_original', Path(__file__).with_name('audit-native-boundary-head-feasibility.py'))
a = s.a
h = module('context_static_model', Path(__file__).with_name('native-context-nail-refinement.py'))
original_validate, original_native_data, original_write = s.validate, s.native_data, a.write_new


def architecture_proof(seed):
    torch.manual_seed(seed)
    before = h.base.NativeBoundaryNailRefiner()
    torch.manual_seed(seed)
    after = h.NativeBoundaryNailRefiner()
    left, right = before.state_dict(), after.state_dict()
    if left.keys() != right.keys() or any(not torch.equal(left[k], right[k]) for k in left):
        raise ValueError('initial tensor identity')
    convs = [after.features[i] for i in (0, 3, 6)]
    if [c.dilation for c in convs] != [(1, 1), (3, 3), (9, 9)] or [c.padding for c in convs] != [c.dilation for c in convs]:
        raise ValueError('context dilation/padding')
    count = sum(p.numel() for p in after.parameters())
    if count != 20385 or any(c.kernel_size != (3, 3) for c in convs):
        raise ValueError('unchanged parameter/kernel contract')
    return {'seed': seed, 'initialTensorsExactlyEqual': True, 'stateTensorCount': len(right),
            'parameterCount': count, 'oldDilations': [1, 1, 1], 'newDilations': [1, 3, 9],
            'convolutionSpatialReceptiveField': 27,
            'scope': 'Only convolution dilation/padding changes; GroupNorm still uses whole-ROI statistics. No learned quality proof.'}


def validate(plan):
    parent, records = original_validate(plan)
    scope = a.read(a.checked(plan['inputs']['contextScope']))
    for binding in scope['inputs'].values():
        a.checked(binding)
    if scope['candidateIds'] != parent['candidateIds'] or scope['qualityGatesUnchanged'] != parent['qualityGatesUnchanged']:
        raise ValueError('context scope/gates/denominator')
    if scope['modelChange']['newDilations'] != [1, 3, 9] or scope['modelChange']['oldDilations'] != [1, 1, 1]:
        raise ValueError('preregistered context variable')
    if scope['inputs']['parentPlan'] != plan['inputs']['parentPlan'] or scope['inputs']['oldHeadSource'] != parent['inputs']['headSource']:
        raise ValueError('frozen parent/base head identity')
    for key, path in [('contextSource', Path(h.__file__)), ('staticAuditor', Path(__file__)), ('originalStaticAuditor', Path(s.__file__))]:
        if plan['inputs'][key] != a.bind(path):
            raise ValueError('executed source not bound: ' + key)
    if scope['reachability']['witnessJointCount'] < scope['reachability']['requiredCount']:
        raise ValueError('unreachable')
    architecture_proof(parent['model']['seed'])
    return parent, records


def native_data(parent, records):
    _, data = original_native_data(parent, records)
    # PIL的F模式数组只读；复制保持相同字节，避免Torch误用不可写数组。
    for item in data:
        item['base'] = item['base'].copy()
    return h, data


def write(path, report):
    if Path(path).name == 'feasibility-report.json':
        plan = a.read(report['inputs']['plan']['path'])
        parent, _ = validate(plan)
        report = {**report, 'architecture': architecture_proof(parent['model']['seed'])}
    return original_write(path, report)


def verify(path):
    result = s.verify(path)
    saved = a.read(path)
    plan = a.read(saved['inputs']['plan']['path'])
    parent, _ = validate(plan)
    if saved['architecture'] != architecture_proof(parent['model']['seed']):
        raise ValueError('architecture proof mismatch')
    for info in saved['models'].values():
        graph = onnx.load(str(a.checked(info['file'])))
        convs = [node for node in graph.graph.node if node.op_type == 'Conv']
        dilation = [list(next(attr.ints for attr in node.attribute if attr.name == 'dilations')) for node in convs]
        if dilation != [[1, 1], [3, 3], [9, 9], [1, 1]]:
            raise ValueError('ONNX did not implement preregistered dilations')
    return {**result, 'architecture': saved['architecture']}


s.validate, s.native_data, a.write_new = validate, native_data, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    plan_path = args.plan.resolve() if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path'])
    parent = a.read(a.read(plan_path)['inputs']['parentPlan']['path'])
    guard = module('context_static_guard', Path(__file__).with_name('train-yolo-seg.py'))
    guard.install_read_only_ultralytics_image_check()
    try:
        if args.verify_report:
            result = verify(args.verify_report)
        else:
            report = s.audit(plan_path, args.output.resolve())
            result = {'decision': report['decision'], 'gradientCount': report['gradient']['candidateCount'],
                      'report': a.bind(args.output.resolve() / 'feasibility-report.json')}
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        for directory in parent['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(directory))


if __name__ == '__main__':
    main()
