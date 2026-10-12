"""新资格先验证原完整分母，再投影；排除行同样必须保真。"""
import copy,importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('admission_v3',R/'model/training/audit-nail-training-admission-contract-v3.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class ProjectionTests(unittest.TestCase):
 def setUp(self):
  self.rows=[{'identity':{'split':'train','fileName':f'{i}.jpg','imageSha256':str(i)},'sourceGroup':f'g{i}','sourceImage':{'path':f'{i}.jpg','sha256':str(i)},'annotation':{'path':f'{i}.json','sha256':str(i)},'maskCount':i+1} for i in range(3)];self.required=m.unique(copy.deepcopy(self.rows));self.ledger={'currentCandidateCounts':{'combinedSources':3,'combinedNails':6},'sourceParentQualificationInventory':copy.deepcopy(self.rows)};self.quality={'originalCandidateCountsPreserved':copy.deepcopy(self.ledger['currentCandidateCounts']),'originalCandidateInventoryPreserved':copy.deepcopy(self.rows),'sourceQualityReviewedSources':3,'sourceQualityRemainingSources':0,'currentQualityEligibleInventory':copy.deepcopy([self.rows[0],self.rows[2]]),'excludedFromFutureTraining':copy.deepcopy([self.rows[1]]),'currentQualityEligibleCounts':{'combinedSources':2,'combinedNails':4},'currentCoverageProjection':{'nativeInputControls':{'complete':False},'conditionalInputs':{'complete':False}}}
 def run_projection(self):return m.project_reviewed_source_quality(self.required,self.ledger,self.quality)
 def test_current_projection_preserves_original(self):
  current,counts,native,roi=self.run_projection();self.assertEqual(len(current),2);self.assertEqual(len(self.required),3);self.assertEqual(self.ledger['currentCandidateCounts']['combinedNails'],6);self.assertFalse(native['complete']);self.assertFalse(roi['complete'])
 def test_incomplete_quality_rejected(self):
  self.quality['sourceQualityRemainingSources']=1
  with self.assertRaisesRegex(ValueError,'incomplete'):self.run_projection()
 def test_excluded_drift_rejected(self):
  self.quality['excludedFromFutureTraining'][0]['annotation']['sha256']='changed'
  with self.assertRaisesRegex(ValueError,'excluded truth drift'):self.run_projection()
 def test_original_denominator_drift_rejected(self):
  self.quality['originalCandidateInventoryPreserved'].pop()
  with self.assertRaisesRegex(ValueError,'original cohort drift'):self.run_projection()
 def test_exclusion_partition_required(self):
  self.quality['excludedFromFutureTraining']=[]
  with self.assertRaisesRegex(ValueError,'partition mismatch'):self.run_projection()
if __name__=='__main__':unittest.main()
