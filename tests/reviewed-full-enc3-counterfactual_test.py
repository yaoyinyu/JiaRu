"""完整enc3数学链的池化精度、语义节点、来源及全阶段保真。"""
import copy
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from onnx import helper as h, numpy_helper

R = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


m = load(R / 'model/training/analyze-reviewed-full-enc3-counterfactual.py', 'full_enc3_test')
fixture = load(R / 'tests/reviewed-enc3-chain-counterfactual_test.py', 'full_enc3_fixture')


def scalar_pool(x):
    out = np.empty((1, x.shape[1], x.shape[2] // 2, x.shape[3] // 2), np.float64)
    for c in range(x.shape[1]):
        for y in range(out.shape[2]):
            for z in range(out.shape[3]):
                out[0, c, y, z] = float(sum((Fraction.from_float(float(x[0, c, 2*y+dy, 2*z+dx])) for dy in (0, 1) for dx in (0, 1)), Fraction()) / 4)
    return out


def full_fixture(root):
    c, p, params, graph = fixture.case_fixture(root)
    c['enc3PoolInput'] = c['features']['enc2.5']
    params['firstEncoderConv'] = np.zeros((64, 32, 3, 3), np.float32)
    params['firstEncoderConv'][:, 0, 1, 1] = .5
    params['firstEncoderConv'][:, 31, 2, 0] = -.25
    return c, p, params, graph


def first_conv_reference(a):
    result = np.repeat(a[:, 0:1] * .5, 64, axis=1)
    result[:, :, :-1, 1:] -= a[:, 31:32, 1:, :-1] * .25
    return result


class FullEnc3Tests(unittest.TestCase):
    def test_pool_matches_exact_rationals_including_odd_edges_and_sub_f32_values(self):
        x = np.arange(30, dtype=np.float32).reshape(1, 2, 3, 5)
        x[0, 0, :2, :2] = [[2**24, 1], [0, 0]]
        actual, stats = m.average_pool64(x)
        np.testing.assert_array_equal(actual, scalar_pool(x))
        self.assertEqual(actual.shape, (1, 2, 1, 2))
        self.assertEqual(actual[0, 0, 0, 0], 4194304.25)
        self.assertNotEqual(actual[0, 0, 0, 0], float(np.float32(actual[0, 0, 0, 0])))
        self.assertFalse(stats['actualPoolCaptureClaimed'])
        with self.assertRaises(ValueError): m.average_pool64(x.astype(np.float64))
        with self.assertRaises(ValueError): m.average_pool64(x[:, :, :1])

    def test_semantic_pool_and_32_to_64_weight_are_bound_and_invalid_variants_refused(self):
        graph = fixture.encoder_graph()
        graph.graph.node.extend([
            h.make_node('AveragePool', ['enc2'], ['pooled'], name='actual-pool', ceil_mode=0, count_include_pad=1, kernel_shape=[2, 2], pads=[0, 0, 0, 0], strides=[2, 2]),
            h.make_node('Conv', ['pooled', 'first.weight'], ['enc3-conv'], name='actual-conv', dilations=[1, 1], group=1, kernel_shape=[3, 3], pads=[1, 1, 1, 1], strides=[1, 1]),
        ])
        graph.graph.initializer.append(numpy_helper.from_array(np.ones((64, 32, 3, 3), np.float32), 'first.weight'))
        mapping = {'enc2.5': {'tensor': 'enc2'}, 'enc3.0': {'tensor': 'enc3-conv'}}
        weight, topology = m.pool_and_first_conv(graph, mapping)
        self.assertEqual(weight.shape, (64, 32, 3, 3))
        self.assertEqual(topology['originalPoolNode']['name'], 'actual-pool')
        self.assertEqual(topology['originalFirstConvNode']['name'], 'actual-conv')
        bad = copy.deepcopy(graph); next(n for n in bad.graph.node if n.name == 'actual-conv').input.append('bias')
        with self.assertRaises(ValueError): m.pool_and_first_conv(bad, mapping)
        bad = copy.deepcopy(graph)
        attr = next(a for a in next(n for n in bad.graph.node if n.name == 'actual-pool').attribute if a.name == 'ceil_mode'); attr.i = 1
        with self.assertRaises(ValueError): m.pool_and_first_conv(bad, mapping)

    def test_both_full_chains_replay_and_independent_prefix_is_correct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = full_fixture(root)
            for branch, origin in zip(m.BRANCHES, ('cuda', 'wasm'), strict=True):
                row = m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch))
                self.assertEqual(row, m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch, True)))
                pool = scalar_pool(m.t.read_tensor(c['enc3PoolInput'][origin])); conv = first_conv_reference(pool)
                self.assertEqual(row['stages'][0]['output'], m.descriptor(pool))
                self.assertEqual(row['stages'][1]['output'], m.descriptor(conv))
                boundary = m.t.read_tensor(next(s['savedRaw'] for s in row['stages'] if s['stage'] == 'enc3LastGelu64'))
                np.testing.assert_allclose(boundary, fixture.independent_prefix(conv, params, p), rtol=0, atol=3e-14)
                self.assertEqual(row['fixedWasmEnc2'], c['fixedWasmEnc2'])
                self.assertEqual(row['originalPoolInput'], c['enc3PoolInput'][origin])
            self.assertEqual(len(list((root / 'events').glob('*.json'))), 104)
            self.assertEqual(len(list((root / 'results').glob('*.bin'))), 4)

    def test_first_gn_consumes_unrounded_computed_conv_not_stored_conv(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = full_fixture(root)
            seen = []; original = m.t.gn64
            def observe(x, *args):
                seen.append(x.copy()); return original(x, *args)
            with patch.object(m.t, 'gn64', side_effect=observe):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[1]))
            np.testing.assert_array_equal(seen[0], first_conv_reference(scalar_pool(m.t.read_tensor(c['enc3PoolInput']['wasm']))))
            self.assertGreater(float(np.abs(seen[0] - m.t.read_tensor(c['originalEnc3FirstConv']['wasm'])).max()), .01)

    def test_unsaved_pool_hash_and_origin_binding_tamper_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = full_fixture(root); b = m.BRANCHES[0]
            m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, b))
            path = next((root / 'events').glob('*enc3AveragePool64-done.json')); raw = path.read_bytes()
            value = json.loads(raw); value['output']['bytesSha256'] = '0' * 64; path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'full stage bytes'): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, b, True))
            path.write_bytes(raw)
            path = next((root / 'events').glob('*enc3AveragePool64-start.json')); value = json.loads(path.read_bytes())
            value['inputs']['originalPoolInput'] = c['enc3PoolInput']['wasm']; path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'start event'): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, b, True))

    def test_full_budget_contract_and_missing_origins_are_rejected(self):
        c = {'ordinal': 1, 'candidateIdentity': {'identity': {'split': 'train'}}, 'candidateInput': {'shape': [1, 4, 8, 12]}}
        p = {'cases': [c], 'fullCandidateCount': 1, 'branches': m.BRANCHES, 'orderedStages': list(m.STAGES),
             'analyticalEvaluationsAllowed': {s: 2 for s in m.STAGES[:-1]} | {'total': 50}, 'singleFinalFloat32Conversions': 2,
             'expectedRawCount': 4, 'expectedRawBytes': 6912, 'storagePolicy': m.POLICY, 'savedStages': list(m.SAVED),
             'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0, 'productHold': True}
        for k in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed'): p[k] = 0
        m.validate_contract(p)
        for key, value in [('expectedRawBytes', 0), ('requiredMaxAbs', 2e-4), ('newProjectModelInputsAllowed', 1)]:
            bad = copy.deepcopy(p); bad[key] = value
            with self.assertRaises(ValueError): m.validate_contract(bad)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = full_fixture(root); del c['enc3PoolInput']['cuda']
            with self.assertRaises(KeyError): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0]))


if __name__ == '__main__': unittest.main()
