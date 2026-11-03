import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('radial',Path(__file__).resolve().parents[1]/'model/training/native-radial-contour.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class RadialContourTest(unittest.TestCase):
    def test_rectangle_intersection(self):
        radius,count=m.ray_intersections([[(2,2),(8,2),(8,8),(2,8)]],(5,5),16)
        np.testing.assert_allclose(radius[::4],[3,3,3,3],atol=1e-12)
        self.assertTrue(np.all(count==1))

    def test_translation_preserves_radii(self):
        p=np.array([[2,2],[9,2],[9,7],[2,7]],float);v=np.array([31.,19.])
        a,_=m.ray_intersections([p],(5.,4.));b,_=m.ray_intersections([p+v],np.array([5.,4.])+v)
        np.testing.assert_array_equal(a,b)

    def test_disjoint_components_report_multiple_crossings(self):
        r,c=m.ray_intersections([[(1,1),(5,1),(5,5),(1,5)],[(7,2),(9,2),(9,4),(7,4)]],(3,3),16)
        self.assertEqual(c[0],3);self.assertEqual(r[0],6)

    def test_native_mask_and_invalid_radius(self):
        mask=m.rasterize((10,10),np.full(64,5.,np.float64),(24,24))
        self.assertEqual(mask.shape,(24,24));self.assertTrue(mask[10,10]);self.assertFalse(mask[0,0])
        with self.assertRaises(ValueError):m.vertices((10,10),np.full(64,-1.))


if __name__=='__main__':unittest.main()
