"""完整30轮Stage A开发训练，逐优化步不可覆盖留证；不覆盖正式发布门。"""
from __future__ import annotations
import argparse
import json
import os
import time
import traceback
from pathlib import Path
import importlib.util


def helper():
    path = Path(__file__).with_name('reviewed-role-development-data.py')
    spec = importlib.util.spec_from_file_location('reviewed_stage_a_data', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


d = helper()


class Journal:
    def __init__(self, root):
        self.root = root; self.sequence = 0; self.steps = 0; self.epochs = 0
        self.in_flight = False; self.started = time.time()
        (root / 'events').mkdir()

    def event(self, phase, **detail):
        self.sequence += 1
        state = {'sequence': self.sequence, 'phase': phase, 'confirmedOptimizerSteps': self.steps,
                 'completedEpochs': self.epochs, 'optimizerStepInFlight': self.in_flight,
                 'elapsedSeconds': time.time() - self.started, **detail}
        d.new(self.root / 'events' / f'{self.sequence:06d}.json', state)
        return state

    def before(self, optimizer, args, kwargs):
        self.in_flight = True
        self.event('optimizer_step_in_flight', attemptedStep=self.steps + 1)

    def after(self, optimizer, args, kwargs):
        # AMP关闭；post hook仅在优化器成功返回后计入优化步。
        self.steps += 1; self.in_flight = False
        self.event('optimizer_step_confirmed')


def train(plan_path, materialization_path, root):
    plan = json.loads(plan_path.read_bytes()); d.checked(plan['inputs']['trainer'])
    if Path(plan['inputs']['trainer']['path']).resolve() != Path(__file__).resolve():
        raise ValueError('trainer binding')
    if plan['training']['epochs'] != 30 or plan['training']['patience'] != 0 or plan['training']['amp']:
        raise ValueError('full30/precision contract')
    if plan['budget'] != {'maximumAttempts': 1, 'resumeConsumedAttemptAllowed': False}:
        raise ValueError('single new budget')
    root.mkdir(parents=True, exist_ok=False)
    d.new(root / 'attempt.json', {'plan': d.bind(plan_path), 'materialization': d.bind(materialization_path),
                               'pid': os.getpid(), 'attemptConsumed': True, 'originalAttemptMayRestart': False})
    journal = Journal(root); journal.event('preflight')
    dataset_root = Path(json.loads(materialization_path.read_bytes())['root'])
    guard = None
    try:
        preflight = d.verify(materialization_path)
        if not preflight['ok']: raise ValueError('materialization not approved')
        guard = d.load(d.checked(plan['inputs']['readOnlyGuard']), 'stage_a_guard')
        guard.install_read_only_ultralytics_image_check()
        import torch
        from ultralytics import YOLO
        if not torch.cuda.is_available(): raise RuntimeError('registered CUDA device unavailable')
        torch.set_num_threads(4)
        d.checked(plan['initialWeights'])
        model = YOLO(plan['initialWeights']['path'])
        hooks = []

        def start(trainer):
            hooks.extend([trainer.optimizer.register_step_pre_hook(journal.before), trainer.optimizer.register_step_post_hook(journal.after)])
            journal.event('training_started', device=str(trainer.device), parameters=sum(p.numel() for p in trainer.model.parameters()), trainSources=plan['counts']['train']['sources'])

        def batch_end(trainer):
            if not torch.isfinite(trainer.loss).all(): raise RuntimeError('nonfinite training loss')

        def epoch_end(trainer):
            torch.cuda.synchronize(trainer.device)
            journal.epochs = int(trainer.epoch) + 1
            journal.event('epoch_completed', loss=[float(x) for x in trainer.tloss.detach().cpu().reshape(-1)],
                          internalDiagnosticMetrics={k: float(v) for k, v in trainer.metrics.items()})
            # 独立完整取证checkpoint，不覆盖共享文件，不构成断点重训权限。
            target = root / f'checkpoint-epoch-{journal.epochs:03d}.pt'
            with target.open('xb') as stream:
                torch.save({'epoch': journal.epochs, 'confirmedOptimizerSteps': journal.steps,
                            'model': trainer.model.state_dict(), 'optimizer': trainer.optimizer.state_dict(),
                            'scheduler': trainer.scheduler.state_dict(), 'plan': d.bind(plan_path),
                            'use': 'forensic_development_only_no_resume_authority'}, stream)
                stream.flush(); os.fsync(stream.fileno())

        def synchronize(trainer): torch.cuda.synchronize(trainer.device)
        model.add_callback('on_train_start', start)
        model.add_callback('on_train_batch_end', batch_end)
        model.add_callback('on_fit_epoch_end', epoch_end)
        model.add_callback('on_train_epoch_end', synchronize)
        model.add_callback('on_val_end', synchronize)
        journal.event('model_loaded')
        result = model.train(data=str(dataset_root / 'dataset.yaml'), project=str(root), name='fit',
                             **plan['training'])
        if journal.epochs != 30 or journal.steps == 0: raise ValueError('incomplete full30 training')
        run = Path(result.save_dir)
        weights = {name: d.bind(run / 'weights' / f'{name}.pt') for name in ('best', 'last')}
        guard.remove_ultralytics_label_caches(dataset_root)
        d.verify(materialization_path)
        terminal = journal.event('training_complete', weights=weights)
        d.new(root / 'terminal.json', terminal)
        d.new(root / 'training-report.json', {'schemaVersion': 1, 'ok': True,
              'decision': 'stage_a_development_full30_complete_quality_unvalidated',
              'plan': d.bind(plan_path), 'materialization': d.bind(materialization_path),
              'completedEpochs': journal.epochs, 'confirmedOptimizerSteps': journal.steps,
              'weights': weights, 'selectedBestAfterFull30': True, 'markerPolicy': plan['markerPolicy'],
              'formalSourceIndependenceProven': False, 'formalThresholdCalibrated': False,
              'formalReleaseAllowed': False, 'productHold': True})
        print(json.dumps({'ok': True, 'epochs': journal.epochs, 'steps': journal.steps, 'report': str(root / 'training-report.json')}), flush=True)
    except BaseException as exc:
        termination = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc(),
                       'confirmedOptimizerSteps': journal.steps, 'completedEpochs': journal.epochs,
                       'optimizerStepInFlight': journal.in_flight, 'originalAttemptMayRestart': False}
        # 异常报告独立创建，优先保留原始异常，即使事件记录再次失败。
        d.new(root / 'termination-report.json', termination)
        terminal = journal.event('training_failed', error={'type': type(exc).__name__, 'message': str(exc)})
        d.new(root / 'terminal.json', terminal)
        raise
    finally:
        if guard:
            guard.remove_ultralytics_label_caches(dataset_root)
            for path in plan['cacheCleanupRoots']: guard.remove_ultralytics_label_caches(Path(path))


