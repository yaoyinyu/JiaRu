"""原图距离单位、完整目标及两侧边界梯度的训练合同测试。"""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import cv2
import torch

P=Path(__file__).resolve().parents[1]/'model/training/normal-stage-b-distance-loss.py'
s=importlib.util.spec_from_file_location('distance_loss_test',P);loss=importlib.util.module_from_spec(s);s.loader.exec_module(loss)


class DistanceLossTests(unittest.TestCase):
    def setUp(self):
        cv2.setNumThreads(1);torch.set_num_threads(2)
        self.truth=np.zeros((40,48),bool);self.truth[10:30,12:36]=True

    def test_sign_zero_level_and_source_pixel_units(self):
        target,band=loss.build_distance_target(self.truth,[0,0,48,40])
        self.assertTrue(np.array_equal(target>0,self.truth))
        self.assertEqual(float(target[10,24]),.5)
        self.assertEqual(float(target[9,24]),-.5)
        self.assertEqual(float(target[12,24]),1.5)
        self.assertTrue(band[6,24]);self.assertFalse(band[5,24])

    def test_crop_is_full_source_distance_without_resize(self):
        full,b=loss.build_distance_target(self.truth,[0,0,48,40])
        crop,c=loss.build_distance_target(self.truth,[7,5,41,35])
        self.assertTrue(np.array_equal(crop,full[5:35,7:41]))
        self.assertTrue(np.array_equal(c,b[5:35,7:41]))

    def test_wrong_inside_and_outside_pixels_have_correct_gradient(self):
        target,band=loss.build_distance_target(self.truth,[0,0,48,40])
        wrong=torch.from_numpy(np.where(self.truth,-4.,4.).astype(np.float32)).requires_grad_(True)
        value=loss.distance_band_loss(wrong,torch.from_numpy(target),torch.from_numpy(band));value.backward()
        self.assertTrue(torch.isfinite(value));g=wrong.grad.numpy()
        self.assertTrue((g[band&self.truth]<0).all());self.assertTrue((g[band&~self.truth]>0).all())
        self.assertTrue((g[~band]==0).all())

    def test_exact_distance_target_has_zero_auxiliary_loss(self):
        target,band=loss.build_distance_target(self.truth,[0,0,48,40]);t=torch.from_numpy(target)
        self.assertEqual(float(loss.distance_band_loss(t,t,torch.from_numpy(band))),0.)

    def test_truncated_or_invalid_truth_is_rejected(self):
        for box in [[13,0,48,40],[-1,0,48,40],[0,0,49,40],[0.,0,48,40]]:
            with self.assertRaises(ValueError):loss.build_distance_target(self.truth,box)
        with self.assertRaises(ValueError):loss.build_distance_target(np.zeros((20,20),bool),[0,0,20,20])

    def test_reject_uses_presence_without_decoder_distance_gradient(self):
        class Base:
            @staticmethod
            def objective(logits,presence,truth,positive,counts,boundary):return presence.square().mean()
        mask=torch.randn(1,1,20,20,requires_grad=True);presence=torch.ones(1,1,requires_grad=True)
        value=loss.objective(mask,presence,torch.zeros_like(mask),False,{},Base,None)
        value.backward();self.assertIsNone(mask.grad);self.assertIsNotNone(presence.grad)


if __name__=='__main__':unittest.main()
