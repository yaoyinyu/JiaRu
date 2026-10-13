"""隔离算子不允许完整模型调用、部分分母或更改epsilon。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

s = importlib.util.spec_from_file_location('saved_operator_test', Path(__file__).resolve().parents[1] / 'model/training/audit-native-saved-operators.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Tests(unittest.TestCase):
    def rejected(self, plan, message):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'plan.json'; m.d.new(path, plan)
            with patch.object(m.d, 'load', side_effect=RuntimeError('must not load model resources')) as loader:
                with self.assertRaisesRegex(ValueError, message): m.resources(path)
                loader.assert_not_called()

    def base(self):
        return {'purpose': 'full68_same_saved_input_operator_localization', 'fullCandidateCount': 68,
                'optimizerStepsAllowed': 0, 'fullModelInputsAllowed': 0, 'valInputsAllowed': 0,
                'protectedInputsAllowed': 0, 'operatorInputsPerBackendAllowed': 204,
                'operations': ['resize_e3_to_e2', 'resize_d2_to_e1', 'dec1.4_group_norm'],
                'inferencePolicy': {'cudnnAllowTf32': False, 'matmulAllowTf32': False},
                'groupNorm': {'groups': 4, 'channels': 16, 'epsilon': 1e-5}}

    def test_partial_denominator_rejected(self):
        plan = self.base(); plan['fullCandidateCount'] = 2
        self.rejected(plan, 'full68')

    def test_full_model_budget_rejected(self):
        plan = self.base(); plan['fullModelInputsAllowed'] = 1
        self.rejected(plan, 'operator-only')

    def test_changed_epsilon_rejected(self):
        plan = self.base(); plan['groupNorm']['epsilon'] = 1e-3
        self.rejected(plan, 'precision/normalization')


if __name__ == '__main__': unittest.main()
