import importlib.util
from pathlib import Path
import unittest
import torch

spec = importlib.util.spec_from_file_location('capacity_test', Path(__file__).resolve().parents[1] / 'model/training/visual-neighborhood-capacity-residual.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class CapacityContracts(unittest.TestCase):
    def test_zero_initialization_preserves_output_and_allows_learning(self):
        torch.manual_seed(19)
        model = capacity.LocalCapacityResidual()
        features = torch.randn(1, 39, 128)
        output = model(features)
        self.assertTrue(torch.equal(output, torch.zeros_like(output)))
        (output - 1).square().mean().backward()
        self.assertGreater(float(model.output.weight.grad.abs().sum()), 0)
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))

    def test_learned_branch_has_no_angular_seam(self):
        torch.manual_seed(23)
        model = capacity.LocalCapacityResidual().eval()
        torch.nn.init.normal_(model.output.weight, std=.1)
        features = torch.randn(1, 39, 128)
        with torch.no_grad():
            original = model(features)
            rotated = model(torch.roll(features, 17, -1))
        torch.testing.assert_close(rotated, torch.roll(original, 17, -1), atol=2e-6, rtol=2e-6)


if __name__ == '__main__':
    torch.set_num_threads(2)
    unittest.main()
