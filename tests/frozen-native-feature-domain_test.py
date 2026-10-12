"""固定特征正负冲突不得被去重或低精度转换隐藏。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
s=importlib.util.spec_from_file_location('frozen_domains',Path(__file__).resolve().parents[1]/'model/training/materialize-frozen-native-presence-features.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_cross_class_collision_preserved(self):
  x=np.zeros((3,128),np.float32);x[2,0]=1
  self.assertEqual(m.validate_features(x,np.array([1,0,1],np.uint8)),[[0,1]])
 def test_float32_domain_and_nonfinite_required(self):
  x=np.zeros((2,128),np.float32);labels=np.array([1,0],np.uint8)
  with self.assertRaises(ValueError):m.validate_features(x.astype(np.float64),labels)
  x[0,4]=np.nan
  with self.assertRaises(ValueError):m.validate_features(x,labels)
if __name__=='__main__':unittest.main()
