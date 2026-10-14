"""独立VJP定义与原重建失败隔离；不放宽任何原门。"""
import importlib.util
import unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(name,file):
    sp=importlib.util.spec_from_file_location(name,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
g=load('vjp_old','audit-reviewed-stage-b-shared-gradients.py')
m=load('vjp_new','measure-reviewed-stage-b-branch-vjps.py')
f=load('vjp_forensic','inspect-reviewed-stage-b-gradient-reconstruction.py')
class Tests(unittest.TestCase):
    def fixture(self):
        return np.array([[1.,0.],[0.,1.],[0.,0.]],np.float32),np.array([[-.1,0.],[0.,.1],[.1,.2]],np.float32),[
            {'candidateIdentity':{'i':i},'positive':i<2,'sourceGroup':str(i)} for i in range(3)]
    def test_new_measurement_keeps_old_gate_failed(self):
        a,b,r=self.fixture();s=m.statistics(a,b,r,g)
        self.assertTrue(s['originalTotalGradientReconstructionGateStillFailed']);self.assertEqual(s['positiveMaskPresenceOpposedCount'],1)
    def test_full_denominator_and_reject_contribution(self):
        a,b,r=self.fixture();s=m.statistics(a,b,r,g)
        self.assertEqual(s['candidateInputs'],3);self.assertAlmostEqual(s['cohortMean']['maskNorm'],np.sqrt(2)/3)
        self.assertAlmostEqual(s['rejectPresenceContributionToCohortMask']['presenceNorm'],np.sqrt(.05)/3,places=7)
    def test_nonfinite_component_cannot_give_statistics(self):
        a,b,r=self.fixture();b[0,0]=np.nan
        with self.assertRaisesRegex(ValueError,'finite'):m.statistics(a,b,r,g)
    def test_nonzero_reject_mask_cannot_give_statistics(self):
        a,b,r=self.fixture();a[-1,0]=1
        with self.assertRaisesRegex(ValueError,'reject'):m.statistics(a,b,r,g)
    def test_forensics_does_not_reclassify_failed_numerical_gate(self):
        a=np.array([1.,0.],np.float32);b=np.zeros(2,np.float32);total=a.copy();total[1]=2e-6
        s=f.error_summary(a,b,total);self.assertFalse(s['frozenComponentGatePassed']);self.assertEqual(s['failedCoordinates'],1)
        self.assertFalse(s['causeOrGradientConflictConclusionAllowed']);self.assertTrue(s['originalFailureNotReclassified'])
    def test_zero_mask_vjp_is_reported_without_inventing_nonzero(self):
        a,b,r=self.fixture();a[0]=0;s=m.statistics(a,b,r,g)
        self.assertEqual(s['maskGradientDiversity']['zeroMaskGradientPositives'],1)
        self.assertIsNone(s['perCandidate'][0]['cosine'])
if __name__=='__main__':unittest.main()
