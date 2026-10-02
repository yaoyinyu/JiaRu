"""只读重建完整split的真值/角色/标记债务；成功盘点不授予训练资格。"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def checked(binding: dict) -> Path:
    path = Path(binding['path']).resolve()
    if not path.is_file() or sha(path) != binding['sha256']:
        raise ValueError(f'authority_binding_mismatch: {path}')
    return path


def read(binding: dict) -> dict:
    return json.loads(checked(binding).read_text(encoding='utf-8'))


def verify_bindings(value: Any) -> None:
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            checked(value)
        else:
            for child in value.values():
                verify_bindings(child)
    elif isinstance(value, list):
        for child in value:
            verify_bindings(child)


def module(binding: dict, name: str):
    spec = importlib.util.spec_from_file_location(name, checked(binding))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def index_unique(rows: list[dict], key: str) -> dict:
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError(f'duplicate_identity: {key}/{value}')
        result[value] = row
    return result


def validate_roi_contract(rows: list[dict], scope: dict) -> dict:
    if [row['id'] for row in rows] != scope['expectedHistoricalRoiIds']:
        raise ValueError('reconstruction_mismatch: historical ROI IDs/order')
    index_unique(rows, 'id')
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['split'], row['sourceFileName'], row['sourceGroup'])].append(row)
    counts = {split: {'instances': sum(len(v) for k, v in grouped.items() if k[0] == split),
                     'sourceImages': sum(k[0] == split for k in grouped),
                     'sourceGroups': len({k[2] for k in grouped if k[0] == split})}
              for split in sorted({k[0] for k in grouped})}
    if counts != scope['historicalSplitCounts']:
        raise ValueError('reconstruction_mismatch: split denominator')
    train_groups = {k[2] for k in grouped if k[0] == 'train'}
    if train_groups & {k[2] for k in grouped if k[0] == 'val'}:
        raise ValueError('reconstruction_mismatch: train/val group overlap')
    return grouped


def current_decision(row: dict) -> str:
    return row.get('currentDecision') or row.get('decision') or row.get('disposition') or row.get('sourceQualityDecision') or 'unknown'


def validate_split_lineage(original_split: str, current_split: str, expected: dict, filename: str) -> None:
    if [original_split, current_split] != expected[filename]:
        raise ValueError('source split lineage mismatch')
    if original_split == 'val' and current_split == 'train':
        raise ValueError('protected validation cannot return to train')


def classification(decision: str, accepted: bool) -> str:
    excluded = 'exclude' in decision or 'excluded' in decision
    isolated = 'isolated' in decision or 'quarantine' in decision
    if accepted and (excluded or isolated):
        raise ValueError('conflicting_current_visual_decisions')
    if excluded:
        return 'source_quality_excluded'
    if isolated:
        return 'source_marker_isolated'
    if accepted:
        return 'recorded_mask_visual_pass_pending_full_split'
    return 'pending_original_resolution_complete_source_and_mask_review'


def protected_hits(image_sha: str, group: str, parents: list[dict], roles: dict) -> list[dict]:
    identities = [('current', image_sha, group)]
    for parent in parents:
        if len(parent.get('imageSha256', '')) != 64 or not parent.get('sourceGroup'):
            raise ValueError('incomplete_parent_identity')
        identities.append(('parent', parent['imageSha256'], parent['sourceGroup']))
    return [{'identity': kind, 'role': role, 'byHash': digest in values['hashes'],
             'byGroup': source_group in values['sourceGroups']}
            for kind, digest, source_group in identities for role, values in sorted(roles.items())
            if digest in values['hashes'] or source_group in values['sourceGroups']]


def build_report(execution_binding: dict) -> dict[str, Any]:
    execution = read(execution_binding)
    if execution['modelCalls'] != 0 or execution['optimizerSteps'] != 0 or execution['trainingAllowed']:
        raise ValueError('execution scope must be read-only and zero-model')
    inputs = execution['inputs']
    verify_bindings(inputs)
    checked(inputs['runnerSource'])
    if Path(inputs['runnerSource']['path']).resolve() != Path(__file__).resolve():
        raise ValueError('runner identity mismatch')
    scope = read(inputs['frozenScope'])
    docs = {key: read(value) for key, value in scope['inputs'].items() if key != 'freezerSource'}
    checked(scope['inputs']['freezerSource'])
    rows = docs['roiManifest']['records']
    grouped = validate_roi_contract(rows, scope)
    historical = index_unique(docs['cycle012MaterializationReport']['records'], 'fileName')
    inventory = index_unique(docs['fullTrainInventory']['sourceImages'], 'sourceFileName')
    if set(inventory) != {k[1] for k in grouped if k[0] == 'train'}:
        raise ValueError('training source inventory coverage mismatch')
    canonical = index_unique(docs['canonicalTruthIndex']['canonicalTruths'], 'fileName')
    supply = index_unique(docs['reviewedSourceSupply']['records'], 'ordinal')
    low = index_unique(docs['lowDebtDiagnosticGate']['sources'], 'ordinal')
    authority = {key: read(value) for key, value in inputs['sourceDecisionReports'].items()}
    dispositions = {}
    for name, doc in authority.items():
        for item in doc.get('sourceDispositions', doc.get('sources', [])):
            ordinal = item['ordinal']
            if ordinal in dispositions:
                raise ValueError('duplicate_current_disposition')
            dispositions[ordinal] = (name, item)
    # New repair ledgers may omit previously excluded sources. Retain those
    # bound source-quality decisions instead of treating omissions as pending.
    fallback_bindings = inputs.get('priorSourceQualityReports', {})
    for name, binding in fallback_bindings.items():
        for item in read(binding)['sources']:
            decision = current_decision(item)
            if 'exclude' in decision and item['ordinal'] not in dispositions:
                dispositions[item['ordinal']] = (name, item)
    clean = read(inputs['shard001CleanDecision'])
    for ordinal in clean['sourceExcludedOrdinals']:
        dispositions[ordinal][1]['currentDecision'] = 'source_quality_excluded'
    for ordinal in clean['watermarkQuarantineOrdinals']:
        dispositions[ordinal][1]['currentDecision'] = 'source_marker_quarantine'
    # shard001 final clean decision supersedes the older repair-needed disposition.
    for ordinal in clean['provisionalCleanOrdinals']:
        dispositions[ordinal][1]['currentDecision'] = 'mask_visual_pass_pending_full_split'

    val_review = read(inputs['historicalValReview'])
    if val_review.get('ok') is not True or val_review['counts']['reviewedInstances'] != scope['historicalSplitCounts']['val']['instances']:
        raise ValueError('historical validation review drift')
    if val_review['inputs']['materializationReport'] != scope['inputs']['roiMaterializationReport']:
        raise ValueError('historical validation review materialization mismatch')
    role_supply = read(inputs['roleSourceSupply'])
    role_helper = module(inputs['roleHelper'], 'full_split_role_helper')
    roles, role_summary = role_helper.role_sets(role_supply)
    roles['currentHistoricalRoiValidation'] = {
        'hashes': {historical[k[1]]['imageSha256'] for k in grouped if k[0] == 'val'},
        'sourceGroups': {k[2] for k in grouped if k[0] == 'val'}}
    replacement = docs['releaseTestRoleReplacement']
    replacement_items = replacement['items'] + replacement['withdrawnTrainItems']
    roles['releaseTestReplacement'] = {'hashes': {r['imageSha256'] for r in replacement_items},
                                      'sourceGroups': {r['sourceGroup'] for r in replacement['withdrawnTrainGroups']} | {r['sourceGroup'] for r in replacement_items}}
    registry_bindings = []
    negative_records = {}
    for binding in docs['protectedHardNegativeRegistry']['entries']:
        manifest = read(binding)
        registry_bindings.append(binding)
        if manifest.get('ok') is not True or manifest.get('status') != 'PASS':
            raise ValueError('negative registry contract drift')
        canonical_sha = hashlib.sha256(json.dumps(manifest['items'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if canonical_sha != manifest['itemsSha256']:
            raise ValueError('negative manifest items drift')
        for item in manifest['items']:
            digest = item['imageSha256']
            identity = (item['sourceGroup'], binding['role'])
            if digest in negative_records and negative_records[digest] != identity:
                raise ValueError('negative metadata conflicting identity')
            negative_records[digest] = identity
    roles['protectedHardNegativeRegistry'] = {'hashes': set(negative_records),
                                            'sourceGroups': {v[0] for v in negative_records.values()}}
    gate_groups = index_unique(docs['groupEligibility']['groups'], 'sourceGroup')
    ledger = index_unique(docs['roleLedger']['records'], 'sha256')
    roi_root = Path(scope['inputs']['roiManifest']['path']).parent.resolve()
    source_root = Path(docs['cycle012MaterializationReport']['outputDir']).resolve()
    checked_files = 0
    for row in rows:
        for field in ('image', 'mask'):
            path = (roi_root / row[field]).resolve()
            if not path.is_relative_to(roi_root):
                raise ValueError('ROI path escapes dataset')
            checked({'path': str(path), 'sha256': row[field + 'Sha256']})
            checked_files += 1
    records = []
    for (split, filename, group), rois in grouped.items():
        original = historical[filename]
        validate_split_lineage(original['developmentSplit'], split, execution['expectedSplitLineage'], filename)
        if original['sourceGroup'] != group:
            raise ValueError('source group mismatch')
        source_image = {'path': str(source_root / original['image']), 'sha256': original['imageSha256']}
        source_label = {'path': str(source_root / original['label']), 'sha256': original['labelSha256']}
        checked(source_image); checked(source_label)
        checked_files += 2
        item = inventory.get(filename) if split == 'train' else None
        ordinal = item['ordinal'] if item else None
        if item and (item['sourceGroup'] != group or item['sourceImage'] != source_image or item['sourceLabel'] != source_label or item['roiIds'] != [r['id'] for r in rois] or item['maskCount'] != len(rois)):
            raise ValueError('training inventory reconstruction mismatch')
        accepted = supply.get(ordinal)
        decision_ref = None
        decision_row = {}
        if ordinal in dispositions:
            name, decision_row = dispositions[ordinal]
            decision_ref = inputs['sourceDecisionReports'].get(name) or fallback_bindings[name]
            digest = decision_row.get('sourceImage', {}).get('sha256') or decision_row.get('sourceImageSha256')
            if digest != source_image['sha256']:
                raise ValueError('current decision source identity mismatch')
            if decision_row.get('sourceGroup', group) != group or decision_row.get('sourceFileName', filename) != filename:
                raise ValueError('current decision group/name mismatch')
        if accepted and (accepted['imageSha256'] != source_image['sha256'] or accepted['sourceGroup'] != group or accepted['fileName'] != filename):
            raise ValueError('accepted supply source identity mismatch')
        status = classification(current_decision(decision_row), bool(accepted)) if split == 'train' else 'historical_internal_roi_review_pass_current_native_qualification_pending'
        truth = canonical.get(filename)
        if truth and (truth['imageSha256'] != source_image['sha256'] or truth['sourceGroup'] != group):
            raise ValueError('canonical truth identity conflict')
        # Missing explicit parent metadata remains a debt; names are only a recall aid.
        parents = original.get('parents', [])
        parent_hint = 'parent-' in group or 'crop' in filename.lower()
        parent_state = 'explicit_parent_metadata_only' if parents else ('derived_parent_identity_unresolved' if parent_hint else 'no_explicit_parent_in_bound_record_not_independence_proof')
        hits = protected_hits(source_image['sha256'], group, parents, roles)
        protected = [h for h in hits if h['role'] != 'developmentTrain']
        conflicting_train = protected if split == 'train' else []
        group_gate = gate_groups.get(group)
        marker_state = accepted['markerStatus'] if accepted else 'marker_review_not_bound'
        debts = ['whole_proposed_split_truth_and_role_approval', 'conditional_native_dataset_and_selection_contract',
                 'source_and_parent_independence_not_proven_by_metadata']
        if status == 'source_quality_excluded':
            debts.append('exclude_in_new_version_preserve_historical_denominator')
        elif status == 'source_marker_isolated':
            debts.append('source_marker_isolation_in_new_version')
        elif status.startswith('pending_'):
            debts.append('original_resolution_complete_source_and_every_nail_mask_review')
        elif split == 'val':
            debts.append('current_native_input_and_source_marker_qualification')
        if ordinal not in low:
            debts.append('current_parent_roles_and_local_feature_pair_visual_adjudication')
        if not accepted or not group_gate or group_gate.get('markerGate') != 'provisional_clear':
            debts.append('whole_source_group_marker_variant_and_shortcut_ablation')
        if parent_hint and not parents:
            debts.append('explicit_derived_parent_sha256_and_source_group')
        if conflicting_train:
            debts.append('protected_role_conflict_training_forbidden')
        records.append({'split': split, 'upstreamDevelopmentSplit': original['developmentSplit'],
                        'ordinal': ordinal, 'fileName': filename, 'sourceGroup': group,
                        'sourceImage': source_image, 'sourceLabel': source_label, 'historicalRoiIds': [r['id'] for r in rois],
                        'historicalMaskCount': len(rois), 'currentSourceDisposition': status,
                        'latestDecision': current_decision(decision_row), 'decisionReport': decision_ref,
                        'existingReviewedMaskCount': accepted['reviewedNailCount'] if accepted else None,
                        'existingReviewSupply': accepted, 'canonicalHistoricalTruth': truth,
                        'currentTruthCandidateEvidence': {k: v for k, v in decision_row.items() if isinstance(v, dict) and 'path' in v and 'sha256' in v and k not in ('sourceImage', 'sourceLabel', 'overview')},
                        'diagnosticOnlyDataGate': low.get(ordinal), 'markerStatus': marker_state,
                        'groupMarkerGate': group_gate.get('markerGate') if group_gate else None,
                        'roleMatches': hits, 'trainProtectedRoleConflicts': conflicting_train,
                        'parentIdentityStatus': parent_state, 'parents': parents,
                        'realMaterialLedgerIdentity': ledger.get(source_image['sha256']),
                        'qualificationDebts': debts, 'formalTrainingApproved': False, 'trainingUse': 'prohibited'})
    if len(records) != sum(c['sourceImages'] for c in scope['historicalSplitCounts'].values()):
        raise ValueError('full source coverage mismatch')
    source_groups = []
    for group in sorted({r['sourceGroup'] for r in records}):
        members = [r for r in records if r['sourceGroup'] == group]
        source_groups.append({'sourceGroup': group, 'split': members[0]['split'], 'files': [r['fileName'] for r in members],
                              'sourceDispositionCounts': dict(sorted(Counter(r['currentSourceDisposition'] for r in members).items())),
                              'qualificationDebts': sorted({debt for r in members for debt in r['qualificationDebts']}),
                              'trainingUse': 'prohibited'})
    summary = {'historicalSplitCounts': scope['historicalSplitCounts'], 'sourceImages': len(records),
               'historicalRois': len(rows), 'sourceGroups': len(source_groups), 'checkedDatasetFileBindings': checked_files,
               'upstreamTrainNowHistoricalRoiValSources': sum(r['upstreamDevelopmentSplit'] == 'train' and r['split'] == 'val' for r in records),
               'sourceDispositionCounts': {split: dict(sorted(Counter(r['currentSourceDisposition'] for r in records if r['split'] == split).items())) for split in ('train', 'val')},
               'canonicalHistoricalTruthMatches': sum(r['canonicalHistoricalTruth'] is not None for r in records),
               'diagnosticOnlyQualifiedSources': len(low), 'reviewedSourceSupplyImages': len(supply),
               'reviewedSourceSupplyMasks': sum(r['reviewedNailCount'] for r in supply.values()),
               'derivedParentIdentitiesUnresolved': sum(r['parentIdentityStatus'] == 'derived_parent_identity_unresolved' for r in records),
               'trainProtectedRoleConflictingSources': sum(bool(r['trainProtectedRoleConflicts']) for r in records),
               'registeredNegativeByteIdentities': len(negative_records), 'formalTrainingApprovedImages': 0}
    return {'schemaVersion': 1, 'ok': True, 'decision': 'full_split_debt_inventory_complete_training_prohibited',
            'execution': execution_binding, 'inputs': inputs, 'frozenScope': scope['inputs'],
            'registryMetadataBindings': registry_bindings, 'historicalRoleSummary': role_summary,
            'summary': summary, 'records': records, 'sourceGroups': source_groups,
            'fidelity': {'historicalRoiIdsAndOrderExact': True, 'fullSourceAndSplitExact': True,
                         'allDatasetFileBindingsExact': True, 'latestBoundDispositionsUsed': True,
                         'historicalFailuresAndDenominatorsPreserved': True},
            'dataReady': False, 'modelCalls': 0, 'optimizerSteps': 0, 'trainingAllowed': False,
            'full30PilotAllowed': False, 'formalTrainingApprovedImages': 0,
            'scope': 'Metadata and byte hashes only; existing visual evidence is crosswalked, no new visual approval or independence proof, no protected image pixels read.'}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding='utf-8'))
        binding = recorded['execution']
    else:
        if not args.execution or not args.output:
            parser.error('--execution and --output required')
        if args.output.exists():
            raise FileExistsError(args.output)
        binding = {'path': str(args.execution.resolve()), 'sha256': sha(args.execution)}
    execution = read(binding)
    trainer = module(execution['inputs']['readOnlyGuardSource'], 'full_split_readonly_trainer')
    trainer.install_read_only_ultralytics_image_check()
    roots = execution['datasetRoots']
    try:
        result = build_report(binding)
        if args.verify_report:
            if result != recorded:
                raise ValueError('reconstruction_mismatch: full report')
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'ok': True, 'verified': bool(args.verify_report), 'decision': result['decision'], 'summary': result['summary']}, ensure_ascii=False))
    finally:
        for root in roots:
            trainer.remove_ultralytics_label_caches(Path(root))


if __name__ == '__main__':
    main()
