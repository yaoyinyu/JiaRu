import importlib.util
from pathlib import Path
import unittest

import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


module = load('tested_recentered_capacity', ROOT/'model/training/visual-neighborhood-recentered-capacity.py')
fixture = load('recentered_fixture', ROOT/'tests/visual_neighborhood_extra_capacity_test.py').fixture


class RecenteredCapacityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): torch.set_num_threads(2)

    def test_sampling_follows_predicted_center_without_target_or_center_gradient(self):
        strip = torch.arange(129, dtype=torch.float32)[None, None, None].expand(1, 5, 2048, 129)
        coarse = torch.full((1, 2048), 20.)
        center = torch.full((1, 2048), 23., requires_grad=True)
        features = module.recentered_features(strip, center, coarse)
        self.assertEqual(tuple(features.shape), (1, 39, 2048))
        self.assertFalse(features.requires_grad)
        self.assertTrue(torch.equal(features[:, 15:20], torch.full((1, 5, 2048), 67.)))
        self.assertTrue(torch.equal(features[:, 35], center.detach()/256))
        moved = module.recentered_features(strip, center.detach()+1, coarse)
        self.assertTrue(torch.equal(moved[:, 15:20]-features[:, 15:20], torch.ones(1, 5, 2048)))

    def test_zero_output_preserves_heads_and_nonzero_output_has_all60_finite_gradients(self):
        model, cache, *args = fixture()
        cache['strip'] = torch.randn(1, 5, 2048, 129)
        module.attach_extra_capacity(model)
        old = module._extra.forward_with_extra_capacity(model, cache, *args)
        current = module.forward_with_recentered_capacity(model, cache, *args)
        for a, b in zip(old, current, strict=True):
            self.assertEqual(a.detach().numpy().tobytes(), b.detach().numpy().tobytes())
        nn.init.normal_(model.extra_capacity.output.weight, std=.01)
        mask, _, radius = module.forward_with_recentered_capacity(model, cache, *args)
        (mask.square().mean()+radius.square().mean()).backward()
        params = [p for p in model.parameters() if p.requires_grad]
        self.assertEqual(len(params), 60)
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in params))
        self.assertTrue(all(p.grad is None for p in model.previous.parameters()))


if __name__ == '__main__': unittest.main()
