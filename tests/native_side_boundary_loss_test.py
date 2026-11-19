"""侧缘监督的旋转、梯度方向与输入保护。"""
import importlib.util
from pathlib import Path
import unittest

import torch

spec = importlib.util.spec_from_file_location(
    'side_loss_test', Path(__file__).resolve().parents[1] / 'model/training/native-side-boundary-loss.py')
loss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loss)


class SideBoundaryLossTest(unittest.TestCase):
    def setUp(self):
        self.truth = torch.zeros(1, 1, 80, 80)
        self.truth[:, :, 10:70, 30:50] = 1
        self.band = loss.previous.previous._previous._band.boundary_band(self.truth)

    def test_rotating_the_same_nail_preserves_loss_and_weights(self):
        logits = (torch.roll(self.truth, 2, -1) * 2 - 1) * 3
        reference = loss.side_boundary_penalty(logits, self.truth, self.band)
        for turns in (1, 2, 3):
            rotate = lambda x: torch.rot90(x, turns, (-2, -1))
            actual = loss.side_boundary_penalty(rotate(logits), rotate(self.truth), rotate(self.band))
            torch.testing.assert_close(actual, reference, rtol=1e-6, atol=1e-6)
            torch.testing.assert_close(loss.side_weights(rotate(self.truth)), rotate(loss.side_weights(self.truth)))

    def test_gradient_corrects_spilled_skin_and_missing_nail(self):
        logits = ((torch.roll(self.truth, 2, -1) * 2 - 1) * 3).requires_grad_()
        value = loss.side_boundary_penalty(logits, self.truth, self.band)
        gradient, = torch.autograd.grad(value, logits)
        self.assertGreater(float(gradient[0, 0, 40, 50]), 0)
        self.assertLess(float(gradient[0, 0, 40, 30]), 0)
        self.assertEqual(float(gradient[0, 0, 0, 0]), 0)
        after = loss.side_boundary_penalty(logits - gradient * 100, self.truth, self.band)
        self.assertLess(float(after.detach()), float(value.detach()))

    def test_invalid_or_missing_truth_band_is_rejected(self):
        with self.assertRaises(ValueError):
            loss.side_boundary_penalty(self.truth, self.truth, torch.zeros_like(self.truth))
        corrupt = self.truth.clone()
        corrupt[0, 0, 20, 40] = float('nan')
        with self.assertRaises(ValueError):
            loss.side_weights(corrupt)


if __name__ == '__main__':
    unittest.main()
