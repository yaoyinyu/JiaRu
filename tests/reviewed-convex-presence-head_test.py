"""独立凸头合成控制：精确间隔、float32舍入、拒识及非头权重保真。"""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
m = load('convex_head_test', 'model/training/fit-reviewed-convex-presence-head.py')
v = load('convex_head_verify_test', 'model/training/verify-reviewed-convex-presence-head.py')


class ConvexHeadTests(unittest.TestCase):
    def inputs(self): return np.array([[1., 0.], [2., 1.], [-1., 0.]], np.float32), np.array([True, True, False])

    def test_fresh_l1_solve_includes_bias_and_both_classes(self):
        f, labels = self.inputs()
        with patch.object(m, 'linprog', wraps=m.linprog) as solve:
            record, head = m.fit_head(f, labels)
        self.assertEqual(solve.call_count, 1); self.assertEqual(head.dtype, np.float32)
        self.assertTrue(all(x >= 2 for x in m.certificate.exact_margins(f, labels, np.asarray(record['scaledCoefficientsBinary64']))))
        with patch.object(m, 'linprog', side_effect=AssertionError('reader cannot solve')):
            self.assertEqual(m.verify_fit(f, labels, record).tobytes(), head.tobytes())

    def test_bias_is_trained_for_translated_separation(self):
        f = np.array([[4.], [5.], [1.]], np.float32); flags = np.array([True, True, False])
        record, head = m.fit_head(f, flags)
        self.assertLess(head[-1], 0); self.assertTrue(all((f[:, 0]*head[0]+head[1] >= 0) == flags))

    def test_exact_margin_tamper_and_wrong_float32_round_rejected(self):
        f, labels = self.inputs(); record, head = m.fit_head(f, labels)
        bad = copy.deepcopy(record); bad['exactSignedMargins'][0] = '999'
        with self.assertRaises(ValueError): m.verify_fit(f, labels, bad)
        bad = copy.deepcopy(record); bad['float32Head'][0] = float(np.nextafter(head[0], np.float32(np.inf)))
        with self.assertRaises(ValueError): m.verify_fit(f, labels, bad)

    def test_infeasible_fit_never_retries(self):
        with patch.object(m, 'linprog', wraps=m.linprog) as solve:
            with self.assertRaises(ValueError): m.fit_head(np.ones((2, 2), np.float32), np.array([True, False]))
        self.assertEqual(solve.call_count, 1)

    def test_bad_features_or_one_class_rejected_before_solve(self):
        f, flags = self.inputs()
        with patch.object(m, 'linprog', side_effect=AssertionError('no solve')):
            for x, y in ((f.astype(np.float64), flags), (f, np.ones(3, bool)), (f*np.nan, flags)):
                with self.assertRaises(ValueError): m.fit_head(x, y)

    def state(self):
        return {'presence.weight': torch.zeros(1, 128), 'presence.bias': torch.zeros(1), 'encoder.weight': torch.tensor([-0., 1.])}

    def test_only_independently_fitted_head_tensor_bytes_change(self):
        original = self.state(); head = np.linspace(-1, 1, 129, dtype=np.float32)
        state = m.updated_state(original, head); m.verify_state(original, state, head)
        self.assertTrue(torch.equal(original['presence.weight'], torch.zeros(1, 128)))
        self.assertEqual(state['encoder.weight'].numpy().tobytes(), original['encoder.weight'].numpy().tobytes())

    def test_nonhead_signed_zero_mutation_is_rejected(self):
        original = self.state(); head = np.ones(129, np.float32); state = m.updated_state(original, head)
        state['encoder.weight'][0] = 0.
        with self.assertRaises(ValueError): m.verify_state(original, state, head)

    def test_presence_nan_domain_and_exact_zero_rejection_semantics(self):
        self.assertTrue(m.presence_gate(np.array(0., np.float32), True))
        self.assertFalse(m.presence_gate(np.array(-0., np.float32), False))
        self.assertTrue(m.presence_gate(np.array(-1., np.float32), False))
        for p in (np.array(np.nan, np.float32), np.array(1., np.float64), np.ones(1, np.float32)):
            with self.assertRaises(ValueError): m.presence_gate(p, True)

    def test_mask_bitwise_gate_rejects_signed_zero_and_nonfinite(self):
        reference = np.zeros((2, 3), np.float32); m.mask_exact(reference, reference.copy(), [3, 2])
        for value in (-0., np.nan):
            bad = reference.copy(); bad[0, 0] = value
            with self.assertRaises(ValueError): m.mask_exact(bad, reference, [3, 2])

    def test_complete_ledger_and_tampered_counter_rejected(self):
        identities = [{'candidate': i} for i in range(74)]
        counters = {'fitSolvesStarted': 0, 'fitSolvesConfirmed': 0, 'cachedInputsStarted': 0, 'cachedInputsConfirmed': 0, 'nativeInputsStarted': 0, 'nativeInputsConfirmed': 0}
        events = []
        def event(phase, **extra): events.append({'sequence': len(events)+1, 'phase': phase, **counters, **extra})
        report = {'execution': {'test': True}, 'fit': {'fit': True}, 'cached': list(range(74)), 'native': list(range(74))}
        event('claimed'); counters['fitSolvesStarted'] = 1; event('fit_started'); counters['fitSolvesConfirmed'] = 1; event('fit_confirmed', fit=report['fit'])
        for kind in ('cached', 'native'):
            for i, identity in enumerate(identities, 1):
                counters[kind+'InputsStarted'] = i; event(kind+'_started', candidateIdentity=identity)
                counters[kind+'InputsConfirmed'] = i
                event(kind+'_confirmed', candidateIdentity=identity, **{('record' if kind == 'cached' else 'output'): i-1})
        event('closed'); report['counters'] = counters.copy()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m.d.new(root/'terminal.json', events[-1]); m.d.new(root/'attempt.json', {'execution': report['execution'], 'attemptConsumed': True, 'restartAllowed': False})
            v.ledger_replay(events, report, identities, root)
            bad = copy.deepcopy(events); bad[19]['cachedInputsConfirmed'] -= 1
            with self.assertRaises(ValueError): v.ledger_replay(bad, report, identities, root)
            with self.assertRaises(ValueError): v.ledger_replay(events[:-1], report, identities, root)


if __name__ == '__main__': unittest.main()
