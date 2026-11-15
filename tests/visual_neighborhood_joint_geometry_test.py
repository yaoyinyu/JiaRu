import importlib.util
from pathlib import Path
import unittest
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'model/training'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


joint = load('tested_joint_geometry', 'visual-neighborhood-joint-geometry.py')
geometry = load('tested_joint_previous', 'native-geometry-radial-refiner.py')
cached = load('tested_joint_old_features', 'cached-visual-neighborhood-training.py')


def fixture():
    torch.manual_seed(20261124)
    visual = nn.ParameterList(nn.Parameter(torch.randn(()), requires_grad=False) for _ in range(79))
    model = joint._sampler.VisualNeighborhoodRadialRefiner(geometry.NativeGeometryRadialRefiner(visual))
    model.angle_context = joint._capacity.LocalCapacityResidual()
    for head in (model.previous.head, model.head, model.angle_context.output):
        nn.init.normal_(head.weight, std=.01)
    cache = dict(features=torch.randn(1,23,128), initial=torch.full((1,128),20.125), presence=torch.tensor([[1.25]]))
    strip = torch.randn(1,5,128,129)
    coarse = torch.full((1,128),20.)
    bins = torch.arange(128).reshape(1,8,16)
    distance = torch.linspace(0,30,128).reshape_as(bins)
    return model,cache,strip,coarse,bins,distance


class JointGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_existing_cached_outputs_and_weights_remain_byte_exact(self):
        model, cache, strip, coarse, bins, distance = fixture()
        before = {k:v.clone() for k,v in model.state_dict().items()}
        with torch.no_grad():
            _,presence,initial = joint._geometry.forward(model.previous,cache,coarse,bins,distance)
            expected_cache = dict(features=cached.features(model,strip,initial,coarse),initial=initial,presence=presence)
            expected = joint._capacity.forward_with_capacity(model,expected_cache,coarse,bins,distance)
        joint.enable_joint_geometry(model)
        actual = joint.forward_with_joint_geometry(model,cache,strip,coarse,bins,distance)
        for a,b in zip(actual,expected,strict=True):
            self.assertEqual(a.detach().numpy().tobytes(),b.numpy().tobytes())
        for k,v in model.state_dict().items():
            self.assertTrue(torch.equal(v,before[k]))

    def test_nonzero_control_reaches_all64_parameters_with_visual79_frozen(self):
        model,*args = fixture()
        params = joint.enable_joint_geometry(model)
        mask,_,radius = joint.forward_with_joint_geometry(model,*args)
        (mask.square().mean()+radius.square().mean()).backward()
        self.assertEqual(len(params),64)
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in params))
        self.assertTrue(model.previous.project.weight.grad.abs().sum()>0)
        self.assertTrue(all(p.grad is None and not p.requires_grad for p in model.previous.base.parameters()))

    def test_sampling_retains_geometry_radius_gradient_and_validates_shape(self):
        model,_,strip,coarse,_,_ = fixture()
        initial=torch.full_like(coarse,20.125,requires_grad=True)
        joint.neighborhood_features(model,strip,initial,coarse).sum().backward()
        self.assertTrue(torch.isfinite(initial.grad).all())
        self.assertGreater(float(initial.grad.abs().sum()),0)
        with self.assertRaisesRegex(ValueError,'angles must align'):
            joint.neighborhood_features(model,strip,initial[:,:64],coarse)


if __name__=='__main__':
    unittest.main()
