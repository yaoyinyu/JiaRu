"""边缘标记匹配控制与坐标存储域的合成像素回归。"""
import importlib.util
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
def module(file, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'model/training' / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
controls = module('build-whole-marker-control-review.py', 'control_fixture')
masks = module('prepare-whole-mask-review.py', 'mask_fixture')

class WholeMarkerControls(unittest.TestCase):
    def setUp(self):
        self.arr = np.arange(24 * 32 * 3, dtype=np.uint16).reshape(24, 32, 3).astype(np.uint8)

    def test_right_bottom_edge_keeps_all_other_pixels(self):
        got = controls.replace_background(self.arr, [28, 20, 32, 24], [20, 20, 24, 24])
        allowed = np.zeros((24, 32), bool)
        allowed[20:24, 28:32] = True
        self.assertTrue(np.array_equal(got[~allowed], self.arr[~allowed]))
        self.assertTrue(np.array_equal(got[20:24, 28:32], self.arr[20:24, 20:24]))

    def test_matched_move_pair_has_same_removal_base(self):
        helper = module('build-matched-native-marker-controls.py', 'move_fixture')
        marker, blank, destination = [28, 20, 32, 24], [20, 20, 24, 24], [28, 12, 32, 16]
        base = controls.replace_background(self.arr, marker, blank)
        marked = helper.relocate(base, self.arr, marker, destination)
        clean = helper.relocate(base, self.arr, blank, destination)
        allowed = np.zeros((24, 32), bool)
        allowed[12:16, 28:32] = True
        self.assertTrue(np.array_equal(marked[~allowed], clean[~allowed]))
        self.assertTrue(np.any(marked[allowed] != clean[allowed]))

    def test_overlapping_donor_rejected(self):
        with self.assertRaises(AssertionError):
            controls.replace_background(self.arr, [20, 20, 24, 24], [21, 20, 25, 24])

    def test_mismatched_size_and_out_of_source_rejected(self):
        for target, donor in [([28, 20, 33, 24], [20, 20, 25, 24]),
                              ([28, 20, 32, 24], [20, 20, 23, 24])]:
            with self.assertRaises(AssertionError):
                controls.replace_background(self.arr, target, donor)

    def test_polygon_storage_forms_render_identically_without_resampling(self):
        raw = Image.fromarray(self.arr)
        points = [[3.5, 2.2], [11.8, 4.0], [7.5, 13.9]]
        a, _ = masks.render(raw, [{'polygon': points}])
        b, _ = masks.render(raw, [{'polygon': [{'x': x, 'y': y} for x, y in points]}])
        self.assertEqual(a.size, raw.size)
        self.assertEqual(a.tobytes(), b.tobytes())

if __name__ == '__main__':
    unittest.main()
