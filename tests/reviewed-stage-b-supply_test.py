"""供给审计必须保留身份、角色及隔离，元数据不能替代实审或晋升。"""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('supply_audit', ROOT / 'model/training/audit-reviewed-stage-b-supply.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
spec2 = importlib.util.spec_from_file_location('supply_audit_v2', ROOT / 'model/training/audit-reviewed-stage-b-supply-v2.py')
b = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(b)


def identity(split='train', digest='a' * 64):
    return {'split': split, 'fileName': 'source.png', 'imageSha256': digest}


def role(split='train', disposition='recorded_mask_visual_pass_pending_full_split'):
    return {'identity': identity(split), 'upstreamDevelopmentSplit': 'train',
            'currentSourceDisposition': disposition, 'protectedTrainConflicts': []}


def pair(group='group'):
    return {'pairIdentity': ['a' * 64, 'b' * 64], 'observations': [
        {'target': {'imageSha256': 'a' * 64, 'sourceGroups': [group]},
         'reference': {'image': {'sha256': 'b' * 64}, 'roles': ['consumedPositiveTest']}}]}


class SupplyTests(unittest.TestCase):
    def test_cross_split_local_ordinals_never_merge(self):
        rows = [{'identity': identity(s), 'ordinal': 1} for s in ('train', 'val')]
        self.assertEqual(len(a.unique(rows)), 2)
        with self.assertRaisesRegex(ValueError, 'duplicate stable identity'):
            a.unique(rows + [copy.deepcopy(rows[0])])

    def test_val_uses_separate_truth_slot(self):
        r = role('val'); r['currentTruth'] = None
        val_truth = {'annotation': 'separate'}
        truth, slot = a.truth_slot(r, {a.key(r['identity']): val_truth})
        self.assertEqual(truth, val_truth)
        self.assertEqual(slot, 'currentInternalValTruthRecords')
        r['identity'] = identity('train'); r['currentTruth'] = {'annotation': 'train'}
        self.assertEqual(a.truth_slot(r, {})[0], r['currentTruth'])

    def test_isolation_and_source_exclusion_preserved(self):
        for state, debt in [('source_marker_isolated', 'current_source_marker_isolated'),
                            ('source_quality_excluded', 'current_source_quality_excluded'),
                            ('exclude_source_quality', 'current_source_quality_excluded')]:
            r = role(disposition=state); before = copy.deepcopy(r)
            self.assertIn(debt, a.evidence_gaps(r, True, False, [], {'annotation': 'x'}))
            self.assertEqual(r, before)

    def test_parent_protected_hit_blocks_train(self):
        hit = {'identity': 'parent', 'role': 'consumedPositiveTest', 'byHash': True}
        self.assertIn('protected_current_parent_or_group_role', a.evidence_gaps(role(), True, False, [hit], {'annotation': 'x'}))

    def test_val_cannot_return_to_train(self):
        gaps = a.evidence_gaps(role('val'), True, False, [], {'annotation': 'x'})
        self.assertIn('current_internal_val_prohibited_for_train', gaps)

    def test_current_decision_overrides_old_pass(self):
        self.assertEqual(a.current_decision({'decision': 'pass', 'currentDecision': 'source_quality_excluded'}), 'source_quality_excluded')

    def test_pending_and_uncertain_keep_whole_group(self):
        p = pair(); disposition = {'pendingPairIdentities': [], 'currentUncertainPairDecisions': [
            {'pairIdentity': p['pairIdentity'], 'decision': 'uncertain'}]}
        result = a.pending_by_group({'pairs': [p]}, disposition)
        self.assertEqual(result['group'][0]['state'], 'uncertain')
        self.assertFalse(result['group'][0]['sourceIndependenceApproved'])
        self.assertIn('whole_group_source_relationship_unresolved', a.evidence_gaps(role(), True, True, [], {'annotation': 'x'}))

    def test_unknown_pending_pair_and_corrupt_observation_rejected(self):
        p = pair(); original = copy.deepcopy(p)
        with self.assertRaisesRegex(ValueError, 'absent from queue'):
            a.pending_by_group({'pairs': []}, {'pendingPairIdentities': [p['pairIdentity']]})
        p['observations'][0]['reference']['image']['sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'pair observation identity'):
            a.pending_by_group({'pairs': [p]}, {'pendingPairIdentities': []})
        self.assertEqual(original['observations'][0]['reference']['image']['sha256'], 'b' * 64)

    def test_byte_drift_detected_after_cached_read(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'evidence.json'; p.write_bytes(b'{}\n')
            e = a.Evidence(); ref = a.bind(p); self.assertEqual(e.read(ref), {})
            p.write_bytes(b'{"changed":true}\n')
            with self.assertRaisesRegex(ValueError, 'changed during audit'):
                e.finish()

    def test_missing_unknown_and_duplicate_binding_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'evidence.json'; p.write_bytes(b'{}')
            e = a.Evidence(); ref = a.bind(p); e.checked(ref)
            wrong = {**ref, 'sha256': 'a' * 64}
            with self.assertRaisesRegex(ValueError, 'conflicting path'):
                e.checked(wrong)
            with self.assertRaisesRegex(ValueError, 'noncanonical binding'):
                e.checked({**ref, 'trainingAllowed': False})
            p.unlink()
            with self.assertRaises(FileNotFoundError):
                a.bind(p)

    def test_relative_review_exact_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); p = root / 'review.json'; p.write_bytes(b'{}\n')
            ref = {'path': 'review.json', 'sha256': a.bind(p)['sha256']}
            e = b.RelativeEvidence(root); before = copy.deepcopy(ref)
            self.assertEqual(e.read(ref), {})
            self.assertEqual(ref, before)
            self.assertEqual(e.finish(), [a.bind(p)])

    def test_relative_escape_and_byte_drift_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); e = b.RelativeEvidence(root)
            with self.assertRaisesRegex(ValueError, 'escapes project root'):
                e.checked({'path': '../outside.json', 'sha256': 'a' * 64})
            p = root / 'review.json'; p.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'file bytes'):
                e.checked({'path': 'review.json', 'sha256': 'a' * 64})


if __name__ == '__main__':
    unittest.main()
