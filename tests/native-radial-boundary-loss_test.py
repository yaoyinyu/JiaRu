import importlib.util
from pathlib import Path
import unittest
import torch

spec = importlib.util.spec_from_file_location('tested_radial_boundary', Path(__file__).resolve().parents[1] / 'model/training/native-radial-boundary-loss.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RadialBoundaryLossTest(unittest.TestCase):
    def test_added_gradient_is_local_and_preserves_base_everywhere_else(self):
        mask = torch.linspace(-2, 2, 25).reshape(1,1,5,5).requires_grad_(True)
        truth = (torch.arange(25).reshape(1,1,5,5) % 3 == 0).float()
        band = torch.zeros_like(truth)
        band[:,:,1:4,1:4] = 1
        r = torch.ones(1,16)
        p = torch.ones(1,1)
        base = m._base.objective(mask,p,r,truth,r)
        bg = torch.autograd.grad(base,mask,retain_graph=True)[0]
        actual = torch.autograd.grad(m.objective(mask,p,r,truth,r,band),mask)[0]
        expected = 2*band*(mask.detach().sigmoid()-truth)/band.sum()
        torch.testing.assert_close(actual-bg,expected)
        self.assertTrue(torch.equal(actual[band==0],bg[band==0]))

    def test_crop_keeps_edges_from_outside_roi_and_reports_complete_count(self):
        full = torch.zeros(1,1,32,32)
        full[:,:,8:25,8:25] = 1
        crop = (12,12,20,20)
        band,total = m.boundary_band_for_crop(full,crop)
        canonical = m._band.boundary_band(full)
        self.assertTrue(torch.equal(band,canonical[:,:,12:20,12:20]))
        self.assertEqual(total,float(canonical.sum()))
        self.assertGreater(float(band.sum()),0)
        self.assertFalse(torch.equal(band,m._band.boundary_band(full[:,:,12:20,12:20])))

    def test_rejects_missing_or_unaligned_boundary_supervision(self):
        mask = torch.zeros(1,1,4,4)
        p = torch.ones(1,1)
        r = torch.ones(1,16)
        with self.assertRaises(ValueError):m.objective(mask,p,r,mask,r,torch.zeros_like(mask))
        with self.assertRaises(ValueError):m.objective(mask,p,r,mask,r,torch.ones(1,1,3,4))


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()
