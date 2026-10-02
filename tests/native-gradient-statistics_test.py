import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('native_gradient_statistics_fixture',Path(__file__).resolve().parents[1]/'model/training/native-gradient-statistics.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class GradientStatisticsTests(unittest.TestCase):
    def test_opposed_vectors_and_zero_empty_not_in_denominator(self):
        result=m.summarize(np.array([[2.,0.],[-1.,0.],[0.,0.]],np.float32),['a','b','empty'],[True,True,False])
        self.assertEqual(result['positiveCount'],2)
        self.assertEqual(result['pairCount'],1)
        self.assertEqual(result['negativePairCount'],1)
        self.assertEqual(result['pairCosineMedian'],-1.)
        self.assertEqual(result['opposedToPositiveMeanIds'],['b'])
        self.assertEqual(result['positiveMeanGradientNorm'],.5)

    def test_aligned_vectors_and_order_are_preserved(self):
        result=m.summarize(np.array([[1.,0.],[3.,0.]],np.float32),['first','second'],[True,True])
        self.assertEqual(result['positiveIds'],['first','second'])
        self.assertEqual(result['negativePairCount'],0)
        self.assertEqual(result['meanGradientNormToMeanIndividualNorm'],1.)
        self.assertEqual(result['pairwiseCosines'],[[1.,1.],[1.,1.]])

    def test_invalid_identity_nonfinite_zero_positive_or_nonzero_empty_rejected(self):
        for values,ids,flags in [
            ([[1.,0.],[0.,0.]],['same','same'],[True,False]),
            ([[float('nan'),0.]],['bad'],[True]),
            ([[0.,0.]],['bad'],[True]),
            ([[1.,0.],[0.,1.]],['positive','empty'],[True,False]),
        ]:
            with self.assertRaises(ValueError):
                m.summarize(np.array(values,np.float32),ids,flags)


if __name__=='__main__':
    unittest.main()
