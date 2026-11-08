import importlib.util
from pathlib import Path
import unittest
import torch
from torch import nn

spec=importlib.util.spec_from_file_location('visual_neighborhood',Path(__file__).parents[1]/'model/training/visual-neighborhood-radial-refiner.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Prior(nn.Module):
    def __init__(self):super().__init__();self.bias=nn.Parameter(torch.tensor(.25))
    def forward_with_radius(self,strip,coarse,bins,distance):
        radius=coarse+self.bias
        return (radius.gather(1,bins.reshape(1,-1)).reshape_as(distance)-distance)[:,None],self.bias.reshape(1),radius

class Tests(unittest.TestCase):
    def test_fractional_sampling_and_clamped_offsets(self):
        strip=torch.arange(129.).reshape(1,1,1,129).expand(1,5,16,129)
        result=m.sample_neighborhood(strip,torch.full((1,16),10.25),torch.full((1,16),10.),[-100.,0.,100.])
        self.assertTrue(torch.equal(result[:,0],torch.zeros(1,16)))
        self.assertTrue(torch.equal(result[:,5],torch.full((1,16),64.25)))
        self.assertTrue(torch.equal(result[:,10],torch.full((1,16),128.)))
    def test_zero_initialization_exact_and_prior_frozen_after_update(self):
        torch.manual_seed(5);model=m.VisualNeighborhoodRadialRefiner(Prior()).train()
        args=(torch.rand(1,5,32,129),torch.full((1,32),30.),torch.arange(32).reshape(1,4,8),torch.full((1,4,8),29.))
        expected=model.previous.forward_with_radius(*args);actual=model.forward_with_radius(*args)
        for a,b in zip(expected,actual):self.assertTrue(torch.equal(a,b))
        opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.001)
        loss=(actual[2]-31).square().mean();loss.backward()
        self.assertIsNone(model.previous.bias.grad);self.assertGreater(model.head.weight.grad.abs().sum(),0)
        opt.step();self.assertEqual(model.previous.bias.item(),.25)
        self.assertFalse(torch.equal(actual[2],model.forward_with_radius(*args)[2]))
        self.assertFalse(model.previous.training)

if __name__=='__main__':unittest.main()
