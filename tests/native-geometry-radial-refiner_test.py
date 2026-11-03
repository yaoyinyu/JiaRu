"""非零基线保真、坐标范围和冻结参数控制。"""
import importlib.util
from pathlib import Path
import unittest

import torch

spec = importlib.util.spec_from_file_location('geometry_test', Path(__file__).resolve().parents[1] /
                                             'model/training/native-geometry-radial-refiner.py')
net = importlib.util.module_from_spec(spec)
spec.loader.exec_module(net)
torch.set_num_threads(2)


class GeometryTests(unittest.TestCase):
    def args(self):
        torch.manual_seed(143)
        strip = torch.randn(1, 5, 32, 129)
        coarse = torch.linspace(10, 70, 32)[None]
        bins = torch.arange(99).remainder(32).reshape(1, 9, 11)
        distance = torch.linspace(0, 80, 99).reshape(1, 9, 11)
        return strip, coarse, bins, distance

    def test_nonzero_baseline_exact_and_frozen(self):
        model = net.NativeGeometryRadialRefiner()
        with torch.no_grad():
            model.base.local.score.weight.normal_(0, .1)
            model.base.context_score.weight.normal_(0, .1)
        args = self.args()
        expected = model.base.forward_with_radius(*args)
        actual = model.forward_with_radius(*args)
        for a, b in zip(expected, actual, strict=True):
            self.assertTrue(torch.equal(a, b))
        model.train()
        self.assertFalse(model.base.training)
        (actual[0].square().mean() + actual[2].square().mean()).backward()
        self.assertTrue(all(p.grad is None for p in model.base.parameters()))
        trainable = [p for p in model.parameters() if p.requires_grad]
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in trainable))
        self.assertGreater(int(torch.count_nonzero(model.head.weight.grad)), 0)

    def test_nonzero_residual_changes_radius_keeps_presence_and_bound(self):
        model = net.NativeGeometryRadialRefiner()
        args = self.args()
        baseline = model.forward_with_radius(*args)
        with torch.no_grad():
            model.head.bias.fill_(200)
        mask, presence, radius = model.forward_with_radius(*args)
        self.assertTrue(torch.equal(presence, baseline[1]))
        self.assertFalse(torch.equal(mask, baseline[0]))
        self.assertTrue(torch.equal(radius, args[1] + 64))
        self.assertTrue(torch.isfinite(mask).all())

    def test_circular_convolution_roll_equivariance(self):
        block = net.CircularResidual(32, 256)
        value = torch.randn(1, 32, 32)
        self.assertTrue(torch.allclose(block(value.roll(7, -1)), block(value).roll(7, -1), atol=1e-6))


if __name__ == '__main__':
    unittest.main()
