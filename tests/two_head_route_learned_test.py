"""学得参考不可混用控制参考，小输出头非有限必须拒绝。"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('learned_route_under_test', ROOT / 'model/training/audit-two-head-route-learned.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class LearnedReferenceTests(unittest.TestCase):
    def test_reference_selects_learned_heads_with_conflicting_control(self):
        learned = {'mask': np.ones((1, 1, 2, 2), np.float32), 'presence': np.ones((1, 1), np.float32)}
        control = {key: -value.copy() for key, value in learned.items()}
        actual = {key: value.copy() for key, value in learned.items()}
        case = {'h': 2, 'w': 2, 'references': {'control': control, 'learned': learned}}
        with patch.object(m.p, 'tensor', side_effect=lambda ref: ref):
            result = m.old.parity(case, actual)
        self.assertTrue(result['numericGatePassed'])
        self.assertTrue(result['presenceDecisionMatched'])
        self.assertEqual(result['decodedMaskPixelDifference'], 0)

    def test_presence_nan_rejected_independently_of_finite_mask(self):
        expected = {'mask': np.ones((1, 1, 2, 2), np.float32), 'presence': np.ones((1, 1), np.float32)}
        actual = {key: value.copy() for key, value in expected.items()}
        actual['presence'][0, 0] = np.nan
        case = {'h': 2, 'w': 2, 'references': {'learned': expected}}
        with patch.object(m.p, 'tensor', side_effect=lambda ref: ref):
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                m.old.parity(case, actual)

    def test_reference_difference_cannot_be_hidden_by_equal_decoding(self):
        expected = {'mask': np.ones((1, 1, 2, 2), np.float32), 'presence': np.ones((1, 1), np.float32)}
        actual = {key: value.copy() for key, value in expected.items()}
        actual['mask'][0, 0, 0, 0] += np.float32(2e-4)
        case = {'h': 2, 'w': 2, 'references': {'learned': expected}}
        with patch.object(m.p, 'tensor', side_effect=lambda ref: ref):
            result = m.old.parity(case, actual)
        self.assertFalse(result['numericGatePassed'])
        self.assertTrue(result['decodedPixelGatePassed'])
        self.assertEqual(result['requiredMaximumDifference'], 1e-4)


if __name__ == '__main__':
    unittest.main()
