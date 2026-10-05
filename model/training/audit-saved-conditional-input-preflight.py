"""完整存档候选的条件输入、目标提示与部署预算预检；零模型调用。"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import importlib.util


def bind(p):
    p = Path(p).resolve()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def checked(ref):
    p = Path(ref['path'])
    if bind(p) != ref:
        raise ValueError('reconstruction_mismatch: ' + str(p))
    return p


def module(ref, name):
    spec = importlib.util.spec_from_file_location(name, checked(ref))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def capped_indices(confidence, maximum):
    if maximum < 1:
        raise ValueError('invalid proposal maximum')
    return sorted(range(len(confidence)), key=lambda j: (-float(confidence[j]), j))[:maximum]


def seed_identity(intersections, target_index):
    own = int(intersections[target_index])
    others = [int(v) for j, v in enumerate(intersections) if j != target_index]
    other = max(others, default=0)
    return {'ownTruthIntersectionPixels': own, 'maximumOtherTruthIntersectionPixels': other,
            'strictlyTargetDominant': own > other and own > 0}


def overlap_area(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def pack_input(rgb, coarse):
    import numpy as np
    if rgb.shape != (384, 384, 3) or coarse.shape != (384, 384) or not np.isin(coarse, [0, 255]).all():
        raise ValueError('conditional input pixel contract')
    values = (rgb.astype(np.float64) / 255 - np.array([.485, .456, .406])) / np.array([.229, .224, .225])
    return np.concatenate([values.transpose(2, 0, 1), coarse[None] / 255], axis=0).astype(np.float32)


CONTRACT = {
    'sources': 7, 'truthNails': 40, 'savedCandidates': 45,
    'cropPolicy': 'square_context_035_as_frozen_diagnostic_not_legacy_browser_rectangle',
    'rgbResize': 'PIL_RGB_uint8_BILINEAR_384', 'coarseResize': 'PIL_L_uint8_NEAREST_384',
    'packedShape': [4, 384, 384], 'packing': 'float64_ImageNet_normalization_then_float32_CHW_plus_binary_same_candidate_mask',
    'promptGate': 'assigned_truth_coarse_intersection_strictly_greater_than_every_other_truth',
    'neighborPixels': 'diagnostic_not_failure_when_same_candidate_prompt_unique',
    'markerSafety': 'roi_zero_intersection_with_registered_marker_box_expanded_10_native_pixels',
    'capPolicy': 'descending_saved_confidence_stable_predictionIndex_first10_before_StageB',
    'maximumProposalsPerImage': 10,
    'capMeaning': 'new_route_diagnostic_using_legacy_preStageB_order_and_cap_not_full_browser_mask_replay',
    'denominator': 'all40_truths_preserved_even_if_candidate_removed',
    'unassignedTargets': 'unresolved_not_auto_background_or_empty',
    'requiredCoverageRatio': 1.0, 'rejectedOutput': 'remove_same_candidate_no_coarse_fallback_success',
    'executionError': 'manual_confirmation_not_valid_empty_rejection',
    'additionalModelCallsAllowed': 0, 'trainingAllowed': False,
}


def analyze(plan_ref):
    plan = json.loads(checked(plan_ref).read_bytes())
    if plan['contract'] != CONTRACT or checked(plan['inputs']['runnerSource']) != Path(__file__).resolve():
        raise ValueError('reconstruction_mismatch: contract/runner')
    refs = plan['inputs']
    guard = module(refs['readOnlyGuard'], 'conditional_preflight_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        import numpy as np
        from PIL import Image
        for ref in refs.values():
            checked(ref)
        scope = json.loads(checked(refs['scope']).read_bytes())
        old = json.loads(checked(refs['attribution']).read_bytes())
        a = module(refs['roiAnalyzer'], 'conditional_roi_analyzer')
        if a.analyze(old['plan']) != old:
            raise ValueError('reconstruction_mismatch: accepted candidates and original attribution')
        pack = json.loads(checked(refs['markerPack']).read_bytes())
        marker_rows = {json.dumps(r['sourceRecordPreserved']['identity'], sort_keys=True): r for r in pack['records']}
        runner = module(refs['probeRunner'], 'conditional_truth_helper')
        helper = module(refs['predictionHelper'], 'conditional_saved_helper')
        expected_keys = [runner.key(s['identity']) for s in scope['sources']]
        if expected_keys != [runner.key(r['identity']) for r in old['records']] or len(set(expected_keys)) != 7:
            raise ValueError('reconstruction_mismatch: stable source order')
        all_candidate_keys, results = [], []
        for r in old['records']:
            source = r['source']
            truth = runner.truth_masks(source)
            boxes, confidence, classes, coarse = helper.load_prediction(r['originalPrediction'], source['imageSize'])
            with Image.open(checked(source['sourceImage'])) as image:
                rgb_image = image.convert('RGB')
            if list(rgb_image.size) != source['imageSize']:
                raise ValueError('source pixel domain drift')
            kept = capped_indices(confidence, 10)
            policies = r['policies']['square_context_035']
            coverage = np.asarray(policies['truthPixelCoverageMatrix'], np.float64)
            ious = np.asarray(r['originalMatchingPreserved']['iouMatrix'], np.float64)
            assignments = {v['predictionIndex'] - 1: v['truthIndex'] - 1 for v in r['originalMatchingPreserved']['assignment']}
            marker_row = marker_rows[json.dumps(source['identity'], sort_keys=True)]
            contract = marker_row['interventionContract']
            w, h = source['imageSize']
            marker = None
            if contract:
                x0, y0, x1, y1 = contract['markerBox']
                marker = [max(0, x0 - 10), max(0, y0 - 10), min(w, x1 + 10), min(h, y1 + 10)]
            candidates = []
            for j, crop in enumerate(policies['crops']):
                key = [*runner.key(source['identity']), j + 1]
                all_candidate_keys.append(key)
                if crop is None:
                    raise ValueError('unmaterializable diagnostic ROI')
                x0, y0, x1, y1 = crop
                rgb = np.asarray(rgb_image.crop(crop).resize((384, 384), Image.Resampling.BILINEAR)).copy()
                seed = np.asarray(Image.fromarray(coarse[j].astype(np.uint8) * 255).crop(crop).resize((384, 384), Image.Resampling.NEAREST)).copy()
                packed = pack_input(rgb, seed)
                if not np.isfinite(packed).all() or packed.shape != (4, 384, 384):
                    raise ValueError('invalid packed input')
                intersections = [int((t & coarse[j]).sum()) for t in truth]
                assigned = assignments.get(j)
                prompt = seed_identity(intersections, assigned) if assigned is not None else None
                other_pixels = sum(int(t[y0:y1, x0:x1].sum()) for k, t in enumerate(truth) if k != assigned) if assigned is not None else None
                candidates.append({'candidateKey': key, 'predictionIndex': j + 1, 'confidence': float(confidence[j]),
                    'cropBox': crop, 'originalAssignedTruthIndex': assigned + 1 if assigned is not None else None,
                    'coarseTruthIntersectionPixels': intersections, 'promptIdentity': prompt,
                    'neighborTruthPixelsInRoi': other_pixels, 'markerHaloIntersectionArea': overlap_area(crop, marker) if marker else 0,
                    'markerSafetyMeaning': 'only_registered_marker_window_not_all_source_shortcuts',
                    'keptByFrozenProposalCap': j in kept,
                    'packedInputSha256': hashlib.sha256(packed.astype('<f4', copy=False).tobytes()).hexdigest(),
                    'rgb384PixelsSha256': hashlib.sha256(rgb.tobytes()).hexdigest(),
                    'coarse384PixelsSha256': hashlib.sha256(seed.tobytes()).hexdigest(),
                    'inputPromptSource': 'same_saved_candidate_mask_no_truth_prompt',
                    'targetStatus': 'same_candidate_assigned_truth_diagnostic_only' if assigned is not None else 'unresolved_no_automatic_empty_target',
                    'trainingUse': 'prohibited'})
            oracle = a.oracle_allocation(coverage[:, kept], ious[:, kept])
            for row in oracle:
                row['predictionIndex'] = kept[row['predictionIndex'] - 1] + 1
            results.append({'identity': source['identity'], 'ordinal': source['ordinal'], 'sourceGroup': source['sourceGroup'],
                'source': source, 'originalPrediction': r['originalPrediction'], 'originalMatchingPreserved': r['originalMatchingPreserved'],
                'candidateCount': len(coarse), 'keptPredictionIndices': [j + 1 for j in kept],
                'discardedPredictionIndices': [j + 1 for j in range(len(coarse)) if j not in kept],
                'discardedOriginalAssignedTruthIndices': [i + 1 for j, i in assignments.items() if j not in kept],
                'capOracleAssignment': oracle, 'capOracleFullCoverageNails': sum(v['completeTruthCoverage'] for v in oracle),
                'candidates': candidates, 'trainingUse': 'prohibited'})
        expected_candidates = [[*runner.key(c['identity']), c['predictionIndex']] for c in scope['candidates']]
        if all_candidate_keys != expected_candidates or len(all_candidate_keys) != 45:
            raise ValueError('reconstruction_mismatch: complete candidate cohort')
        positives = [c for r in results for c in r['candidates'] if c['originalAssignedTruthIndex'] is not None]
        ceiling = sum(r['capOracleFullCoverageNails'] for r in results)
        unique = sum(c['promptIdentity']['strictlyTargetDominant'] for c in positives)
        safe = sum(c['markerHaloIntersectionArea'] == 0 for c in positives)
        ok = ceiling == 40 and unique == 40 and safe == 40
        return {'schemaVersion': 1, 'ok': ok, 'decision': 'conditional_input_preflight_diagnostic_pass_pending_qualification' if ok else 'conditional_input_preflight_fail_no_training',
                'plan': plan_ref, 'contract': CONTRACT, 'acceptedCandidateReconstructionIdentical': True, 'records': results,
                'counts': {'sourceImages': 7, 'truthNails': 40, 'savedCandidates': 45, 'assignedCandidates': len(positives),
                           'unresolvedUnassignedCandidates': 45 - len(positives), 'strictlyUniqueAssignedPrompts': unique,
                           'assignedRoisWithoutRegisteredMarkerHalo': safe, 'assignedRoisContainingNeighborTruth': sum(c['neighborTruthPixelsInRoi'] > 0 for c in positives),
                           'capOracleFullCoverageNails': ceiling, 'discardedOriginalAssignedTruths': sum(len(r['discardedOriginalAssignedTruthIndices']) for r in results)},
                'capGeometricCeiling': {'ratio': ceiling / 40, 'requiredDiagnosticRatio': 1.0, 'ceilingToRequiredRatio': ceiling / 40,
                                       'geometryReachable': ceiling == 40, 'semanticQualityNotProven': True},
                'originalMarkerProtocolFailurePreserved': True, 'trainingAllowed': False, 'full30PilotAllowed': False,
                'formalTrainingApprovedImages': 0, 'additionalModelCalls': 0, 'optimizerSteps': 0,
                'limitations': ['same train-role7/40 cohort; not independent release evidence',
                                'source/parent/whole-group marker protocol and complete split qualification remain',
                                'tensor hashes validate input preparation, not trained segmentation or live browser crop equivalence',
                                'unassigned candidates require semantic review before empty target assignment']}
    finally:
        guard.remove_ultralytics_label_caches(Path(plan['datasetRoot']))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--plan', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--verify-report', type=Path)
    args = p.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        assert analyze(old['plan']) == old, 'reconstruction_mismatch: preflight report'
        print(json.dumps({'replay': True, 'ok': old['ok'], 'decision': old['decision'], 'counts': old['counts']}))
    else:
        if not args.plan or not args.output:
            p.error('--plan/--output required')
        result = analyze(bind(args.plan))
        with args.output.open('xb') as f:
            f.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        print(json.dumps({'sha256': bind(args.output)['sha256'], 'ok': result['ok'], 'decision': result['decision'], 'counts': result['counts']}))
