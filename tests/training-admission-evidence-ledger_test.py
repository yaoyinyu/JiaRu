import importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('ledger',R/'model/training/audit-training-admission-evidence-ledger.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def row(name,n=5):return {'identity':{'split':'train','fileName':name,'imageSha256':name*64},'sourceGroup':'g','maskCount':n,'annotation':{'path':name,'sha256':'x'}}
class LedgerTests(unittest.TestCase):
 def test_stable_identity_missing_nails_not_report_count(self):
  c=m.coverage([row('a',5),row('b',8)],[row('a',5)]);self.assertEqual((c['missingSources'],c['missingNails']),(1,8));self.assertFalse(c['complete'])
 def test_duplicate_unknown_and_changed_truth_rejected(self):
  for obs in [[row('a'),row('a')],[row('b')],[row('a',6)]]:
   with self.assertRaises(ValueError):m.coverage([row('a')],obs)
 def test_split_is_part_of_identity(self):
  r=row('a');v={**r,'identity':{**r['identity'],'split':'val'}}
  with self.assertRaises(ValueError):m.coverage([r],[v])
 def test_ast_reads_literal_gate_states(self):
  self.assertEqual(m.literal_gate_assignments("gates={'a':False,'b':True,'c':predicate()}"),{'a':False,'b':True})
 def test_only_explicit_edges_establish_cycles(self):
  edges=[['data','admission'],['admission','training'],['training','release']];self.assertFalse(m.has_cycle(edges));self.assertTrue(m.has_cycle(edges+[['training','admission']]))
if __name__=='__main__':unittest.main()
