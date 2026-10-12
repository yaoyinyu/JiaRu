"""原像素候选条件输入的完整性及拒识语义反例。"""
import importlib.util
import unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('stage_b_input_tests',R/'model/training/materialize-reviewed-stage-b-inputs.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class Tests(unittest.TestCase):
 def fixture(self):
  rgb=np.arange(20*24*3,dtype=np.uint8).reshape(20,24,3);coarse=np.zeros((20,24),bool);coarse[7:12,8:15]=True;truth=np.zeros_like(coarse);truth[6:13,7:16]=True
  return rgb,coarse,truth
 def test_native_pixels_preserved_with_correct_origin(self):
  rgb,c,t=self.fixture();r,seed,target=m.crop_values(rgb,c,t,(5,4,18,15),True)
  self.assertTrue(np.array_equal(r,rgb[4:15,5:18]));self.assertEqual(int((target>0).sum()),int(t.sum()));self.assertEqual(seed.shape,target.shape)
 def test_partial_truth_crop_rejected(self):
  rgb,c,t=self.fixture()
  with self.assertRaisesRegex(ValueError,'pixels lost'):m.crop_values(rgb,c,t,(8,7,17,14),True)
 def test_candidate_rejection_does_not_remove_neighbor_rgb(self):
  rgb,c,t=self.fixture();r,seed,target=m.crop_values(rgb,c,np.zeros_like(t),(5,4,18,15),False)
  self.assertTrue(np.array_equal(r,rgb[4:15,5:18]));self.assertTrue(seed.any());self.assertFalse(target.any())
 def test_wrong_empty_target_and_seed_rejected(self):
  rgb,c,t=self.fixture()
  with self.assertRaisesRegex(ValueError,'rejection target'):m.crop_values(rgb,c,t,(5,4,18,15),False)
  with self.assertRaisesRegex(ValueError,'empty same-candidate'):m.crop_values(rgb,np.zeros_like(c),t,(5,4,18,15),True)
if __name__=='__main__':unittest.main()
