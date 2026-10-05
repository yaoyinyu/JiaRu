"""固定既有mask重复规则在Stage B候选预算前的存档可达性诊断。"""
import argparse
import json
from pathlib import Path
import importlib.util


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


p = module(Path(__file__).with_name('audit-saved-conditional-input-preflight.py'), 'proposal_preflight')
CONTRACT = {'maskIoUThreshold': 0.6, 'smallerMaskContainmentThreshold': 0.85, 'moreCompleteScoreTolerance': 0.12,
            'maximumProposalsPerImage': 10, 'changedVariable': 'existing_mask_duplicate_rule_before_StageB_confidence_cap',
            'order': 'descending_saved_confidence_stable_predictionIndex', 'postDedupCapOrder': 'same_kept_slot_order_as_existing_rule',
            'denominator': 'all7_sources_all40_truths_no_deletions', 'unassignedSemanticTargets': 'unresolved_not_auto_empty',
            'role': 'train_saved_only_diagnostic_no_threshold_scan', 'additionalModelCallsAllowed': 0}


def select_masks(confidence, masks):
    kept, events = [], []
    for j in p.capped_indices(confidence, max(1, len(confidence))):
        duplicate = None
        area = int(masks[j].sum())
        for slot, k in enumerate(kept):
            other = int(masks[k].sum())
            intersection = int((masks[j] & masks[k]).sum())
            if not area or not other or not intersection:
                continue
            iou = intersection / (area + other - intersection)
            containment = intersection / min(area, other)
            if iou >= .6 or containment >= .85:
                duplicate = (slot, k, other, iou, containment)
                break
        if duplicate is None:
            kept.append(j)
        else:
            slot, k, other, iou, containment = duplicate
            replace = area > other and float(confidence[j]) + .12 >= float(confidence[k])
            if replace:
                kept[slot] = j
            events.append({'candidateIndex': j + 1, 'selectedIndexBefore': k + 1, 'maskIoU': iou,
                           'smallerMaskContainment': containment, 'replacementByExistingRule': replace,
                           'discardedIndex': k + 1 if replace else j + 1})
    return kept[:10], kept, events


