import importlib.util
from pathlib import Path
import unittest

import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tested_extra_capacity', ROOT/'model/training/visual-neighborhood-extra-capacity.py')
extra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extra)


def fixture():
    torch.manual_seed(20261123)
    model = nn.Module()
    model.previous = nn.ParameterList(nn.Parameter(torch.randn(()), requires_grad=False) for _ in range(103))
    model.project = nn.Conv1d(39, 32, 1)
    model.convs = nn.ModuleList(nn.Conv1d(32, 32, 3, dilation=d) for d in (1, 2, 4, 8))
    model.norms = nn.ModuleList(nn.GroupNorm(4, 32) for _ in model.convs)
    model.head = nn.Conv1d(32, 1, 1)
    model.angle_context = extra._parent.LocalCapacityResidual()
    cache = dict(features=torch.randn(1, 39, 2048), initial=torch.full((1, 2048), 20.125), presence=torch.tensor([[1.25]]))
    coarse = torch.full((1, 2048), 20.)
    bins = torch.arange(1024).reshape(1, 32, 32)
    distance = torch.linspace(0, 30, 1024).reshape(1, 32, 32)
    return model, cache, coarse, bins, distance


class ExtraCapacityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_zero_initialization_preserves_all_heads_weights_and_rng(self):
        model, *args = fixture()
        before = {k: v.clone() for k, v in model.state_dict().items()}
        expected = extra._parent.forward_with_capacity(model, *args)
        rng = torch.get_rng_state().clone()
        extra.attach_extra_capacity(model)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        actual = extra.forward_with_extra_capacity(model, *args)
        for a, b in zip(expected, actual, strict=True):
            self.assertEqual(a.detach().numpy().tobytes(), b.detach().numpy().tobytes())
        for key, value in before.items():
            self.assertEqual(value.numpy().tobytes(), model.state_dict()[key].numpy().tobytes())
        self.assertEqual(sum(p.requires_grad for p in model.parameters()), 60)
        self.assertEqual(sum(not p.requires_grad for p in model.parameters()), 103)
        with self.assertRaisesRegex(ValueError, 'already attached'):
            extra.attach_extra_capacity(model)

    def test_nonzero_branch_has_finite_gradients_and_keeps_frozen_parameters(self):
        model, *args = fixture()
        extra.attach_extra_capacity(model)
        nn.init.normal_(model.extra_capacity.output.weight, std=.01)
        mask, _, radius = extra.forward_with_extra_capacity(model, *args)
        (mask.square().mean()+radius.square().mean()).backward()
        parameters = [p for p in model.parameters() if p.requires_grad]
        self.assertEqual(len(parameters), 60)
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in parameters))
        self.assertTrue(all(p.grad is None for p in model.previous.parameters()))
        self.assertTrue(torch.all(radius >= 0))
        self.assertTrue(torch.all(radius <= args[1]+64))

    def test_large_corrections_keep_existing_radius_limits(self):
        model, *args = fixture()
        extra.attach_extra_capacity(model)
        with torch.no_grad():
            model.extra_capacity.output.bias.fill_(1000)
        _, presence, radius = extra.forward_with_extra_capacity(model, *args)
        self.assertTrue(torch.equal(radius, args[1]+64))
        self.assertIs(presence, args[0]['presence'])
        with torch.no_grad():
            model.extra_capacity.output.bias.fill_(-1000)
        _, _, radius = extra.forward_with_extra_capacity(model, *args)
        self.assertTrue(torch.equal(radius, (args[1]-64).clamp_min(0)))


if __name__ == '__main__':
    unittest.main()
