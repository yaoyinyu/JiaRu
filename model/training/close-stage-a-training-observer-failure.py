"""仅修复已跑满训练后的回调计数解释；旧失败、事件、权重及预算不改。"""
import argparse
import csv
import inspect
import json
import math
from pathlib import Path
import importlib.util


def helper():
    spec = importlib.util.spec_from_file_location('stage_a_close_data', Path(__file__).with_name('reviewed-role-development-data.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


d = helper()


def build(root):
    import torch
    from ultralytics.engine.trainer import BaseTrainer
    from ultralytics.utils.metrics import SegmentMetrics, DetMetrics
    attempt = json.loads((root / 'attempt.json').read_bytes()); plan = d.read(attempt['plan'])
    if plan['training']['epochs'] != 30 or attempt['originalAttemptMayRestart'] or not attempt['attemptConsumed']:
        raise ValueError('frozen attempt budget')
    d.verify(d.checked(attempt['materialization']))
    terminal = json.loads((root / 'terminal.json').read_bytes())
    failure = json.loads((root / 'termination-report.json').read_bytes())
    if failure['type'] != 'ValueError' or failure['message'] != 'incomplete full30 training' or failure['completedEpochs'] != 31 or failure['optimizerStepInFlight']:
        raise ValueError('unsupported observer failure; no generic exception approval')
    paths = sorted((root / 'events').glob('*.json'))
    events = [json.loads(path.read_bytes()) for path in paths]
    if [event['sequence'] for event in events] != list(range(1, len(events) + 1)) or events[-1] != terminal or terminal['phase'] != 'training_failed':
        raise ValueError('original failed journal identity')
    confirmations = [r['confirmedOptimizerSteps'] for r in events if r['phase'] == 'optimizer_step_confirmed']
    in_flight = [r['attemptedStep'] for r in events if r['phase'] == 'optimizer_step_in_flight']
    expected_steps = math.ceil(plan['counts']['train']['sources'] / plan['training']['batch']) * 30
    if confirmations != list(range(1, expected_steps + 1)) or in_flight != confirmations or failure['confirmedOptimizerSteps'] != expected_steps:
        raise ValueError('successful optimization denominator')
    epochs = [r for r in events if r['phase'] == 'epoch_completed']
    if [r['completedEpochs'] for r in epochs] != list(range(1, 32)) or any(r['confirmedOptimizerSteps'] != (i + 1) * 5 for i, r in enumerate(epochs[:30])):
        raise ValueError('first30 epoch/optimizer identity')
    if epochs[-1]['confirmedOptimizerSteps'] != epochs[-2]['confirmedOptimizerSteps'] or epochs[-1]['loss'] != epochs[-2]['loss']:
        raise ValueError('final callback performed new optimization')
    if [r['phase'] for r in events if r['sequence'] > epochs[-2]['sequence']] != ['epoch_completed', 'training_failed']:
        raise ValueError('extra events after real final epoch')
    # 安装版本的最终评估会另触发fit回调；读取并冻结实际源码，不凭旧经验追认。
    final_source = inspect.getsource(BaseTrainer.final_eval)
    loop_source = inspect.getsource(BaseTrainer._do_train)
    if not ('self.epoch += 1' in final_source and 'self.epoch -= 1' in final_source and 'epoch += 1' in loop_source):
        raise ValueError('installed callback lifecycle differs')
    if not final_source.index('self.epoch += 1') < final_source.index('self.run_callbacks("on_fit_epoch_end")') < final_source.index('self.epoch -= 1'):
        raise ValueError('final validation callback is not bracketed by temporary epoch increment')
    rows = list(csv.DictReader((root / 'fit/results.csv').open(encoding='utf-8')))
    if [int(row['epoch']) for row in rows] != list(range(1, 31)):
        raise ValueError('CSV does not prove full30')
    if len(list(root.glob('checkpoint-epoch-*.pt'))) != 31:
        raise ValueError('forensic checkpoint denominator')
    weights = {name: d.bind(root / 'fit/weights' / f'{name}.pt') for name in ('best', 'last')}
    payloads = {name: torch.load(ref['path'], map_location='cpu', weights_only=False) for name, ref in weights.items()}
    best_metrics = payloads['best']['train_metrics']
    matches = [row for row in rows if all(float(row[k]) == float(value) for k, value in best_metrics.items() if k in row)]
    if len(matches) != 1 or len([k for k in best_metrics if k in rows[0]]) < 8:
        raise ValueError('best weight does not bind one real epoch')
    best_epoch = int(matches[0]['epoch'])
    fitness = [float(row['metrics/mAP50-95(B)']) + float(row['metrics/mAP50-95(M)']) for row in rows]
    metrics_source = inspect.getsource(SegmentMetrics.fitness.fget)
    if 'self.seg.fitness() + DetMetrics.fitness.fget(self)' not in metrics_source or 'self.box.fitness()' not in inspect.getsource(DetMetrics.fitness.fget):
        raise ValueError('fitness definition differs')
    if not math.isclose(best_metrics['fitness'], max(fitness), abs_tol=1e-12) or best_epoch != 1 + fitness.index(max(fitness)):
        raise ValueError('best not selected from full30')
    if any(float(payloads['last']['train_metrics'][k]) != float(rows[-1][k]) for k in payloads['last']['train_metrics'] if k in rows[-1]):
        raise ValueError('last weights epoch binding')
    return {'schemaVersion': 1, 'ok': True,
            'decision': 'full30_execution_verified_observer_failure_preserved_quality_pending',
            'inputs': {'plan': attempt['plan'], 'materialization': attempt['materialization'], 'attempt': d.bind(root / 'attempt.json'),
                       'oldTermination': d.bind(root / 'termination-report.json'), 'oldTerminal': d.bind(root / 'terminal.json'),
                       'csv': d.bind(root / 'fit/results.csv'), 'verifier': d.bind(__file__),
                       'installedTrainer': d.bind(inspect.getfile(BaseTrainer)), 'installedMetrics': d.bind(inspect.getfile(SegmentMetrics))},
            'eventBindings': [d.bind(path) for path in paths], 'completedEpochs': 30,
            'confirmedOptimizerSteps': expected_steps, 'bestEpoch': best_epoch, 'weights': weights,
            'observerReportedEpoch31Preserved': True, 'actualOptimizerStepsInExtraCallback': 0,
            'originalFailedExecutionDecisionPreserved': True, 'newTrainingAttemptConsumed': True,
            'originalAttemptMayRestart': False, 'checkpointCountPreserved': 31,
            'meaning': 'execution_and_best_selection_only_not_source_independence_or_model_quality',
            'newInferenceCallsInThisAudit': 0, 'newOptimizerStepsInThisAudit': 0,
            'formalThresholdCalibrationAllowed': False, 'formalReleaseAllowed': False, 'productHold': True}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--training-dir', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); args = p.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes()); root = Path(old['inputs']['attempt']['path']).parent
        result = build(root)
        if result != old: raise ValueError('reconstruction_mismatch: closeout')
    else:
        result = build(args.training_dir.resolve()); d.new(args.output.resolve(), result)
    print(json.dumps({k: result[k] for k in ('ok', 'decision', 'completedEpochs', 'confirmedOptimizerSteps', 'bestEpoch', 'formalReleaseAllowed')}))


if __name__ == '__main__': main()
