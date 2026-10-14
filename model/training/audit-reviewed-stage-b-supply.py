"""整组开发供给只读审计；继承绑定证据，不产生图片/模型输入或晋升资格。"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def fail(message):
    raise ValueError('reconstruction_mismatch: ' + message)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def load(ref, name):
    if bind(ref['path']) != ref:
        fail('helper binding')
    sys.path.insert(0, str(Path(ref['path']).parent))
    spec = importlib.util.spec_from_file_location(name, ref['path'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def key(identity):
    values = tuple(identity[k] for k in ('split', 'fileName', 'imageSha256'))
    if values[0] not in ('train', 'val') or not values[1] or len(values[2]) != 64:
        fail('stable identity')
    return values


def unique(rows, identity=lambda row: key(row['identity'])):
    result = {}
    for row in rows:
        k = identity(row)
        if k in result:
            fail('duplicate stable identity')
        result[k] = row
    return result


def current_decision(row):
    return row.get('currentDecision', row.get('decision'))


class Evidence:
    """同路径不能绑定多个SHA；读取仅限字节与JSON，不解码图片。"""
    def __init__(self):
        self.refs = {}

    def checked(self, ref):
        path = Path(ref['path']).resolve()
        actual = {'path': str(path), 'sha256': ref['sha256']}
        if set(ref) != {'path', 'sha256'} or actual != ref:
            fail('noncanonical binding')
        previous = self.refs.get(str(path))
        if previous is not None and previous != ref:
            fail('conflicting path bindings')
        if previous is None and bind(path) != ref:
            fail('file bytes ' + str(path))
        self.refs[str(path)] = ref
        return path

    def read(self, ref):
        return json.loads(self.checked(ref).read_bytes())

    def nested_bindings(self, value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                self.checked(value)
            else:
                for item in value.values():
                    self.nested_bindings(item)
        elif isinstance(value, list):
            for item in value:
                self.nested_bindings(item)

    def finish(self):
        for ref in self.refs.values():
            if bind(ref['path']) != ref:
                fail('binding changed during audit')
        return sorted(self.refs.values(), key=lambda ref: ref['path'])


def pending_by_group(queue, disposition):
    pairs = unique(queue['pairs'], lambda row: tuple(row['pairIdentity']))
    pending = list(map(tuple, disposition['pendingPairIdentities']))
    if len(set(pending)) != len(pending):
        fail('duplicate pending pairs')
    uncertain = unique(disposition.get('currentUncertainPairDecisions', []),
                       lambda row: tuple(row['pairIdentity']))
    wanted = set(pending) | {k for k, row in uncertain.items() if current_decision(row) == 'uncertain'}
    if not wanted <= pairs.keys():
        fail('unresolved pair absent from queue')
    groups = defaultdict(list)
    for ordinal, (pair, row) in enumerate(pairs.items(), 1):
        if len(pair) != 2 or pair[0] >= pair[1]:
            fail('unordered pair identity')
        for observation in row['observations']:
            t, r = observation['target'], observation['reference']
            if tuple(sorted((t['imageSha256'], r['image']['sha256']))) != pair:
                fail('pair observation identity')
        if pair not in wanted:
            continue
        affected = sorted({g for o in row['observations'] for g in o['target']['sourceGroups']})
        item = {'pairIdentity': list(pair), 'queueOrdinal': ordinal,
                'state': 'uncertain' if pair in uncertain and current_decision(uncertain[pair]) == 'uncertain' else 'pending',
                'observationsPreserved': row['observations'],
                'uncertainDecisionPreserved': uncertain.get(pair), 'sourceIndependenceApproved': False}
        for group in affected:
            groups[group].append(item)
    return dict(groups)


def truth_slot(row, vals):
    if row['identity']['split'] == 'val':
        return vals.get(key(row['identity'])), 'currentInternalValTruthRecords'
    return row.get('currentTruth'), 'currentTruth'


def evidence_gaps(row, quality_candidate, pending, hits, truth):
    gaps = []
    if row['identity']['split'] != 'train':
        gaps.append('current_internal_val_prohibited_for_train')
    if row['upstreamDevelopmentSplit'] != 'train':
        gaps.append('upstream_role_not_train')
    if row['currentSourceDisposition'] in ('source_quality_excluded', 'exclude_source_quality'):
        gaps.append('current_source_quality_excluded')
    if row['currentSourceDisposition'] in ('source_marker_isolated', 'source_marker_quarantine'):
        gaps.append('current_source_marker_isolated')
    if not quality_candidate:
        gaps.append('not_current_quality_candidate')
    if not truth:
        gaps.append('complete_reviewed_truth_not_in_current_slot')
    if row.get('protectedTrainConflicts') or any(h['role'] != 'developmentTrain' for h in hits):
        gaps.append('protected_current_parent_or_group_role')
    if pending:
        gaps.append('whole_group_source_relationship_unresolved')
    return gaps


def audit(execution_ref):
    e = Evidence()
    execution = e.read(execution_ref)
    if execution['purpose'] != 'read_only_stage_b_whole_group_supply_execution' or execution['sources']['runner'] != bind(__file__):
        fail('execution identity')
    e.nested_bindings(execution['sources'])
    scope = e.read(execution['scope'])
    if scope['purpose'] != 'metadata_only_normal_stage_b_whole_group_train_supply_audit':
        fail('scope purpose')
    for name in ('newModelInputsAllowed', 'optimizerStepsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed'):
        if scope[name] != 0:
            fail('nonzero scope budget')
    for name in ('datasetMaterializationAllowed', 'roleMutationAllowed', 'trainingBudgetAllocated', 'trainingAllowed', 'formalTrainingQualified', 'formalReleaseAllowed'):
        if scope[name] is not False:
            fail('scope permission')
    d = load(scope['sources']['dataHelper'], 'stage_b_supply_data')
    e.nested_bindings(scope['sources'])
    docs = {name: e.read(ref) for name, ref in scope['inputs'].items()}
    contract, roles, quality = (docs[name] for name in ('trainingContract', 'roles', 'quality'))
    for name in ('quality', 'roles', 'pairDisposition', 'lineage', 'referenceInventory', 'readiness'):
        if contract['inputs'][name] != scope['inputs'][name]:
            fail('scope and training contract differ')
    if docs['route']['inputs']['attributionV2'] != scope['inputs']['attributionV2'] or docs['route']['inputs']['trainingContract'] != scope['inputs']['trainingContract']:
        fail('route inputs')
    if docs['route']['trainingAllowed'] or docs['attributionV2']['formalReleaseAllowed']:
        fail('prior route permissions')
    if docs['attributionV2']['summaries']['actual_refined']['jointBoundaryCount'] != 0:
        fail('frozen attribution mismatch')
    quality_runner_ref = quality['inputs']['runner']
    e.checked(quality_runner_ref)
    quality_runner = load(quality_runner_ref, 'stage_b_supply_quality')
    if quality_runner.analyze(quality['plan']) != quality:
        fail('complete source quality report reconstruction')
    index = unique(roles['records'])
    vals = unique(roles['currentInternalValTruthRecords'])
    if not vals.keys() <= index.keys() or any(k[0] != 'val' for k in vals):
        fail('val truth roles')
    inventory = quality['currentQualityEligibleInventory']
    candidates = unique(inventory)
    if scope['allQualityEligibleInventory'] != inventory or scope['allQualityEligibleIdentities'] != [r['identity'] for r in inventory]:
        fail('quality inventory contract')
    readiness = unique(docs['readiness']['records'])
    selected = d.validate(contract)
    selected_keys = {key(r['identity']) for r in selected}
    if [r['identity'] for r in selected] != scope['currentSelectedIdentities']:
        fail('selected identities')
    disposition = docs['pairDisposition']
    queue = e.read(disposition['inputs']['queue'])
    e.nested_bindings(queue)
    e.nested_bindings(disposition.get('currentUncertainPairDecisions', []))
    pending = pending_by_group(queue, disposition)
    if set(pending) != d.unresolved_groups(disposition):
        fail('unresolved groups differ from frozen helper')
    pending_train = [r for r in inventory if r['identity']['split'] == 'train' and r['sourceGroup'] in pending]
    if pending_train != scope['pendingTrainInventory']:
        fail('pending train cohort')
    reference = docs['referenceInventory']
    role_helper_ref = reference['inputs']['rolesHelper']
    e.checked(role_helper_ref)
    role_helper = load(role_helper_ref, 'stage_b_supply_roles')
    role_sets, _ = role_helper.role_sets(e.read(reference['inputs']['roleSourceSupply']))
    old = e.read(reference['inputs']['frozenReadinessPlan'])
    replacement = e.read(old['inputs']['releaseTestRoleReplacement'])
    rr = replacement['items'] + replacement['withdrawnTrainItems']
    role_sets['releaseTestReplacement'] = {'hashes': {r['imageSha256'] for r in rr}, 'sourceGroups': {r['sourceGroup'] for r in rr} | {r['sourceGroup'] for r in replacement['withdrawnTrainGroups']}}
    negatives = []
    for entry in e.read(old['inputs']['protectedHardNegativeRegistry'])['entries']:
        value = e.read({'path': entry['path'], 'sha256': entry['sha256']})
        if entry['role'] not in ('training', 'test', 'holdout') or not value['ok'] or value['status'] != 'PASS':
            fail('protected registry')
        negatives.extend(value['items'])
    role_sets['protectedHardNegativeRegistry'] = {'hashes': {r['imageSha256'] for r in negatives}, 'sourceGroups': {r['sourceGroup'] for r in negatives}}
    val_roles = [r for r in roles['records'] if r['identity']['split'] == 'val']
    role_sets['currentInternalVal'] = {'hashes': {r['identity']['imageSha256'] for r in val_roles}, 'sourceGroups': {r['sourceGroup'] for r in val_roles}}
    readiness_helper_ref = docs['lineage']['inputs']['readinessHelper']
    e.checked(readiness_helper_ref)
    rh = load(readiness_helper_ref, 'stage_b_supply_readiness')
    lineage = unique(docs['lineage']['records'])
    if not lineage.keys() <= index.keys():
        fail('lineage missing current identity')
    reviews = unique([e.read(ref) for ref in quality['qualityReviewBindings']])
    review_refs = {key(e.read(ref)['identity']): ref for ref in quality['qualityReviewBindings']}
    records = []
    for row in roles['records']:
        ident = row['identity']; k = key(ident); group = row['sourceGroup']
        if row['sourceImage']['sha256'] != ident['imageSha256'] or row['trainingUse'] != 'prohibited' or row['formalTrainingApproved']:
            fail('current role and bytes')
        e.nested_bindings(row)
        ancestors = list(row['parents'])
        if k in lineage:
            lr = lineage[k]
            if lr['sourceImage'] != row['sourceImage'] or lr['sourceGroup'] != group or lr['originalParentsPreserved'] != row['parents'] or not lr['lineageMetadataAndPixelsVerified']:
                fail('lineage metadata')
            e.nested_bindings(lr)
            ancestors.append(lr['parent'])
        hits = rh.protected_hits(ident['imageSha256'], group, ancestors, role_sets)
        truth, slot = truth_slot(row, vals)
        if truth:
            e.nested_bindings(truth)
        geometry = None
        if k in candidates:
            inv = candidates[k]
            if group != inv['sourceGroup'] or row['sourceImage'] != inv['sourceImage'] or not truth or truth['annotation'] != inv['annotation']:
                fail('candidate current truth identity')
            if k not in reviews or current_decision(reviews[k]) != 'source_quality_candidate':
                fail('candidate missing source quality pass')
            if reviews[k]['annotation'] != inv['annotation'] or reviews[k]['maskCountPreserved'] != inv['maskCount']:
                fail('quality and truth bindings')
            size = truth['imageSize'] if ident['split'] == 'train' else readiness[k]['size']
            polygons = d.polygons(inv['annotation'], *size, ident)
            if len(polygons) != inv['maskCount']:
                fail('candidate truth denominator')
            if ident['split'] == 'train':
                if not truth['geometry']['polygonValid'] or not truth['geometry']['pairwiseZeroOverlap'] or truth['geometry']['maskCount'] != len(polygons):
                    fail('candidate truth geometry')
            else:
                closure = e.read(truth['maskClosure'])
                if closure['identity'] != ident or closure['annotation'] != inv['annotation'] or not closure['ok'] or not closure['fullSourceMaskApproved']:
                    fail('independent val truth slot closure')
            geometry = {'size': size, 'maskCount': len(polygons), 'valid': True, 'pairwiseZeroOverlap': True}
        gaps = evidence_gaps(row, k in candidates, group in pending, hits, truth)
        if k in reviews and current_decision(reviews[k]) == 'source_quality_excluded':
            gaps.append('latest_native_source_quality_excluded')
        if k in selected_keys and k[0] == 'train' and gaps:
            fail('selected training source has evidence gap')
        if k in candidates and k[0] == 'train' and not gaps and k not in selected_keys:
            fail('unselected train source without gap')
        records.append({'identity': ident, 'sourceGroup': group, 'roleRecordPreserved': row,
                        'parentLineagePreserved': lineage.get(k), 'currentAndParentProtectedMatches': hits,
                        'truthSlot': slot, 'truthRecordPreserved': truth, 'geometryRebuilt': geometry,
                        'latestQualityReview': review_refs.get(k), 'latestSourceQualityDecision': current_decision(reviews[k]) if k in reviews else None,
                        'qualityInventoryCandidate': k in candidates, 'currentContractSelected': k in selected_keys,
                        'developmentTrainEligibleUnderCurrentContract': k[0] == 'train' and k in selected_keys and not gaps,
                        'evidenceGaps': gaps, 'formalTrainingQualified': False})
    acquisition = e.read(queue['inputs']['acquisitionInventory'])
    acquisition_groups = unique(acquisition['groups'], lambda g: g['sourceGroup'])
    groups = []
    by_group = defaultdict(list)
    for row in records:
        by_group[row['sourceGroup']].append(row)
    asset_count = 0
    for group in sorted(by_group):
        members = by_group[group]; ag = acquisition_groups.get(group)
        assets = []
        if ag:
            for member in ag['frozenCurrentMembership']:
                original = index[key(member['identity'])]
                if original['sourceGroup'] != group or original['sourceImage'] != member['sourceImage'] or original['currentSourceDisposition'] != member['currentSourceDisposition']:
                    fail('whole acquisition group role membership')
            if {key(r['identity']) for r in ag['frozenCurrentMembership']} != {key(r['identity']) for r in members}:
                fail('acquisition group omitted role member')
            unique(ag['acquisitionEntries'], lambda a: (a['entryPreserved']['fileName'], a['image']['sha256']))
            for asset in ag['acquisitionEntries']:
                e.checked(asset['image'])
                if asset['entryPreserved']['sha256'] != asset['image']['sha256'] or asset['entryPreserved']['sourceGroup'] != group:
                    fail('acquisition asset identity')
                # 按精确SHA继承角色；未入split的资产保持原处置，不推断质量排除。
                matches = [r['identity'] for r in records if r['identity']['imageSha256'] == asset['image']['sha256']]
                assets.append({'assetPreserved': asset, 'currentRoleIdentities': matches,
                               'originalDispositionPreserved': current_decision(asset['entryPreserved']),
                               'trainingAllowed': False})
            asset_count += len(assets)
        pending_sources = [r for r in members if r['qualityInventoryCandidate'] and r['identity']['split'] == 'train' and 'whole_group_source_relationship_unresolved' in r['evidenceGaps']]
        groups.append({'sourceGroup': group, 'memberIdentities': [r['identity'] for r in members],
                       'dispositionCountsPreserved': dict(sorted(Counter(r['roleRecordPreserved']['currentSourceDisposition'] for r in members).items())),
                       'acquisitionAlbumMapped': ag['acquisitionAlbumMapped'] if ag else None,
                       'acquisitionScopePresent': bool(ag), 'acquisitionAssets': assets,
                       'noMappingNeverMeansNoOtherMembers': True,
                       'unresolvedPairs': pending.get(group, []), 'pendingTrainIdentities': [r['identity'] for r in pending_sources],
                       'pendingTrainNails': sum(r['geometryRebuilt']['maskCount'] for r in pending_sources),
                       'formalSourceIndependenceApproved': False})
    if not acquisition_groups.keys() <= by_group.keys() or asset_count != acquisition['counts']['mappedAcquisitionAssets']:
        fail('all acquisition assets/groups accounting')
    train = [r for r in selected if r['identity']['split'] == 'train']
    val = [r for r in selected if r['identity']['split'] == 'val']
    observed = {'roleRecords': len(records), 'qualityEligibleSources': len(inventory), 'currentSelectedSources': len(selected),
                'currentTrainSources': len(train), 'currentTrainSourceGroups': len({r['sourceGroup'] for r in train}),
                'currentTrainTruthNails': sum(r['maskCount'] for r in train), 'currentInternalValSources': len(val),
                'currentInternalValTruthNails': sum(r['maskCount'] for r in val), 'pendingTrainQualityEligibleSources': len(pending_train),
                'allRoleRecordsAndWholeGroupsMustRemain': True}
    if observed != scope['expectedCounts']:
        fail('complete denominator contract')
    supply = docs['attributionV2']['normalStageBRoute']['auditedTrainSupply']
    if (supply['auditedTrainSources'], supply['auditedTrainSourceGroups'], supply['auditedTrainTruthNails'], supply['auditedTrainRejectCandidates']) != (len(train), len({r['sourceGroup'] for r in train}), sum(r['maskCount'] for r in train), 2):
        fail('prior audited supply')
    priorities = sorted([{'sourceGroup': g['sourceGroup'], 'pendingTrainSources': len(g['pendingTrainIdentities']),
                          'pendingTrainNails': g['pendingTrainNails'], 'unresolvedPairs': len(g['unresolvedPairs']),
                          'currentWholeGroupRoleMembers': len(g['memberIdentities']), 'acquisitionAssets': len(g['acquisitionAssets']),
                          'selectionBasis': 'metadata_only_fewest_unresolved_pairs_then_source_group_not_model_quality'}
                         for g in groups if g['pendingTrainIdentities']], key=lambda g: (g['unresolvedPairs'], g['sourceGroup']))
    return {'schemaVersion': 1, 'ok': True, 'decision': 'whole_group_supply_reconstructed_no_new_training_qualification',
            'execution': execution_ref, 'observedCounts': observed, 'roleRecords': records, 'wholeGroups': groups,
            'currentTrainSupply': {'sources': len(train), 'sourceGroups': len({r['sourceGroup'] for r in train}),
                                   'nails': sum(r['maskCount'] for r in train), 'rejectCandidates': supply['auditedTrainRejectCandidates'],
                                   'identities': [r['identity'] for r in train]},
            'pendingTrainGroupPriorities': priorities, 'currentDispositionCounts': dict(sorted(Counter(r['currentSourceDisposition'] for r in roles['records']).items())),
            'mappedAcquisitionAssets': asset_count, 'verifiedBindings': e.finish(),
            'newEligibleTrainingSources': 0, 'allExistingTruthsRolesExclusionsAndIsolationPreserved': True,
            'newModelCalls': 0, 'optimizerSteps': 0, 'protectedModelInputs': 0, 'newChatImageInputs': 0,
            'newVisualPairDecisions': 0, 'pixelDecodes': 0, 'datasetMaterialization': False, 'roleMutation': False,
            'trainingBudgetAllocated': False, 'trainingAllowed': False, 'formalTrainingQualified': False,
            'formalSourceIndependenceApproved': False, 'formalReleaseAllowed': False, 'productHold': True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execution', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--verify-report', type=Path)
    args = p.parse_args()
    if args.verify_report:
        prior = json.loads(args.verify_report.read_bytes())
        result = audit(prior['execution'])
        if result != prior:
            fail('whole frozen report differs')
    else:
        if not args.execution or not args.output:
            p.error('--execution and --output required')
        result = audit(bind(args.execution))
        with args.output.open('xb') as stream:
            stream.write(raw(result)); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'ok': result['ok'], 'decision': result['decision'], 'counts': result['observedCounts'],
                      'pendingTrainGroups': len(result['pendingTrainGroupPriorities']),
                      'nextGroup': result['pendingTrainGroupPriorities'][:1],
                      'verifiedBindings': len(result['verifiedBindings']), 'trainingAllowed': False, 'productHold': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
