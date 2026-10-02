"""空间上下文单变量的一次容量训练；复用冻结优化/损失/终评/事件协议。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import importlib.util


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


t = module('context_microfit_original', Path(__file__).with_name('train-native-boundary-head-microfit.py'))
c = module('context_microfit_static', Path(__file__).with_name('audit-native-context-head-feasibility.py'))
a = t.a
original_validate, original_write = t.validate, t.j.write_durable_new
t.s.validate, t.s.native_data = c.validate, c.native_data


def validate(plan):
    result = original_validate(plan)
    previous = a.read(a.checked(plan['inputs']['previousCapacityPlan']))
    if any(plan[key] != previous[key] for key in ('training', 'loss', 'gates', 'candidateIds', 'approval', 'maximumExperiments', 'upstreamModelCalls')):
        raise ValueError('single variable changed training/loss/gates/budget')
    for key, path in [('trainerSource', Path(__file__)), ('originalTrainerSource', Path(t.__file__)), ('contextSource', Path(c.h.__file__))]:
        if plan['inputs'][key] != a.bind(path):
            raise ValueError('executed source not bound: ' + key)
    static = a.read(plan['inputs']['staticReport']['path'])
    if static.get('architecture') != c.architecture_proof(plan['training']['seed']):
        raise ValueError('unverified architecture')
    old_report = a.read(a.checked(plan['inputs']['previousCapacityReport']))
    if old_report['decision'] != 'native_capacity_fail_no_full30':
        raise ValueError('previous consumed branch not closed as FAIL')
    return result


def write(path, report):
    if Path(path).name == 'microfit-report.json':
        report = {**report, 'architecture': c.architecture_proof(1605)}
    return original_write(path, report)


t.validate, t.j.write_durable_new = validate, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    plan_path = args.plan.resolve() if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path'])
    parent = a.read(a.read(plan_path)['inputs']['parentPlan']['path'])
    guard = module('context_microfit_guard', Path(__file__).with_name('train-yolo-seg.py'))
    guard.install_read_only_ultralytics_image_check()
    try:
        if args.verify_report:
            result = t.verify(args.verify_report)
            saved = a.read(args.verify_report)
            if saved['architecture'] != c.architecture_proof(1605):
                raise ValueError('architecture replay')
        else:
            report = t.train(plan_path, args.output.resolve())
            result = {key: report[key] for key in ('ok', 'decision', 'metrics', 'elapsedSeconds')}
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        for directory in parent['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(directory))


if __name__ == '__main__':
    main()
