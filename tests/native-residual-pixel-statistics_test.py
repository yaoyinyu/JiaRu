import importlib.util
from pathlib import Path
import unittest
import numpy as np
spec=importlib.util.spec_from_file_location('residual_pixel_fixture',Path(__file__).resolve().parents[1]/'model/training/native-residual-pixel-statistics.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PixelStatisticsTests(unittest.TestCase):
    def test_native_threshold_and_separate_error_directions(self):
        base=np.array([[.9,.1,.5,.5]],np.float32)
        probability=np.array([[.95,.05,.5,.5]],np.float32)
        truth=np.array([[False,True,False,True]])
        band=np.array([[True,True,False,False]])
        result=m.summarize(base,probability,truth,band)
        self.assertEqual(result['falsePositiveInsideBand'],1)
        self.assertEqual(result['falseNegativeInsideBand'],1)
        self.assertEqual(result['falsePositiveOutsideBand'],1)
        self.assertEqual(result['falseNegativeOutsideBand'],0)
        self.assertEqual(result['wrongHighConfidenceFalsePositiveInsideBand'],1)
        self.assertEqual(result['wrongHighConfidenceFalseNegativeInsideBand'],1)

    def test_transitions_conserve_both_error_denominators(self):
        base=np.array([[.1,.9,.9,.1]],np.float32)
        after=np.array([[.9,.1,.9,.1]],np.float32)
        truth=np.ones((1,4),bool)
        result=m.summarize(base,after,truth,np.ones((1,4),bool))
        self.assertEqual([result[k] for k in ('correctedPixels','introducedPixels','persistentWrongPixels','unchangedCorrectPixels')],[1,1,1,1])
        self.assertEqual(result['oldWrongPixels'],2)
        self.assertEqual(result['currentWrongPixels'],2)

    def test_empty_target_preserves_nonempty_rgb_candidate_semantics(self):
        probability=np.zeros((2,3),np.float32)
        result=m.summarize(probability,probability,np.zeros((2,3),bool),np.zeros((2,3),bool))
        self.assertEqual(result['currentWrongPixels'],0)
        self.assertEqual(result['unchangedCorrectPixels'],6)

    def test_invalid_domain_or_probability_is_rejected(self):
        p=np.zeros((2,2),np.float32);truth=np.zeros((2,2),bool)
        for bad in (p.astype(np.float64),np.full_like(p,np.nan),np.full_like(p,1.1),p[:1]):
            with self.assertRaises(ValueError):m.summarize(p,bad,truth,truth)


if __name__=='__main__':unittest.main()
