"""修复合同不能缩减分母、放宽数值门或打开val预算。"""
import importlib.util
import unittest
from pathlib import Path

s = importlib.util.spec_from_file_location('resize_contract', Path(__file__).resolve().parents[1] / 'model/training/audit-native-resize-repair.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Tests(unittest.TestCase):
    def scope(self):
        return {'purpose': 'same_weights_resize_expression_repair_then_full68_cpu_gate', 'fullCandidateCount': 68,
            'targetResizeNodes': ['/Resize', '/Resize_1'], 'operatorRepairInputsAllowed': 136,
            'operatorDiagnosticMaximumDifference': 2e-5, 'learnedCpuOrtInputsAllowedAfterControls': 68,
            'newLearnedTorchInputsAllowed': 0, 'nonzeroUntrainedTorchControlsAllowed': 68,
            'nonzeroUntrainedOrtControlsAllowed': 68, 'requiredFullModelNumericDifference': 1e-4,
            'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
            'optimizerStepsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'browserInputsAllowed': 0,
            'allOriginalNativeShapesRequired': True, 'nonzeroControlMayNotSelectModelQuality': True,
            'oldFailedOnnxAndAllFailuresPreserved': True, 'formalReleaseAllowed': False, 'productHold': True}

    def test_partial_denominator_rejected(self):
        scope = self.scope(); scope['fullCandidateCount'] = 2
        with self.assertRaisesRegex(ValueError, 'contract'): m.validate(scope)

    def test_relaxed_numeric_gate_rejected(self):
        scope = self.scope(); scope['requiredFullModelNumericDifference'] = 1e-3
        with self.assertRaisesRegex(ValueError, 'contract'): m.validate(scope)

    def test_val_budget_rejected(self):
        scope = self.scope(); scope['valInputsAllowed'] = 1
        with self.assertRaisesRegex(ValueError, 'contract'): m.validate(scope)


if __name__ == '__main__': unittest.main()
