"""数值门内的符号变化仍必须被实际解码门拒绝。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
s=importlib.util.spec_from_file_location('complete_decode',Path(__file__).resolve().parents[1]/'model/training/verify-native-multiscale-browser-v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_mask_sign_flip_inside_numeric_tolerance_is_not_pixel_pass(self):
  r=m.compare_outputs(np.array([1e-6],np.float32),np.ones(1,np.float32),np.array([-1e-6],np.float32),np.ones(1,np.float32),1,1)
  self.assertTrue(r['numericGatePassed']);self.assertFalse(r['decodedPixelGatePassed'])
 def test_presence_is_part_of_complete_decode(self):
  mask=np.ones(1,np.float32)
  r=m.compare_outputs(mask,np.array([1e-6],np.float32),mask,np.array([-1e-6],np.float32),1,1)
  self.assertTrue(r['numericGatePassed']);self.assertFalse(r['presenceDecisionMatched']);self.assertEqual(r['decodedMaskPixelDifference'],1)
 def test_either_reference_or_actual_head_nan_and_domain_rejected(self):
  for i in range(4):
   arrays=[np.ones(1,np.float32) for _ in range(4)];arrays[i][0]=np.nan
   with self.assertRaises(ValueError):m.compare_outputs(*arrays,1,1)
  with self.assertRaises(ValueError):m.compare_outputs(np.ones(1,np.float64),*[np.ones(1,np.float32) for _ in range(3)],1,1)
if __name__=='__main__':unittest.main()
