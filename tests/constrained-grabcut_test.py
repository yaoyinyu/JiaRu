"""纯合成控制：图像驱动纠偏、带外锁定、拒识、种子不足及错误域。"""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

s = importlib.util.spec_from_file_location('constrained_grabcut', Path(__file__).resolve().parents[1] / 'model/training/refine-mask-with-grabcut.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class ConstrainedGrabCutTests(unittest.TestCase):
    def fixture(self):
        rgb = np.full((83, 111, 3), [35, 70, 45], np.uint8)
        truth = np.zeros((83, 111), bool); truth[22:63, 30:80] = True
        rgb[truth] = [210, 110, 160]
        base = np.zeros_like(truth); base[19:59, 34:84] = True
        return rgb, truth, base

    def test_image_colors_restore_over_and_under_selection(self):
        rgb, truth, base = self.fixture()
        actual, status = m.refine(rgb, base, presence_accepted=True)
        self.assertEqual(status, 'refined')
        self.assertTrue(np.array_equal(actual, truth))
        second, _ = m.refine(rgb, base, presence_accepted=True)
        self.assertTrue(np.array_equal(actual, second))
        self.assertFalse(np.array_equal(base, truth))

    def test_strong_internal_and_external_edges_cannot_cross_band(self):
        rgb, truth, base = self.fixture()
        inner, outer = m.constraints(base)
        rgb[25:48, 48:62] = [0, 0, 0]
        rgb[~outer] = [210, 110, 160]
        actual, status = m.refine(rgb, base, presence_accepted=True)
        self.assertEqual(status, 'refined')
        self.assertTrue(actual[inner].all())
        self.assertFalse(actual[~outer].any())
        self.assertTrue(np.array_equal(actual[~(outer & ~inner)], base[~(outer & ~inner)]))

    def test_reject_empty_and_missing_seeds_are_distinct(self):
        rgb, _, base = self.fixture()
        actual, status = m.refine(rgb, base, presence_accepted=False)
        self.assertEqual(status, 'rejected'); self.assertFalse(actual.any())
        actual, status = m.refine(rgb, np.zeros_like(base), presence_accepted=True)
        self.assertEqual(status, 'empty'); self.assertFalse(actual.any())
        base[:] = False; base[30:32, 40:42] = True
        actual, status = m.refine(rgb, base, presence_accepted=True)
        self.assertEqual(status, 'abstained_missing_hard_seeds')
        self.assertTrue(np.array_equal(actual, base))

    def test_invalid_domains_fail_instead_of_counting_as_rejection(self):
        rgb, _, base = self.fixture()
        for image, mask, options in [(rgb.astype(float), base, {}), (rgb, base.astype(np.uint8), {}),
                                     (rgb, base, {'radius': 0}), (rgb, base, {'iterations': 0}),
                                     (rgb[:-1], base, {})]:
            with self.assertRaises(ValueError):
                m.refine(image, mask, presence_accepted=True, **options)


if __name__ == '__main__':
    unittest.main()
