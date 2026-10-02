import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'model/training/audit-full-split-data-readiness.py'
spec = importlib.util.spec_from_file_location('readiness', path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ReadinessContracts(unittest.TestCase):
    def test_full_denominator_and_order_cannot_shrink(self):
        rows = [dict(id='a', split='train', sourceFileName='one', sourceGroup='g1'),
                dict(id='b', split='val', sourceFileName='two', sourceGroup='g2')]
        scope = {'expectedHistoricalRoiIds': ['a', 'b'], 'historicalSplitCounts': {
            'train': {'instances': 1, 'sourceImages': 1, 'sourceGroups': 1},
            'val': {'instances': 1, 'sourceImages': 1, 'sourceGroups': 1}}}
        self.assertEqual(len(audit.validate_roi_contract(rows, scope)), 2)
        for changed in [rows[:1], rows[::-1], [rows[0], dict(rows[1], sourceGroup='g1')]]:
            with self.assertRaises(ValueError):
                audit.validate_roi_contract(changed, scope)

    def test_latest_repair_and_conflict_are_not_old_pending_or_auto_approval(self):
        row = {'decision': 'pending_every_nail_review', 'currentDecision': 'mask_visual_pass_role_pending'}
        self.assertEqual(audit.current_decision(row), 'mask_visual_pass_role_pending')
        self.assertEqual(audit.classification(audit.current_decision(row), True), 'recorded_mask_visual_pass_pending_full_split')
        with self.assertRaises(ValueError):
            audit.classification('source_quality_excluded', True)
        with self.assertRaises(ValueError):
            audit.index_unique([{'fileName': 'same'}, {'fileName': 'same'}], 'fileName')

    def test_parent_protection_and_missing_identity_fail_closed(self):
        roles = {'consumedPositiveTest': {'hashes': {'a' * 64}, 'sourceGroups': {'protected'}}}
        parent = {'imageSha256': 'a' * 64, 'sourceGroup': 'other'}
        hits = audit.protected_hits('b' * 64, 'training', [parent], roles)
        self.assertEqual(hits, [{'identity': 'parent', 'role': 'consumedPositiveTest', 'byHash': True, 'byGroup': False}])
        with self.assertRaises(ValueError):
            audit.protected_hits('b' * 64, 'training', [{'sourceGroup': 'protected'}], roles)

    def test_versioned_internal_val_lineage_does_not_allow_return_to_train(self):
        audit.validate_split_lineage('train', 'val', {'f': ['train', 'val']}, 'f')
        with self.assertRaises(ValueError):
            audit.validate_split_lineage('val', 'train', {'f': ['val', 'train']}, 'f')
        with self.assertRaises(ValueError):
            audit.validate_split_lineage('train', 'train', {'f': ['train', 'val']}, 'f')


if __name__ == '__main__':
    unittest.main()
