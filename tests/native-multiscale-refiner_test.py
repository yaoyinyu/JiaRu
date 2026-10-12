"""下一结构的原尺寸/拒识接口检查；不证明学得质量。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('native_multiscale_tests',R/'model/training/native-multiscale-conditional-refiner.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def test_odd_native_shape_and_initial_coarse_output(self):
  model=m.NativeConditionalMaskRefiner();x=torch.randn(1,4,31,37);x[:,3]=(x[:,3]>0).float();logits,p=model(x)
  self.assertEqual(tuple(logits.shape),(1,1,31,37));self.assertTrue(torch.equal(logits,x[:,3:4]*8-4));self.assertEqual(tuple(p.shape),(1,1))
 def test_candidate_rejection_keeps_native_size_without_coarse_fallback(self):
  self.assertFalse(m.decode(np.ones((19,23),np.float32),-1).any())
if __name__=='__main__':unittest.main()
