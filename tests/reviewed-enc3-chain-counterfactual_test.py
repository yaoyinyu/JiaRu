"""enc3整链的真实F64边界、原图参数解析和不可覆盖证据校验。"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import onnx
from onnx import helper as h, numpy_helper
from scipy.special import erf

R = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


m = load(R / 'model/training/analyze-reviewed-enc3-chain-counterfactual.py', 'enc3_chain_test')
fixture = load(R / 'tests/reviewed-deep-decoder-counterfactual_test.py', 'enc3_deep_fixture')


def case_fixture(root):
    c, p, params, graph = fixture.test_case(root)
    rng = np.random.default_rng(317)
    c['originalEnc3FirstConv'] = {origin: m.t.save(root / (origin + '-enc3-conv.bin'), rng.normal(size=(1, 64, 2, 3)).astype(np.float32)) for origin in ('cuda', 'wasm')}
    c['fixedWasmEnc2'] = c['features']['enc2.5']['wasm']
    eps = float(np.float32(1e-5))
    p |= {'encoderGroupNorms': [{'groups': 4, 'epsilon': eps}] * 2, 'encoderGelu': p['gelu']}
    for suffix in ('1', '4'):
        params['encoderGamma' + suffix] = rng.uniform(.8, 1.2, size=(64, 1, 1)).astype(np.float32)
        params['encoderBeta' + suffix] = rng.normal(0, .02, size=(64, 1, 1)).astype(np.float32)
    params['encoderConv3'] = np.zeros((64, 64, 3, 3), np.float32)
    params['encoderConv3'][:, 0, 1, 1] = .25
    params['encoderConv3'][:, 51, 0, 1] = -.125
    params['encoderConv3'][:, 63, 1, 2] = .0625
    return c, p, params, graph


def independent_prefix(x, params, p):
    def gn(a, suffix):
        grouped = a.reshape(4, -1)
        result = np.empty_like(grouped)
        for group in range(4):
            centered = grouped[group] - np.mean(grouped[group], dtype=np.float64)
            result[group] = centered / np.sqrt(np.mean(centered * centered, dtype=np.float64) + p['encoderGroupNorms'][0]['epsilon'])
        return result.reshape(a.shape) * params['encoderGamma' + suffix].astype(np.float64) + params['encoderBeta' + suffix].astype(np.float64)
    def gelu(a): return (a * (1 + erf(a / float(np.float32(np.sqrt(2)))))) * .5
    a = gelu(gn(x.astype(np.float64), '1'))
    conv = np.repeat(a[:, 0:1] * .25, 64, axis=1)
    conv[:, :, 1:, :] -= a[:, 51:52, :-1, :] * .125
    conv[:, :, :, :-1] += a[:, 63:64, :, 1:] * .0625
    return gelu(gn(conv, '4'))


def encoder_graph():
    nodes, inits = [], []
    def init(name, value): inits.append(numpy_helper.from_array(np.asarray(value, np.float32), name)); return name
    for suffix in ('1', '4'):
        prefix = f'/enc3/enc3.{suffix}/'
        shape = prefix + 'shape'
        nodes.append(h.make_node('Constant', [], [shape], name=shape, value=numpy_helper.from_array(np.array([0, 4, -1], np.int64))))
        nodes.append(h.make_node('Reshape', ['input', shape], [prefix + 'reshaped'], name=prefix + 'Reshape'))
        nodes.append(h.make_node('Add', ['variance', init(prefix + 'eps', [1e-5])], [prefix + 'variance_eps'], name=prefix + 'eps_add'))
        nodes.append(h.make_node('Sqrt', [prefix + 'variance_eps'], [prefix + 'std'], name=prefix + 'sqrt'))
        nodes.append(h.make_node('Div', ['centered', prefix + 'std'], [prefix + 'InstanceNormalization_output_0'], name=prefix + 'InstanceNormalization'))
        nodes.append(h.make_node('Mul', [prefix + 'InstanceNormalization_output_0', init(prefix + 'gamma', np.ones((64, 1, 1)))], [prefix + 'scaled'], name=prefix + 'mul'))
        nodes.append(h.make_node('Add', [prefix + 'scaled', init(prefix + 'beta', np.zeros((64, 1, 1)))], [prefix + 'Add_output_0'], name=prefix + 'Add'))
    nodes.append(h.make_node('Conv', ['input', init('enc3.3.weight', np.zeros((64, 64, 3, 3)))], ['conv'], name='/enc3/enc3.3/Conv', dilations=[1, 1], group=1, kernel_shape=[3, 3], pads=[1, 1, 1, 1], strides=[1, 1]))
    for suffix in ('2', '5'):
        for name, value in zip(('Constant', 'Constant_1', 'Constant_2'), (np.float32(np.sqrt(2)), np.float32(1), np.float32(.5)), strict=True):
            name = f'/enc3/enc3.{suffix}/' + name
            nodes.append(h.make_node('Constant', [], [name + '_output_0'], name=name, value=numpy_helper.from_array(value)))
    return h.make_model(h.make_graph(nodes, 'metadata-only', [], [], inits))


class Enc3ChainTests(unittest.TestCase):
    def test_original_parameter_domains_and_constants_parsed_and_invalid_graph_rejected(self):
        graph = encoder_graph()
        params, configs = m.encoder_parameters(graph)
        self.assertEqual(params['encoderConv3'].shape, (64, 64, 3, 3))
        self.assertEqual(configs['encoderGroupNorms'], [{'groups': 4, 'channels': 64, 'epsilon': float(np.float32(1e-5))}] * 2)
        self.assertEqual(configs['encoderGelu']['sqrt2FromOriginalFloat32'], 1.4142135381698608)
        self.assertEqual(len(configs['encoderParameterBindings']), 7)
        bad = copy.deepcopy(graph)
        next(n for n in bad.graph.node if n.op_type == 'Conv').input.append('fake-bias')
        with self.assertRaises(ValueError): m.encoder_parameters(bad)
        bad = copy.deepcopy(graph)
        shape = next(n for n in bad.graph.node if n.name == '/enc3/enc3.1/shape')
        shape.attribute[0].t.CopyFrom(numpy_helper.from_array(np.array([0, 8, -1], np.int64)))
        with self.assertRaises(ValueError): m.encoder_parameters(bad)

    def test_complete_two_origin_chain_and_independent_prefix_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            for branch, origin in zip(m.BRANCHES, ('cuda', 'wasm'), strict=True):
                row = m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch))
                self.assertEqual(row, m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch, True)))
                stored = m.t.read_tensor(next(s['savedRaw'] for s in row['stages'] if s['stage'] == 'enc3LastGelu64'))
                np.testing.assert_allclose(stored, independent_prefix(m.t.read_tensor(c['originalEnc3FirstConv'][origin]), params, p), rtol=0, atol=2e-14)
                self.assertEqual(row['originalEnc3FirstConv'], c['originalEnc3FirstConv'][origin])
                self.assertEqual(row['fixedWasmEnc2'], c['features']['enc2.5']['wasm'])
                self.assertEqual([s['stage'] for s in row['stages']], list(m.STAGES))
            self.assertEqual(len(list((root / 'events').glob('*.json'))), 96)
            self.assertEqual(len(list((root / 'results').glob('*.bin'))), 4)

    def test_first_resize_receives_unrounded_float64_encoder_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            inputs = []; original = m.resize_propagated64
            def observe(x, *args):
                inputs.append(x.copy()); return original(x, *args)
            with patch.object(m, 'resize_propagated64', side_effect=observe):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[1]))
            self.assertEqual(len(inputs), 2)
            self.assertEqual(inputs[0].dtype, np.float64)
            self.assertGreater(float(np.abs(inputs[0] - inputs[0].astype(np.float32).astype(np.float64)).max()), 0)
            self.assertEqual(inputs[1].dtype, np.float64)

    def test_missing_input_unknown_branch_and_nonfinite_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            with self.assertRaises(ValueError): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, 'unknown'))
            del c['originalEnc3FirstConv']['wasm']
            with self.assertRaises(KeyError): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[1]))
            with self.assertRaises(ValueError): m.descriptor(np.array([np.inf], np.float64))

    def test_unsaved_stage_hash_or_saved_boundary_tamper_refuses_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root); b = m.BRANCHES[0]
            m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, b))
            path = next((root / 'events').glob('*enc3SecondConv64-done.json')); raw = path.read_bytes()
            value = json.loads(raw); value['output']['bytesSha256'] = '0' * 64; path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'full stage bytes'): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, b, True))
            path.write_bytes(raw)
            path = next((root / 'results').glob('*enc3LastGelu64.bin')); path.write_bytes(b'\0' * path.stat().st_size)
            with self.assertRaises(ValueError): m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, b, True))

    def test_contract_rejects_wrong_raw_size_budget_role_threshold_and_storage(self):
        c = {'ordinal': 1, 'candidateIdentity': {'identity': {'split': 'train'}}, 'candidateInput': {'shape': [1, 4, 8, 12]}}
        p = {'cases': [c], 'fullCandidateCount': 1, 'branches': m.BRANCHES, 'orderedStages': list(m.STAGES),
             'analyticalEvaluationsAllowed': {s: 2 for s in m.STAGES[:-1]} | {'total': 46}, 'singleFinalFloat32Conversions': 2,
             'expectedRawCount': 4, 'expectedRawBytes': 6912, 'storagePolicy': m.POLICY, 'savedStages': list(m.SAVED),
             'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0, 'productHold': True}
        for k in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed'): p[k] = 0
        m.validate_contract(p)
        for key, value in [('expectedRawBytes', 0), ('requiredMaxAbs', 2e-4), ('savedStages', ['mask32']), ('protectedInputsAllowed', 1)]:
            bad = copy.deepcopy(p); bad[key] = value
            with self.assertRaises(ValueError): m.validate_contract(bad)
        bad = copy.deepcopy(p); bad['cases'][0]['candidateIdentity']['identity']['split'] = 'val'
        with self.assertRaises(ValueError): m.validate_contract(bad)


if __name__ == '__main__': unittest.main()
