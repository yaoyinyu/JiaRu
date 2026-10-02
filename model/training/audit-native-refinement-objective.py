"""保存输出的全候选保真与编辑带梯度审计；无模型forward或优化。"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def wilson(count, total):
    z = 1.959963984540054
    p = count / total
    scale = 1 + z*z / total
    center = (p + z*z / (2*total)) / scale
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / scale
    return [center-half, center+half]


def build(plan_path):
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    runner = module('native_objective_capacity', plan['inputs']['capacityVerifier']['path'])
    t = getattr(runner, 't', runner)
    a = t.a
    for value in plan['inputs'].values():
        a.checked(value)
    if plan['modelCalls'] != 0 or plan['optimizerSteps'] != 0 or plan['diagnostic'] != 'all45 saved outputs, current loss components and normalized-band BCE analytic gradient':
        raise ValueError('frozen loss-only scope')
    path = a.checked(plan['inputs']['capacityReport'])
    report = a.read(path)
    replay = t.verify(path)
    frozen = a.read(a.checked(report['inputs']['plan']))
    _, parent, records = t.validate(frozen)
    h, data = t.s.native_data(parent, records)
    if report['architecture'] != runner.c.architecture_proof(frozen['training']['seed']):
        raise ValueError('architecture fidelity')
    with np.load(a.checked(report['finalDeltas']), allow_pickle=False) as saved:
        if saved['candidateIds'].tolist() != frozen['candidateIds']:
            raise ValueError('reconstruction_mismatch: identities')
        deltas = [saved[f'delta_{i:03d}'].copy() for i in range(45)]
    rows, summary = t.metrics(data, deltas, h)
    if rows != report['perCandidate'] or summary != report['metrics'] or report['gates'] != parent['qualityGatesUnchanged']:
        raise ValueError('reconstruction_mismatch: full45 metrics/gates')
    previous = a.read(a.checked(plan['inputs']['previousCapacityReport']))
    if [row['id'] for row in previous['perCandidate']] != [row['id'] for row in rows]:
        raise ValueError('reconstruction_mismatch: prior identities')
    loss_module = module('native_objective_loss', a.checked(frozen['inputs']['lossSource']))
    torch.set_num_threads(2)
    diagnostics = []
    for item, delta, accepted in zip(data, deltas, rows, strict=True):
        target = torch.from_numpy(item['target'][None, None].copy())
        band = torch.from_numpy(item['band'][None, None].copy())
        logits = h.compose_native_logits(torch.from_numpy(item['base'][None, None].copy()), torch.from_numpy(delta[None, None]), band).detach().requires_grad_(True)
        loss, recorded = loss_module.conditional_mask_loss(logits, target, boundary_weight=frozen['loss']['boundaryWeight'])
        probability = logits.sigmoid()
        positive = bool(item['row']['presenceTarget'])
        bce = F.binary_cross_entropy_with_logits(logits, target)
        dice = 1 - (2*(probability*target).sum()+1) / (probability.sum()+target.sum()+1) if positive else logits.sum()*0
        edge = (1-loss_module.boundary.soft_boundary_iou_per_instance(probability, target, {'nearBoundaryKernel':5, 'epsilon':1e-6}).mean()) * frozen['loss']['boundaryWeight'] if positive else logits.sum()*0
        if not torch.allclose(loss, bce+dice+edge, atol=1e-7, rtol=0):
            raise ValueError('reconstruction_mismatch: frozen loss formula')
        gradients = {name: torch.autograd.grad(value, logits, retain_graph=True)[0][band].detach().numpy()
                     for name, value in [('bce', bce), ('dice', dice), ('weightedBoundary', edge)]}
        if any(not np.isfinite(value).all() for value in gradients.values()):
            raise ValueError('nonfinite loss-only gradient')
        pixels, editable = item['base'].size, int(item['band'].sum())
        scale = pixels / editable if editable else None
        pred = h.apply_native_delta(item['base'], delta, item['band']) >= .5
        wrong = pred != (item['target'] >= .5)
        gradient_l1 = {name: float(np.abs(value.astype(np.float64)).sum()) for name, value in gradients.items()}
        total_grad = sum(gradients.values())
        bce_grad = gradients['bce']
        diagnostics.append({'id':accepted['id'], 'positive':positive, 'jointPass':accepted.get('jointPass'),
                            'lossComponents':recorded, 'editablePixels':editable, 'totalPixels':pixels,
                            'editableFraction':editable/pixels, 'bandBceGradientScaleIfNormalized':scale,
                            'gradientAbsoluteSumInsideBand':gradient_l1,
                            'wrongPixelsInsideBand':int((wrong & item['band']).sum()),
                            'wrongPixelsOutsideBand':int((wrong & ~item['band']).sum()),
                            'lossGradientOpposesPixelTruthInsideBand':int(((total_grad*bce_grad)<0).sum()),
                            'scope':'Direct loss derivative at saved final logits; not a model derivative or trained alternative.'})
    positive_rows = [row for row in rows if row['positive']]
    positive_diag = [row for row in diagnostics if row['positive']]
    previous_by_id = {row['id']:row for row in previous['perCandidate']}
    transition = {kind:[] for kind in ['newFailure','recovered','persistentFailure','persistentPass']}
    for row in positive_rows:
        old, new = previous_by_id[row['id']]['jointPass'], row['jointPass']
        kind = ('persistentPass' if new else 'newFailure') if old else ('recovered' if new else 'persistentFailure')
        transition[kind].append(row['id'])
    return {'schemaVersion':1, 'ok':True, 'decision':'all45_quality_fail_fidelity_and_loss_only_gradient_diagnostic',
            'inputs':{'plan':a.bind(plan_path), **plan['inputs']}, 'qualityDecision':report['decision'],
            'metrics':summary, 'failureCounts':{'joint':sum(not row['jointPass'] for row in positive_rows),
                    'iou':sum(row['iou']<.75 for row in positive_rows), 'boundaryIou':sum(row['boundaryIou']<.75 for row in positive_rows),
                    'boundaryF1':sum(row['boundaryF1']<.9 for row in positive_rows)},
            'instanceTransitionsDiagnosticOnly':transition, 'perCandidate':diagnostics, 'journal':replay['journal'],
            'objectiveSummary':{'positiveEditableFractionMedian':float(np.median([row['editableFraction'] for row in positive_diag])),
                    'positiveBandBceScaleMedian':float(np.median([row['bandBceGradientScaleIfNormalized'] for row in positive_diag])),
                    'positiveBandBceScaleRange':[min(row['bandBceGradientScaleIfNormalized'] for row in positive_diag),max(row['bandBceGradientScaleIfNormalized'] for row in positive_diag)],
                    'gradientAbsoluteSumInsideBand':{name:sum(row['gradientAbsoluteSumInsideBand'][name] for row in positive_diag) for name in ['bce','dice','weightedBoundary']},
                    'wrongPixelsInsideBand':sum(row['wrongPixelsInsideBand'] for row in positive_diag),
                    'wrongPixelsOutsideBand':sum(row['wrongPixelsOutsideBand'] for row in positive_diag)},
            'jointWilson95':wilson(summary['jointPassCount'],34), 'relativeClaim':False,
            'branchDecisionBasis':'Absolute capacity gate; transitions are error bookkeeping, not significance or retention',
            'modelCalls':0, 'optimizerSteps':0, 'formalTrainingApprovedImages':0, 'full30PilotAllowed':False,
            'scope':'Train-only all45 saved outputs. Analytic band normalization changes gradient scale, not proof of capacity/generalization, best-model selection or release readiness.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify-report',type=Path)
    args = parser.parse_args()
    saved = json.loads(args.verify_report.read_text(encoding='utf-8')) if args.verify_report else None
    plan_path = args.plan if args.plan else Path(saved['inputs']['plan']['path'])
    guard = module('native_objective_guard',Path(__file__).with_name('train-yolo-seg.py'))
    guard.install_read_only_ultralytics_image_check()
    try:
        report = build(plan_path)
        if saved is not None and report != saved:
            raise ValueError('reconstruction_mismatch: objective diagnostic')
        if saved is None:
            with args.output.open('x',encoding='utf-8',newline='\n') as stream:
                stream.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({key:report[key] for key in ['ok','decision','failureCounts','objectiveSummary','jointWilson95','instanceTransitionsDiagnosticOnly']},ensure_ascii=False),flush=True)
    finally:
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        parent = json.loads(Path(plan['inputs']['parentPlan']['path']).read_text(encoding='utf-8'))
        for directory in parent['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(directory))


if __name__ == '__main__':
    main()
