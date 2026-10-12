"""旧分割参数或重复参数不得进入新头优化器。"""
import importlib.util,unittest
from pathlib import Path
import torch
s=importlib.util.spec_from_file_location('head_optimizer_guard',Path(__file__).resolve().parents[1]/'model/training/train-frozen-native-presence-head.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_only_new129_parameters_allowed(self):
  head=m.fresh_head();params=m.exact_head_parameters(head,head.parameters());self.assertEqual(sum(p.numel() for p in params),129)
  with self.assertRaises(ValueError):m.exact_head_parameters(head,[head.weight,torch.nn.Parameter(torch.zeros(128))])
  with self.assertRaises(ValueError):m.exact_head_parameters(head,[head.weight,head.weight])
 def test_fresh_initialization_and_balanced_both_class_gradients(self):
  head=m.fresh_head();self.assertTrue(torch.equal(head.weight,torch.zeros_like(head.weight)));self.assertEqual(float(head.bias.detach()),2.)
  x=torch.randn(68,128);y=torch.ones(68,1);y[-2:]=0;loss=m.balanced_loss(head,x,y);loss.backward()
  self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in head.parameters()))
if __name__=='__main__':unittest.main()
