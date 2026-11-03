import importlib.util
from pathlib import Path
import unittest
import numpy as np
import torch
spec=importlib.util.spec_from_file_location('radial_strip',Path(__file__).resolve().parents[1]/'model/training/native-radial-strip-refiner.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class RadialStripRefinerTest(unittest.TestCase):
    def test_zero_head_is_exact_original_coordinate_radial_baseline(self):
        torch.manual_seed(19);net=m.NativeRadialStripRefiner()
        strip=torch.randn(1,5,32,129);radius=torch.arange(32,dtype=torch.float32)[None]+3
        bins=torch.arange(400).reshape(1,20,20)%32;distance=torch.arange(400,dtype=torch.float32).reshape(1,20,20)/10
        mask,presence=net(strip,radius,bins,distance)
        expected=radius.gather(1,bins.reshape(1,-1)).reshape_as(distance)-distance
        self.assertTrue(torch.equal(mask[:,0],expected));self.assertTrue(torch.equal(presence,torch.tensor([[2.]])))
        (mask.square().mean()+presence.square().mean()).backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in net.parameters()))

    def test_sampling_uses_source_pixels_and_fixed_position_channel(self):
        rgb=np.full((19,23,3),128,np.uint8);seed=np.zeros((19,23),bool);seed[5:14,7:16]=True
        a=m.build_strip(rgb,seed,(11.,9.),np.full(32,5,np.float32))
        self.assertEqual(a.shape,(5,32,129));self.assertEqual(a.dtype,np.float32)
        np.testing.assert_array_equal(a[4,0],np.arange(-64,65,dtype=np.float32)/64)
        np.testing.assert_allclose(a[:3,0,0],(np.float32(128)/255-np.array([.485,.456,.406]))/np.array([.229,.224,.225]),rtol=1e-5)

    def test_angular_block_is_periodic_equivariant(self):
        torch.manual_seed(7);block=m.AngularConv(5,16).eval();x=torch.randn(1,5,32,129)
        with torch.no_grad():a=block(x);b=block(torch.roll(x,5,2))
        self.assertTrue(torch.allclose(torch.roll(a,5,2),b,rtol=1e-5,atol=1e-5))


if __name__=='__main__':unittest.main()
