"""可行证书与同特征矛盾标签必须区分，数学系数不作训练权重。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
s=importlib.util.spec_from_file_location('linear_reach',Path(__file__).resolve().parents[1]/'model/training/certify-frozen-presence-linear-reachability.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_feasible_native_float32_linear_certificate(self):
  x=np.zeros((2,128),np.float32);x[:,0]=[1,-1];labels=np.array([1,0],np.uint8)
  report,w=m.solve_certificate(x,labels);self.assertTrue(report['reachable']);self.assertEqual(w.dtype,np.float32)
  self.assertGreater(report['minimumCpuFloat32SignedMargin'],0)
 def test_identical_feature_opposite_targets_unreachable(self):
  report,w=m.solve_certificate(np.zeros((2,128),np.float32),np.array([1,0],np.uint8))
  self.assertFalse(report['reachable']);self.assertEqual(report['solverCalls'],0);self.assertIsNone(w)
if __name__=='__main__':unittest.main()
