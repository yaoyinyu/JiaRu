"""完整双头误差归属须拒绝分母、身份或原判定漂移。"""
import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
R = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('native_head_tests', R/'model/training/analyze-reviewed-native-head-errors.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
c = m.d.load(R/'model/training/verify-native-multiscale-browser-v2.py', 'fixture_head_compare')


class Tests(unittest.TestCase):
    def fixture(self):
        ref = lambda key: {'key': key, 'shape': [1,1,1,1] if key.startswith('mask') else [1,1], 'dtype': 'float32'}
        case = {'ordinal': 1, 'h': 1, 'w': 1, 'candidateIdentity': {'stable': 'one'}, 'references': {'learned': {'mask': ref('mask0'), 'presence': ref('presence0')}}}
        arrays = {'mask0': np.zeros((1,1,1,1), np.float32), 'presence0': np.ones((1,1), np.float32),
                  'mask1': np.full((1,1,1,1), 0.001, np.float32)}
        cap = {'ordinal': 1, 'candidateIdentity': case['candidateIdentity'], 'outputs': {'mask': ref('mask1'), 'presence': ref('presence0')}}
        stats = c.compare_outputs(arrays['mask0'].reshape(-1), arrays['presence0'].reshape(-1), arrays['mask1'].reshape(-1), arrays['presence0'].reshape(-1), 1, 1)
        report = {'ok': True, 'kind': 'learned', 'inputs': {'preparation': 'prep'},
            'captures': {b: [copy.deepcopy(cap)|{'backend': b}] for b in ('cpu','wasm','webgpu')},
            'records': [{'backend': b, 'ordinal': 1, 'candidateIdentity': case['candidateIdentity'], 'parity': copy.deepcopy(stats), 'gatePassed': False} for b in ('cpu','wasm','webgpu')]}
        scope = {'cases': [case], 'candidateIdentities': [case['candidateIdentity']], 'quality': {'maximumBothHeadDifference': 1e-4}}
        store = {'report': report, 'prep': {'execution': 'exec'}, 'exec': {'scope': 'scope', 'sources': {'comparator': 'compare'}}, 'scope': scope}
        return report, scope, arrays, store

    def run_fixture(self, store, arrays):
        with patch.object(m.d, 'read', side_effect=lambda ref: store[ref]), patch.object(m.d, 'checked', side_effect=lambda ref: ref), patch.object(m.d, 'bind', return_value='reader'), patch.object(m.d, 'load', return_value=c), patch.object(m.m, 'tensor', side_effect=lambda ref: arrays[ref['key']]):
            return m.analyze('report')

    def test_mask_failure_not_presence_failure_and_no_model_calls(self):
        report, scope, arrays, store = self.fixture(); result = self.run_fixture(store, arrays)
        self.assertEqual(result['summary']['wasm']['mask']['failedOrdinals'], [1])
        self.assertEqual(result['summary']['wasm']['presence']['failedOrdinals'], [])
        self.assertEqual(result['newModelCalls'], 0); self.assertFalse(result['rootCauseProven'])

    def test_missing_backend_record_rejected(self):
        report, scope, arrays, store = self.fixture(); report['records'].pop()
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): self.run_fixture(store, arrays)

    def test_identity_replacement_rejected(self):
        report, scope, arrays, store = self.fixture(); report['captures']['wasm'][0]['candidateIdentity'] = {'stable': 'other'}
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): self.run_fixture(store, arrays)

    def test_original_parity_drift_rejected(self):
        report, scope, arrays, store = self.fixture(); report['records'][0]['parity']['numericGatePassed'] = True
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): self.run_fixture(store, arrays)

    def test_hidden_case_denominator_rejected(self):
        report, scope, arrays, store = self.fixture(); scope['candidateIdentities'].append({'stable':'missing'})
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): self.run_fixture(store, arrays)


if __name__ == '__main__': unittest.main()
