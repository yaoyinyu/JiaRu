"""半径平滑正则的恒等性、方向性、循环边界与输入保护。"""

import importlib.util
import math
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'radial_smoothness_test', ROOT / 'model/training/native-radial-smoothness-loss.py')
loss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loss)
torch.manual_seed(7)


def _inputs(bins=2048, side=32):
    coordinates = torch.arange(side, dtype=torch.float32)
    grid_y, grid_x = torch.meshgrid(coordinates, coordinates, indexing='ij')
    truth = (((grid_y - side / 2) ** 2 + (grid_x - side / 2) ** 2) <= 64).float()[None, None]
    angle = torch.arange(bins, dtype=torch.float32) * (2 * math.pi / bins)
    smooth = (70 + 4 * torch.cos(angle) + 2 * torch.sin(2 * angle)).float()
    return dict(
        mask=torch.zeros(1, 1, side, side),
        presence=torch.zeros(()),
        radius=smooth.clone()[None].requires_grad_(True),
        truth=truth,
        target_radius=smooth.clone()[None],
        boundary_band=torch.ones(1, 1, side, side),
    )


def _args(data):
    return (data['mask'], data['presence'], data['radius'], data['truth'], data['target_radius'], data['boundary_band'])


def _configure(target_radius=None, weight=0.0):
    loss.configure(weight)


class ZeroWeightIdentityTest(unittest.TestCase):
    def test_upstream_is_the_closed_side_boundary_loss(self):
        self.assertEqual(Path(loss.previous.__file__).name, 'native-side-boundary-loss.py')

    def test_zero_weight_returns_upstream_objective_bit_exactly(self):
        data = _inputs()
        _configure(data['target_radius'])
        expected = loss.previous.objective(*_args(data))
        actual = loss.objective(*_args(data), smoothness_weight=0.0)
        self.assertEqual(actual.detach().cpu().numpy().tobytes(), expected.detach().cpu().numpy().tobytes())

    def test_default_configured_weight_is_zero(self):
        data = _inputs()
        _configure(data['target_radius'], 0.0)
        self.assertEqual(loss._state['weight'], 0.0)
        expected = loss.previous.objective(*_args(data))
        actual = loss.objective(*_args(data))
        self.assertEqual(actual.detach().cpu().numpy().tobytes(), expected.detach().cpu().numpy().tobytes())

    def test_positive_weight_only_adds_the_penalty(self):
        data = _inputs()
        rough = data['radius'].detach().clone()
        rough[0, 1::2] += 1.5
        data['radius'] = rough.requires_grad_(True)
        _configure(data['target_radius'], 0.0)
        base = loss.previous.objective(*_args(data))
        penalty = loss.radial_smoothness_penalty(data['radius'])
        weighted = loss.objective(*_args(data), smoothness_weight=0.3)
        self.assertGreater(float(penalty.detach()), 1e-3)
        self.assertAlmostEqual(float((weighted - base).detach()), 0.3 * float(penalty.detach()), places=5)
        self.assertGreater(float(weighted.detach()), float(base.detach()))

    def test_smooth_radius_adds_negligible_penalty(self):
        data = _inputs()
        _configure(data['target_radius'], 0.0)
        self.assertLess(float(loss.radial_smoothness_penalty(data['radius']).detach()), 1e-7)


class PenaltyShapeTest(unittest.TestCase):
    def test_constant_radius_has_exactly_zero_penalty(self):
        self.assertEqual(float(loss.radial_smoothness_penalty(torch.full((1, 2048), 70.0))), 0.0)

    def test_smooth_arc_is_almost_free(self):
        angle = torch.arange(2048, dtype=torch.float32) * (2 * math.pi / 2048)
        arc = (70 + 5 * torch.cos(angle) + 3 * torch.sin(2 * angle))[None]
        self.assertLess(float(loss.radial_smoothness_penalty(arc)), 1e-7)

    def test_sawtooth_is_penalized_by_orders_of_magnitude(self):
        angle = torch.arange(2048, dtype=torch.float32) * (2 * math.pi / 2048)
        arc = (70 + 5 * torch.cos(angle))[None]
        sawtooth = arc.clone()
        sawtooth[0, 1::2] += 2.0
        smooth_penalty = float(loss.radial_smoothness_penalty(arc))
        rough_penalty = float(loss.radial_smoothness_penalty(sawtooth))
        self.assertGreater(rough_penalty / max(smooth_penalty, 1e-12), 1e4)

    def test_penalty_is_rotation_invariant_across_the_bin_seam(self):
        angle = torch.arange(2048, dtype=torch.float32) * (2 * math.pi / 2048)
        vector = (70 + 5 * torch.cos(angle) + 0.6 * torch.sin(37 * angle))[None]
        for shift in (1, 17, 1023):
            self.assertAlmostEqual(
                float(loss.radial_smoothness_penalty(vector)),
                float(loss.radial_smoothness_penalty(torch.roll(vector, shift, 1))),
                places=5)

    def test_penalty_scales_quadratically_with_amplitude(self):
        angle = torch.arange(2048, dtype=torch.float32) * (2 * math.pi / 2048)
        vector = (0.7 * torch.sin(41 * angle))[None]
        single = float(loss.radial_smoothness_penalty(vector))
        doubled = float(loss.radial_smoothness_penalty(vector * 2))
        self.assertAlmostEqual(doubled, 4 * single, places=6)


class GradientTest(unittest.TestCase):
    def test_one_step_reduces_bin_to_bin_jitter(self):
        angle = torch.arange(2048, dtype=torch.float32) * (2 * math.pi / 2048)
        base = (70 + 5 * torch.cos(angle)).float()
        jitter = torch.zeros(2048)
        jitter[1::2] = 1.5
        radius = (base + jitter)[None].clone().requires_grad_(True)
        before = float((torch.roll(radius, -1, 1) - radius).detach().std())
        penalty = loss.radial_smoothness_penalty(radius)
        penalty.backward()
        with torch.no_grad():
            radius -= 0.05 * radius.grad
        after = float((torch.roll(radius, -1, 1) - radius).detach().std())
        self.assertLess(after, before)


class InputGuardTest(unittest.TestCase):
    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            loss.radial_smoothness_penalty(torch.zeros(2048))
        with self.assertRaises(ValueError):
            loss.radial_smoothness_penalty(torch.zeros(1, 2))
        with self.assertRaises(ValueError):
            loss.radial_smoothness_penalty(torch.full((1, 2048), float('nan')))
        with self.assertRaises(ValueError):
            loss.radial_smoothness_penalty(torch.zeros(1, 2048), scale=0.0)
        with self.assertRaises(ValueError):
            loss.configure(-1.0)
        with self.assertRaises(ValueError):
            loss.configure(float('nan'))


if __name__ == '__main__':
    unittest.main()
