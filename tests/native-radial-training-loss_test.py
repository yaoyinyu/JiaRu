import importlib.util
from pathlib import Path
import unittest
import torch

spec = importlib.util.spec_from_file_location('radial_loss', Path(__file__).resolve().parents[1] / 'model/training/native-radial-training-loss.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class RadialLossTest(unittest.TestCase):
    def test_full_objective_native_gather_gradient_matches_finite_difference(self):
        radius = torch.tensor([[3., 4., 5.]], dtype=torch.float64, requires_grad=True)
        presence = torch.tensor([[1.]], dtype=torch.float64, requires_grad=True)
        bins = torch.tensor([[0, 1, 2, 0, 1, 2]])
        distance = torch.tensor([[2., 3., 4., 5., 6., 7.]], dtype=torch.float64)
        truth = torch.tensor([[[[1., 1., 1., 0., 0., 0.]]]], dtype=torch.float64)
        target = torch.tensor([[3.4, 4.3, 5.2]], dtype=torch.float64)
        def f(r, p):
            return m.objective((r.gather(1, bins)-distance).reshape_as(truth), p, r, truth, target)
        self.assertTrue(torch.autograd.gradcheck(f, (radius, presence)))

    def test_auxiliary_moves_toward_truth_both_directions(self):
        r = torch.tensor([[2., 7.]], requires_grad=True)
        target = torch.tensor([[4., 5.]])
        loss = torch.nn.functional.smooth_l1_loss(r/8, target/8, beta=.125)
        loss.backward()
        self.assertLess(r.grad[0,0], 0); self.assertGreater(r.grad[0,1], 0)


if __name__ == '__main__': unittest.main()