def analyze(plan_ref):
    plan = json.loads(p.checked(plan_ref).read_bytes())
    if plan['contract'] != CONTRACT or p.checked(plan['inputs']['runnerSource']) != Path(__file__).resolve():
        raise ValueError('reconstruction_mismatch: dedup contract')
    for ref in plan['inputs'].values():
        p.checked(ref)
    old = json.loads(p.checked(plan['inputs']['failedPreflight']).read_bytes())
    if old['ok'] is not False or old['decision'] != 'conditional_input_preflight_fail_no_training':
        raise ValueError('original cap failure not preserved')
    if p.analyze(old['plan']) != old:
        raise ValueError('reconstruction_mismatch: old full candidate preflight')
    previous_plan = json.loads(p.checked(old['plan']).read_bytes())
    guard = p.module(previous_plan['inputs']['readOnlyGuard'], 'dedup_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        import numpy as np
        helper = p.module(previous_plan['inputs']['predictionHelper'], 'dedup_saved_helper')
        a = p.module(previous_plan['inputs']['roiAnalyzer'], 'dedup_roi_helper')
        previous = json.loads(p.checked(previous_plan['inputs']['attribution']).read_bytes())
        rows = []
        for r, geometry in zip(old['records'], previous['records'], strict=True):
            if r['identity'] != geometry['identity']:
                raise ValueError('stable identity drift')
            _, confidence, _, masks = helper.load_prediction(r['originalPrediction'], r['source']['imageSize'])
            chosen, all_dedup, events = select_masks(confidence, masks)
            coverage = np.asarray(geometry['policies']['square_context_035']['truthPixelCoverageMatrix'])
            ious = np.asarray(geometry['originalMatchingPreserved']['iouMatrix'])
            allocation = a.oracle_allocation(coverage[:, chosen], ious[:, chosen])
            for v in allocation:
                v['predictionIndex'] = chosen[v['predictionIndex'] - 1] + 1
            lookup = {c['predictionIndex']: c for c in r['candidates']}
            input_valid = 0
            for v in allocation:
                c = lookup[v['predictionIndex']]
                intersections = c['coarseTruthIntersectionPixels']
                prompt = p.seed_identity(intersections, v['truthIndex'] - 1)
                v['sameCandidateStrictlyTargetDominant'] = prompt['strictlyTargetDominant']
                v['registeredMarkerHaloSafe'] = c['markerHaloIntersectionArea'] == 0
                v['inputGeometricallyValid'] = v['completeTruthCoverage'] and prompt['strictlyTargetDominant'] and v['registeredMarkerHaloSafe']
                input_valid += v['inputGeometricallyValid']
            rows.append({'identity': r['identity'], 'ordinal': r['ordinal'], 'source': r['source'],
                         'originalMatchingPreserved': r['originalMatchingPreserved'], 'originalPrediction': r['originalPrediction'],
                         'originalCandidateCount': len(masks), 'selectedPredictionIndices': [v + 1 for v in chosen],
                         'deduplicatedPredictionIndicesBeforeCap': [v + 1 for v in all_dedup], 'suppressionEvents': events,
                         'oracleAssignment': allocation, 'fullCoverageNails': sum(v['completeTruthCoverage'] for v in allocation),
                         'geometricallyValidConditionalInputs': input_valid, 'trainingUse': 'prohibited'})
        ceiling = sum(r['fullCoverageNails'] for r in rows)
        valid = sum(r['geometricallyValidConditionalInputs'] for r in rows)
        passed = ceiling == valid == 40
        return {'schemaVersion': 1, 'ok': passed,
                'decision': 'dedup_before_cap_diagnostic_geometric_input_pass_pending_qualification' if passed else 'dedup_before_cap_diagnostic_fail_no_training',
                'plan': plan_ref, 'contract': CONTRACT, 'records': rows,
                'counts': {'sourceImages': 7, 'truthNails': 40, 'originalCandidates': 45,
                           'selectedCandidates': sum(len(r['selectedPredictionIndices']) for r in rows),
                           'suppressedCandidates': sum(len(r['suppressionEvents']) for r in rows),
                           'fullCoverageNails': ceiling, 'geometricallyValidConditionalInputs': valid},
                'capGeometricCeiling': {'ratio': ceiling / 40, 'requiredDiagnosticRatio': 1.0, 'ceilingToRequiredRatio': ceiling / 40},
                'oldDirectConfidenceCapFailurePreserved': True, 'oldMarkerProtocolFailurePreserved': True,
                'acceptedOriginalCandidatesPreserved': True, 'newModelCalls': 0, 'optimizerSteps': 0,
                'formalTrainingApprovedImages': 0, 'trainingAllowed': False, 'full30PilotAllowed': False,
                'limitations': ['new acceptance/assignment is an explicit versioned diagnostic, not replacement of original Hungarian failures',
                                'coarse duplicates still need native semantic review; not automatically approved removal or empty targets',
                                'no live browser export or latency measurement; shape-filter/quality-score pipeline not claimed equivalent',
                                'geometry/prompt/registered-window safety are not whole-group shortcut or source independence gates']}
    finally:
        guard.remove_ultralytics_label_caches(Path(previous_plan['datasetRoot']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        assert analyze(old['plan']) == old, 'reconstruction_mismatch: dedup report'
        result = old
    else:
        if not args.plan or not args.output:
            parser.error('--plan/--output required')
        result = analyze(p.bind(args.plan))
        with args.output.open('xb') as f:
            f.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': result['ok'], 'decision': result['decision'], 'counts': result['counts'],
                      'report': p.bind(args.verify_report or args.output)}))
