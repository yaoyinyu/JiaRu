"""整圈上下文的初态保真、梯度与干预有效性。"""
import copy
import importlib.util
from pathlib import Path
import unittest

import torch

TOOLS = Path(__file__).resolve().parents[1] / 'model/training'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capacity = load('visual-neighborhood-capacity-residual')
context = load('visual-neighborhood-global-context')


class GlobalContextTest(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        torch.manual_seed(20261120)
        model = torch.nn.Module()
        model.project = torch.nn.Conv1d(39, 32, 1)
        model.convs = torch.nn.ModuleList(torch.nn.Conv1d(32, 32, 3, dilation=d) for d in (1, 2, 4, 8))
        model.norms = torch.nn.ModuleList(torch.nn.GroupNorm(4, 32) for _ in model.convs)
        model.head = torch.nn.Conv1d(32, 1, 1)
        model.angle_context = capacity.LocalCapacityResidual()
        torch.nn.init.normal_(model.angle_context.output.weight, std=.01)
        self.control = model
        self.expanded = copy.deepcopy(model)
        context.install(self.expanded)
        self.cache = dict(features=torch.randn(1, 39, 2048), initial=torch.full((1, 2048), 20.125), presence=torch.tensor([[1.25]]))
        self.args = (torch.full((1, 2048), 20.), (torch.arange(1024) % 2048).reshape(1, 32, 32),
                     torch.linspace(0, 30, 1024).reshape(1, 32, 32))

    def test_nonzero_original_heads_remain_byte_exact(self):
        before = capacity.forward_with_capacity(self.control, self.cache, *self.args)
        after = context.forward(self.expanded, self.cache, *self.args)
        for a, b in zip(before, after, strict=True):
            self.assertEqual(a.detach().numpy().tobytes(), b.detach().numpy().tobytes())
        for name, value in self.control.state_dict().items():
            self.assertTrue(torch.equal(value, self.expanded.state_dict()[name]))

    def test_initial_gradients_reach_zero_output_but_encoder_is_zero(self):
        context.forward(self.expanded, self.cache, *self.args)[2].square().mean().backward()
        params = list(self.expanded.parameters())
        self.assertEqual(len(params), 44)
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in params))
        self.assertGreater(torch.count_nonzero(self.expanded.global_context.output.weight.grad).item(), 0)
        self.assertEqual(torch.count_nonzero(self.expanded.global_context.encoder.weight.grad).item(), 0)

    def test_nonzero_context_changes_radius_and_encoder_receives_gradients(self):
        before = context.forward(self.expanded, self.cache, *self.args)
        with torch.no_grad():
            self.expanded.global_context.output.weight.normal_(std=.01)
        after = context.forward(self.expanded, self.cache, *self.args)
        self.assertFalse(torch.equal(before[2], after[2]))
        self.assertTrue(torch.equal(before[1], after[1]))
        after[2].square().mean().backward()
        self.assertGreater(torch.count_nonzero(self.expanded.global_context.encoder.weight.grad).item(), 0)

    def test_global_statistics_use_distant_angular_samples(self):
        with torch.no_grad():
            self.expanded.global_context.output.weight.normal_(std=.01)
        features = self.cache['features']
        altered = features.clone()
        altered[:, :, 1024:] += 1
        self.assertFalse(torch.equal(self.expanded.global_context(features), self.expanded.global_context(altered)))
        with self.assertRaises(ValueError):
            context.install(self.expanded)


if __name__ == '__main__':
    unittest.main()