def verify(root):
    report = json.loads((root / 'training-report.json').read_bytes()); plan = d.read(report['plan'])
    d.verify(d.checked(report['materialization']))
    events = [json.loads(p.read_bytes()) for p in sorted((root / 'events').glob('*.json'))]
    if [e['sequence'] for e in events] != list(range(1, len(events) + 1)):
        raise ValueError('journal sequence gap')
    confirmations = [e['confirmedOptimizerSteps'] for e in events if e['phase'] == 'optimizer_step_confirmed']
    if confirmations != list(range(1, report['confirmedOptimizerSteps'] + 1)):
        raise ValueError('optimization journal gap')
    attempted = [e['attemptedStep'] for e in events if e['phase'] == 'optimizer_step_in_flight']
    if attempted != confirmations: raise ValueError('unconfirmed optimization step')
    epochs = [e['completedEpochs'] for e in events if e['phase'] == 'epoch_completed']
    if epochs != list(range(1, 31)) or report['completedEpochs'] != plan['training']['epochs']:
        raise ValueError('epoch journal gap')
    if json.loads((root / 'terminal.json').read_bytes()) != events[-1] or events[-1]['phase'] != 'training_complete':
        raise ValueError('terminal journal mismatch')
    for ref in report['weights'].values(): d.checked(ref)
    checkpoints = list(root.glob('checkpoint-epoch-*.pt'))
    if len(checkpoints) != 30: raise ValueError('checkpoint count')
    return {'ok': True, 'epochs': 30, 'steps': report['confirmedOptimizerSteps'], 'events': len(events), 'checkpoints': 30, 'qualityPassed': False}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--plan', type=Path); p.add_argument('--materialization', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); args = p.parse_args()
    if args.verify_report: print(json.dumps(verify(args.verify_report.parent)))
    else: train(args.plan.resolve(), args.materialization.resolve(), args.output.resolve())


if __name__ == '__main__': main()
