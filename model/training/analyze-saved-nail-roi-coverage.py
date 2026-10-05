"""存档预测的候选几何与原像素边界诊断；不运行模型，不批准数据或发布。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path


def binding(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def checked(ref):
    p = Path(ref['path'])
    if binding(p) != ref:
        raise ValueError('reconstruction_mismatch: ' + str(p))
    return p


def load(ref, name):
    spec = importlib.util.spec_from_file_location(name, checked(ref))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def crop_box(box, width, height, policy):
    x0, y0, x1, y1 = map(float, box)
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or x1 <= x0 or y1 <= y0:
        raise ValueError('invalid candidate box')
    if policy == 'native_xyxy_floor_ceil':
        crop = (min(width, max(0, math.floor(x0))), min(height, max(0, math.floor(y0))),
                min(width, max(0, math.ceil(x1))), min(height, max(0, math.ceil(y1))))
        return crop if crop[2] > crop[0] and crop[3] > crop[1] else None
    if policy != 'square_context_035':
        raise ValueError('unknown frozen ROI policy')
    side = max(16, math.ceil(max(x1 - x0, y1 - y0) * 1.7))
    if side > min(width, height):
        return None
    left = min(max(round((x0 + x1) / 2 - side / 2), 0), width - side)
    top = min(max(round((y0 + y1) / 2 - side / 2), 0), height - side)
    return left, top, left + side, top + side


def coverage_matrix(truths, boxes, policy):
    import numpy as np
    height, width = truths.shape[1:]
    crops = [crop_box(b, width, height, policy) for b in boxes]
    matrix = np.zeros((len(truths), len(boxes)), np.float64)
    for i, truth in enumerate(truths):
        pixels = int(truth.sum())
        if not pixels:
            raise ValueError('empty truth')
        for j, crop in enumerate(crops):
            if crop is not None:
                x0, y0, x1, y1 = crop
                matrix[i, j] = int(truth[y0:y1, x0:x1].sum()) / pixels
    return crops, matrix


def oracle_allocation(coverage, seed_ious):
    """一候选最多归属一真值；先最大化完整覆盖数量，再以粗mask IoU确定分配。"""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    if coverage.shape != seed_ious.shape:
        raise ValueError('coverage/seed matrix mismatch')
    valid = seed_ious > 0
    full = (coverage == 1) & valid
    bonus = min(coverage.shape) + 1
    scores = np.where(valid, full.astype(float) * bonus + seed_ious, -bonus)
    rows, cols = linear_sum_assignment(-scores) if scores.size else ([], [])
    return [{'truthIndex': int(i) + 1, 'predictionIndex': int(j) + 1,
             'truthPixelCoverage': float(coverage[i, j]), 'coarseMaskIoU': float(seed_ious[i, j]),
             'completeTruthCoverage': bool(full[i, j])}
            for i, j in zip(rows, cols, strict=True) if valid[i, j]]


def boundary_stats(truth, prediction, tolerance):
    import cv2
    import numpy as np
    kernel = np.ones((3, 3), np.uint8)
    tb = truth & ~cv2.erode(truth.astype(np.uint8), kernel).astype(bool)
    pb = prediction & ~cv2.erode(prediction.astype(np.uint8), kernel).astype(bool)
    near = np.ones((2 * tolerance + 1, 2 * tolerance + 1), np.uint8)
    tn = cv2.dilate(tb.astype(np.uint8), near).astype(bool)
    pn = cv2.dilate(pb.astype(np.uint8), near).astype(bool)
    precision = int((pb & tn).sum()) / max(1, int(pb.sum()))
    recall = int((tb & pn).sum()) / max(1, int(tb.sum()))
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    tband, pband = truth & tn, prediction & pn
    union = int((tband | pband).sum())
    return {'nativePixelTolerance': tolerance, 'boundaryF1': f1,
            'boundaryIoU': int((tband & pband).sum()) / union if union else 0.0,
            'truthMissingPixels': int((truth & ~prediction).sum()),
            'predictionOutsideTruthPixels': int((prediction & ~truth).sum()),
            'outsideTruthMeaning': '相对该真值的多余像素，可能为邻甲；未经视觉审核不叫背景误检。'}


CONTRACT = {
    'sources': 7, 'truthNails': 40, 'originalCandidates': 45, 'originalIoU075Matches': 36,
    'truthIoUThreshold': 0.75, 'acceptance': 'all_saved_candidates_exactly_no_threshold_scan_or_topk',
    'roiPolicies': ['native_xyxy_floor_ceil', 'square_context_035'],
    'primaryRoiPolicy': 'square_context_035', 'completeCoverage': 'all_native_truth_pixels_inside_crop_exactly_1',
    'candidateSeedValidity': 'saved_coarse_mask_and_truth_have_nonzero_intersection',
    'primaryAssignment': 'preserve_original_hungarian_mask_iou_assignment',
    'oracleAssignment': 'one_to_one_max_complete_coverage_then_coarse_mask_iou',
    'nativeBoundaryTolerancePixels': 2, 'squareContextRatio': 0.35,
    'geometryMeaning': 'diagnostic_crop_geometry_only_not_current_production_policy_or_segmentation_success',
    'decisionRule': 'primary_baseline_low_iou_without_full_roi=proposal_geometry_deficit_else_mask_quality_deficit',
    'oracleMeaning': 'theoretical_geometric_upper_bound_not_semantic_segmentation_feasibility_or_95_percent_usability',
    'requiredDiagnosticCompleteCoverageRatio': 1.0,
    'additionalModelCallsAllowed': 0, 'trainingAllowed': False,
}


def analyze(plan_ref):
    plan = json.loads(checked(plan_ref).read_bytes())
    if plan['contract'] != CONTRACT or checked(plan['inputs']['analyzerSource']) != Path(__file__).resolve():
        raise ValueError('reconstruction_mismatch: frozen contract or analyzer')
    inputs = plan['inputs']
    guard = load(inputs['readOnlyGuard'], 'saved_roi_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        import numpy as np
        probe = json.loads(checked(inputs['savedProbeReport']).read_bytes())
        scope = json.loads(checked(inputs['attributionScope']).read_bytes())
        failure = json.loads(checked(inputs['originalProtocolFailure']).read_bytes())
        if failure['ok'] is not False or failure['decision'] != 'reconstruction_mismatch':
            raise ValueError('historical protocol failure drift')
        runner = load(inputs['probeRunner'], 'saved_roi_probe_runner')
        # 硬保真：全部55输入的接受候选、完整实例分配及旧指标须逐项同构。
        if runner.reconstruct(probe['execution'], checked(inputs['savedProbeReport']).parent) != probe:
            raise ValueError('reconstruction_mismatch: accepted candidates')
        helper = load(inputs['predictionHelper'], 'saved_roi_prediction_helper')
        # 仅编译已绑定源中的纯几何函数；不加载历史训练器及其模块副作用。
        import ast
        crop_tree = ast.parse(checked(inputs['squareCropReference']).read_text(encoding='utf-8'))
        node = next(n for n in crop_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'proposal_crop_box')
        namespace = {'math': math}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<bound-proposal-crop>', 'exec'), namespace)
        sources = scope['sources']
        source_keys = [runner.key(s['identity']) for s in sources]
        if len(set(source_keys)) != CONTRACT['sources'] or sum(s['completeVisibleNails'] for s in sources) != CONTRACT['truthNails']:
            raise ValueError('reconstruction_mismatch: full cohort')
        if [runner.key(r['identity']) for r in probe['records']] != source_keys:
            raise ValueError('reconstruction_mismatch: stable identity order')
        results = []
        for source, old in zip(sources, probe['records'], strict=True):
            checked(source['sourceImage'])
            truth = runner.truth_masks(source)
            original = old['predictions']['original']
            boxes, confidence, classes, masks = helper.load_prediction(original['prediction'], source['imageSize'])
            matching = helper.match_masks(masks, truth, CONTRACT['truthIoUThreshold'])
            rebuilt = {'prediction': original['prediction'], 'boxesXyxy': boxes.tolist(), 'confidence': confidence.tolist(),
                       'classes': classes.tolist(), 'instanceCount': len(masks), **matching}
            if rebuilt != original:
                raise ValueError('reconstruction_mismatch: original candidate identity')
            ious = np.asarray(matching['iouMatrix'], np.float64)
            policies = {}
            for policy in CONTRACT['roiPolicies']:
                crops, coverage = coverage_matrix(truth, boxes, policy)
                if policy == 'square_context_035':
                    w, h = source['imageSize']
                    if crops != [namespace['proposal_crop_box'](tuple(b), w, h, 0.35) for b in boxes]:
                        raise ValueError('reconstruction_mismatch: reference crop geometry')
                assignments = oracle_allocation(coverage, ious)
                policies[policy] = {'crops': [list(c) if c else None for c in crops], 'truthPixelCoverageMatrix': coverage.tolist(),
                                    'oracleOneToOneAssignment': assignments,
                                    'oracleFullCoverageNails': sum(a['completeTruthCoverage'] for a in assignments)}
            instances = []
            allocation = {a['truthIndex']: a for a in matching['assignment']}
            for i, target in enumerate(truth, 1):
                assigned = allocation.get(i)
                j = assigned['predictionIndex'] - 1 if assigned else None
                roi = {policy: float(policies[policy]['truthPixelCoverageMatrix'][i - 1][j]) if j is not None else 0.0
                       for policy in CONTRACT['roiPolicies']}
                missed = i in matching['missedTruthIndices']
                full = roi[CONTRACT['primaryRoiPolicy']] == 1.0 and assigned is not None and assigned['iou'] > 0
                instances.append({'truthIndex': i, 'originalAssignmentPreserved': assigned,
                                  'originalIoU075Failed': missed, 'baselineCandidateRoiCoverage': roi,
                                  'baselinePrimaryFullTruthCoverage': full,
                                  'diagnosticAttribution': ('proposal_geometry_deficit' if not full else 'mask_quality_deficit') if missed else 'original_iou_gate_matched_not_pixel_boundary_pass',
                                  'nativeBoundary': boundary_stats(target, masks[j] if j is not None else np.zeros_like(target), 2)})
            results.append({'identity': source['identity'], 'ordinal': source['ordinal'], 'sourceGroup': source['sourceGroup'],
                            'source': source, 'originalPrediction': original['prediction'], 'originalMatchingPreserved': matching,
                            'policies': policies, 'instances': instances, 'trainingUse': 'prohibited'})
        all_instances = [a for r in results for a in r['instances']]
        failed = [a for a in all_instances if a['originalIoU075Failed']]
        if len(failed) != 4 or sum(len(r['originalMatchingPreserved']['predictionMaskPixels']) for r in results) != 45:
            raise ValueError('reconstruction_mismatch: original full cohort totals')
        ceiling = sum(r['policies'][CONTRACT['primaryRoiPolicy']]['oracleFullCoverageNails'] for r in results) / 40
        return {'schemaVersion': 1, 'ok': True, 'decision': 'saved_prediction_roi_and_boundary_diagnostic_only',
                'plan': plan_ref, 'contract': CONTRACT, 'acceptedCandidateReconstructionIdentical': True,
                'originalProtocolFailurePreserved': True, 'records': results,
                'counts': {'sources': 7, 'truthNails': 40, 'acceptedOriginalCandidates': 45, 'originalIoU075Matches': 36,
                           'originalIoU075Failures': 4, 'failedWithPrimaryFullRoi': sum(a['baselinePrimaryFullTruthCoverage'] for a in failed),
                           'failedWithPrimaryRoiDeficit': sum(not a['baselinePrimaryFullTruthCoverage'] for a in failed),
                           'baselinePrimaryFullCoverageNails': sum(a['baselinePrimaryFullTruthCoverage'] for a in all_instances),
                           'oracleFullCoverageNailsByPolicy': {p: sum(r['policies'][p]['oracleFullCoverageNails'] for r in results) for p in CONTRACT['roiPolicies']}},
                'geometricCeiling': {'ratio': ceiling, 'requiredDiagnosticRatio': 1.0, 'ceilingToRequiredRatio': ceiling,
                                    'geometryReachable': ceiling == 1.0, 'doesNotProveSemanticOrReleaseQuality': True},
                'additionalModelCalls': 0, 'optimizerSteps': 0, 'formalTrainingApprovedImages': 0,
                'trainingAllowed': False, 'full30PilotAllowed': False,
                'limitations': ['train-role seven-source cohort only; not clean98 or independent release evidence',
                                'native2px is original-pixel diagnostic, not input384 proxy or formal completeness approval',
                                'outside-truth pixels and unassigned candidates need visual review before semantic attribution',
                                'old marker protocol failure and whole-split/source-parent/training-input debts remain']}
    finally:
        guard.remove_ultralytics_label_caches(Path(plan['datasetRoot']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        if analyze(old['plan']) != old:
            raise ValueError('reconstruction_mismatch: analysis report')
        print(json.dumps({'ok': True, 'additionalModelCalls': 0, 'replay': True, 'counts': old['counts']}))
        return
    if not args.plan or not args.output:
        parser.error('--plan and --output required')
    result = analyze(binding(args.plan))
    with args.output.open('xb') as f:
        f.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'sha256': binding(args.output)['sha256'], 'counts': result['counts'], 'ceiling': result['geometricCeiling']}))


if __name__ == '__main__':
    main()
