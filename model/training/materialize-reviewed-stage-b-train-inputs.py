"""按完整已审供给物化train-only原尺寸条件输入；不执行模型或批准训练。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


d = module(HERE / 'reviewed-role-development-data.py', 'train_native_data')


def require(condition, message):
    if not condition:
        raise ValueError('reconstruction_mismatch: ' + message)


def validate_cohort(plan, sources, diagnostics, reviewed_rejections):
    """完整重建候选顺序、真值一一分配、角色与拒识；不以候选数代替真值。"""
    index = {d.key(s['identity']): s for s in sources}
    keys = [d.key(r['identity']) for r in diagnostics]
    require(len(index) == len(sources) and len(keys) == len(set(keys)), 'source identity collision')
    require(set(keys) == set(index), 'full train source denominator')
    require(all(s['identity']['split'] == 'train' for s in sources), 'non-train source')
    expected = []
    truths = set()
    for row in diagnostics:
        key = d.key(row['identity']); source = index[key]
        require(row['truthNails'] == source['maskCount'] == len(row['truthMaskSha256']), 'truth denominator')
        require(row['annotation'] == source['annotation'] and row['sourceGroup'] == source['sourceGroup'] and row['size'] == source['size'], 'diagnostic source metadata')
        require(row['candidates'] == len(row['predictionMaskSha256']), 'candidate denominator')
        pairs = {p['predictionIndex']: p for p in row['primaryAssignment']}
        require(len(pairs) == len(row['primaryAssignment']), 'candidate assignment collision')
        assigned_truths = [p['truthIndex'] for p in pairs.values()]
        require(sorted(assigned_truths) == list(range(1, source['maskCount'] + 1)), 'complete one-to-one truth assignment')
        require(all(1 <= j <= row['candidates'] for j in pairs), 'assignment candidate index')
        rejected = set(range(1, row['candidates'] + 1)) - set(pairs)
        require(rejected == set(reviewed_rejections.get(key, [])), 'unreviewed or missing same-candidate rejection')
        for j in range(1, row['candidates'] + 1):
            pair = pairs.get(j)
            if pair:
                require(pair['roiFullTruthCoverage'] and pair['coarseMaskSeedValid'], 'incomplete ROI or seed')
                target = {'kind': 'complete_reviewed_nail_mask', 'truthIndex': pair['truthIndex'],
                          'truthMaskSha256': row['truthMaskSha256'][pair['truthIndex'] - 1]}
                truths.add((key, pair['truthIndex']))
            else:
                target = {'kind': 'reject_same_candidate_only', 'truthIndex': None,
                          'emptyTargetIsNotNoNailsInRgbRoi': True}
            expected.append((key, j, row['prediction'], row['predictionMaskSha256'][j - 1], target))
    require(len(plan['records']) == len(expected), 'all-candidate denominator')
    for record, (key, j, prediction, coarse_sha, target) in zip(plan['records'], expected, strict=True):
        ci = record['candidateIdentity']; source = index[key]
        require(ci == {'identity': source['identity'], 'prediction': prediction, 'predictionIndex': j,
                       'coarseMaskSha256': coarse_sha}, 'candidate identity/order/seed')
        require(record['currentSplit'] == 'train' and record['target'] == target, 'target or split drift')
        for name in ('sourceImage', 'annotation', 'sourceGroup', 'size'):
            require(record[name] == source[name], 'candidate source ' + name)
    total = sum(s['maskCount'] for s in sources)
    counts = {'train': {'sources': len(sources), 'sourceGroups': len({s['sourceGroup'] for s in sources}),
                        'truthNails': total, 'candidateInputs': len(expected),
                        'positiveInputs': len(truths), 'rejectInputs': len(expected) - len(truths)}}
    require(len(truths) == total and plan['counts'] == counts, 'full truth/counts contract')
    require(plan['fullTruthDenominator'] == total and plan['missingTruthsPreserved'] == [], 'missing truth denominator')
    require(plan['reachability'] == {'primaryFullRoiNails': total, 'oracleFullRoiNails': total,
                                    'trainRatio': 1.0, 'geometryOnlyNotSegmentationQuality': True}, 'geometric reachability contract')
    return counts


def resources(execution_ref):
    execution = d.read(execution_ref)
    require(execution['purpose'] == 'reviewed_train_only_native_stage_b_pixel_materialization', 'execution purpose')
    for ref in execution['sources'].values():
        d.checked(ref)
    require(d.checked(execution['sources']['materializer']) == Path(__file__).resolve(), 'materializer identity')
    require(execution['budget'] == {'newInferenceCalls': 0, 'optimizerSteps': 0, 'newChatImageInputs': 0,
                                    'trainingAllowed': False}, 'zero-model materialization budget')
    plan = d.read(execution['plan'])
    for ref in plan['inputs'].values():
        d.checked(ref)
    require(plan['purpose'] == 'expanded_train_only_native_stage_b_pixel_materialization_contract_not_training_budget', 'plan purpose')
    require(plan['datasetMaterializationAllowed'] and not plan['trainingAllowed'] and not plan['trainingBudgetAllocated'], 'materialization-only authorization')
    require(plan['newInferenceCallsAllowed'] == plan['optimizerStepsAllowed'] == plan['newChatImageInputsAllowed'] == 0, 'zero-model plan')
    require(plan['sameCandidateCoarseMaskRequired'] and plan['rgbRoiFullNailPixelsRequired'] and plan['roiPolicy'] == 'square_context_035', 'native input policy')
    require(plan['nativeTruthDomain'] == 'Pillow L255 original polygon threshold>0 bool; native output L255 binary', 'native truth storage domain')
    require(plan['internalValRecordsAndFilesReadOnlyNotMaterializedIntoNewTrain'] and plan['old124InputsAnd745FilesPreserved'], 'old roles/assets preservation')
    audit = d.read(plan['inputs']['expandedSupplyAudit']); scope = d.read(audit['scope'])
    require(audit['ok'] and audit['developmentSourceMetadataAndCompleteTruthsQualified'], 'source metadata qualification')
    original = d.read(scope['inputs']['existingTrainingContract'])
    adapter = copy.deepcopy(original)
    adapter['records'] = scope['proposedFullQualityInventory']
    adapter['inputs']['pairDisposition'] = scope['inputs']['currentPairDisposition']
    adapter['counts'] = {s: {'sources': sum(r['identity']['split'] == s for r in adapter['records']),
                             'nails': sum(r['maskCount'] for r in adapter['records'] if r['identity']['split'] == s)}
                         for s in ('train', 'val')}
    selected = d.validate(adapter)
    # JSON坐标对还原为读取器返回的tuple；仅比较完整序列化字节，不改写权威存储域。
    require(d.raw(selected) == d.raw(audit['selectedSources']), 'full reviewed source metadata')
    sources = [s for s in selected if s['identity']['split'] == 'train']
    prior_plan = d.read(plan['inputs']['priorNativeInputPlan'])
    legacy = module(d.checked(execution['sources']['priorMaterializer']), 'train_native_legacy')
    legacy.validate(prior_plan)
    prior = d.read(plan['inputs']['priorNativeMaterialization'])
    require(prior['plan'] == plan['inputs']['priorNativeInputPlan'] and prior['ok'], 'prior native plan')
    for ref in prior['files']:
        d.checked(ref)
    old_diagnostic = d.read(prior_plan['inputs']['diagnostic'])
    old_rows = [r for r in old_diagnostic['records'] if r['identity']['split'] == 'train']
    diagnostic = d.read(plan['inputs']['singleSourceDiagnostic'])
    require(diagnostic['ok'] and diagnostic['allTrainRecords'] == old_rows + [diagnostic['newSourceRecord']], 'saved diagnostic preservation')
    require(diagnostic['existing10TrainRecordsExactlyPreserved'] and diagnostic['internalValInputs'] == diagnostic['protectedHoldoutInputs'] == diagnostic['optimizerSteps'] == 0, 'diagnostic roles/budget')
    require(plan['inputs']['stageAWeights'] == audit['existingStageAWeights'] == prior_plan['inputs']['stageAWeights'], 'same actual Stage A weights')
    prior_train = [r for r in prior_plan['records'] if r['currentSplit'] == 'train']
    require(plan['records'][:len(prior_train)] == prior_train, 'prior train candidate records')
    old_visual = d.read(prior_plan['inputs']['wholeVisual']); visual = d.read(plan['inputs']['wholeVisual'])
    reviewed = {d.key(r['identity']): r['backgroundFalsePositiveCandidateIndices'] + r['duplicateOrContaminatedCandidateIndices']
                for r in old_visual['records'] if r['identity']['split'] == 'train'}
    require(visual['ok'] and visual['identity'] == diagnostic['newSourceRecord']['identity'], 'new visual identity')
    reviewed[d.key(visual['identity'])] = visual['backgroundFalsePositiveCandidateIndices'] + visual['duplicateOrContaminatedCandidateIndices']
    validate_cohort(plan, sources, diagnostic['allTrainRecords'], reviewed)
    for r in plan['records']:
        d.checked(r['visualEvidence']); d.checked(r['candidateIdentity']['prediction'])
    return execution, plan, sources, prior, original['cacheCleanupRoots']


def crop_native(rgb, coarse, target, box, positive):
    require(rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3, 'RGB uint8 storage')
    require(coarse.dtype == target.dtype == np.bool_ and coarse.shape == target.shape == rgb.shape[:2], 'bool full-source mask storage')
    require(len(box) == 4 and all(isinstance(n, (int, np.integer)) for n in box), 'integer ROI origin')
    x0, y0, x1, y1 = box
    require(0 <= x0 < x1 <= rgb.shape[1] and 0 <= y0 < y1 <= rgb.shape[0], 'ROI bounds')
    c = coarse[y0:y1, x0:x1].copy(); t = target[y0:y1, x0:x1].copy()
    require(c.any(), 'empty same-candidate coarse seed')
    if positive:
        require(target.any() and (target & coarse).any(), 'positive truth/seed intersection')
    else:
        require(not target.any(), 'rejection target contains source nail pixels')
    restored = np.zeros_like(target); restored[y0:y1, x0:x1] = t
    require(np.array_equal(restored, target), 'full truth lost in integer ROI roundtrip')
    return {'nativeRgb': rgb[y0:y1, x0:x1].copy(), 'nativeCoarse': c.astype(np.uint8) * 255,
            'nativeTarget': t.astype(np.uint8) * 255}


def image_array(path, mode):
    with Image.open(path) as image:
        image.load()
        require(image.mode == mode, 'native image mode ' + mode)
        return np.asarray(image).copy()


def native_file(path, pixels, replay):
    if replay:
        require(np.array_equal(image_array(path, 'RGB' if pixels.ndim == 3 else 'L'), pixels), 'native pixel reconstruction')
    else:
        with path.open('xb') as stream:
            Image.fromarray(pixels).save(stream, format='PNG'); stream.flush(); os.fsync(stream.fileno())
        require(np.array_equal(image_array(path, 'RGB' if pixels.ndim == 3 else 'L'), pixels), 'PNG roundtrip')
    return d.bind(path)


def build(execution_ref, root, replay=False):
    execution, plan, sources, prior, cleanup_roots = resources(execution_ref)
    guard = d.load(d.checked(plan['inputs']['readOnlyGuard']), 'train_native_guard')
    guard.install_read_only_ultralytics_image_check()
    created = False; decoded = {}; files = []; rows = []; source_rows = []
    try:
        helper = module(d.checked(plan['inputs']['predictionHelper']), 'train_native_predictions')
        roi = module(d.checked(plan['inputs']['roiHelper']), 'train_native_roi')
        evaluator = module(d.checked(execution['sources']['truthReader']), 'train_native_truths')
        claim = {'execution': execution_ref, 'newInferenceCalls': 0, 'optimizerSteps': 0,
                 'newChatImageInputs': 0, 'trainingAllowed': False}
        if replay:
            require(d.read(d.bind(root / 'attempt.json')) == claim, 'original materialization claim')
        else:
            root.mkdir(parents=True, exist_ok=False); created = True
            d.new(root / 'attempt.json', claim)
        source_map = {d.key(s['identity']): s for s in sources}
        old_map = {(d.key(r['candidateIdentity']['identity']), r['candidateIdentity']['predictionIndex']): r
                   for r in prior['records'] if r['split'] == 'train'}
        inherited_count = 0
        for number, row in enumerate(plan['records'], 1):
            ci = row['candidateIdentity']; key = d.key(ci['identity']); source = source_map[key]
            if key not in decoded:
                rgb = image_array(d.checked(source['sourceImage']), 'RGB')
                require([rgb.shape[1], rgb.shape[0]] == source['size'], 'original image size')
                boxes, _, _, masks = helper.load_prediction(ci['prediction'], source['size'])
                truth = evaluator.truths(source)
                require(len(truth) == source['maskCount'], 'full source truth denominator')
                decoded[key] = rgb, boxes, masks, truth
                source_rows.append({'identity': source['identity'], 'sourceGroup': source['sourceGroup'],
                                    'sourceImage': source['sourceImage'], 'annotation': source['annotation'],
                                    'size': source['size'], 'maskCount': len(truth),
                                    'originalRgbSha256': hashlib.sha256(rgb.tobytes()).hexdigest(),
                                    'truthMaskSha256': [hashlib.sha256(t.tobytes()).hexdigest() for t in truth]})
            rgb, boxes, masks, truth = decoded[key]; j = ci['predictionIndex'] - 1
            require(hashlib.sha256(masks[j].tobytes()).hexdigest() == ci['coarseMaskSha256'], 'same candidate seed SHA')
            box = roi.crop_box(boxes[j], *source['size'], plan['roiPolicy'])
            require(box is not None, 'invalid native ROI')
            positive = row['target']['truthIndex'] is not None
            target = truth[row['target']['truthIndex'] - 1] if positive else np.zeros(rgb.shape[:2], bool)
            if positive:
                require(hashlib.sha256(target.tobytes()).hexdigest() == row['target']['truthMaskSha256'], 'original truth bool domain')
            values = crop_native(rgb, masks[j], target, box, positive)
            paths = {name: native_file(root / f'{number:03d}-{name}.png', pixels, replay)
                     for name, pixels in values.items()}
            files.extend(paths.values())
            old_row = old_map.get((key, ci['predictionIndex']))
            if old_row is not None:
                require(old_row['candidateIdentity'] == ci and old_row['target'] == row['target'] and old_row['cropBox'] == list(box), 'inherited native candidate metadata')
                for name, pixels in values.items():
                    old_path = d.checked(old_row['paths'][name])
                    require(np.array_equal(image_array(old_path, 'RGB' if name == 'nativeRgb' else 'L'), pixels), 'inherited native pixels')
                inherited_count += 1
            x0, y0, x1, y1 = box
            neighbor = np.any(truth, axis=0)[y0:y1, x0:x1]
            rows.append({'ordinal': number, 'candidateIdentity': ci, 'sourceGroup': source['sourceGroup'],
                         'split': 'train', 'target': row['target'], 'cropBox': list(box),
                         'nativeSize': [x1-x0, y1-y0], 'presenceTarget': positive, 'paths': paths,
                         'nativePixelSha256': {name: hashlib.sha256(p.tobytes()).hexdigest() for name,p in values.items()},
                         'sourceTruthPixels': int(target.sum()), 'nativeTargetPixels': int((values['nativeTarget'] > 0).sum()),
                         'sourceTruthPixelsLost': 0, 'integerCoordinateRoundtripExact': True,
                         'candidateRejectIsNotEmptyRgb': not positive,
                         'reviewedNailPixelsInRejectRgbContext': int(neighbor.sum()) if not positive else None,
                         'inheritedOriginalNativePixelsExact': old_row is not None})
        require(inherited_count == len(old_map), 'all prior train native inputs inherited')
        # 重验所有绑定及旧物化文件；源树的权威全树重放由执行尾链串行完成。
        for ref in prior['files']:
            d.checked(ref)
        for source in sources:
            d.checked(source['sourceImage']); d.checked(source['annotation'])
        for ref in execution['sources'].values():
            d.checked(ref)
        require(len(files) == len(plan['records']) * 3, 'native file denominator')
        result = {'schemaVersion': 1, 'ok': True, 'decision': 'train_only_native_pixels_exact_normal_training_contract_pending',
                  'execution': execution_ref, 'plan': execution['plan'], 'root': str(root.resolve()),
                  'sources': execution['sources'], 'sourceRecords': source_rows, 'records': rows, 'files': files,
                  'counts': plan['counts'], 'fullTruthDenominator': plan['fullTruthDenominator'],
                  'candidateInputs': len(rows), 'generatedFiles': len(files), 'nativeFilesPerCandidate': 3,
                  'fullTruthIntegerCoordinateRoundtripExact': True, 'sourceTruthPixelsLost': 0,
                  'inheritedPriorTrainNativeInputsPixelExact': inherited_count,
                  'priorNativeMaterialization': plan['inputs']['priorNativeMaterialization'],
                  'allPriorNativeFilesSha256Preserved': True, 'internalValMaterializedIntoNewTrain': 0,
                  'nativeLayout': {'coordinateMapping': 'integer source crop origin plus unscaled local coordinates',
                                   'padding': 0, 'resampling': False, 'rgb': 'uint8 RGB', 'masks': 'uint8 L 0/255'},
                  'newChatImageInputs': 0, 'sourceInferenceInputs': 0, 'optimizerSteps': 0,
                  'normalTrainingBudgetAllocated': False, 'trainingAllowed': False,
                  'formalReleaseAllowed': False, 'productHold': True}
        expected_tree = {Path(f['path']).resolve() for f in files} | {(root/'attempt.json').resolve(), (root/'materialization.json').resolve()}
        if replay:
            require((root/'materialization.json').read_bytes() == d.raw(result), 'full materialization JSON bytes')
        else:
            d.new(root/'materialization.json', result)
        require({p.resolve() for p in root.rglob('*') if p.is_file()} == expected_tree, 'full native file tree')
        return result
    except BaseException as error:
        if created and not (root/'failure.json').exists():
            d.new(root/'failure.json', {'type': type(error).__name__, 'message': str(error), 'completedCandidateInputs': len(rows),
                                      'newModelCalls': 0, 'optimizerSteps': 0, 'trainingAllowed': False})
        raise
    finally:
        decoded.clear()
        for path in [*cleanup_roots, root]:
            guard.remove_ultralytics_label_caches(Path(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path); parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        result = build(old['execution'], args.verify_report.resolve().parent, replay=True)
    else:
        require(args.execution is not None and args.output is not None, 'execution and output required')
        result = build(d.bind(args.execution), args.output.resolve())
    print(json.dumps({k: result[k] for k in ('ok', 'decision', 'candidateInputs', 'generatedFiles', 'counts', 'trainingAllowed')}))


if __name__ == '__main__':
    main()
