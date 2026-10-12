"""持久、恢复、新增误差以同一原像素域保真分区。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
s=importlib.util.spec_from_file_location('prior_partition',Path(__file__).resolve().parents[1]/'model/training/analyze-native-coarse-prior-errors.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_persistent_corrected_new_partition(self):
  truth=np.zeros((64,64),bool);truth[20:44,20:44]=True;coarse=truth.copy();coarse[20,25:35]=False
  prediction=truth.copy();prediction[20,25:30]=False;prediction[3,3]=True
  r=m.error_partition(truth,coarse,prediction)
  self.assertEqual((r['coarseErrorPixels'],r['finalErrorPixels']),(10,6))
  self.assertEqual((r['correctedPriorErrorPixels'],r['persistentPriorErrorPixels'],r['newErrorPixels']),(5,5,1))
  self.assertEqual(r['seedEdgeOriginalPixelStrips']['2']['finalErrorPixels'],5)
  self.assertEqual(r['coarseErrorPixels'],r['correctedPriorErrorPixels']+r['persistentPriorErrorPixels'])
  self.assertEqual(r['finalErrorPixels'],r['persistentPriorErrorPixels']+r['newErrorPixels'])
 def test_domain_or_shape_drift_rejected(self):
  mask=np.zeros((16,16),bool)
  with self.assertRaises(ValueError):m.error_partition(mask,mask.astype(np.uint8),mask)
  with self.assertRaises(ValueError):m.error_partition(mask,mask,np.zeros((17,16),bool))
if __name__=='__main__':unittest.main()
