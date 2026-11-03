import importlib.util
from pathlib import Path
import unittest
import numpy as np
spec=importlib.util.spec_from_file_location('pixel_radial',Path(__file__).resolve().parents[1]/'model/training/native-pixel-radial-field.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PixelRadialFieldTest(unittest.TestCase):
    def test_round_trip_disk_at_original_pixel_centers(self):
        bins,distance=m.lattice((47,51),(25.,23.))
        truth=distance<=np.float32(13.)
        radius=m.fit_radius(truth,bins,distance)
        np.testing.assert_array_equal(m.logits(radius,bins,distance)>=0,truth)

    def test_domains_and_shape_are_preserved(self):
        bins,distance=m.lattice((33,29),(14.2,16.4),64)
        self.assertEqual(bins.dtype,np.int32);self.assertEqual(distance.dtype,np.float32)
        self.assertTrue(np.all((bins>=0)&(bins<64)))
        radius=m.fit_radius(distance<6,bins,distance,64)
        self.assertEqual(radius.dtype,np.float32);self.assertEqual(m.logits(radius,bins,distance).shape,(33,29))

    def test_non_star_hole_remains_visible_as_representation_error(self):
        bins,distance=m.lattice((41,41),(20.,20.))
        truth=(distance<12)&(distance>5);radius=m.fit_radius(truth,bins,distance)
        prediction=m.logits(radius,bins,distance)>=0
        self.assertTrue(prediction[20,20]);self.assertFalse(truth[20,20])
        self.assertGreater(int((prediction!=truth).sum()),0)

    def test_empty_mask_rejected(self):
        bins,distance=m.lattice((10,10),(5.,5.))
        with self.assertRaises(ValueError):m.fit_radius(np.zeros((10,10),bool),bins,distance)


if __name__=='__main__':unittest.main()
