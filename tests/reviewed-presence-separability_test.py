"""特征观测非干预、精确可行/不可行证书及不确定状态反例。"""
import copy
import importlib.util
import unittest
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parents[1]
def load(file,name):
    sp=importlib.util.spec_from_file_location(name,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
c=load('capture-reviewed-presence-features.py','capture_feature_tests')
s=load('certify-reviewed-presence-separability.py','separability_tests')
net=load('native-multiscale-conditional-refiner-v3.py','feature_nonzero_control')

class Tests(unittest.TestCase):
    def test_separable_complete_two_class_data_certified_exactly(self):
        f=np.array([[1.,1.],[2.,1.],[-1.,1.],[-2.,1.]],np.float32);flags=np.array([True,True,False,False])
        result=s.certify(f,flags);self.assertTrue(result['exactFeasible']);self.assertTrue(result['allExactSignedMarginsAtLeastOne'])
        self.assertEqual(s.verify_certificate(f,flags,result),result)
    def test_opposite_duplicate_has_exact_infeasibility_certificate(self):
        f=np.array([[1.,2.],[1.,2.]],np.float32);flags=np.array([True,False]);result=s.certify(f,flags)
        self.assertTrue(result['exactInfeasible']);s.verify_certificate(f,flags,result)
    def test_solver_infeasibility_without_exact_dual_remains_inconclusive(self):
        f=np.array([[1.,1.],[-1.,-1.],[1.,-1.],[-1.,1.]],np.float32);flags=np.array([True,True,False,False])
        result=s.certify(f,flags);self.assertFalse(result['exactInfeasible']);self.assertEqual(result['decision'],'inconclusive_solver_no_exact_certificate')
    def test_nonfinite_feature_rejected_before_solver(self):
        with self.assertRaisesRegex(ValueError,'domain'):s.certify(np.array([[np.nan],[1.]],np.float32),np.array([True,False]))
    def test_float64_rounding_cannot_hide_exact_margin_below_one(self):
        f=np.array([[1.,1.],[-1.,-1.]],np.float32);w=np.array([1.,-2.**-54,0.],np.float64)
        margins=s.exact_margins(f,np.array([True,False]),w);self.assertTrue(all(x<1 for x in margins))
        self.assertEqual(float(np.dot(f[0].astype(np.float64),w[:-1])),1.)
    def test_forged_exact_margin_rejected(self):
        f=np.array([[1.],[-1.]],np.float32);flags=np.array([True,False]);result=s.certify(f,flags);result['exactSignedMargins'][0]='999'
        with self.assertRaisesRegex(ValueError,'rational'):s.verify_certificate(f,flags,result)
    def test_certificate_cannot_shrink_full_denominator(self):
        f=np.array([[1.],[-1.]],np.float32);flags=np.array([True,False]);result=s.certify(f,flags);result['positiveInputs']=0
        with self.assertRaisesRegex(ValueError,'denominator'):s.verify_certificate(f,flags,result)
    def test_nonzero_full_model_control_hook_preserves_both_heads(self):
        torch.set_num_threads(2);torch.manual_seed(314159);model=net.NativeConditionalMaskRefiner().eval()
        with torch.no_grad():
            model.presence.weight.copy_(torch.linspace(-.3,.4,128).reshape(1,128));model.delta.weight.normal_();model.delta.bias.fill_(.25)
        x=torch.randn(1,4,16,20);x[:,3:4]=(x[:,3:4]>0).float();stored=[]
        with torch.inference_mode():original=model(x)
        hook=model.presence.register_forward_pre_hook(lambda m,args:c.observe_input(m,args,stored))
        try:
            with torch.inference_mode():actual=model(x)
        finally:hook.remove()
        self.assertEqual(len(stored),1)
        for a,b in zip(original,actual):self.assertEqual(a.numpy().tobytes(),b.numpy().tobytes())
        reconstructed=torch.nn.functional.linear(torch.from_numpy(stored[0]),model.presence.weight.detach(),model.presence.bias.detach())
        self.assertEqual(reconstructed.numpy().tobytes(),actual[1].numpy().tobytes())
    def test_hook_rejects_wrong_feature_storage(self):
        with self.assertRaisesRegex(ValueError,'float32'):c.observe_input(torch.nn.Linear(128,1),(torch.ones(1,128,dtype=torch.float64),),[])
    def test_hook_returns_none_and_does_not_alias_tensor_storage(self):
        value=torch.ones(1,128);stored=[];self.assertIsNone(c.observe_input(torch.nn.Linear(128,1),(value,),stored));stored[0][:]=0
        self.assertTrue(torch.equal(value,torch.ones_like(value)))

if __name__=='__main__':unittest.main()
