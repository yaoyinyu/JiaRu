"""旧误标ROI与新版甲面分母分离的反例回归。"""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manual_v2', ROOT / 'model/training/audit-native-manual-mask-review-v2.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DenominatorTests(unittest.TestCase):
    def setUp(self):
        self.source = {'ordinal': 1, 'fileName': 'nail.jpg', 'sourceGroup': 'group',
                       'sourceImage': {'path': 'image', 'sha256': 'a' * 64},
                       'sourceLabel': {'path': 'label', 'sha256': 'b' * 64},
                       'historicalMaskCount': 2, 'fullyTraceableNails': 1, 'spuriousOldNails': [2]}
        review = {**copy.deepcopy(self.source), 'sourceQualityDecision': 'complete_visible_nails_traceable',
                  'additionalUntraceableNails': 0}
        self.row = {**copy.deepcopy(self.source), 'split': 'train', 'currentSourceDisposition': 'label_rework',
                    'historicalRoiIds': ['nail1', 'skin2'], 'parents': [{'sha256': 'c' * 64}],
                    'roleMatches': [{'role': 'developmentTrain'}], 'groupMarkerGate': None,
                    'latestOriginalPixelReview': review, 'qualificationDebts': ['whole_group_marker_gate']}
        self.decision = {**copy.deepcopy(self.source), 'completeVisibleNails': 1, 'decision': audit.PASS,
                         'annotation': {'path': 'new', 'sha256': 'd' * 64}, 'failedNailIndices': []}
        self.scope = {'sources': [self.source]}

    def test_declared_skin_roi_removed_only_from_new_truth_not_history(self):
        audit.validate_denominators(self.row, self.source, self.decision)
        result = audit.apply_reviews({'currentFullSplitRecords': [self.row]}, [self.decision], self.scope, {})[0]
        self.assertEqual(result['historicalMaskCount'], 2)
        self.assertEqual(result['historicalRoiIds'], ['nail1', 'skin2'])
        self.assertEqual(result['existingReviewedMaskCount'], 1)
        self.assertEqual(result['latestOriginalPixelReview'], self.row['latestOriginalPixelReview'])
        self.assertEqual(result['parents'], self.row['parents'])
        self.assertEqual(result['roleMatches'], self.row['roleMatches'])
        self.assertFalse(result['formalTrainingApproved'])
        self.assertEqual(result['trainingUse'], 'prohibited')

    def test_undeclared_or_duplicate_spurious_roi_cannot_shrink_denominator(self):
        for spurious in ([], [2, 2], [3]):
            source = {**copy.deepcopy(self.source), 'spuriousOldNails': spurious}
            with self.assertRaises(ValueError):
                audit.validate_denominators(self.row, source, self.decision)

    def test_frozen_source_judgment_or_new_denominator_drift_rejected(self):
        row = copy.deepcopy(self.row)
        row['latestOriginalPixelReview']['fullyTraceableNails'] = 2
        with self.assertRaises(ValueError):
            audit.validate_denominators(row, self.source, self.decision)
        changed = {**self.decision, 'completeVisibleNails': 2}
        with self.assertRaises(ValueError):
            audit.validate_denominators(self.row, self.source, changed)

    def test_failed_source_is_not_partially_promoted_and_other_roles_preserved(self):
        other = {**copy.deepcopy(self.row), 'ordinal': None, 'split': 'val', 'fileName': 'val.jpg'}
        fail = {**copy.deepcopy(self.decision), 'decision': 'label_rework', 'failedNailIndices': [1]}
        result = audit.apply_reviews({'currentFullSplitRecords': [self.row, other]}, [fail], self.scope, {})
        self.assertEqual(result[1], other)
        self.assertEqual(result[0]['existingReviewedMaskCount'], 0)
        self.assertEqual(result[0]['currentTruthCandidateEvidence']['status'], 'manual_mask_rework_required')
        self.assertEqual(result[0]['currentSourceDisposition'], 'label_rework')

    def test_excluded_source_and_partial_scope_cannot_be_overridden(self):
        excluded = {**self.row, 'currentSourceDisposition': 'source_quality_excluded'}
        with self.assertRaises(ValueError):
            audit.apply_reviews({'currentFullSplitRecords': [excluded]}, [self.decision], self.scope, {})
        with self.assertRaises(ValueError):
            audit.apply_reviews({'currentFullSplitRecords': [self.row]}, [], self.scope, {})


if __name__ == '__main__':
    unittest.main()
