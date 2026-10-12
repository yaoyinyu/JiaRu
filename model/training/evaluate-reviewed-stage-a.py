"""固定整图输入的一次Stage A诊断；保存逐源预测，重放不再次推理。"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import traceback
from pathlib import Path
import importlib.util


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


HERE = Path(__file__).resolve().parent
d = module(HERE / 'reviewed-role-development-data.py', 'stage_a_eval_data')


def resources(execution_ref):
    execution = d.read(execution_ref); plan = d.read(execution['inputs']['plan'])
    for ref in execution['inputs'].values(): d.checked(ref)
    if Path(execution['inputs']['runner']['path']).resolve() != Path(__file__).resolve(): raise ValueError('runner identity')
    if plan['purpose'] != 'fixed_runtime_stage_a_diagnostic_only': raise ValueError('diagnostic scope')
    if plan['runtime'] != {'imgsz': 512, 'conf': 0.25, 'iou': 0.7, 'maxDet': 10, 'retinaMasks': True, 'rect': False, 'device': 0, 'thresholdCalibrationAllowed': False}:
        raise ValueError('frozen runtime drift')
    if plan['budget'] != {'maximumNewSourceInferenceInputs': 20, 'inferencesPerSource': 1, 'optimizerSteps': 0, 'automaticRestartAllowed': False, 'protectedHoldoutInputs': 0}:
        raise ValueError('source inference budget drift')
    contract = d.read(plan['inputs']['contract'])
    selected = d.validate(contract)
    d.verify(d.checked(plan['inputs']['materialization']))
    if plan['records'] != contract['records'] or plan['counts'] != contract['counts'] or len(selected) != 20:
        raise ValueError('reconstruction_mismatch: full cohort')
    for ref in plan['inputs'].values(): d.checked(ref)
    helper = module(d.checked(execution['inputs']['predictionHelper']), 'stage_a_saved_predictions')
    roi = module(d.checked(execution['inputs']['roiHelper']), 'stage_a_saved_roi')
    guard = d.load(d.checked(plan['inputs']['readOnlyGuard']), 'stage_a_eval_guard')
    guard.install_read_only_ultralytics_image_check()
    return execution, plan, contract, selected, helper, roi, guard


def truths(source):
    import numpy as np
    from PIL import Image, ImageDraw
    masks = []
    for polygon in source['polygons']:
        image = Image.new('L', tuple(source['size']))
        ImageDraw.Draw(image).polygon(polygon, fill=255)
        masks.append(np.asarray(image) > 0)
    result = np.stack(masks)
    if not result.any(axis=(1, 2)).all(): raise ValueError('empty native truth')
    return result


def geometry(source, prediction_ref, helper, roi, contract):
    import numpy as np
    truth = truths(source)
    boxes, scores, classes, masks = helper.load_prediction(prediction_ref, source['size'])
    if len(masks) > 10 or (scores < 0.25).any(): raise ValueError('saved acceptance set differs from plan')
    matched = helper.match_masks(masks, truth, 0.75)
    if len(truth) != source['maskCount']: raise ValueError('truth denominator')
    ious = np.array(matched['iouMatrix'], dtype=np.float64).reshape(len(truth), len(masks))
    crops, coverage = roi.coverage_matrix(truth, boxes, contract['roiPolicy'])
    oracle = roi.oracle_allocation(coverage, ious)
    primary = []
    for pair in matched['assignment']:
        i, j = pair['truthIndex'] - 1, pair['predictionIndex'] - 1
        intersection = int((truth[i] & masks[j]).sum())
        primary.append({**pair, 'coarseMaskSeedValid': intersection > 0,
                        'roiBox': list(crops[j]) if crops[j] is not None else None,
                        'roiTruthCoverage': float(coverage[i, j]),
                        'roiFullTruthCoverage': bool(intersection > 0 and coverage[i, j] == 1),
                        'truthSurfaceCoverage': intersection / max(1, int(truth[i].sum())),
                        'predictionPrecisionAgainstAssignedTruth': intersection / max(1, int(masks[j].sum())),
                        **roi.boundary_stats(truth[i], masks[j], contract['nativeBoundaryTolerancePixels'])})
    # 未分配/低IoU不是自动背景误检；保存待视觉裁决候选。
    weak = [row for row in primary if row['iou'] < 0.75]
    zero_overlap = [j + 1 for j in range(len(masks)) if not (ious[:, j] > 0).any()]
    duplicates = []
    for a in range(len(masks)):
        for b in range(a + 1, len(masks)):
            overlap = int((masks[a] & masks[b]).sum())
            union = int((masks[a] | masks[b]).sum())
            containment = overlap / max(1, min(int(masks[a].sum()), int(masks[b].sum())))
            if (overlap / max(1, union)) >= 0.6 or containment >= 0.85:
                duplicates.append({'predictionIndices': [a + 1, b + 1], 'maskIoU': overlap / max(1, union), 'smallerContainment': containment})
    return {'identity': source['identity'], 'sourceGroup': source['sourceGroup'], 'size': source['size'],
            'annotation': source['annotation'], 'prediction': prediction_ref,
            'truthMaskSha256': [hashlib.sha256(mask.tobytes()).hexdigest() for mask in truth],
            'predictionMaskSha256': [hashlib.sha256(mask.tobytes()).hexdigest() for mask in masks],
            'truthNails': len(truth), 'candidates': len(masks), 'confidence': scores.tolist(), 'boxesXyxy': boxes.tolist(),
            'matchIoU075': matched, 'primaryAssignment': primary, 'roiOneToOneOracle': oracle,
            'weakAssignedPredictions': weak, 'unassignedPredictionsPendingVisual': matched['unmatchedPredictionIndices'],
            'zeroTruthOverlapPredictionsPendingVisual': zero_overlap, 'duplicateGeometryCandidates': duplicates,
            'matchedNails': len(matched['matches']), 'missedNailsAtIoU075': len(matched['missedTruthIndices']),
            'primaryFullRoiNails': sum(p['roiFullTruthCoverage'] for p in primary),
            'oracleFullRoiNails': sum(p['completeTruthCoverage'] for p in oracle),
            'maskQualityVisualApproved': False, 'formalIndependentValAllowed': False}


def summary(rows):
    result = {}
    for split in ('train', 'val'):
        sources = [row for row in rows if row['identity']['split'] == split]
        truth = sum(r['truthNails'] for r in sources)
        result[split] = {'sources': len(sources), 'truthNails': truth,
                         'candidates': sum(r['candidates'] for r in sources), 'matchedNailsIoU075': sum(r['matchedNails'] for r in sources),
                         'missedNailsIoU075': sum(r['missedNailsAtIoU075'] for r in sources),
                         'missedSourcesIoU075': sum(r['missedNailsAtIoU075'] > 0 for r in sources),
                         'primaryFullRoiNails': sum(r['primaryFullRoiNails'] for r in sources),
                         'oracleFullRoiNails': sum(r['oracleFullRoiNails'] for r in sources),
                         'unassignedPredictionsPendingVisual': sum(len(r['unassignedPredictionsPendingVisual']) for r in sources)}
        result[split]['recallIoU075'] = result[split]['matchedNailsIoU075'] / truth
        result[split]['missedSourceRateIoU075'] = result[split]['missedSourcesIoU075'] / len(sources)
        result[split]['primaryFullRoiRatio'] = result[split]['primaryFullRoiNails'] / truth
        result[split]['oracleFullRoiRatio'] = result[split]['oracleFullRoiNails'] / truth
    return result


def reconstruct(execution_ref, root):
    e, plan, contract, selected, helper, roi, guard = resources(execution_ref)
    try:
        claim = json.loads((root / 'attempt.json').read_bytes())
        if claim != {'execution': execution_ref, 'sourceInferenceInputsAllowed': 20, 'attemptConsumed': True, 'resumeAllowed': False}:
            raise ValueError('once-only inference claim')
        events = [json.loads(p.read_bytes()) for p in sorted((root / 'events').glob('*.json'))]
        if len(events) != 42 or [r['sequence'] for r in events] != list(range(1, 43)):
            raise ValueError('incomplete source inference journal')
        if events[0]['phase'] != 'prepared' or events[-1] != {'sequence': 42, 'phase': 'complete', 'completedSourceInputs': 20}:
            raise ValueError('terminal source confirmation')
        rows = []
        for number, source in enumerate(selected, 1):
            start, done = events[2 * number - 1:2 * number + 1]
            if start['phase'] != 'input_started' or done['phase'] != 'input_complete' or any(r['inputIndex'] != number or r['identity'] != source['identity'] for r in (start, done)):
                raise ValueError('source sequence/identity drift')
            if done['completedSourceInputs'] != number or start['completedSourceInputs'] != number - 1:
                raise ValueError('source confirmation count')
            if d.checked(done['prediction']) != (root / 'predictions' / f'{number:03d}.npz').resolve(): raise ValueError('prediction path')
            rows.append(geometry(source, done['prediction'], helper, roi, e['metricContract']))
        return {'schemaVersion': 1, 'ok': True, 'decision': 'fixed_runtime_development_diagnostic_quality_not_approved',
                'execution': execution_ref, 'records': rows, 'summaryBySplit': summary(rows),
                'confirmedSourceInferenceInputs': 20, 'optimizerSteps': 0, 'newChatImageInputsDuringLocalInference': 0,
                'sourceInputMeaning': '20 calls to model.predict with one original source each; backend warmup is not a source input',
                'fullPixelMaskQualityApproved': False, 'formalSourceIndependenceProven': False,
                'formalReleaseAllowed': False, 'productHold': True}
    finally:
        materialization = d.read(plan['inputs']['materialization'])
        for path in [materialization['root'], *contract['cacheCleanupRoots']]: guard.remove_ultralytics_label_caches(Path(path))


def run(execution_path, root):
    execution_ref = d.bind(execution_path)
    e, plan, contract, selected, helper, roi, guard = resources(execution_ref)
    completed = attempted = sequence = 0
    try:
        from PIL import Image
        import numpy as np
        import torch
        from ultralytics import YOLO
        if not torch.cuda.is_available(): raise RuntimeError('registered CUDA unavailable')
        root.mkdir(parents=True, exist_ok=False); (root / 'events').mkdir(); (root / 'predictions').mkdir()
        d.new(root / 'attempt.json', {'execution': execution_ref, 'sourceInferenceInputsAllowed': 20, 'attemptConsumed': True, 'resumeAllowed': False})
        def event(phase, **fields):
            nonlocal sequence
            sequence += 1
            d.new(root / 'events' / f'{sequence:06d}.json', {'sequence': sequence, 'phase': phase, **fields})
        event('prepared', completedSourceInputs=0)
        model = YOLO(str(d.checked(plan['inputs']['weights'])))
        copy_root = Path(d.read(plan['inputs']['materialization'])['root'])
        for number, source in enumerate(selected, 1):
            path = copy_root / 'images' / source['identity']['split'] / source['identity']['fileName']
            if d.bind(path)['sha256'] != source['identity']['imageSha256']: raise ValueError('isolated source byte identity')
            with Image.open(path) as image:
                image.load()
                if list(image.size) != source['size']: raise ValueError('source dimensions')
                rgb = image.convert('RGB')
                bgr = np.asarray(rgb)[:, :, ::-1].copy()
            attempted = number
            event('input_started', inputIndex=number, identity=source['identity'], completedSourceInputs=completed)
            result = model.predict(source=bgr, imgsz=512, conf=0.25, iou=0.7, max_det=10,
                                   device=0, retina_masks=True, rect=False, verbose=False, save=False, stream=False)[0]
            boxes = result.boxes.xyxy.cpu().numpy().astype(np.float32)
            scores = result.boxes.conf.cpu().numpy().astype(np.float32)
            classes = result.boxes.cls.cpu().numpy().astype(np.float32)
            masks = result.masks.data.cpu().numpy() > 0.5 if result.masks is not None else np.zeros((0, source['size'][1], source['size'][0]), dtype=bool)
            prediction = helper.save_prediction(root / 'predictions' / f'{number:03d}.npz', boxes, scores, classes, masks)
            completed = number
            event('input_complete', inputIndex=number, identity=source['identity'], completedSourceInputs=completed, prediction=prediction)
        event('complete', completedSourceInputs=completed)
    except BaseException as exc:
        if root.exists():
            d.new(root / 'failure.json', {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc(),
                                       'attemptedSourceInputs': attempted, 'confirmedSourceInputs': completed, 'resumeAllowed': False})
        raise
    finally:
        copy_root = Path(d.read(plan['inputs']['materialization'])['root'])
        for path in [copy_root, *map(Path, contract['cacheCleanupRoots'])]: guard.remove_ultralytics_label_caches(path)
    report = reconstruct(execution_ref, root)
    d.new(root / 'report.json', report)
    return report


def main():
    p = argparse.ArgumentParser(); p.add_argument('--execution', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); args = p.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes()); report = reconstruct(old['execution'], args.verify_report.parent)
        if old != report: raise ValueError('reconstruction_mismatch: frozen diagnostic')
    else: report = run(args.execution.resolve(), args.output.resolve())
    print(json.dumps({'ok': True, 'summaryBySplit': report['summaryBySplit'], 'formalReleaseAllowed': False}))


if __name__ == '__main__': main()
