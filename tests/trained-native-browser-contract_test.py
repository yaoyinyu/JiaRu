"""真实浏览器证据不能由空PASS、错误预算顺序或漂移身份替代。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

R = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


server = module(R / 'model/training/serve-trained-native-browser.py', 'browser_test_server')
audit = module(R / 'model/training/audit-trained-native-browser.py', 'browser_test_audit')


class Tests(unittest.TestCase):
    def scope(self):
        return {'purpose': 'repaired_same_weights_full68_real_wasm_webgpu_gate', 'requiredBackends': ['wasm', 'webgpu'],
            'fullCandidateCount': 68, 'optimizerStepsAllowed': 0, 'newTorchInputsAllowed': 0,
            'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'controlInputsPerBackendAllowed': 68,
            'learnedInputsPerBackendAllowedAfterAllControls': 68, 'requiredNumericDifference': 1e-4,
            'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0, 'graphOptimizationLevel': 'disabled'}

    def reject_scope(self, field, value, error):
        plan = self.scope(); plan[field] = value
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'plan.json'; server.d.new(path, plan)
            with patch.object(server.d, 'load', side_effect=RuntimeError('must not load model resources')) as loader:
                with self.assertRaisesRegex(ValueError, error): server.resources(path)
                loader.assert_not_called()

    def test_partial_denominator_rejected(self): self.reject_scope('fullCandidateCount', 2, 'full68')
    def test_relaxed_numeric_contract_rejected(self): self.reject_scope('requiredNumericDifference', 1e-3, 'numeric')
    def test_protected_budget_rejected(self): self.reject_scope('protectedInputsAllowed', 1, 'scope')

    def reject_live(self, scenario, expected_error):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'browser-capture').mkdir(); (root / 'started-inputs').mkdir()
            for filename in ('server.py', 'browser.html'): (root / filename).write_text('fixture', encoding='utf-8')
            plan_path = root / 'plan.json'; audit.d.new(plan_path, {})
            plan_ref = audit.d.bind(plan_path)
            config_path = root / 'config.json'; audit.d.new(config_path, {'planSha256': plan_ref['sha256'], 'configSha256': 'fixture'})
            audit.d.new(root / 'preparation.json', {'server': audit.d.bind(root / 'server.py'), 'html': audit.d.bind(root / 'browser.html'), 'config': audit.d.bind(config_path), 'plan': plan_ref})
            cases = [{'ordinal': i, 'candidateIdentity': {'identity': {'split': 'train', 'fileName': f'{i}.png', 'imageSha256': str(i)}}, 'h': 1, 'w': 1} for i in range(1, 69)]
            live = {'planSha256': plan_ref['sha256'], 'configSha256': 'fixture', 'userAgent': 'fixture-browser', 'origin': 'http://127.0.0.1:8827',
                    'crossOriginIsolated': True, 'startedInputs': [], 'records': [], 'errors': [], 'ok': True}
            if scenario != 'empty_pass':
                event = {'kind': 'learned' if scenario=='wrong_order' else 'control', 'backend': 'wasm', 'ordinal': 1,
                         'candidateIdentity': cases[0]['candidateIdentity'], 'startedAtUnixNs': 1}
                if scenario=='identity_drift': event['candidateIdentity'] = cases[1]['candidateIdentity']
                audit.d.new(root / 'started-inputs' / f'{event["kind"]}-wasm-1.json', event)
                live['startedInputs'] = [{k: v for k, v in event.items() if k!='startedAtUnixNs'}]
            audit.d.new(root / 'browser-capture/live-browser.json', live)
            pixel = Mock(side_effect=RuntimeError('must not read RAW'))
            fake_server = SimpleNamespace(resources=lambda _: ({}, cases, SimpleNamespace(buffer=pixel)))
            with patch.object(audit.d, 'load', return_value=fake_server):
                with self.assertRaisesRegex(ValueError, expected_error): audit.build(root)
            pixel.assert_not_called()

    def test_empty_outer_pass_is_rejected(self): self.reject_live('empty_pass', 'terminal decision')
    def test_learned_before_controls_rejected_before_raw_read(self): self.reject_live('wrong_order', 'budget start')
    def test_identity_drift_rejected_before_raw_read(self): self.reject_live('identity_drift', 'stable identity')


if __name__ == '__main__': unittest.main()
