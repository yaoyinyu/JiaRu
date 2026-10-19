"""原生上下文残差的权重继承、非零路径和分支梯度合同。"""
import importlib.util
from pathlib import Path
import unittest
import torch
import torch.nn.functional as F

P=Path(__file__).resolve().parents[1]/'model/training/native-context-residual-conditional-refiner.py'
s=importlib.util.spec_from_file_location('context_test_model',P);net=importlib.util.module_from_spec(s);s.loader.exec_module(net)


class ContextRefinerTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        torch.manual_seed(20261019)
        self.old=net.base.NativeConditionalMaskRefiner().float()
        with torch.no_grad():
            self.old.delta.weight.uniform_(-.03,.03)
            self.old.delta.bias.fill_(.17)
            self.old.presence.weight.uniform_(-.03,.03)
        self.new=net.NativeConditionalMaskRefiner().float()
        self.new.load_base_state(self.old.state_dict())

    def sample(self,h,w):
        x=torch.randn(1,4,h,w);x[:,3]=(torch.rand(1,h,w)>.6).float()
        return x

    def test_warm_identity_on_odd_and_minimum_native_sizes(self):
        for h,w in [(16,16),(33,47),(64,64),(129,131)]:
            x=self.sample(h,w)
            with torch.inference_mode():a=self.old(x);b=self.new(x)
            self.assertTrue(all(torch.equal(u,v) for u,v in zip(a,b)))
            self.assertEqual(tuple(b[0].shape),(1,1,h,w))

    def test_bad_base_binding_rejected_before_weight_mutation(self):
        original={k:v.clone() for k,v in self.new.state_dict().items()}
        bad=dict(self.old.state_dict());bad['delta.weight']=torch.zeros(3)
        with self.assertRaises(ValueError):self.new.load_base_state(bad)
        self.assertTrue(all(torch.equal(v,self.new.state_dict()[k]) for k,v in original.items()))

    def test_positive_uses_every_parameter_even_zero_projection_upstream_gradient(self):
        mask,pres=self.new(self.sample(65,79));loss=F.binary_cross_entropy_with_logits(mask,torch.ones_like(mask))+F.binary_cross_entropy_with_logits(pres,torch.ones_like(pres));loss.backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in self.new.parameters()))
        self.assertTrue(bool(self.new.context_projection.weight.grad.abs().max()>0))
        self.assertTrue(all(not bool(p.grad.abs().max()>0) for n,p in self.new.named_parameters() if n.startswith(('context_down.','context_deep.','context_up.'))))

    def test_conditional_reject_keeps_mask_and_context_gradients_unused(self):
        mask,pres=self.new(self.sample(65,79));F.binary_cross_entropy_with_logits(pres,torch.zeros_like(pres)).backward()
        for name,p in self.new.named_parameters():
            if name.startswith(('dec1.','dec2.','delta.','context_')):self.assertIsNone(p.grad)
            else:self.assertTrue(p.grad is not None and torch.isfinite(p.grad).all())

    def test_nonzero_context_changes_mask_but_preserves_presence(self):
        with torch.no_grad():self.new.context_projection.weight.uniform_(-.04,.04)
        x=self.sample(65,79)
        with torch.inference_mode():a=self.old(x);b=self.new(x)
        self.assertFalse(torch.equal(a[0],b[0]));self.assertTrue(torch.equal(a[1],b[1]))
        self.assertTrue(all(torch.isfinite(v).all() for v in b))

    def test_invalid_input_domain_rejected(self):
        for shape in [(1,4,15,30),(2,4,32,32),(1,3,32,32)]:
            with self.assertRaises(ValueError):self.new(torch.zeros(shape))


if __name__=='__main__':unittest.main()
