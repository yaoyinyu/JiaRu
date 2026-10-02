import importlib.util
from pathlib import Path
import unittest
import torch

spec=importlib.util.spec_from_file_location('native_pcgrad_fixture',Path(__file__).resolve().parents[1]/'model/training/native-pcgrad.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NativePcgradTests(unittest.TestCase):
    def test_aligned_vectors_preserve_window_mean_and_input(self):
        values=torch.tensor([[1.,0.],[3.,0.],[0.,0.]])
        before=values.clone()
        result,metadata=m.project_mean(values,generator=torch.Generator().manual_seed(1605))
        self.assertTrue(torch.equal(result,values.mean(dim=0)))
        self.assertTrue(torch.equal(values,before))
        self.assertEqual(metadata['projectionCount'],0)
        self.assertEqual(metadata['candidateCount'],3)

    def test_two_opposed_vectors_are_projected(self):
        result,metadata=m.project_mean(torch.tensor([[2.,0.],[-1.,0.]]),generator=torch.Generator().manual_seed(1605))
        self.assertTrue(torch.equal(result,torch.zeros(2)))
        self.assertEqual(metadata['projectionCount'],2)

    def test_zero_gradient_window_stays_finite_with_original_denominator(self):
        result,metadata=m.project_mean(torch.zeros(5,7),generator=torch.Generator().manual_seed(1605))
        self.assertTrue(torch.equal(result,torch.zeros(7)))
        self.assertEqual(metadata['candidateCount'],5)
        self.assertEqual(metadata['emptyGradientCount'],5)

    def test_independent_order_rng_does_not_consume_sampler(self):
        values=torch.tensor([[1.,-2.,0.],[-3.,1.,1.],[0.,2.,-1.]])
        sampler=torch.Generator().manual_seed(1605)
        state=sampler.get_state().clone()
        one,_=m.project_mean(values,generator=torch.Generator().manual_seed(1605))
        two,_=m.project_mean(values,generator=torch.Generator().manual_seed(1605))
        self.assertTrue(torch.equal(one,two))
        self.assertTrue(torch.equal(sampler.get_state(),state))

    def test_invalid_inputs_rejected(self):
        for bad in (torch.ones(3),torch.empty(0,3),torch.ones(2,3,dtype=torch.float64),torch.tensor([[float('nan')]])):
            with self.assertRaises(ValueError):
                m.project_mean(bad,generator=torch.Generator().manual_seed(1605))


if __name__=='__main__':
    unittest.main()
