"""非零控制验证前向不变，分别验证分类与像素损失的梯度路径。"""
import importlib.util,unittest
from pathlib import Path
import torch
import torch.nn.functional as F
R=Path(__file__).resolve().parents[1]
def load(name,file):
 s=importlib.util.spec_from_file_location(name,R/'model/training'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('detached_test','native-presence-detached-conditional-refiner.py')
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def models(self):
  torch.manual_seed(211);old=m.base.NativeConditionalMaskRefiner();new=m.NativeConditionalMaskRefiner();new.load_state_dict(old.state_dict())
  for model in (old,new):
   with torch.no_grad():model.delta.weight.fill_(.1);model.presence.weight.fill_(.1)
  return old,new
 def test_nonzero_logits_and_presence_forward_identical(self):
  old,new=self.models();x=torch.randn(1,4,31,37);x[:,3]=(x[:,3]>0).float()
  with torch.inference_mode():a,p=old(x);b,q=new(x)
  self.assertTrue(torch.equal(a,b));self.assertTrue(torch.equal(p,q));self.assertFalse(torch.equal(a,x[:,3:4]*8-4))
 def test_classification_gradient_cannot_enter_encoder(self):
  _,new=self.models();x=torch.randn(1,4,31,37);x[:,3]=(x[:,3]>0).float();mask,p=new(x)
  F.binary_cross_entropy_with_logits(p,torch.zeros_like(p)).backward()
  self.assertTrue(all(v.grad is None for n,v in new.named_parameters() if not n.startswith('presence.')))
  self.assertTrue(all(v.grad is not None and torch.isfinite(v.grad).all() for n,v in new.named_parameters() if n.startswith('presence.')))
 def test_positive_mask_still_updates_encoder_and_final_reject_still_empty(self):
  _,new=self.models();x=torch.randn(1,4,31,37);x[:,3]=(x[:,3]>0).float();mask,p=new(x)
  F.binary_cross_entropy_with_logits(mask,torch.ones_like(mask)).backward()
  self.assertTrue(any(v.grad is not None and bool(v.grad.abs().max()>0) for n,v in new.named_parameters() if n.startswith('enc')))
  self.assertFalse(m.decode(mask.detach().numpy()[0,0],-1).any())
if __name__=='__main__':unittest.main()
