"""训练目标身份、正权重梯度和原侧缘目标保持。"""
import hashlib
import importlib.util
from pathlib import Path
import unittest
import torch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('weighted_boundary_test', ROOT/'model/training/native-sample-weighted-boundary-loss.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class FrozenWeightsTest(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.target = torch.full((1, 2048), 4., dtype=torch.float32)
        self.key = hashlib.sha256(self.target.numpy().tobytes()).hexdigest()

    def test_weight_scales_actual_original_loss_and_both_gradients(self):
        y, x = torch.meshgrid(torch.arange(11), torch.arange(11), indexing='ij')
        truth = (((x-5)**2+(y-5)**2)<=16).float()[None,None]
        band = torch.ones_like(truth)
        gradients = []
        values = []
        for weight in [1., 4.]:
            mask = (5.-((x-5).float().square()+(y-5).float().square()).sqrt())[None,None].requires_grad_()
            presence = torch.zeros((), requires_grad=True)
            radius = torch.full((1,2048), 5., requires_grad=True)
            loss = M.FrozenSampleWeightedObjective({self.key:weight}).objective(mask,presence,radius,truth,self.target,band)
            loss.backward()
            values.append(loss.detach())
            gradients.append([mask.grad, presence.grad, radius.grad])
        self.assertTrue(torch.equal(values[1],values[0]*4))
        for a,b in zip(*gradients):
            self.assertTrue(bool(torch.isfinite(a).all()))
            self.assertTrue(bool(a.abs().sum()>0))
            self.assertTrue(torch.equal(b,a*4))

    def test_unknown_or_invalid_target_stops_before_base_objective(self):
        called=[]
        obj=M.FrozenSampleWeightedObjective({self.key:1.},lambda *args:called.append(True))
        for target in [self.target+1,self.target.double(),self.target[:,:2],self.target*float('nan')]:
            with self.assertRaises(ValueError): obj.objective(None,None,None,None,target,None)
        self.assertEqual(called,[])

    def test_recipe_copy_and_invalid_weights(self):
        weights={self.key:1.}
        obj=M.FrozenSampleWeightedObjective(weights)
        weights[self.key]=4.
        self.assertEqual(obj.multiplier(self.target),1.)
        for value in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError): M.FrozenSampleWeightedObjective({self.key:value})
        with self.assertRaises(ValueError): M.FrozenSampleWeightedObjective({'invalid':1.})


if __name__=='__main__': unittest.main()
