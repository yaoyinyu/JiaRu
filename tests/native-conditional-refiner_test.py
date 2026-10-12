"""原尺寸输出、初态同候选条件及明确拒识的检查。"""
import importlib.util,unittest
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('native_refiner_tests',R/'model/training/native-conditional-mask-refiner.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def test_native_shape_and_seed_initialization(self):
  model=m.NativeConditionalMaskRefiner();values=torch.zeros((1,4,23,29));values[:,3,8:15,10:18]=1
  logits,presence=model(values)
  self.assertEqual(tuple(logits.shape),(1,1,23,29));self.assertTrue(torch.equal(logits,(values[:,3:4]*8-4)))
  self.assertGreater(float(presence.detach()),0)
 def test_rejection_does_not_fallback_to_nonempty_mask(self):
  logits=np.ones((17,19),np.float32)
  self.assertFalse(m.decode(logits,-.1).any());self.assertTrue(m.decode(logits,.1).all())
  with self.assertRaises(ValueError):m.decode(np.full((2,2),np.nan),1.)
 def test_empty_target_gradients_finite_and_used(self):
  model=m.NativeConditionalMaskRefiner();values=torch.randn(1,4,17,19);values[:,3]=(values[:,3]>0).float()
  logits,presence=model(values);loss=m.candidate_loss(logits,presence,torch.zeros_like(logits),torch.zeros(1));loss.backward()
  self.assertTrue(torch.isfinite(loss));self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))
 def test_native_pack_does_not_resize_or_drop_rgb(self):
  rgb=np.full((13,17,3),128,np.uint8);coarse=np.zeros((13,17),np.uint8);coarse[3:9,4:12]=255
  packed=m.pack(rgb,coarse);self.assertEqual(packed.shape,(4,13,17));self.assertTrue(np.array_equal(packed[3],coarse/255))
if __name__=='__main__':unittest.main()
