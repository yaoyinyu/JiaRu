import importlib.util
from pathlib import Path
import unittest
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('context_fixture',R/'model/training/saved-roi-context-policy.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ContextTests(unittest.TestCase):
    def test_old_policy_identical_including_edge_clamp(self):
        for box in [(1,1,20,35),(40,40,60,60),(80,60,99,90)]:
            self.assertEqual(m.crop_box(box,100,100,'square_context_035'),m.legacy.crop_box(box,100,100,'square_context_035'))
    def test_fixed_new_context_expands_same_center_without_truth_input(self):
        old=m.crop_box((40,40,60,60),100,100,'square_context_035')
        new=m.crop_box((40,40,60,60),100,100,'square_context_045')
        self.assertEqual(old,(33,33,67,67));self.assertEqual(new,(31,31,69,69))
    def test_full_truth_is_retained_not_cropped_to_new_denominator(self):
        t=np.zeros((1,100,100),bool);t[0,35:65,35:69]=True
        _,old=m.coverage_matrix(t,np.array([[40,40,60,60]]),'square_context_035')
        _,new=m.coverage_matrix(t,np.array([[40,40,60,60]]),'square_context_045')
        self.assertLess(old[0,0],1);self.assertEqual(new[0,0],1)
    def test_oversized_box_is_not_silently_changed_to_whole_image(self):
        self.assertIsNone(m.crop_box((0,0,100,100),100,100,'square_context_045'))
    def test_invalid_box_and_unknown_policy_rejected(self):
        for box in [(1,1,1,2),(0,0,float('nan'),4)]:
            with self.assertRaises(ValueError):m.crop_box(box,100,100,'square_context_045')
        with self.assertRaises(ValueError):m.crop_box((1,1,2,2),100,100,'scan_context')
if __name__=='__main__':unittest.main()
