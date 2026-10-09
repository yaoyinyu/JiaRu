import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('admission_contract', ROOT / 'model/training/audit-nail-training-admission-contract-v2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def source(name='a', group='g'):
    return {'identity': {'split': 'train', 'fileName': name, 'imageSha256': name * 64},
            'sourceGroup': group, 'maskCount': 2, 'annotation': {'path': name, 'sha256': name * 64}}


def row():
    result = {'markerControlRequired': True, 'variants': {}}
    for name in m.VARIANTS:
        result['variants'][name] = {'truths': [
            {'truthIndex': i, 'matchedCandidateId': str(i), 'iou': .8, 'boundaryIou': .8, 'boundaryF1': .9}
            for i in (1, 2)], 'acceptedCandidateIds': ['1', '2'], 'spuriousCount': 0,
            'markerWindowAcceptedPixels': 0, 'executionError': False, 'coarseFallbackUsed': False}
    return result


class AdmissionContractTests(unittest.TestCase):
    def test_equal_control_pass_and_denominator_preserved(self):
        value = row(); before = copy.deepcopy(value)
        self.assertTrue(m.marker_row_pass(value, source()))
        self.assertEqual(value, before)

    def test_net_match_count_cannot_hide_instance_migration(self):
        value = row(); truths = value['variants']['marker_removed']['truths']
        truths[0]['matchedCandidateId'], truths[1]['matchedCandidateId'] = '2', '1'
        self.assertFalse(m.marker_row_pass(value, source()))

    def test_more_sensitivity_than_blank_fails_even_if_quality_improves(self):
        value = row(); value['variants']['marker_removed']['truths'][0]['iou'] = .9
        self.assertFalse(m.marker_row_pass(value, source()))

    def test_loss_spurious_marker_pixels_error_and_fallback_fail(self):
        for field, changed in [('spuriousCount', 1), ('markerWindowAcceptedPixels', 1),
                               ('executionError', True), ('coarseFallbackUsed', True)]:
            value = row(); value['variants']['marker_removed'][field] = changed
            self.assertFalse(m.marker_row_pass(value, source()), field)
        value = row(); value['variants']['marker_moved']['truths'][0]['boundaryIou'] = .7
        self.assertFalse(m.marker_row_pass(value, source()))

    def test_missing_variant_truth_nonfinite_and_duplicate_candidate_rejected(self):
        cases = []
        value = row(); del value['variants']['blank_moved']; cases.append(value)
        value = row(); value['variants']['original']['truths'].pop(); cases.append(value)
        value = row(); value['variants']['original']['truths'][0]['iou'] = float('nan'); cases.append(value)
        value = row(); value['variants']['original']['truths'][1]['matchedCandidateId'] = '1'; cases.append(value)
        for value in cases:
            with self.assertRaises(ValueError): m.marker_row_pass(value, source())

    def test_unmarked_original_is_not_counted_as_paired(self):
        value = row(); value['markerControlRequired'] = False
        value['variants'] = {'original': value['variants']['original']}
        self.assertTrue(m.marker_row_pass(value, source()))
        value['markerControlRequired'] = None
        with self.assertRaises(ValueError): m.marker_row_pass(value, source())

    def test_no_evidence_never_approves_source_or_model(self):
        required = m.unique([source()])
        self.assertFalse(m.source_coverage(required, None, {})['complete'])
        self.assertFalse(m.marker_coverage(required, None, {})['complete'])

    def test_no_hit_not_source_proof_and_foreign_identity_rejected(self):
        required = m.unique([source()]); contract = {'inputs': {'referenceInventory': {'path': 'ref', 'sha256': 'a'}}}
        evidence = {'referenceInventory': contract['inputs']['referenceInventory'], 'records': [source()]}
        evidence['records'][0]['sourceImage'] = {'path': 'src', 'sha256': 'a'}
        required[next(iter(required))]['sourceImage'] = evidence['records'][0]['sourceImage']
        for kind in ('no_hit', 'all_recalled_pairs_distinct', 'metadata_zero_conflicts'):
            evidence['records'][0]['proofKind'] = kind
            with self.assertRaises(ValueError): m.source_coverage(required, evidence, contract)
        evidence['records'] = [source('z')]
        with self.assertRaises(ValueError): m.source_coverage(required, evidence, contract)

    def test_whole_group_marker_failure_prevents_partial_promotion(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'model/reviews/test-temp') as folder:
            folder = Path(folder)
            def save(name, data):
                path = folder / name; path.write_text(json.dumps(data), encoding='utf-8'); return m.bind(path)
            pixel = save('metadata-only-input-fixture.json', {'fixture': True})
            required = m.unique([source('a'), source('b')]); models = {'fixture': True}
            components = {}
            for component in ('stageA', 'stageB'):
                components[component] = []
                for required_row in required.values():
                    item = row(); item.update(copy.deepcopy(required_row))
                    for variant in item['variants'].values(): variant['inputImage'] = pixel
                    proof = {'identity': item['identity'], 'annotation': item['annotation'],
                             'markerControlRequired': True, 'allOriginalPixelsActuallyViewed': True,
                             'scalingNotice': False, 'inputControlsPassed': True, 'pages': [pixel],
                             'variants': {name: pixel for name in m.VARIANTS}}
                    item['nativeInputProof'] = save(required_row['identity']['fileName'] + '-proof.json', proof) if component == 'stageA' else components['stageA'][len(components[component])]['nativeInputProof']
                    components[component].append(item)
            evidence = {'referenceModels': models, 'acceptanceRules': m.RULES,
                        'phase': 'pretraining_reference', 'components': components}
            contract = {'referenceModels': models}
            self.assertTrue(m.marker_coverage(required, evidence, contract)['complete'])
            components['stageB'][1]['variants']['marker_moved']['markerWindowAcceptedPixels'] = 1
            outcome = m.marker_coverage(required, evidence, contract)
            self.assertEqual(outcome['passedSources'], 0)
            evidence['referenceModels'] = {'otherModel': True}
            with self.assertRaises(ValueError): m.marker_coverage(required, evidence, contract)

    def test_immutable_binding_and_exclusive_freeze(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'model/reviews/test-temp') as folder:
            path = Path(folder) / 'proof.json'; m.freeze(path, {'ok': False})
            ref = m.bind(path)
            with self.assertRaises(FileExistsError): m.freeze(path, {'ok': True})
            self.assertEqual(m.read(ref), {'ok': False})
            path.write_bytes(b'{}')
            with self.assertRaises(ValueError): m.checked(ref)

    def test_known_parent_omission_or_group_change_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'model/reviews/test-temp') as folder:
            folder = Path(folder)
            def save(name, data):
                path = folder / name; path.write_text(json.dumps(data), encoding='utf-8'); return m.bind(path)
            artifact = save('artifact.json', {'fixture': True})
            parent = {'sourceImage': artifact, 'sourceGroup': 'protected-parent', 'imageSha256': artifact['sha256']}
            src = source(); src.update(sourceImage=artifact, parents=[parent])
            required = m.unique([src]); ref_inventory = artifact
            origin = {'identity': src['identity'], 'sourceImage': artifact, 'sourceGroup': src['sourceGroup'],
                      'originArtifact': artifact, 'parents': [], 'knownParentsPreserved': [], 'completeParentChain': True}
            proof = {**src, 'proofKind': 'origin_chain_and_native_review', 'originChain': save('origin.json', origin),
                     'nativeOriginReview': save('review.json', {})}
            evidence = {'referenceInventory': ref_inventory, 'records': [proof]}
            contract = {'inputs': {'referenceInventory': ref_inventory}}
            with self.assertRaisesRegex(ValueError, 'known parent'): m.source_coverage(required, evidence, contract)
            for changed in ([{**parent, 'sourceGroup': 'changed'}], [parent]):
                origin['knownParentsPreserved'] = changed
                proof['originChain'] = save('origin.json', origin)
                with self.assertRaisesRegex(ValueError, 'known parent'): m.source_coverage(required, evidence, contract)

    def test_contract_rejects_weakened_rules_or_future_model_cycle(self):
        base = {'schemaVersion': 1, 'acceptanceRules': copy.deepcopy(m.RULES), 'phaseEdges': copy.deepcopy(m.PHASES)}
        weakened = copy.deepcopy(base); weakened['acceptanceRules']['markerWindowAcceptedPixels'] = 1
        with self.assertRaises(ValueError): m.validate_contract(weakened)
        circular = copy.deepcopy(base); circular['phaseEdges'].append(['full30', 'training_admission'])
        with self.assertRaises(ValueError): m.validate_contract(circular)


if __name__ == '__main__':
    (ROOT / 'model/reviews/test-temp').mkdir(parents=True, exist_ok=True)
    unittest.main()
