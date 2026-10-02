import copy,importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('effects',ROOT/'model/training/audit-matched-marker-sensitivity-effects.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class MarkerEffectsTests(unittest.TestCase):
    def fixture(self):
        base={'split':'train','ordinal':1,'fileName':'nail','sourceGroup':'g','sourceImage':{},'upstreamDevelopmentSplit':'train','parents':[],'trainingUse':'prohibited',
              'currentSourceDisposition':'mask_pending_roles','historicalMaskCount':2}
        record={k:v for k,v in base.items() if k not in ('split','currentSourceDisposition','historicalMaskCount')}
        record.update(completeVisibleNails=2,comparisons={'pair':{'unionSymmetricDifferencePixels':2,'unionIoU':.98,'candidateCountDelta':0,'newMissedTruthIndices':[],'recoveredTruthIndices':[]}},
                      predictions={'original':{'missedTruthIndices':[2],'assignment':[{'truthIndex':1,'predictionIndex':1,'iou':.9},{'truthIndex':2,'predictionIndex':2,'iou':.6}]}})
        return {'records':[record],'counts':{'sourceImages':1,'completeVisibleNails':2}},{'currentFullSplitRecords':[base]}
    def test_existing_low_iou_candidate_is_not_missing_roi_proof(self):
        probe,baseline=self.fixture();result=m.summarize(probe,baseline)
        self.assertEqual(result['originalLowIoUAssignedCandidates'][0]['predictionIndex'],2)
        self.assertIn('not proof of absent',result['originalLowIoUAssignedCandidates'][0]['interpretation'])
    def test_group_coverage_retains_unprobed_or_excluded_sources(self):
        probe,baseline=self.fixture();extra=copy.deepcopy(baseline['currentFullSplitRecords'][0]);extra.update(ordinal=2,currentSourceDisposition='source_quality_excluded')
        baseline['currentFullSplitRecords'].append(extra);g=m.summarize(probe,baseline)['groupCoverage'][0]
        self.assertEqual(g['fullSnapshotSources'],2);self.assertEqual(g['unprobedSourceRecords'][0]['ordinal'],2);self.assertFalse(g['wholeGroupShortcutExclusionProven'])
    def test_denominator_role_and_parent_drift_fail_closed(self):
        probe,baseline=self.fixture()
        for key,value in [('fileName','wrong'),('parents',[{}]),('trainingUse','allowed')]:
            changed=copy.deepcopy(probe);changed['records'][0][key]=value
            with self.assertRaises(ValueError):m.summarize(changed,baseline)
        changed=copy.deepcopy(probe);changed['counts']['completeVisibleNails']=1
        with self.assertRaises(ValueError):m.summarize(changed,baseline)
    def test_union_sensitivity_does_not_erase_no_match_migration(self):
        probe,baseline=self.fixture();r=m.summarize(probe,baseline)['comparisons']['pair']
        self.assertEqual(r['sourcesWithTruthMatchMigration'],0);self.assertEqual(r['maxUnionDifferentPixels'],2);self.assertAlmostEqual(r['maxUnionChangedFraction'],.02)
if __name__=='__main__':unittest.main()
