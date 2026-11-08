"""原2px内边界几何与损失梯度的机制控制。"""
from pathlib import Path
import importlib.util
import unittest
import cv2
import numpy as np
import torch

spec=importlib.util.spec_from_file_location('boundary_iou_loss',Path(__file__).resolve().parents[1]/'model/training/native-boundary-iou-loss.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class NativeBoundaryIoULossTests(unittest.TestCase):
    def test_hard_band_matches_authoritative_geometry_including_frame_edges(self):
        shapes=[]
        for x0 in (0,7):
            a=np.zeros((43,61),np.uint8);a[3:35,x0:42]=1;a[10:15,15:19]=0;shapes.append(a)
        shapes.append(np.ones((43,61),np.uint8))
        for a in shapes:
            edge=a & (1-cv2.erode(a,np.ones((3,3),np.uint8)))
            expected=a & cv2.dilate(edge,np.ones((5,5),np.uint8))
            actual=m.inner_boundary_band(torch.from_numpy(a.astype(np.float32))[None,None])[0,0].numpy()
            np.testing.assert_array_equal(actual,expected)

    def test_boundary_gradient_corrects_both_inward_and_outward_radius(self):
        y,x=torch.meshgrid(torch.arange(65),torch.arange(65),indexing='ij');distance=((x-32)**2+(y-32)**2).float().sqrt()
        truth=(distance<=19).float()[None,None]
        for radius in (17.,21.):
            r=torch.tensor(radius,requires_grad=True)
            value=m.soft_boundary_iou((r-distance)[None,None],truth);value.backward()
            self.assertTrue(torch.isfinite(value));self.assertGreater(float(r.grad)*(radius-19),0)
            improved=m.soft_boundary_iou((r.detach()-.2*r.grad.sign()-distance)[None,None],truth)
            self.assertLess(float(improved),float(value.detach()))

    def test_empty_target_rejected(self):
        with self.assertRaisesRegex(ValueError,'positive full target'):
            m.soft_boundary_iou(torch.zeros(1,1,16,16),torch.zeros(1,1,16,16))


if __name__=='__main__':unittest.main()
