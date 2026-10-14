"""双头RAW保真、完整分母及共享梯度分解的合成反例。"""
import importlib.util
import unittest
from pathlib import Path
import numpy as np
import torch

R=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
m=load(R/'model/training/audit-reviewed-stage-b-shared-gradients.py','gradient_tests')
trainer=load(R/'model/training/train-reviewed-stage-b-normal-development.py','gradient_original')
band=load(R/'model/training/normal-stage-b-boundary-loss.py','gradient_band')

class Tests(unittest.TestCase):
    def heads(self):return np.ones((3,4),np.float32),np.array(0.,np.float32)

    def test_heads_exact_accepts_finite_scalar_presence(self):
        a,b=self.heads();self.assertTrue(m.heads_exact(a,b,a.copy(),b.copy())['allHeadBytesExactlySaved'])

    def test_heads_rejects_presence_nan_even_when_mask_finite(self):
        a,b=self.heads();b[...]=np.nan
        with self.assertRaisesRegex(ValueError,'finite'):m.heads_exact(a,b,a.copy(),b.copy())

    def test_heads_rejects_mask_nan_even_when_presence_finite(self):
        a,b=self.heads();a[0,0]=np.nan
        with self.assertRaisesRegex(ValueError,'finite'):m.heads_exact(a,b,a.copy(),b.copy())

    def test_heads_rejects_signed_zero_byte_change(self):
        a,b=self.heads()
        with self.assertRaisesRegex(ValueError,'bitwise'):m.heads_exact(a,b,a.copy(),np.array(-0.,np.float32))

    def test_heads_rejects_shape_and_storage_changes(self):
        a,b=self.heads()
        for other in (a.astype(np.float64),a.reshape(4,3)):
            with self.assertRaisesRegex(ValueError,'storage'):m.heads_exact(a,b,other,b.copy())

    def test_pair_aligned_and_opposed(self):
        a=np.array([3.,4.]);self.assertAlmostEqual(m.pair(a,2*a)['cosine'],1)
        self.assertTrue(m.pair(a,-2*a)['opposed']);self.assertLess(m.pair(a,-2*a)['combinedGradientDotAgainstMask'],0)

    def test_zero_gradient_has_no_invented_cosine_or_ratio(self):
        result=m.pair(np.zeros(2),np.ones(2));self.assertIsNone(result['cosine']);self.assertIsNone(result['presenceNormToMaskNorm'])

    def matrices(self):
        mask=np.array([[2.,0.],[0.,2.],[0.,0.]],np.float32);presence=np.array([[-1.,0.],[0.,1.],[3.,3.]],np.float32)
        records=[{'candidateIdentity':{'ordinal':i},'positive':i<2,'sourceGroup':'a' if i==0 else 'b'} for i in range(3)]
        return mask,presence,mask+presence,records

    def test_full_cohort_includes_reject_in_denominator(self):
        a,b,c,rows=self.matrices();stats=m.summarize(a,b,c,rows)
        self.assertEqual(stats['candidateInputs'],3);self.assertEqual(stats['positiveInputs'],2);self.assertEqual(stats['rejectInputs'],1)
        self.assertAlmostEqual(stats['cohortMean']['maskNorm'],np.sqrt(8)/3)
        self.assertEqual(stats['positiveMaskPresenceOpposedCount'],1);self.assertEqual(len(stats['sourceGroups']),2)

    def test_nonzero_reject_mask_gradient_rejected(self):
        a,b,c,rows=self.matrices();a[-1,0]=1;c=a+b
        with self.assertRaisesRegex(ValueError,'reject mask'):m.summarize(a,b,c,rows)

    def test_mismatched_gradient_sum_rejected(self):
        a,b,c,rows=self.matrices();c[0,0]+=.01
        with self.assertRaisesRegex(ValueError,'reconstruction'):m.summarize(a,b,c,rows)

    def test_loss_decomposition_preserves_original_shared_gradients(self):
        torch.set_num_threads(2)
        w=torch.tensor([.2,-.3],requires_grad=True);x=torch.arange(192,dtype=torch.float32).reshape(1,1,12,16)/192
        logits=w[0]*x+w[1];presence=(w[0]-2*w[1]).reshape(1,1)
        truth=(x>.5).float();counts={'candidateInputs':74,'positiveInputs':71,'rejectInputs':3}
        mask,p=m.losses(logits,presence,truth,True,counts,band)
        original=trainer.objective(logits,presence,truth,True,counts,band)
        gm=torch.autograd.grad(mask,w,retain_graph=True)[0];gp=torch.autograd.grad(p,w,retain_graph=True)[0]
        gt=torch.autograd.grad(original,w)[0]
        self.assertTrue(torch.allclose(gm+gp,gt,rtol=1e-5,atol=1e-6))

    def test_reject_has_no_rgb_empty_target_pixel_loss(self):
        logits=torch.ones((1,1,12,16),requires_grad=True);presence=torch.ones((1,1),requires_grad=True)
        mask,p=m.losses(logits,presence,torch.zeros_like(logits),False,{'candidateInputs':74,'positiveInputs':71,'rejectInputs':3},band)
        self.assertIsNone(mask);p.backward();self.assertIsNone(logits.grad);self.assertTrue(torch.isfinite(presence.grad).all())

if __name__=='__main__':unittest.main()
