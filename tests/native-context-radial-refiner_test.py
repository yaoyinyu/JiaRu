"""周期接缝、全域内容和零残差初始化的独立控制。"""
import importlib.util
from pathlib import Path
import unittest
import torch

spec = importlib.util.spec_from_file_location('context_test', Path(__file__).resolve().parents[1] /
                                             'model/training/native-context-radial-refiner.py')
net = importlib.util.module_from_spec(spec)
spec.loader.exec_module(net)
torch.set_num_threads(2)


class ContextTests(unittest.TestCase):
    def args(self):
        torch.manual_seed(27)
        strip = torch.randn(1, 5, 32, 129)
        radius = torch.full((1, 32), 20.)
        bins = torch.arange(9 * 11).remainder(32).reshape(1, 9, 11)
        distance = torch.linspace(0, 40, 99).reshape(1, 9, 11)
        return strip, radius, bins, distance

    def test_periodic_pixel_centers(self):
        value = torch.arange(4, dtype=torch.float32).reshape(1, 1, 4, 1)
        result = net.periodic_resize(value, (8, 1)).reshape(-1)
        self.assertTrue(torch.equal(result, torch.tensor([.75, .25, .75, 1.25, 1.75, 2.25, 2.75, 2.25])))

    def test_nonzero_local_exact_and_finite_gradients(self):
        model = net.NativeContextRadialRefiner()
        with torch.no_grad():
            model.local.score.weight.normal_(0, .03)
            model.local.presence.weight.normal_(0, .03)
        args = self.args()
        expected = model.local.forward_with_radius(*args)
        actual = model.forward_with_radius(*args)
        for left, right in zip(expected, actual, strict=True):
            self.assertTrue(torch.equal(left, right))
        (actual[0].square().mean() + actual[1].square().mean()).backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))
        self.assertGreater(int(torch.count_nonzero(model.context_score.weight.grad)), 0)
        self.assertGreater(int(torch.count_nonzero(model.context_presence.weight.grad)), 0)

    def test_global_content_remote_dependency(self):
        torch.manual_seed(14)
        attention = net.GlobalContentAttention(8, 2)
        value = torch.randn(1, 8, 4, 3, requires_grad=True)
        attention(value)[0, 0, 0, 0].backward()
        self.assertGreater(float(value.grad[0, :, -1, -1].abs().sum()), 0.)

    def test_nonzero_context_changes_both_heads(self):
        model = net.NativeContextRadialRefiner()
        args = self.args()
        expected = model(*args)
        with torch.no_grad():
            model.context_score.weight.normal_(0, .1)
            model.context_presence.weight.fill_(.1)
            model.context_presence.bias.fill_(.2)
        actual = model(*args)
        for left, right in zip(expected, actual, strict=True):
            self.assertTrue(torch.isfinite(right).all())
            self.assertFalse(torch.equal(left, right))


if __name__ == '__main__':
    unittest.main()
