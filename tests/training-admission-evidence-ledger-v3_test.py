import copy,importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('ledger3',R/'model/training/audit-training-admission-evidence-ledger-v3.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def source(name,n=5):return {'identity':{'split':'train','fileName':name,'imageSha256':name*64},'sourceGroup':'g-'+name,'annotation':{'path':name+'.json','sha256':name*64},'maskCount':n}
class QualificationCoverageTests(unittest.TestCase):
 def test_excluded_observed_proof_preserved_without_current_coverage(self):
  allRows=[source('a'),source('b',7)];snapshot=copy.deepcopy(allRows);kept,d=m.restrict_observed_to_required(allRows[:1],allRows,allRows)
  self.assertEqual(allRows,snapshot);self.assertEqual(kept,allRows[:1]);self.assertEqual((d['originalProofSources'],d['originalProofNails'],d['qualificationExcludedProofSources'],d['qualificationExcludedProofNails']),(2,12,1,7));self.assertFalse(d['trainingAllowed']);self.assertTrue(d['originalRowsPreserved']);self.assertEqual(m.coverage(allRows[:1],kept)['coveredNails'],5)
 def test_excluded_bad_truth_cannot_be_hidden_by_filter(self):
  allRows=[source('a'),source('b')]
  for field in ('sourceGroup','annotation','maskCount'):
   observed=copy.deepcopy(allRows);observed[1][field]=9
   with self.assertRaises(ValueError):m.restrict_observed_to_required(allRows[:1],allRows,observed)
 def test_foreign_or_duplicate_observations_rejected(self):
  allRows=[source('a'),source('b')]
  for observed in ([source('z')],[allRows[1],allRows[1]]):
   with self.assertRaises(ValueError):m.restrict_observed_to_required(allRows[:1],allRows,observed)
 def test_required_truth_and_membership_must_match_original(self):
  allRows=[source('a'),source('b')];bad=copy.deepcopy(allRows[:1]);bad[0]['maskCount']=6
  for required in (bad,[source('z')]):
   with self.assertRaises(ValueError):m.restrict_observed_to_required(required,allRows,allRows)
 def test_missing_eligible_proof_is_not_promoted(self):
  allRows=[source('a'),source('b')];kept,d=m.restrict_observed_to_required(allRows[:1],allRows,allRows[1:]);c=m.coverage(allRows[:1],kept)
  self.assertFalse(c['complete']);self.assertEqual((c['coveredSources'],c['missingSources'],c['missingNails']),(0,1,5));self.assertFalse(d['trainingAllowed'])
if __name__=='__main__':unittest.main()
