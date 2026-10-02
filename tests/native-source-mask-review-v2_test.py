"""新版处置必须保持最新split，并明确区分旧ROI与新人工甲面分母。"""
import copy
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('native_audit_v2', Path(__file__).resolve().parents[1] / 'model/training/audit-native-source-mask-review-v2.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class NativeReviewV2Tests(unittest.TestCase):
    def setUp(self):
        self.record = {'sourceFileName': 'source.jpg', 'sourceGroup': 'g',
                       'sourceImage': {'path': 'image', 'sha256': 'a' * 64},
                       'sourceLabel': {'path': 'label', 'sha256': 'b' * 64},
                       'historicalNails': 2, 'rawTiles': [{'image': {'path': 'raw'}}],
                       'nailPanels': [{'image': {'path': 'pair1'}}, {'image': {'path': 'pair2'}}]}
        self.decision = {'ordinal': 1, 'fileName': 'source.jpg', 'sourceGroup': 'g',
                         'sourceImage': self.record['sourceImage'], 'sourceLabel': self.record['sourceLabel'],
                         'historicalMaskCount': 2, 'reviewedHistoricalNailIndices': [1, 2],
                         'viewedArtifacts': [p['image'] for p in self.record['rawTiles'] + self.record['nailPanels']],
                         'retainedApprovedOldMaskIndices': [], 'trainingUse': 'prohibited',
                         'reason': 'Old second mask is skin; one complete nail remains.', 'markerDecision': 'badge',
                         'sourceQualityDecision': 'complete_visible_nails_traceable', 'maskDecision': 'label_rework',
                         'fullyTraceableNails': 1, 'defectiveOldNails': [1, 2], 'spuriousOldNails': [2]}

    def test_explicit_spurious_old_roi_preserves_old_denominator(self):
        audit.validate_decision(self.record, self.decision)
        self.assertEqual(self.decision['historicalMaskCount'], 2)
        for spurious in ([], [2, 2], [3]):
            d = copy.deepcopy(self.decision)
            d['spuriousOldNails'] = spurious
            with self.assertRaises(ValueError): audit.validate_decision(self.record, d)

    def test_partial_additional_nail_excludes_whole_source_without_reducing_old_count(self):
        d = copy.deepcopy(self.decision)
        d.update(sourceQualityDecision='exclude_incomplete_nail_boundary', maskDecision='source_quality_excluded',
                 fullyTraceableNails=2, additionalUntraceableNails=1)
        audit.validate_decision(self.record, d)
        d['trainingUse'] = 'allowed'
        with self.assertRaises(ValueError): audit.validate_decision(self.record, d)

    def test_latest_disposition_is_baseline_not_stale_records(self):
        row = {**self.decision, 'split': 'train',
               'currentSourceDisposition': 'pending_original_resolution_complete_source_and_mask_review',
               'historicalRoiIds': ['roi1', 'roi2'], 'parents': [{'sourceGroup': 'protected'}]}
        old_done = {**row, 'ordinal': 2, 'fileName': 'reviewed.jpg', 'currentSourceDisposition': 'recorded_mask_visual_pass_pending_full_split'}
        val = {**row, 'split': 'val', 'ordinal': 3, 'upstreamDevelopmentSplit': 'train'}
        baseline = {'currentFullSplitRecords': [row, old_done, val], 'records': []}
        result = audit.apply_dispositions(baseline, [self.decision])
        self.assertEqual(result[1:], baseline['currentFullSplitRecords'][1:])
        self.assertEqual(result[0]['historicalRoiIds'], ['roi1', 'roi2'])
        self.assertEqual(result[0]['parents'], row['parents'])
        with self.assertRaises(ValueError): audit.apply_dispositions({'currentFullSplitRecords': result}, [self.decision])

    def test_missing_page_or_automatic_old_mask_promotion_rejected(self):
        for key, value in [('viewedArtifacts', self.decision['viewedArtifacts'][:-1]),
                           ('retainedApprovedOldMaskIndices', [1]), ('reviewedHistoricalNailIndices', [1])]:
            d = copy.deepcopy(self.decision)
            d[key] = value
            with self.assertRaises(ValueError): audit.validate_decision(self.record, d)

if __name__ == '__main__': unittest.main()
