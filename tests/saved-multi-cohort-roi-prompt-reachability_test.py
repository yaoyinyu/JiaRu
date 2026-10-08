"""多报告/空标记兼容不放松一一覆盖、种子和冻结原分配。"""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('multi_roi',R/'model/training/audit-saved-multi-cohort-roi-prompt-reachability.py')
roi=load('multi_roi_geometry',R/'model/training/analyze-saved-nail-roi-coverage.py')
prompt=load('multi_prompt_geometry',R/'model/training/audit-saved-conditional-input-preflight.py')
class MultiTests(unittest.TestCase):
 def test_legacy_top_level_and_nested_marker_boxes_match(self):
  b=[1,2,3,4]
  self.assertEqual(m.registered_markers({'markerBox':b}),[b])
  self.assertEqual(m.registered_markers({'sourcePreserved':{'markerBox':b}}),[b])
 def test_empty_registration_does_not_fabricate_marker_at_origin(self):
  boxes=m.registered_markers({'sourcePreserved':{'windows':[]}})
  self.assertEqual(boxes,[])
  self.assertEqual(m.marker_halos(boxes,100,100),[])
  self.assertEqual(m.marker_intersection([0,0,20,20],[],prompt),0)
  self.assertIsNone(m.marker_intersection(None,[],prompt))
 def test_any_of_multiple_registered_markers_blocks_roi(self):
  boxes=m.registered_markers({'sourcePreserved':{'windows':[{'markerBox':[30,30,35,35]},{'markerBox':[80,80,90,90]}]}})
  halos=m.marker_halos(boxes,100,100)
  self.assertEqual(m.marker_intersection([0,0,10,10],halos,prompt),0)
  self.assertGreater(m.marker_intersection([70,70,90,90],halos,prompt),0)
 def test_invalid_marker_geometry_rejected(self):
  for b in [[1,2,3], [2,2,1,3], [1,2,float('nan'),4]]:
   with self.assertRaises(ValueError):m.registered_markers({'markerBox':b})
 def test_large_single_candidate_never_covers_multiple_truths_in_oracle(self):
  self.assertEqual(len(m.joint_oracle(np.ones((3,1),bool),np.ones((3,1)))),1)
 def test_fixed_assignment_remains_failed_even_if_different_oracle_exists(self):
  old={'assignment':[{'truthIndex':1,'predictionIndex':1,'iou':.8},{'truthIndex':2,'predictionIndex':2,'iou':.7}]}
  cov=np.array([[0,1],[1,0]],float);valid=cov>0
  stats=m.variant_stats([0,1],cov,np.ones((2,2)),valid,old,roi)
  self.assertEqual(stats['primaryFullCoverageNails'],0)
  self.assertEqual(stats['oracleFullCoverageNails'],2)
  self.assertEqual(stats['unresolvedOriginalTruthIndices'],[1,2])
 def test_removed_assigned_candidate_keeps_complete_truth_denominator(self):
  old={'assignment':[{'truthIndex':1,'predictionIndex':1,'iou':.8},{'truthIndex':2,'predictionIndex':2,'iou':.8}]}
  stats=m.variant_stats([0],np.eye(2),np.eye(2),np.eye(2,dtype=bool),old,roi)
  self.assertEqual(len(stats['primaryAssignmentPreserved']),2)
  self.assertEqual(stats['unresolvedOriginalTruthIndices'],[2])
if __name__=='__main__':unittest.main()
