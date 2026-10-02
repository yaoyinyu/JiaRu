"""绑定新人工轮廓的逐甲视觉记录并更新处置；几何/重放不自动批准训练。"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

PASS = 'mask_visual_pass_pending_role_and_marker_gates'
RECORDED = 'recorded_mask_visual_pass_pending_full_split'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p): return {'path': str(Path(p).resolve()), 'sha256': sha(p)}
def checked(ref):
    p = Path(ref['path']).resolve()
    if not p.is_file() or sha(p) != ref['sha256']: raise ValueError('binding_mismatch: ' + str(p))
    return p
def read(ref): return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref, name):
    p = checked(ref); sys.path.insert(0, str(p.parent))
    spec = importlib.util.spec_from_file_location(name, p)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result
def unique(rows, key):
    result = {}
    for row in rows:
        if row[key] in result: raise ValueError('duplicate identity')
        result[row[key]] = row
    return result


def validate_visual(record, decision, prior):
    for key in ('ordinal', 'fileName', 'sourceGroup', 'sourceImage', 'sourceLabel', 'annotation', 'completeVisibleNails'):
        if record[key] != decision[key]: raise ValueError('source or annotation reconstruction mismatch')
    if decision['reviewedNailIndices'] != list(range(1, record['completeVisibleNails'] + 1)):
        raise ValueError('complete nail denominator changed')
    expected = [t['image'] for t in record['nativeSourceTiles']] + [p['image'] for p in record['nailPanels']]
    actual = decision['viewedArtifacts']
    if [r['sha256'] for r in actual] != [r['sha256'] for r in expected]:
        raise ValueError('original pixel view coverage mismatch')
    mode = decision['reviewEvidenceMode']
    if mode == 'direct_original_pixel_review':
        if actual != expected: raise ValueError('direct review path mismatch')
    elif mode == 'prior_approved_annotation_and_panels_sha256_identical':
        if (prior is None or prior['decision'] != PASS or prior['failedNailIndices'] or
                prior['annotation']['sha256'] != record['annotation']['sha256'] or
                prior['viewedArtifacts'] != actual or prior['reviewedNailIndices'] != decision['reviewedNailIndices']):
            raise ValueError('invalid prior approved review reuse')
        for key in ('ordinal', 'fileName', 'sourceGroup', 'sourceImage', 'sourceLabel', 'completeVisibleNails'):
            if prior[key] != record[key]: raise ValueError('prior source changed')
    else: raise ValueError('unsupported visual review provenance')
    if decision['trainingUse'] != 'prohibited': raise ValueError('unexpected training promotion')
    if not decision['reason'] or not decision['markerDecision']: raise ValueError('missing manual decision')
    failed = decision['failedNailIndices']
    if len(set(failed)) != len(failed) or any(i not in decision['reviewedNailIndices'] for i in failed):
        raise ValueError('invalid failed nail identity')
    if decision['decision'] == PASS:
        if failed: raise ValueError('failed nail cannot pass')
    elif decision['decision'] == 'label_rework':
        if not failed: raise ValueError('rework needs explicit failed nail')
    else: raise ValueError('unsupported mask disposition')


def apply_reviews(baseline, decisions, evidence_ref):
    rows = copy.deepcopy(baseline['currentFullSplitRecords'])
    index = unique([r for r in rows if r['split'] == 'train'], 'ordinal')
    unique(decisions, 'ordinal')
    for d in decisions:
        r = index[d['ordinal']]
        if r['currentSourceDisposition'] != 'label_rework': raise ValueError('cannot override another source disposition')
        for key in ('fileName', 'sourceGroup', 'sourceImage', 'sourceLabel'):
            if r[key] != d[key]: raise ValueError('baseline source identity changed')
        if r['historicalMaskCount'] != d['completeVisibleNails']: raise ValueError('historical denominator changed')
        r['currentSourceDisposition'] = RECORDED if d['decision'] == PASS else 'label_rework'
        r['latestManualMaskReview'] = d
        r['currentTruthCandidateEvidence'] = {'annotation': d['annotation'], 'visualReviewReport': evidence_ref,
                                            'status': 'reviewed_manual_mask_pending_role_marker_full_split'}
        r['existingReviewedMaskCount'] = d['completeVisibleNails'] if d['decision'] == PASS else 0
        if d['decision'] == PASS:
            r['qualificationDebts'] = [debt for debt in r.get('qualificationDebts', [])
                                       if debt != 'original_resolution_complete_source_and_every_nail_mask_review']
        r['formalTrainingApproved'] = False; r['trainingUse'] = 'prohibited'
    return rows


def audit(execution_ref):
    execution = read(execution_ref); inputs = execution['inputs']
    if checked(inputs['runnerSource']) != Path(__file__).resolve(): raise ValueError('runner identity mismatch')
    guard = module(inputs['readOnlyGuard'], 'manual_review_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        candidates = read(inputs['candidateReport']); prior_candidates = read(inputs['priorCandidateReport'])
        visual = read(inputs['visualDecisions']); prior_visual = read(inputs['priorVisualDecisions'])
        baseline = read(inputs['baselineDisposition'])
        for report in (candidates, prior_candidates, visual, prior_visual, baseline):
            if any(report[k] != 0 for k in ('modelCalls', 'optimizerSteps', 'formalTrainingApprovedImages')):
                raise ValueError('unexpected inference or truth promotion')
            if report['full30PilotAllowed'] or report['trainingAllowed']: raise ValueError('unexpected training authorization')
        if visual['inputs']['candidateReport'] != inputs['candidateReport'] or visual['inputs']['priorVisualDecisions'] != inputs['priorVisualDecisions']:
            raise ValueError('visual report identity mismatch')
        if prior_visual['inputs']['candidateReport'] != inputs['priorCandidateReport']:
            raise ValueError('prior visual candidate identity mismatch')
        # Reconstruct both immutable candidate versions, not only the latest selected polygons.
        for candidate, ref in ((prior_candidates, inputs['priorCandidateReport']), (candidates, inputs['candidateReport'])):
            runner = module(candidate['inputs']['runnerSource'], 'manual_candidates_runner')
            if runner.build(candidate['execution'], checked(ref).parent, verify=True) != candidate:
                raise ValueError('candidate report reconstruction mismatch')
        runner = module(read(baseline['execution'])['inputs']['runnerSource'], 'prior_source_review_runner')
        if runner.audit(baseline['execution']) != baseline: raise ValueError('baseline disposition replay mismatch')
        scope = read(candidates['inputs']['scope'])
        if scope['inputs']['sourceDispositionReport'] != inputs['baselineDisposition']:
            raise ValueError('repair scope baseline identity mismatch')
        frozen = [s['ordinal'] for s in scope['sources']]
        records = unique(candidates['records'], 'ordinal'); previous = unique(prior_candidates['records'], 'ordinal')
        decisions = unique(visual['sourceDispositions'], 'ordinal'); priors = unique(prior_visual['sourceDispositions'], 'ordinal')
        if any(list(mapping) != frozen for mapping in (records, previous, decisions, priors)):
            raise ValueError('full repair source order or coverage mismatch')
        for ordinal in frozen:
            old_decision = {**priors[ordinal], 'reviewEvidenceMode': 'direct_original_pixel_review'}
            validate_visual(previous[ordinal], old_decision, None)
            validate_visual(records[ordinal], decisions[ordinal], priors[ordinal])
            for ref in priors[ordinal]['viewedArtifacts'] + decisions[ordinal]['viewedArtifacts']: checked(ref)
        updated = apply_reviews(baseline, list(decisions.values()), inputs['visualDecisions'])
        train = [r for r in updated if r['split'] == 'train']
        passed = [d for d in decisions.values() if d['decision'] == PASS]
        return {'schemaVersion': 1, 'ok': True, 'decision': 'manual_mask_visual_records_bound_training_prohibited',
                'execution': execution_ref, 'inputs': inputs, 'baselineDisposition': inputs['baselineDisposition'],
                'canonicalTruthIndex': candidates['canonicalTruthIndex'],
                'sourceDispositions': visual['sourceDispositions'], 'priorSourceDispositions': prior_visual['sourceDispositions'],
                'currentFullSplitRecords': updated,
                'counts': {**candidates['counts'], 'maskVisualPassedImages': len(passed),
                           'maskVisualPassedNails': sum(d['completeVisibleNails'] for d in passed),
                           'labelReworkImages': len(decisions) - len(passed),
                           'priorVisualFailedImages': sum(d['decision'] == 'label_rework' for d in priors.values()),
                           'priorVisualFailedNails': sum(len(d['failedNailIndices']) for d in priors.values()),
                           'fullSourceImages': len(updated), 'historicalRois': sum(r['historicalMaskCount'] for r in updated),
                           'recordedTrainMaskCount': sum(r['existingReviewedMaskCount'] or 0 for r in train if r['currentSourceDisposition'] == RECORDED),
                           'trainDispositions': dict(sorted(Counter(r['currentSourceDisposition'] for r in train).items()))},
                'fidelity': {'bothCandidateVersionsReplayed': True, 'priorFailurePreserved': True,
                             'unaffectedSourcesAndRolesPreserved': True, 'canonicalTruthIndexUnchanged': True},
                'visualReviewReplayMeaning': 'Binding and pixel reconstruction do not repeat or replace original visual judgment.',
                'modelCalls': 0, 'optimizerSteps': 0, 'formalTrainingApprovedImages': 0,
                'trainingAllowed': False, 'full30PilotAllowed': False}
    finally: guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execution', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path)
    args = p.parse_args()
    if args.verify_report:
        report = json.loads(args.verify_report.read_text(encoding='utf-8'))
        if audit(report['execution']) != report: raise ValueError('manual review report reconstruction mismatch')
        print(json.dumps({'ok': True, 'decision': 'manual_review_replay_identical'}))
    else:
        if not args.execution or not args.output: p.error('--execution and --output required')
        report = audit(bind(args.execution))
        with args.output.open('x', encoding='utf-8') as stream: stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: report[k] for k in ('ok', 'decision', 'counts')}, ensure_ascii=False))


if __name__ == '__main__': main()
