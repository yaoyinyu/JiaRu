"""新完整分母的阶段门反例，不改已冻结物化器测试。"""
import copy
import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_stage_tests', ROOT/'model/training/audit-reviewed-native-deployment.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


class Tests(unittest.TestCase):
    def test_all_new_controls_required_before_learned_gate(self):
        runner.N = 74
        parity = {k: True for k in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched', 'allReferenceAndCapturedHeadsFinite')}
        report = {'ok': True, 'kind': 'control', 'allThreeBackendStageGatesPassed': True,
            'modelInputsConsumedPerBackend': {k: 74 for k in ('cpu', 'wasm', 'webgpu')},
            'records': [{'backend': backend, 'ordinal': i, 'gatePassed': True, 'parity': copy.deepcopy(parity)}
                        for backend in ('cpu', 'wasm', 'webgpu') for i in range(1, 75)]}
        runner.require_control_gate(report)
        bad = copy.deepcopy(report); bad['records'][-1]['parity']['numericGatePassed'] = False
        with self.assertRaises(ValueError): runner.require_control_gate(bad)
        bad = copy.deepcopy(report); bad['records'].pop()
        with self.assertRaises(ValueError): runner.require_control_gate(bad)

    def test_browser_complete_count_is_derived_from_actual_cases(self):
        self.assertIn('r.records.length===c.cases.length*2', runner.HTML)
        self.assertNotIn('r.records.length===136', runner.HTML)
        self.assertIn('await post(\'/start/', runner.HTML)
        self.assertIn('persistedAckRecoveries', runner.HTML)


if __name__ == '__main__': unittest.main()
