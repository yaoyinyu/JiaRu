"""零推理归因的存储域、空输出语义、原像素边界与相对诊断限制。"""
import importlib.util
import unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load(R/'model/training/analyze-reviewed-internal-val-outcomes.py','val_outcome_test')
v2=load(R/'model/training/analyze-reviewed-internal-val-outcomes-v2.py','val_outcome_v2_test')
runner=load(R/'model/training/audit-reviewed-internal-val-native.py','val_runner_test')
boundary=load(R/'model/training/analyze-saved-nail-roi-coverage.py','val_boundary_test')
Q={'maskAcceptanceLogit':0.,'presenceAcceptanceLogit':0.,'maskIou':.75,'boundaryIou':.75,'boundaryF1':.9,'boundaryToleranceOriginalPixels':2}

class Tests(unittest.TestCase):
    def test_presence_rejection_never_falls_back_to_raw_mask(self):
        raw,accepted,actual=m.decode_native(np.ones((1,1,4,5),np.float32),np.array([[-1]],np.float32),4,5,Q)
        self.assertTrue(raw.all());self.assertFalse(accepted);self.assertFalse(actual.any())

    def test_storage_dtype_shape_and_both_heads_finite(self):
        good=np.ones((1,1,4,5),np.float32);presence=np.ones((1,1),np.float32)
        for x,p in ((good.astype(np.float64),presence),(good.reshape(1,4,5,1),presence),(good,np.array([[np.nan]],np.float32)),(good,presence.reshape(1))):
            with self.assertRaises(ValueError):m.decode_native(x,p,4,5,Q)

    def test_zero_logit_is_accepted_without_threshold_scan(self):
        raw,accepted,actual=m.decode_native(np.zeros((1,1,4,5),np.float32),np.zeros((1,1),np.float32),4,5,Q)
        self.assertTrue(accepted);self.assertTrue(raw.all());self.assertTrue(np.array_equal(raw,actual))

    def test_native_perfect_boundary_and_overlap(self):
        truth=np.zeros((40,40),bool);truth[10:30,10:30]=True;r=m.metrics(truth,truth,Q,boundary)
        self.assertEqual(r['maskIou'],1.);self.assertEqual(r['boundary']['boundaryF1'],1.);self.assertTrue(r['jointBoundaryPassed']);self.assertEqual(r['boundary']['nativePixelTolerance'],2)

    def test_high_overlap_cannot_replace_original_pixel_boundary(self):
        truth=np.zeros((100,100),bool);truth[20:80,20:80]=True;pred=np.zeros_like(truth);pred[24:84,20:80]=True;r=m.metrics(truth,pred,Q,boundary)
        self.assertTrue(r['iou075Passed']);self.assertFalse(r['jointBoundaryPassed'])

    def test_metrics_refuse_different_pixel_domain(self):
        truth=np.ones((4,5),bool)
        with self.assertRaises(ValueError):m.metrics(truth,np.ones((5,4),bool),Q,boundary)
        with self.assertRaises(ValueError):m.metrics(truth,np.ones((4,5),np.uint8),Q,boundary)

    def test_zero_relative_change_has_no_finite_discriminating_n(self):
        r=m.minimum_distinguishable(0,0,50,runner.wilson)
        self.assertEqual(r['sameDenominatorMinimumDistinguishableIncreaseCount'],4);self.assertIsNone(r['minimumSampleSizeAtObservedRatesBinomialPlanningOnly']);self.assertTrue(r['withinBaselineWilson95']);self.assertEqual(r['relativeGateDecision'],'not_registered_no_branch_pass_or_fail')

    def test_nonzero_relative_change_reports_planning_and_full_n(self):
        r=m.minimum_distinguishable(47,43,50,runner.wilson)
        self.assertAlmostEqual(r['observedSignedDifference'],-.08);self.assertGreater(r['minimumSampleSizeAtObservedRatesBinomialPlanningOnly'],0);self.assertTrue(r['withinSourceCorrelationAndUpstreamHistoryPreventFormalInference'])

    def test_impossible_endpoint_difference_is_not_one_success(self):
        low=v2.statistics(0,0,50,m.minimum_distinguishable,runner.wilson);high=v2.statistics(50,50,50,m.minimum_distinguishable,runner.wilson)
        self.assertIsNone(low['sameDenominatorMinimumDistinguishableDecreaseCount']);self.assertTrue(low['decreaseUnreachableWithinCurrentDenominator']);self.assertEqual(low['sameDenominatorMinimumDistinguishableIncreaseCount'],4)
        self.assertIsNone(high['sameDenominatorMinimumDistinguishableIncreaseCount']);self.assertTrue(high['increaseUnreachableWithinCurrentDenominator'])

    def test_v2_statistics_rejects_shrunk_or_fractional_actual_counts(self):
        for values in ((51,43,50),(47,43,0),(47,43.5,50)):
            with self.assertRaises(ValueError):v2.statistics(*values,m.minimum_distinguishable,runner.wilson)

if __name__=='__main__':unittest.main()
