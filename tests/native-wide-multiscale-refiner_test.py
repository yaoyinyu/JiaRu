"""宽度变量的原尺寸、初态种子及有限梯度控制。"""
import importlib.util,unittest
from pathlib import Path
import torch
s=importlib.util.spec_from_file_location('wide_native_model',Path(__file__).resolve().parents[1]/'model/training/native-wide-multiscale-conditional-refiner.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def test_odd_native_shapes_and_same_initial_seed_logits(self):
  model=m.NativeConditionalMaskRefiner()
  self.assertEqual(sum(p.numel() for p in model.parameters()),472738)
  for h,w in ((17,19),(31,37)):
   x=torch.randn(1,4,h,w);x[:,3]=(x[:,3]>0).float();logits,presence=model(x)
   self.assertEqual(tuple(logits.shape),(1,1,h,w));self.assertTrue(torch.equal(logits,x[:,3:4]*8-4))
   self.assertTrue(torch.equal(presence,torch.full_like(presence,2.)))
 def test_positive_finite_used_gradients_and_rejection_decode(self):
  model=m.NativeConditionalMaskRefiner();x=torch.randn(1,4,31,37);x[:,3]=(x[:,3]>0).float()
  logits,presence=model(x);truth=(torch.rand_like(logits)>.5).float()
  loss=m.candidate_loss(logits,presence,truth,torch.ones(1));loss.backward()
  self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))
  self.assertFalse(m.decode(logits.detach().numpy()[0,0],-1).any())
if __name__=='__main__':unittest.main()
