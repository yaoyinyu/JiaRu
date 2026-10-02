"""原像素带外保真、拒识和零初始回归；仅合成fixture，无真实图推理。"""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import torch
root=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('native_head_fixture',root/'model/training/native-boundary-nail-refinement.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class NativeBoundaryTests(unittest.TestCase):
    def test_outside_band_is_bit_exact_and_zero_delta_preserves_mask(self):
        rng=np.random.default_rng(12);p=(rng.random((32,40))*.1).astype(np.float32);p[8:24,10:30]=.9
        band=m.editable_boundary_band(p)
        zero=m.apply_native_delta(p,np.zeros_like(p),band)
        self.assertTrue(np.array_equal(zero>=.5,p>=.5))
        result=m.apply_native_delta(p,np.full_like(p,20),band)
        self.assertTrue(np.array_equal(result[~band].view(np.uint32),p[~band].view(np.uint32)))
        self.assertTrue((result[band]>=.5).all())

    def test_empty_base_and_errors_remain_distinct(self):
        p=np.full((16,20),.01,np.float32);band=m.editable_boundary_band(p)
        self.assertFalse(band.any())
        self.assertTrue(np.array_equal(m.apply_native_delta(p,np.full_like(p,50),band),p))
        delta=np.zeros_like(p);delta[0,0]=np.nan
        with self.assertRaises(ValueError):m.apply_native_delta(p,delta,band)
        with self.assertRaises(ValueError):m.apply_native_delta(p,np.zeros_like(p),np.ones_like(band))

    def test_head_native_shape_zero_initial_and_packing(self):
        torch.set_num_threads(2);torch.manual_seed(1605)
        p=np.zeros((24,31),np.float32);p[5:20,8:22]=1
        packed,band=m.pack_native_input(np.zeros((24,31,3),np.uint8),np.zeros((24,31),np.uint8),p)
        self.assertEqual(packed.shape,(6,24,31));head=m.NativeBoundaryNailRefiner()
        self.assertEqual(sum(x.numel() for x in head.parameters()),20385)
        delta=head(torch.from_numpy(packed[None]));self.assertEqual(tuple(delta.shape),(1,1,24,31));self.assertEqual(float(delta.detach().abs().max()),0)
        value=m.compose_native_logits(torch.from_numpy(p[None,None]),delta,torch.from_numpy(band[None,None]))
        self.assertTrue(torch.isfinite(value).all());self.assertTrue(np.array_equal(value.detach().sigmoid().numpy()[0,0]>=.5,p>=.5))


if __name__=='__main__':unittest.main()
