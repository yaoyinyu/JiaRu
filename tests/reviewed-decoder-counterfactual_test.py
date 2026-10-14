"""双域完整数学合同与同坐标分解的独立边界验证。"""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np

R = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('reviewed_decoder_test', R / 'model/training/analyze-reviewed-decoder-counterfactual.py')
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def contract(count=74):
    return {'cases': [{'ordinal': i} for i in range(1, count + 1)], 'fullCandidateCount': count,
            'branchCandidateCount': 2 * count, 'branches': list(m.BRANCHES),
            'analyticalEvaluationsAllowed': {stage: 2 * count for stage in m.STAGES} | {'total': 14 * count},
            'singleFinalFloat32Conversions': 2 * count, 'requiredNumericDifferenceUnchanged': 1e-4,
            'requiredDecodedPixelDifferencesUnchanged': 0, 'requiredPresenceDecisionDifferencesUnchanged': 0,
            'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0,
            'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
            'productHold': True, 'formalReleaseAllowed': False, 'fullModelLearnedGatePassed': False}


class ReviewedDecoderTests(unittest.TestCase):
    def test_dynamic_denominator_does_not_reuse_68(self):
        p = contract()
        m.validate_contract(p)
        for key, value in [('fullCandidateCount', 68), ('branchCandidateCount', 136),
                           ('singleFinalFloat32Conversions', 136), ('analyticalEvaluationsAllowed', contract(68)['analyticalEvaluationsAllowed'])]:
            bad = copy.deepcopy(p)
            bad[key] = value
            with self.assertRaises(ValueError):
                m.validate_contract(bad)

    def test_missing_duplicate_or_reordered_identity_denominator_rejected(self):
        p = contract()
        for rows in (p['cases'][:-1], [p['cases'][0]] * 74, list(reversed(p['cases']))):
            bad = copy.deepcopy(p)
            bad['cases'] = rows
            with self.assertRaises(ValueError):
                m.validate_contract(bad)

    def test_no_relaxed_quality_release_or_neural_budget(self):
        for key, value in [('requiredNumericDifferenceUnchanged', .001), ('requiredDecodedPixelDifferencesUnchanged', 1),
                           ('requiredPresenceDecisionDifferencesUnchanged', 1), ('newProjectModelInputsAllowed', 1),
                           ('newSyntheticModelInputsAllowed', 1), ('optimizerStepsAllowed', 1), ('valInputsAllowed', 1),
                           ('protectedInputsAllowed', 1), ('newChatImageInputsAllowed', 1), ('productHold', False),
                           ('formalReleaseAllowed', True), ('fullModelLearnedGatePassed', True)]:
            bad = contract()
            bad[key] = value
            with self.assertRaises(ValueError):
                m.validate_contract(bad)

    def test_signed_parts_use_same_coordinate_not_independent_maxima(self):
        c = np.array([0., 0.], np.float32)
        w = np.array([3., -1.], np.float32)
        ic = np.array([20., -2.], np.float64)
        iw = np.array([21., 8.], np.float64)
        r = m.decompose(c, w, ic, iw)
        self.assertEqual(r['actualMaximumCoordinate'], [0])
        self.assertEqual(r['propagatedInputMaxAbs'], 10)
        self.assertEqual(r['signedAtSameCoordinate'], {'actual': 3., 'propagatedInput': 1.,
                                                      'wasmCumulativeChainResidual': -18., 'cudaCumulativeChainResidual': -20.})
        self.assertEqual(r['equationResidualMaxAbs'], 0)
        self.assertTrue(r['residualsAreCumulativeFromDec1_0NotIndividualOperatorErrors'])

    def test_nonfinite_shape_and_storage_mismatch_rejected(self):
        x = np.zeros((2,), np.float32)
        with self.assertRaises(ValueError):
            m.decompose(x, x, x.astype(np.float64), np.array([np.nan, 0.]))
        with self.assertRaises(ValueError):
            m.decompose(x, x, x.astype(np.float64), np.zeros((1, 2)))
        with self.assertRaises(ValueError):
            m.same_bytes(x, x.astype(np.float64))
        with self.assertRaises(ValueError):
            m.same_bytes(x, x.reshape(1, 2))


if __name__ == '__main__':
    unittest.main()
