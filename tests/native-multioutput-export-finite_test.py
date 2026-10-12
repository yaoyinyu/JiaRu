"""小输出头NaN不得被max(正常mask误差,NaN)吞掉。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
s=importlib.util.spec_from_file_location('multioutput_export_finite',Path(__file__).resolve().parents[1]/'model/training/audit-native-multiscale-export-v3.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_any_head_in_either_reference_or_ort_nonfinite_rejected(self):
  for index in range(4):
   for bad in (np.nan,np.inf):
    arrays=[np.zeros((1,1,16,16),np.float32),np.zeros((1,1),np.float32),np.zeros((1,1,16,16),np.float32),np.zeros((1,1),np.float32)]
    arrays[index].flat[0]=bad
    with self.assertRaises(ValueError):m.checked_output_error(*arrays,16,16)
 def test_presence_shape_and_small_head_error_cannot_hide(self):
  a=np.zeros((1,1,16,16),np.float32);p=np.zeros((1,1),np.float32)
  self.assertEqual(m.checked_output_error(a,p,a,p,16,16),0)
  with self.assertRaises(ValueError):m.checked_output_error(a,p,a,p+.001,16,16)
  with self.assertRaises(ValueError):m.checked_output_error(a,p,a,np.zeros((1,),np.float32),16,16)
if __name__=='__main__':unittest.main()
