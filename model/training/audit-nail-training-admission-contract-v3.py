"""零推理训练准入合同验收；合同有效、证据齐备和训练许可分别报告。

仅检查冻结元数据及逐实例诊断记录，不解码图像、不执行模型、不签发许可。
来源独立性还须由绑定的来源原件和原像素裁决证明，召回无命中不能替代。
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
VARIANTS = ('original', 'marker_removed', 'blank_removed', 'marker_moved', 'blank_moved')
RULES = {'wholeGroupRequired': True, 'allTruthDenominatorRequired': True, 'candidateMigrationRequired': True, 'maximumExcessLostMatchesOverBlank': 0, 'maximumExcessSpuriousOverBlank': 0, 'maximumExcessIouLossOverBlank': 0, 'maximumExcessBoundaryIouLossOverBlank': 0, 'maximumExcessBoundaryF1LossOverBlank': 0, 'maximumExcessAbsoluteMetricChangeOverBlank': 0, 'markerWindowAcceptedPixels': 0, 'noCoarseFallbackForRejectedCandidate': True, 'absenceOfMeasuredEffectIsNotCausalProof': True}
SOURCE_POLICY = {'proofKind': 'origin_chain_and_native_review', 'allCurrentSourcesAndParentsRequired': True, 'knownParentBindingsCannotBeOmitted': True, 'wholeGroupRequired': True, 'noHitNeverApproves': True, 'recallCompleteNeverApproves': True, 'metadataZeroConflictsNeverApproves': True, 'internalValNeverFormalIndependentOrTrain': True}
PHASES = [['native_controls', 'reference_marker_ablation'], ['source_origin_evidence', 'training_admission'], ['conditional_inputs', 'training_admission'], ['reference_marker_ablation', 'training_admission'], ['training_admission', 'train_only_reachability_capacity'], ['train_only_reachability_capacity', 'full30'], ['full30', 'candidate_marker_ablation'], ['candidate_marker_ablation', 'release_quality'], ['release_quality', 'completion_audit_v3']]

def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def checked(ref):
    if bind(ref['path']) != ref:
        raise ValueError('reconstruction_mismatch: binding ' + ref['path'])
    return Path(ref['path'])

def read(ref):
    return json.loads(checked(ref).read_bytes())

def identity(row):
    return tuple((row['identity'][k] for k in ('split', 'fileName', 'imageSha256')))

def unique(rows):
    keys = [identity(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate stable identity')
    return {identity(row): row for row in rows}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def validate_contract(contract):
    if contract['schemaVersion'] != 1 or contract['acceptanceRules'] != RULES:
        raise ValueError('unsupported or weakened marker rules')
    if contract['phaseEdges'] != PHASES:
        raise ValueError('dependency contract drift or future-model pretraining cycle')
    if contract['candidateMarkerRequiredBeforeRelease'] is not True:
        raise ValueError('candidate-specific marker gate missing')
    if contract['scopeMeaning'] != 'development_admission_not_formal_independent_val_or_release':
        raise ValueError('development evidence promoted to release')
    components = contract['referenceModels']
    if set(components) != {'stageA', 'stageB'}:
        raise ValueError('both reference components required')
    required = {'stageA': {'weights', 'inferenceSource'}, 'stageB': {'baseWeights', 'headWeights', 'headSource', 'contextSource', 'baseSource', 'packingSource'}}
    for name, component in components.items():
        if not required[name] <= set(component['artifacts']) or not component['runtime']:
            raise ValueError('model identity incomplete: ' + name)
        for ref in component['artifacts'].values():
            checked(ref)
        expected = digest({'artifacts': component['artifacts'], 'runtime': component['runtime']})
        if component['identitySha256'] != expected:
            raise ValueError('model component identity drift: ' + name)
    if contract['sourceOriginPolicy'] != SOURCE_POLICY:
        raise ValueError('source origin proof policy drift')
    if checked(contract['verifierSource']) != Path(__file__).resolve():
        raise ValueError('executed contract verifier not bound')
    for name in ('scope', 'ledger', 'disposition', 'targets', 'recall', 'referenceInventory', 'historicalAdmission', 'isolation'):
        checked(contract['inputs'][name])
    return True

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (not math.isfinite(value)):
        raise ValueError('nonfinite or invalid marker metric')
    return value

def marker_row_pass(row, required):
    """所有真值逐甲比较；原图失败仍留分母，不用净漏甲数隐藏实例迁移。"""
    variants = row['variants']
    paired = row['markerControlRequired']
    if type(paired) is not bool:
        raise ValueError('marker requirement unresolved')
    if set(variants) != (set(VARIANTS) if paired else {'original'}):
        raise ValueError('variant or paired denominator drift')
    for variant in variants.values():
        if len(variant['truths']) != required['maskCount']:
            raise ValueError('all-truth denominator drift')
        if [r['truthIndex'] for r in variant['truths']] != list(range(1, required['maskCount'] + 1)):
            raise ValueError('truth order or identity drift')
        if len(variant['acceptedCandidateIds']) != len(set(variant['acceptedCandidateIds'])):
            raise ValueError('duplicate candidate identity')
        candidates = [r['matchedCandidateId'] for r in variant['truths'] if r['matchedCandidateId'] is not None]
        if len(candidates) != len(set(candidates)) or not set(candidates) <= set(variant['acceptedCandidateIds']):
            raise ValueError('one-to-one accepted candidate assignment drift')
        for truth in variant['truths']:
            for metric in ('iou', 'boundaryIou', 'boundaryF1'):
                if not 0 <= number(truth[metric]) <= 1:
                    raise ValueError('metric range')
        for count in ('spuriousCount', 'markerWindowAcceptedPixels'):
            if type(variant[count]) is not int or variant[count] < 0:
                raise ValueError('invalid marker count')
        if variant['executionError'] or variant['coarseFallbackUsed']:
            return False
        if variant['markerWindowAcceptedPixels'] != 0:
            return False
    if not paired:
        return True
    for marker, blank in [('marker_removed', 'blank_removed'), ('marker_moved', 'blank_moved')]:
        intervention, control = (variants[marker], variants[blank])
        if intervention['spuriousCount'] > control['spuriousCount']:
            return False
        for actual, baseline, original in zip(intervention['truths'], control['truths'], variants['original']['truths']):
            if actual['matchedCandidateId'] != baseline['matchedCandidateId']:
                return False
            if any((actual[m] < baseline[m] for m in ('iou', 'boundaryIou', 'boundaryF1'))):
                return False
            if any((abs(actual[m] - original[m]) > abs(baseline[m] - original[m]) for m in ('iou', 'boundaryIou', 'boundaryF1'))):
                return False
        if set(intervention['acceptedCandidateIds']) != set(control['acceptedCandidateIds']):
            return False
    return True

def marker_coverage(required, evidence, contract):
    missing = list(required)
    passed = []
    if evidence is not None:
        if evidence['referenceModels'] != contract['referenceModels']:
            raise ValueError('marker evidence belongs to another model identity')
        if evidence['acceptanceRules'] != RULES or evidence['phase'] != 'pretraining_reference':
            raise ValueError('marker phase/rules mismatch')
        for name in ('stageA', 'stageB'):
            rows = unique(evidence['components'][name])
            if not set(rows) <= set(required):
                raise ValueError('marker includes qualification-excluded or foreign identity')
            for key, row in rows.items():
                source = required[key]
                if row['annotation'] != source['annotation'] or row['sourceGroup'] != source['sourceGroup']:
                    raise ValueError('marker truth/source drift')
                control = read(row['nativeInputProof'])
                if control['identity'] != row['identity'] or control['annotation'] != source['annotation'] or control['markerControlRequired'] != row['markerControlRequired'] or (control['allOriginalPixelsActuallyViewed'] is not True) or (control['scalingNotice'] is not False) or (control['inputControlsPassed'] is not True) or (not control['pages']):
                    raise ValueError('native paired input proof not closed')
                for ref in control['pages']:
                    checked(ref)
                if set(control['variants']) != set(row['variants']):
                    raise ValueError('model/native input variant drift')
                for variant, ref in control['variants'].items():
                    checked(ref)
                    if ref != row['variants'][variant]['inputImage']:
                        raise ValueError('inferred input image drift')
                marker_row_pass(row, source)
        for key in required:
            rows = [unique(evidence['components'][name]).get(key) for name in ('stageA', 'stageB')]
            if all((row is not None and marker_row_pass(row, required[key]) for row in rows)):
                if rows[0]['nativeInputProof'] != rows[1]['nativeInputProof']:
                    raise ValueError('components use different native input proof')
                passed.append(key)
        failed_groups = {required[k]['sourceGroup'] for k in required if k not in passed}
        passed = [k for k in passed if required[k]['sourceGroup'] not in failed_groups]
        missing = [k for k in required if k not in passed]
    return {'complete': not missing, 'passedSources': len(passed), 'missingSources': len(missing), 'missingIdentities': [required[k]['identity'] for k in missing]}

def source_coverage(required, evidence, contract):
    """来源原件链与原像素裁决须另提供；近重复完整召回不自动产生本证明。"""
    passed = []
    if evidence is not None:
        if evidence['referenceInventory'] != contract['inputs']['referenceInventory']:
            raise ValueError('source reference coverage drift')
        rows = unique(evidence['records'])
        if not set(rows) <= set(required):
            raise ValueError('source evidence outside current scope')
        for key, row in rows.items():
            source = required[key]
            if row['sourceGroup'] != source['sourceGroup'] or row['sourceImage'] != source['sourceImage']:
                raise ValueError('source identity drift')
            if row['proofKind'] != 'origin_chain_and_native_review':
                raise ValueError('no-hit/metadata cannot prove independence')
            origin = read(row['originChain'])
            review = read(row['nativeOriginReview'])
            if origin['identity'] != row['identity'] or origin['sourceImage'] != source['sourceImage'] or origin['sourceGroup'] != source['sourceGroup']:
                raise ValueError('origin identity drift')
            parent_refs = origin['parents']
            known_parents = source.get('parents', [])
            if origin['knownParentsPreserved'] != known_parents:
                raise ValueError('known parent identity/sourceGroup omitted or changed')
            for parent in known_parents:
                if parent['sourceImage'] not in parent_refs:
                    raise ValueError('known parent artifact omitted')
            for ref in [origin['originArtifact'], *parent_refs]:
                checked(ref)
            if review['identity'] != row['identity'] or review['originChain'] != row['originChain']:
                raise ValueError('native origin binding drift')
            if not review['pages']:
                raise ValueError('origin review pages missing')
            for ref in review['pages']:
                checked(ref)
            if origin['completeParentChain'] is True and review['allOriginalPixelsActuallyViewed'] is True and (review['scalingNotice'] is False) and (review['protectedOverlapDecision'] == 'no_overlap') and (review['referenceInventory'] == contract['inputs']['referenceInventory']) and (review['scope'] == 'source_and_all_parents_against_frozen_reference_inventory'):
                passed.append(key)
    failed_groups = {required[k]['sourceGroup'] for k in required if k not in passed}
    passed = [k for k in passed if required[k]['sourceGroup'] not in failed_groups]
    missing = [k for k in required if k not in passed]
    return {'complete': not missing, 'passedSources': len(passed), 'missingSources': len(missing), 'missingIdentities': [required[k]['identity'] for k in missing]}

def project_reviewed_source_quality(required, ledger, quality):
    if quality['originalCandidateCountsPreserved'] != ledger['currentCandidateCounts'] or quality['originalCandidateInventoryPreserved'] != ledger['sourceParentQualificationInventory']:
        raise ValueError('source quality original cohort drift')
    if quality['sourceQualityReviewedSources'] != len(required) or quality['sourceQualityRemainingSources'] != 0:
        raise ValueError('source quality full cohort review incomplete')
    current = unique(quality['currentQualityEligibleInventory'])
    if not set(current) <= set(required):
        raise ValueError('source quality scope outside original cohort')
    for k, row in current.items():
        for field in ('identity', 'sourceGroup', 'sourceImage', 'annotation', 'maskCount'):
            if row[field] != required[k][field]:
                raise ValueError('source quality retained truth drift')
    excluded = unique(quality['excludedFromFutureTraining'])
    if set(current) & set(excluded) or set(current) | set(excluded) != set(required):
        raise ValueError('source quality exclusion partition mismatch')
    for k, row in excluded.items():
        for field in ('identity', 'sourceGroup', 'sourceImage', 'annotation', 'maskCount'):
            if row[field] != required[k][field]:
                raise ValueError('source quality excluded truth drift')
    counts = quality['currentQualityEligibleCounts']
    if len(current) != counts['combinedSources'] or sum((r['maskCount'] for r in current.values())) != counts['combinedNails']:
        raise ValueError('source quality effective denominator drift')
    return ({k: required[k] for k in current}, counts, quality['currentCoverageProjection']['nativeInputControls'], quality['currentCoverageProjection']['conditionalInputs'])

def analyze(contract_ref, evidence_refs):
    contract = read(contract_ref)
    validate_contract(contract)
    docs = {name: read(ref) for name, ref in contract['inputs'].items()}
    scope, ledger = (docs['scope'], docs['ledger'])
    required = unique([r for g in scope['groups'] if not g.get('prospectiveTrainingCandidateExcluded') for r in g['activeQualificationSources']])
    if scope['prospectiveCandidateCounts'] != ledger['currentCandidateCounts']:
        raise ValueError('scope/ledger denominator drift')
    if len(required) != ledger['currentCandidateCounts']['combinedSources']:
        raise ValueError('cohort count drift')
    if sum((r['maskCount'] for r in required.values())) != ledger['currentCandidateCounts']['combinedNails']:
        raise ValueError('cohort nail drift')
    if any((r['identity']['split'] not in ('train', 'val') or r['trainingAllowed'] for r in required.values())):
        raise ValueError('protected role or premature approval')
    inventory = unique(ledger['sourceParentQualificationInventory'])
    if set(inventory) != set(required):
        raise ValueError('ledger/current qualification identities drift')
    for key, row in required.items():
        for field in ('identity', 'sourceGroup', 'sourceImage', 'annotation', 'maskCount'):
            if inventory[key][field] != row[field]:
                raise ValueError('ledger/source binding drift')
        row['parents'] = inventory[key]['parents']
        if row['identity']['split'] == 'train' and inventory[key]['knownRoleConflicts']:
            raise ValueError('protected source or parent conflict')
    current_counts = ledger['currentCandidateCounts']
    native, roi = (ledger['nativeInputControls'], ledger['conditionalInputs'])
    if 'sourceQualityEligibility' in docs:
        quality = docs['sourceQualityEligibility']
        import importlib.util
        plan = read(quality['plan'])
        runner = checked(plan['inputs']['runner'])
        spec = importlib.util.spec_from_file_location('admission_quality_projection', runner)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if module.analyze(quality['plan']) != quality:
            raise ValueError('source quality evidence reconstruction mismatch')
        required, current_counts, native, roi = project_reviewed_source_quality(required, ledger, quality)
    evidence = {name: read(ref) for name, ref in evidence_refs.items()}
    source = source_coverage(required, evidence.get('sourceOrigin'), contract)
    marker = marker_coverage(required, evidence.get('referenceMarker'), contract)
    gates = {'sourceParentIndependenceQualified': source['complete'], 'wholeGroupMarkerQualification': marker['complete'] and native['complete'], 'fullCohortConditionalInputQualified': roi['complete']}
    no_hits = []
    for result in docs['recall']['results']:
        query = read(result['report'])
        if not query['recalledPairs']:
            no_hits.append(query['target'])
    eligible_hashes = {r['identity']['imageSha256'] for r in required.values()}
    return {'schemaVersion': 1, 'contract': contract_ref, 'evidence': evidence_refs, 'contractDefinitionOk': True, 'ok': all(gates.values()), 'decision': 'evidence_ready_not_training_permission' if all(gates.values()) else 'admission_hold_missing_evidence', 'counts': current_counts, 'gates': gates, 'sourceOrigin': source, 'referenceMarker': marker, 'nativeInputControls': native, 'conditionalInputs': roi, 'noHitTargets': len(no_hits), 'currentNoHitSources': sum((t['imageSha256'] in eligible_hashes for t in no_hits)), 'noHitIsNotApproval': True, 'phaseEdges': PHASES, 'candidateMarkerRequiredBeforeRelease': True, 'approvalAuthority': 'none_contract_audit_only', 'trainingAllowed': False, 'formalTrainingApprovedImages': 0, 'full30PilotAllowed': False, 'newModelCalls': 0, 'optimizerSteps': 0, 'productHold': True}

def freeze(path, value):
    with Path(path).open('xb') as handle:
        handle.write((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())
        handle.flush()
        os.fsync(handle.fileno())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path)
    parser.add_argument('--source-origin', type=Path)
    parser.add_argument('--reference-marker', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        if analyze(old['contract'], old['evidence']) != old:
            raise ValueError('reconstruction_mismatch: admission contract report')
        print(json.dumps({'reconstructionOk': True, 'trainingAllowed': False, 'decision': old['decision']}))
        return
    if not args.contract or not args.output:
        parser.error('--contract and --output required')
    refs = {k: bind(p) for k, p in [('sourceOrigin', args.source_origin), ('referenceMarker', args.reference_marker)] if p is not None}
    result = analyze(bind(args.contract), refs)
    freeze(args.output, result)
    print(json.dumps({k: result[k] for k in ('contractDefinitionOk', 'ok', 'decision', 'gates', 'noHitTargets', 'currentNoHitSources', 'trainingAllowed')}, ensure_ascii=False))
if __name__ == '__main__':
    main()
