"""可变配对输入的单次train角色诊断；原像素预测持久化，重放不推理。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

NAMES = ['original', 'marker_removed', 'blank_removed', 'marker_occluded',
         'blank_occluded', 'marker_blurred', 'blank_blurred', 'marker_moved', 'blank_moved']
PAIRS = [('original', n) for n in NAMES[1:]] + [
    ('marker_removed', 'blank_removed'), ('marker_occluded', 'blank_occluded'),
    ('marker_blurred', 'blank_blurred'), ('marker_moved', 'blank_moved')]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p): return {'path': str(Path(p).resolve()), 'sha256': sha(p)}
def checked(ref):
    p = Path(ref['path']).resolve()
    if not p.is_file() or sha(p) != ref['sha256']: raise ValueError('reconstruction_mismatch: ' + str(p))
    return p
def read(ref): return json.loads(checked(ref).read_bytes())
def module(ref, name):
    p = checked(ref); sys.path.insert(0, str(p.parent))
    spec = importlib.util.spec_from_file_location(name, p); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
def key(identity): return (identity['split'], identity['fileName'], identity['imageSha256'])


def validate_scope(plan, pack, index):
    """完整来源组与稳定身份校验，ordinal不作为全局键。"""
    if plan['contract']['variantOrder'] != NAMES or not plan['contract']['oneInferencePerVariant']:
        raise ValueError('variant contract drift')
    sources = plan['sources']; records = pack['records']
    ids = [key(s['identity']) for s in sources]
    if len(set(ids)) != len(ids) or len(sources) != len(records): raise ValueError('source cardinality or duplicate identity')
    idx = {key(r['identity']): r for r in index['records']}
    if len(idx) != len(index['records']): raise ValueError('duplicate index identity')
    groups = {s['sourceGroup'] for s in sources}
    expected_ids = {key(r['identity']) for r in index['records'] if r['sourceGroup'] in groups}
    if set(ids) != expected_ids: raise ValueError('incomplete whole source group')
    count = nails = marked = 0
    for s, p in zip(sources, records, strict=True):
        r = p['sourceRecordPreserved']; role = idx[key(s['identity'])]
        if s['identity'] != r['identity'] or s['sourceGroup'] != r['sourceGroup'] or s['sourceImage'] != r['sourceImage']:
            raise ValueError('stable source identity drift')
        if s['annotation'] != r['currentTruth']['annotation'] or s['imageSize'] != r['currentTruth']['imageSize']:
            raise ValueError('truth identity or pixel domain drift')
        if s['completeVisibleNails'] != p['sourceNails'] or s['completeVisibleNails'] <= 0:
            raise ValueError('complete nail denominator drift')
        if s['roleEvidence'] != role or role['sourceImage'] != s['sourceImage'] or role['sourceGroup'] != s['sourceGroup']:
            raise ValueError('role or parent lineage drift')
        if s['identity']['split'] != 'train' or role['upstreamDevelopmentSplit'] != 'train' or role['trainingUse'] != 'prohibited' or role['formalTrainingApproved']:
            raise ValueError('only prohibited upstream/current train sources allowed')
        if role['protectedTrainConflicts'] or any(v['role'] != 'developmentTrain' for v in role['currentAndParentRoleMatches']):
            raise ValueError('protected current or parent role')
        names = NAMES if r['markerControlRequired'] else ['original']
        if [v['name'] for v in s['variants']] != names or s['variants'] != [{'name': v['name'], 'image': v['image']} for v in p['variants']]:
            raise ValueError('variant order or identity drift')
        if s['trainingUse'] != 'prohibited': raise ValueError('unexpected training promotion')
        count += len(names); nails += s['completeVisibleNails']; marked += bool(r['markerControlRequired'])
    if plan['counts'] != {'sourceImages': len(sources), 'completeVisibleNails': nails, 'markedSources': marked, 'plannedInferenceInputs': count}:
        raise ValueError('input budget or truth denominator drift')
    return count


def truth_masks(source):
    from PIL import Image, ImageDraw
    import numpy as np
    path = checked(source['annotation']); w, h = source['imageSize']
    if source['truthFormat'] == 'original_pixel_polygon_annotation_json':
        d = json.loads(path.read_bytes())
        polygons = [[(q['x'], q['y']) for q in a['polygon']] for a in d['annotations']]
    elif source['truthFormat'] == 'yolo_normalized_polygon_label':
        polygons = []
        for line in path.read_text(encoding='utf-8').splitlines():
            vals = list(map(float, line.split()))
            if len(vals) < 7 or len(vals) % 2 != 1 or vals[0] != 0 or any(not 0 <= x <= 1 for x in vals[1:]):
                raise ValueError('invalid normalized truth')
            polygons.append([(vals[j] * w, vals[j+1] * h) for j in range(1, len(vals), 2)])
    else: raise ValueError('unsupported truth storage domain')
    if len(polygons) != source['completeVisibleNails']: raise ValueError('truth count drift')
    masks = []
    for p in polygons:
        im = Image.new('L', (w, h)); ImageDraw.Draw(im).polygon(p, fill=255); mask = np.asarray(im) > 0
        if not mask.any(): raise ValueError('empty truth')
        masks.append(mask)
    return np.stack(masks)


def resources(execution_ref):
    execution = read(execution_ref); inputs = execution['inputs']
    if checked(inputs['runnerSource']) != Path(__file__).resolve(): raise ValueError('runner identity drift')
    helper = module(inputs['predictionHelper'], 'native_prediction_helper')
    guard = module(inputs['readOnlyGuard'], 'variable_probe_guard'); guard.install_read_only_ultralytics_image_check()
    plan = read(inputs['plan']); pack = read(plan['inputs']['variantPack']); index = read(plan['inputs']['truthRoleIndex'])
    expected = validate_scope(plan, pack, index)
    checked(plan['inputs']['frozenWeight'])
    return execution, plan, pack, helper, guard, expected


def summarize_rows(sources, predictions, helper, threshold):
    rows = []; aggregates = {n: {'sourceImages': 0, 'truthNails': 0, 'matchedNails': 0, 'missedNails': 0, 'missedImages': 0, 'candidateCount': 0, 'unmatchedPredictions': 0} for n in NAMES}
    paired_original = {'sourceImages': 0, 'truthNails': 0, 'matchedNails': 0, 'missedNails': 0, 'missedImages': 0, 'candidateCount': 0, 'unmatchedPredictions': 0}
    for s in sources:
        truths = truth_masks(s); rp = {}; masks = {}
        for v in s['variants']:
            name = v['name']; ref = predictions[(key(s['identity']), name)]
            boxes, conf, classes, mask = helper.load_prediction(ref, s['imageSize']); masks[name] = mask
            match = helper.match_masks(mask, truths, threshold)
            rp[name] = {'prediction': ref, 'boxesXyxy': boxes.tolist(), 'confidence': conf.tolist(), 'classes': classes.tolist(), 'instanceCount': len(mask), **match}
            counts = {'sourceImages': 1, 'truthNails': len(truths), 'matchedNails': len(match['matches']), 'missedNails': len(match['missedTruthIndices']),
                      'missedImages': int(bool(match['missedTruthIndices'])), 'candidateCount': len(mask), 'unmatchedPredictions': len(match['unmatchedPredictionIndices'])}
            for k, value in counts.items(): aggregates[name][k] += value
            if name == 'original' and len(s['variants']) > 1:
                for k, value in counts.items(): paired_original[k] += value
        comparisons = {f'{a}__{b}': helper.comparison(rp[a], rp[b], masks[a], masks[b]) for a, b in PAIRS if a in rp and b in rp}
        rows.append({'identity': s['identity'], 'ordinal': s['ordinal'], 'sourceGroup': s['sourceGroup'], 'sourceNails': s['completeVisibleNails'],
                     'predictions': rp, 'comparisons': comparisons, 'trainingUse': 'prohibited'})
    comparison_summary = {}
    for a, b in PAIRS:
        name = f'{a}__{b}'; values = [r['comparisons'][name] for r in rows if name in r['comparisons']]
        comparison_summary[name] = {'sourcesCompared': len(values), 'sourcesWithCandidateCountChange': sum(v['candidateCountDelta'] != 0 for v in values),
            'sourcesWithTruthMatchMigration': sum(bool(v['newMissedTruthIndices'] or v['recoveredTruthIndices']) for v in values),
            'sourcesWithAnyUnionMaskDifference': sum(v['unionSymmetricDifferencePixels'] != 0 for v in values),
            'totalUnionDifferentPixels': sum(v['unionSymmetricDifferencePixels'] for v in values),
            'maxUnionChangedFraction': max((1-v['unionIoU'] for v in values), default=0.)}
    return rows, aggregates, paired_original, comparison_summary


def reconstruct(execution_ref, output):
    execution, plan, pack, helper, guard, expected = resources(execution_ref)
    try:
        claim_ref = read(bind(output / 'budget-claim-reference.json'))['claim']
        claim = read(claim_ref)
        if claim['execution'] != execution_ref or claim['plannedInputs'] != expected: raise ValueError('budget claim identity drift')
        read(execution['inputs']['environment'])
        events = []
        for seq, p in enumerate(sorted((output/'events').glob('*.json')), 1):
            d = json.loads(p.read_bytes())
            if d['sequence'] != seq or p.name != f'{seq:06d}.json': raise ValueError('event gap')
            events.append(d['value'])
        if len(events) != expected*2+2 or events[0] != {'phase': 'prepared', 'completedInputs': 0, 'attemptedInputs': 0}:
            raise ValueError('incomplete budget evidence')
        if events[-1] != {'phase': 'complete', 'completedInputs': expected, 'attemptedInputs': expected}: raise ValueError('incomplete terminal event')
        predictions = {}; number = 0
        for s in plan['sources']:
            checked(s['sourceImage']); checked(s['annotation'])
            for v in s['variants']:
                number += 1; started, done = events[2*number-1:2*number+1]
                for e in (started, done):
                    if e['inputIndex'] != number or e['identity'] != s['identity'] or e['variant'] != v['name'] or e['input'] != v['image'] or e['attemptedInputs'] != number:
                        raise ValueError('event stable identity drift')
                if started['phase'] != 'input_started' or done['phase'] != 'input_complete' or started['completedInputs'] != number-1 or done['completedInputs'] != number:
                    raise ValueError('per-input confirmation drift')
                prediction_path = output/'predictions'/f'{number:03d}-{v["name"]}.npz'
                if checked(done['prediction']) != prediction_path.resolve(): raise ValueError('prediction slot drift')
                checked(v['image']); predictions[(key(s['identity']), v['name'])] = done['prediction']
        rows, aggregates, paired_original, summary = summarize_rows(plan['sources'], predictions, helper, execution['controls']['truthIoUThreshold'])
        return {'schemaVersion': 1, 'ok': True, 'decision': 'variable_train_role_marker_sensitivity_diagnostic_only', 'execution': execution_ref,
                'inputs': execution['inputs'], 'contract': plan['contract'], 'records': rows,
                'counts': {**plan['counts'], 'confirmedInferenceInputs': expected, 'progressEvents': len(events)},
                'aggregateByVariant': aggregates, 'markedSourceOriginalAggregate': paired_original, 'comparisonSummary': summary,
                'recordedModelCalls': expected, 'optimizerSteps': 0, 'formalTrainingApprovedImages': 0, 'trainingAllowed': False,
                'full30PilotAllowed': False, 'wholeSourceGroupsApproved': False, 'independentShortcutExclusionProven': False,
                'limitations': ['Existing train-role Stage A developer weight only; not new Stage B quality.',
                    'No effect or no IoU0.75 match migration does not prove shortcut absence.',
                    'Unmatched predictions are not automatically background false positives; keep all assignments.',
                    'Per-variant denominators differ for original-only members; matched-original aggregate is explicit.',
                    'Local texture and global context remain confounds; full split/parent independence pending.']}
    finally: guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def run(execution_path):
    execution_ref = bind(execution_path)
    execution, plan, pack, helper, guard, expected = resources(execution_ref)
    output = Path(execution['outputRoot']); completed = attempted = sequence = 0; claimed = False; t0 = time.monotonic()
    try:
        if helper.environment() != read(execution['inputs']['environment']): raise ValueError('environment drift')
        preflight = read(plan['inputs']['preflight']); auditor = module(preflight['inputs']['runnerSource'], 'frozen_input_preflight')
        if auditor.build() != preflight or not preflight['diagnosticProbePrerequisitesMet'] or preflight['counts']['missingInputOrVisualSources']:
            raise ValueError('reconstruction_mismatch: input preflight')
        controls = execution['controls']; contract = plan['contract']
        if [contract[k] for k in ('imgsz', 'conf', 'iou', 'device', 'retinaMasks')] != [512, .25, .7, 'cpu', True] or controls['truthIoUThreshold'] != .75:
            raise ValueError('fixed diagnostic contract drift')
        for s in plan['sources']:
            checked(s['sourceImage']); truth_masks(s)
            for v in s['variants']: checked(v['image'])
        if output.exists(): raise FileExistsError(output)
        claim_path = checked(execution['inputs']['plan']).parent / f'variable-marker-probe-budget-{execution["inputs"]["plan"]["sha256"]}.json'
        helper.durable_new(claim_path, {'execution': execution_ref, 'plannedInputs': expected, 'resumingAllowed': False})
        claimed = True; output.mkdir(); (output/'events').mkdir(); (output/'predictions').mkdir()
        helper.durable_new(output/'budget-claim-reference.json', {'claim': bind(claim_path)})
        sequence += 1; helper.journal(output/'events', sequence, {'phase': 'prepared', 'completedInputs': 0, 'attemptedInputs': 0})
        import torch
        import cv2
        import numpy as np
        from ultralytics import YOLO
        torch.set_num_threads(controls['cpuThreads']); torch.manual_seed(controls['seed'])
        model = YOLO(str(checked(plan['inputs']['frozenWeight'])))
        for s in plan['sources']:
            for v in s['variants']:
                attempted += 1; event = {'inputIndex': attempted, 'identity': s['identity'], 'variant': v['name'], 'input': v['image']}
                sequence += 1; helper.journal(output/'events', sequence, {'phase': 'input_started', 'completedInputs': completed, 'attemptedInputs': attempted, **event})
                image = cv2.imdecode(np.frombuffer(checked(v['image']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                if image is None or list(image.shape[:2][::-1]) != s['imageSize']: raise ValueError('native input dimensions')
                result = model.predict(source=image, imgsz=contract['imgsz'], conf=contract['conf'], iou=contract['iou'], device='cpu',
                                       retina_masks=True, max_det=controls['maxDet'], verbose=False, save=False, stream=False)[0]
                boxes = result.boxes.xyxy.cpu().numpy().astype(np.float32); conf = result.boxes.conf.cpu().numpy().astype(np.float32); classes = result.boxes.cls.cpu().numpy().astype(np.float32)
                if result.masks is None:
                    if len(boxes): raise ValueError('boxes without segmentation masks')
                    masks = np.zeros((0, *image.shape[:2]), bool)
                else: masks = result.masks.data.cpu().numpy() > .5
                if masks.shape != (len(boxes), *image.shape[:2]): raise ValueError('native mask dimensions')
                prediction = helper.save_prediction(output/'predictions'/f'{attempted:03d}-{v["name"]}.npz', boxes, conf, classes, masks)
                completed += 1; sequence += 1
                helper.journal(output/'events', sequence, {'phase': 'input_complete', 'completedInputs': completed, 'attemptedInputs': attempted, 'prediction': prediction, **event})
            print(json.dumps({'confirmedInputs': completed, 'plannedInputs': expected, 'lastOrdinal': s['ordinal']}), flush=True)
        sequence += 1; helper.journal(output/'events', sequence, {'phase': 'complete', 'completedInputs': completed, 'attemptedInputs': attempted})
        report = reconstruct(execution_ref, output); helper.durable_new(output/'model-probe-report.json', report)
        helper.durable_new(output/'terminal.json', {'phase': 'complete', 'completedInputs': completed, 'attemptedInputs': attempted, 'wallSeconds': time.monotonic()-t0, 'report': bind(output/'model-probe-report.json')})
        print(json.dumps({'ok': True, 'report': bind(output/'model-probe-report.json'), 'counts': report['counts'], 'aggregateByVariant': report['aggregateByVariant'], 'comparisonSummary': report['comparisonSummary']}), flush=True)
    except BaseException as error:
        if claimed:
            failure = {'phase': 'aborted', 'completedInputs': completed, 'attemptedInputs': attempted, 'exceptionType': type(error).__name__, 'message': str(error), 'execution': execution_ref, 'resumingAllowed': False}
            path = output/'exception-terminal.json' if output.is_dir() else Path(str(output)+'-exception-terminal.json')
            helper.durable_new(path, failure)
        raise
    finally: guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--execution', type=Path); p.add_argument('--verify-report', type=Path); a = p.parse_args()
    if a.verify_report:
        old = json.loads(a.verify_report.read_bytes())
        if reconstruct(old['execution'], a.verify_report.parent) != old: raise ValueError('reconstruction_mismatch: saved predictions')
        print(json.dumps({'ok': True, 'decision': 'saved_prediction_replay_identical', 'additionalModelCalls': 0})); return
    if not a.execution: p.error('--execution required')
    run(a.execution)
if __name__ == '__main__': main()
