import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('native_audit', Path(__file__).resolve().parents[1] / 'model/training/audit-native-source-mask-review.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        image = {'path': 'image', 'sha256': 'a' * 64}
        label = {'path': 'label', 'sha256': 'b' * 64}
        raw = {'path': 'raw', 'sha256': 'c' * 64}
        pair = {'path': 'pair', 'sha256': 'd' * 64}
        self.record = {'sourceFileName': 'nail.jpg', 'sourceGroup': 'group', 'sourceImage': image,
                       'sourceLabel': label, 'historicalNails': 1, 'rawTiles': [{'image': raw}], 'nailPanels': [{'image': pair}]}
        self.decision = {'ordinal': 1, 'fileName': 'nail.jpg', 'sourceGroup': 'group', 'sourceImage': image,
                         'sourceLabel': label, 'historicalMaskCount': 1, 'reviewedHistoricalNailIndices': [1],
                         'viewedArtifacts': [raw, pair], 'retainedApprovedOldMaskIndices': [], 'trainingUse': 'prohibited',
                         'reason': 'visible old edge contamination', 'markerDecision': 'badge',
                         'sourceQualityDecision': 'complete_visible_nails_traceable', 'maskDecision': 'label_rework',
                         'fullyTraceableNails': 1, 'defectiveOldNails': [1]}

    def test_missing_raw_or_nail_view_and_changed_denominator_rejected(self):
        audit.validate_decision(self.record, self.decision)
        for key, value in [('viewedArtifacts', self.decision['viewedArtifacts'][1:]), ('reviewedHistoricalNailIndices', [])]:
            d = copy.deepcopy(self.decision); d[key] = value
            with self.assertRaises(ValueError): audit.validate_decision(self.record, d)

    def test_replay_cannot_approve_old_masks_or_train(self):
        for key, value in [('retainedApprovedOldMaskIndices', [1]), ('trainingUse', 'allowed'), ('fullyTraceableNails', 0)]:
            d = copy.deepcopy(self.decision); d[key] = value
            with self.assertRaises(ValueError): audit.validate_decision(self.record, d)

    def test_existing_exclusion_and_val_roles_preserved(self):
        row = {**self.decision, 'split': 'train', 'currentSourceDisposition': 'pending_original_resolution_complete_source_and_mask_review',
               'historicalRoiIds': ['fixed'], 'parents': [{'imageSha256': 'e' * 64, 'sourceGroup': 'parent'}]}
        excluded = {**row, 'ordinal': 2, 'fileName': 'excluded.jpg', 'currentSourceDisposition': 'source_quality_excluded'}
        val = {**row, 'ordinal': None, 'split': 'val', 'fileName': 'val.jpg', 'upstreamDevelopmentSplit': 'train'}
        baseline = {'records': [row, excluded, val]}
        result = audit.apply_dispositions(baseline, [self.decision])
        self.assertEqual(result[1:], baseline['records'][1:])
        self.assertEqual(result[0]['parents'], row['parents'])
        self.assertEqual(result[0]['historicalRoiIds'], ['fixed'])
        self.assertEqual(result[0]['currentSourceDisposition'], 'label_rework')
        with self.assertRaises(ValueError): audit.apply_dispositions({'records': result}, [self.decision])

    def test_native_tiles_cover_odd_dimensions_without_resize(self):
        boxes = audit.tiles(1079, 1423, 900, 900)
        self.assertEqual(boxes, [[0, 0, 900, 900], [900, 0, 1079, 900], [0, 900, 900, 1423], [900, 900, 1079, 1423]])
        self.assertEqual(sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes), 1079 * 1423)


if __name__ == '__main__': unittest.main()
