"""重放全部人工候选版本；分离旧ROI与新版完整甲面，不自动批准训练。"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location('manual_review_shared', Path(__file__).with_name('audit-native-manual-mask-review.py'))
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)
PASS, RECORDED = shared.PASS, shared.RECORDED


def validate_denominators(row, source, decision):
    for key in ('ordinal', 'fileName', 'sourceGroup', 'sourceImage', 'sourceLabel', 'historicalMaskCount'):
        if row[key] != source[key]:
            raise ValueError('scope historical identity mismatch')
    if decision['completeVisibleNails'] != source['fullyTraceableNails']:
        raise ValueError('new complete denominator changed')
    old_count = row['historicalMaskCount']
    spurious = source['spuriousOldNails']
    if len(set(spurious)) != len(spurious) or any(i not in range(1, old_count + 1) for i in spurious):
        raise ValueError('invalid declared historical spurious identity')
    review = row.get('latestOriginalPixelReview')
    if review is None:
        raise ValueError('missing frozen original source judgment')
    for key in ('ordinal', 'fileName', 'sourceGroup', 'sourceImage', 'sourceLabel', 'historicalMaskCount', 'fullyTraceableNails', 'spuriousOldNails'):
        if review[key] != source[key]:
            raise ValueError('source judgment denominator mismatch')
    if (review['sourceQualityDecision'] != 'complete_visible_nails_traceable' or
            review.get('additionalUntraceableNails', 0) != 0 or
            source['fullyTraceableNails'] != old_count - len(spurious)):
        raise ValueError('unexplained historical/new denominator change')


def apply_reviews(baseline, decisions, scope, evidence_ref):
    rows = copy.deepcopy(baseline['currentFullSplitRecords'])
    train = shared.unique([r for r in rows if r['split'] == 'train'], 'ordinal')
    sources = shared.unique(scope['sources'], 'ordinal')
    if list(shared.unique(decisions, 'ordinal')) != list(sources):
        raise ValueError('full repair coverage mismatch')
    for d in decisions:
        row = train[d['ordinal']]
        if row['currentSourceDisposition'] != 'label_rework':
            raise ValueError('cannot override another source disposition')
        for key in ('fileName', 'sourceGroup', 'sourceImage', 'sourceLabel'):
            if row[key] != d[key]:
                raise ValueError('baseline source changed')
        validate_denominators(row, sources[d['ordinal']], d)
        passed = d['decision'] == PASS
        row['currentSourceDisposition'] = RECORDED if passed else 'label_rework'
        row['latestManualMaskReview'] = d
        row['currentTruthCandidateEvidence'] = {
            'annotation': d['annotation'], 'visualReviewReport': evidence_ref,
            'status': 'reviewed_manual_mask_pending_role_marker_full_split' if passed else 'manual_mask_rework_required'}
        row['existingReviewedMaskCount'] = d['completeVisibleNails'] if passed else 0
        if passed:
            row['qualificationDebts'] = [x for x in row.get('qualificationDebts', [])
                                        if x != 'original_resolution_complete_source_and_every_nail_mask_review']
        row['formalTrainingApproved'] = False
        row['trainingUse'] = 'prohibited'
    selected = set(sources)
    for before, after in zip(baseline['currentFullSplitRecords'], rows):
        if (before['split'] != 'train' or before['ordinal'] not in selected) and before != after:
            raise ValueError('unaffected source or role changed')
    return rows


def audit(execution_ref):
    execution = shared.read(execution_ref)
    inputs = execution['inputs']
    if shared.checked(inputs['runnerSource']) != Path(__file__).resolve():
        raise ValueError('runner mismatch')
    if shared.checked(inputs['visualValidator']) != Path(shared.__file__).resolve():
        raise ValueError('shared validator mismatch')
    guard = shared.module(inputs['readOnlyGuard'], 'manual_v2_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        versions = inputs['candidateVersions']
        if not versions:
            raise ValueError('missing candidate lineage')
        baseline = shared.read(inputs['baselineDisposition'])
        runner = shared.module(shared.read(baseline['execution'])['inputs']['runnerSource'], 'manual_v2_baseline')
        if runner.audit(baseline['execution']) != baseline:
            raise ValueError('baseline reconstruction mismatch')
        prior_decisions = None
        prior_visual_ref = None
        scope = None
        lineage = []
        seen = set()
        for version in versions:
            candidate_ref, visual_ref = version['candidateReport'], version['visualDecisions']
            if candidate_ref['sha256'] in seen:
                raise ValueError('duplicate candidate version')
            seen.add(candidate_ref['sha256'])
            candidate, visual = shared.read(candidate_ref), shared.read(visual_ref)
            for report in (candidate, visual):
                if (any(report[k] != 0 for k in ('modelCalls', 'optimizerSteps', 'formalTrainingApprovedImages')) or
                        report['trainingAllowed'] or report['full30PilotAllowed']):
                    raise ValueError('unexpected model use or training promotion')
            if (visual['inputs']['candidateReport'] != candidate_ref or
                    visual['inputs'].get('priorVisualDecisions') != prior_visual_ref):
                raise ValueError('visual lineage identity mismatch')
            builder = shared.module(candidate['inputs']['runnerSource'], 'manual_v2_builder')
            if builder.build(candidate['execution'], shared.checked(candidate_ref).parent, verify=True) != candidate:
                raise ValueError('candidate reconstruction mismatch')
            current_scope = shared.read(candidate['inputs']['scope'])
            if current_scope['inputs']['sourceDispositionReport'] != inputs['baselineDisposition']:
                raise ValueError('scope baseline mismatch')
            if scope is not None and current_scope != scope:
                raise ValueError('candidate version changed frozen scope')
            scope = current_scope
            frozen = [s['ordinal'] for s in scope['sources']]
            records = shared.unique(candidate['records'], 'ordinal')
            decisions = shared.unique(visual['sourceDispositions'], 'ordinal')
            if list(records) != frozen or list(decisions) != frozen:
                raise ValueError('source order or coverage mismatch')
            for ordinal in frozen:
                shared.validate_visual(records[ordinal], decisions[ordinal], None if prior_decisions is None else prior_decisions[ordinal])
                for ref in decisions[ordinal]['viewedArtifacts']:
                    shared.checked(ref)
            lineage.append({'candidateReport': candidate_ref, 'visualDecisions': visual_ref,
                            'failedNails': sum(len(d['failedNailIndices']) for d in decisions.values()),
                            'sourceDispositions': visual['sourceDispositions']})
            prior_decisions, prior_visual_ref = decisions, visual_ref
        shared.checked(candidate['canonicalTruthIndex'])
        updated = apply_reviews(baseline, list(decisions.values()), scope, visual_ref)
        train = [r for r in updated if r['split'] == 'train']
        passed = [d for d in decisions.values() if d['decision'] == PASS]
        failed_nails = sum(len(d['failedNailIndices']) for d in decisions.values())
        return {
            'schemaVersion': 2, 'ok': True, 'decision': 'manual_mask_visual_records_bound_training_prohibited',
            'execution': execution_ref, 'inputs': inputs, 'baselineDisposition': inputs['baselineDisposition'],
            'canonicalTruthIndex': candidate['canonicalTruthIndex'], 'candidateLineage': lineage,
            'sourceDispositions': visual['sourceDispositions'], 'currentFullSplitRecords': updated,
            'counts': {**candidate['counts'], 'candidateVersionsReplayed': len(versions),
                       'maskVisualPassedImages': len(passed), 'maskVisualPassedNails': sum(d['completeVisibleNails'] for d in passed),
                       'individualVisualPassedNails': candidate['counts']['completeVisibleNails'] - failed_nails,
                       'failedNails': failed_nails, 'labelReworkImages': len(decisions) - len(passed),
                       'fullSourceImages': len(updated), 'historicalRois': sum(r['historicalMaskCount'] for r in updated),
                       'unaffectedSources': len(updated) - len(decisions),
                       'recordedTrainMaskCount': sum(r['existingReviewedMaskCount'] or 0 for r in train if r['currentSourceDisposition'] == RECORDED),
                       'trainDispositions': dict(sorted(Counter(r['currentSourceDisposition'] for r in train).items()))},
            'fidelity': {'allCandidateVersionsReplayed': True, 'historicalFailuresPreserved': True,
                         'historicalAndNewDenominatorsSeparated': True, 'unaffectedSourcesAndRolesPreserved': True,
                         'canonicalTruthIndexUnchanged': True},
            'visualReviewReplayMeaning': 'Hash/pixel reconstruction binds evidence; it cannot repeat or replace actual visual judgment.',
            'modelCalls': 0, 'optimizerSteps': 0, 'formalTrainingApprovedImages': 0,
            'trainingAllowed': False, 'full30PilotAllowed': False}
    finally:
        guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        report = json.loads(args.verify_report.read_text(encoding='utf-8'))
        if audit(report['execution']) != report:
            raise ValueError('manual disposition reconstruction mismatch')
        print(json.dumps({'ok': True, 'decision': 'manual_review_v2_replay_identical'}))
    else:
        if not args.execution or not args.output:
            parser.error('--execution and --output required')
        report = audit(shared.bind(args.execution))
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'ok': report['ok'], 'counts': report['counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
