import importlib.util
from pathlib import Path
import unittest

import torch

spec = importlib.util.spec_from_file_location('hard_boundary_test', Path(__file__).resolve().parents[1] / 'model/training/normal-stage-b-hard-boundary-loss.py')
loss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loss)


class HardBoundaryLossTest(unittest.TestCase):
    def setUp(self):
        self.truth = torch.zeros((1, 1, 24, 24))
        self.truth[:, :, 7:17, 7:17] = 1

    def test_fraction_one_matches_original_loss_and_gradient(self):
        torch.manual_seed(17)
        a = torch.randn_like(self.truth, requires_grad=True)
        b = a.detach().clone().requires_grad_(True)
        new = loss.hard_boundary_bce(a, self.truth, fraction=1)
        old = loss.reference.boundary_band_bce(b, self.truth)
        self.assertTrue(torch.allclose(new, old, atol=1e-7, rtol=1e-7))
        new.backward(); old.backward()
        self.assertTrue(torch.equal(a.grad, b.grad))

    def test_hard_error_receives_more_gradient_without_changing_truth(self):
        original = self.truth.clone()
        a = ((self.truth * 2 - 1) * 5).requires_grad_(True)
        with torch.no_grad(): a[0, 0, 7, 9] = -5
        b = a.detach().clone().requires_grad_(True)
        loss.boundary_band_bce(a, self.truth).backward()
        loss.reference.boundary_band_bce(b, self.truth).backward()
        self.assertLess(float(a.grad[0, 0, 7, 9]), 0)
        self.assertGreater(float(a.grad[0, 0, 7, 9].abs()), 3.9 * float(b.grad[0, 0, 7, 9].abs()))
        self.assertTrue(torch.equal(self.truth, original))

    def test_ties_have_reproducible_gradients(self):
        gradients = []
        for _ in range(2):
            a = torch.zeros_like(self.truth, requires_grad=True)
            loss.boundary_band_bce(a, self.truth).backward()
            gradients.append(a.grad)
        self.assertTrue(torch.equal(*gradients))

    def test_invalid_or_empty_targets_rejected(self):
        for fraction in (0, 1.1, float('nan')):
            with self.assertRaises(ValueError): loss.hard_boundary_bce(self.truth, self.truth, fraction=fraction)
        with self.assertRaises(ValueError): loss.boundary_band_bce(self.truth, torch.zeros_like(self.truth))


if __name__ == '__main__':
    unittest.main()
