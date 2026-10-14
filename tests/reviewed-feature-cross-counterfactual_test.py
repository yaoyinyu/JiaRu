"""特征2×2交叉按原坐标分解交互项，分清继承与新预算。"""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np

R = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('feature_cross_test', R / 'model/training/analyze-reviewed-feature-cross-counterfactual.py')
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def contract():
    count = 74
    return {'cases': [{'ordinal': i} for i in range(1, count + 1)], 'fullCandidateCount': count,
            'newBranchCandidateCount': 148, 'inheritedBranchCandidateCount': 148, 'fourCellCandidateCount': 296,
            'branches': list(m.BRANCHES), 'analyticalEvaluationsAllowed': {stage: 148 for stage in m.STAGES} | {'total': 1332},
            'singleFinalFloat32Conversions': 148, 'inheritedResizeCount': 148,
            'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
            'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0,
            'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
            'productHold': True, 'formalReleaseAllowed': False, 'fullModelLearnedGatePassed': False}


class FeatureCrossTests(unittest.TestCase):
    def test_nonadditive_four_cell_identity_at_original_failure_coordinate(self):
        cc = np.array([1., 1.], np.float32)
        wc = np.array([3., 11.], np.float32)
        cw = np.array([4., 0.], np.float32)
        ww = np.array([8., 5.], np.float32)
        result = m.interaction(cc, ww, wc, cw, np.zeros(2, np.float32), np.array([9., 2.], np.float32))
        self.assertEqual(result['coordinateOfOriginalActualMax'], [0])
        self.assertEqual(result['signedAtSameCoordinate'], {'originalActualDifference': 9., 'mathematicalTotal': 7., 'deepOnlyEffect': 2., 'skipOnlyEffect': 3., 'interaction': 2.})
        self.assertEqual(result['deepOnlyMaxAbs'], 10.)
        self.assertEqual(result['equationResidualMaxAbs'], 0.)
        self.assertTrue(result['notIndividualOperatorOrSourceCausalityProof'])

    def test_inherited_and_new_budgets_cannot_be_merged_or_reused(self):
        p = contract()
        m.validate_contract(p)
        for key, value in [('fullCandidateCount', 68), ('newBranchCandidateCount', 296), ('inheritedBranchCandidateCount', 0),
                           ('fourCellCandidateCount', 148), ('inheritedResizeCount', 0), ('singleFinalFloat32Conversions', 296),
                           ('analyticalEvaluationsAllowed', {stage: 148 for stage in m.u.STAGES} | {'total': 1480})]:
            bad = copy.deepcopy(p)
            bad[key] = value
            with self.assertRaises(ValueError):
                m.validate_contract(bad)

    def test_nonfinite_shape_and_relaxed_gate_rejected(self):
        x = np.zeros(2, np.float32)
        with self.assertRaises(ValueError):
            m.interaction(x, x, x, x, x, x * np.nan)
        with self.assertRaises(ValueError):
            m.interaction(x, x, x, x, x, x.reshape(1, 2))
        for key, value in [('requiredMaxAbs', .001), ('requiredDecodedPixelDifferences', 1), ('newProjectModelInputsAllowed', 1), ('formalReleaseAllowed', True), ('productHold', False)]:
            bad = contract()
            bad[key] = value
            with self.assertRaises(ValueError):
                m.validate_contract(bad)

    def test_one_effect_zero_keeps_other_effect_without_fake_interaction(self):
        cc = np.array([2., -3.], np.float32)
        skip = np.array([5., -2.], np.float32)
        result = m.interaction(cc, skip, cc, skip, cc, skip)
        self.assertEqual(result['deepOnlyMaxAbs'], 0)
        self.assertEqual(result['interactionMaxAbs'], 0)
        self.assertEqual(result['mathematicalTotalMaxAbs'], result['skipOnlyMaxAbs'])


if __name__ == '__main__':
    unittest.main()
