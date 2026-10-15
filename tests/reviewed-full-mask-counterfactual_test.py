"""完整mask数学链：独立逐算子参考、F64跳连和全部未保存阶段重算。"""
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
from scipy.special import erf

R = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load(R / 'model/training/analyze-reviewed-full-mask-counterfactual.py', 'full_mask_test')
previous = load(R / 'tests/reviewed-full-enc3-counterfactual_test.py', 'full_mask_fixture')
coordinates = load(R / 'tests/reviewed-upstream-counterfactual_test.py', 'full_mask_coordinates')


def front_graph():
    nodes, initializers = [], []
    def init(name, value):
        initializers.append(numpy_helper.from_array(np.asarray(value, np.float32), name))
        return name
    for block, incoming, channels, source in [('enc1', 4, 16, 'candidate'), ('enc2', 16, 32, 'pool1')]:
        for suffix, inputs in [('0', incoming), ('3', channels)]:
            nodes.append(h.make_node('Conv', [source, init(block + suffix + 'weight', np.zeros((channels, inputs, 3, 3)))], [block + suffix + 'conv'], name=f'/{block}/{block}.{suffix}/Conv', dilations=[1, 1], group=1, kernel_shape=[3, 3], pads=[1, 1, 1, 1], strides=[1, 1]))
        for suffix in ('1', '4'):
            prefix = f'/{block}/{block}.{suffix}/'
            nodes.append(h.make_node('Constant', [], [prefix + 'shape'], name=prefix + 'constant', value=numpy_helper.from_array(np.array([0, 4, -1], np.int64))))
            nodes.append(h.make_node('Reshape', [source, prefix + 'shape'], [prefix + 'reshape'], name=prefix + 'Reshape'))
            nodes.append(h.make_node('Add', ['variance', init(prefix + 'eps', [1e-5])], [prefix + 'epsilon_added']))
            nodes.append(h.make_node('Sqrt', [prefix + 'epsilon_added'], [prefix + 'std']))
            nodes.append(h.make_node('Div', ['centered', prefix + 'std'], [prefix + 'InstanceNormalization_output_0']))
            nodes.append(h.make_node('Mul', [prefix + 'InstanceNormalization_output_0', init(prefix + 'gamma', np.ones((channels, 1, 1)))], [prefix + 'scaled']))
            nodes.append(h.make_node('Add', [prefix + 'scaled', init(prefix + 'beta', np.zeros((channels, 1, 1)))], [prefix + 'Add_output_0']))
        for suffix in ('2', '5'):
            for constant, value in zip(('Constant', 'Constant_1', 'Constant_2'), (np.float32(np.sqrt(2)), np.float32(1), np.float32(.5)), strict=True):
                name = f'/{block}/{block}.{suffix}/' + constant
                nodes.append(h.make_node('Constant', [], [name + '_output_0'], name=name, value=numpy_helper.from_array(value)))
    nodes.append(h.make_node('AveragePool', ['/enc1/enc1.5/Mul_1_output_0'], ['pool1'], name='pool1', ceil_mode=0, count_include_pad=1, kernel_shape=[2, 2], pads=[0, 0, 0, 0], strides=[2, 2]))
    return h.make_model(h.make_graph(nodes, 'front-parameter-fixture', [], [], initializers))


def case_fixture(root):
    c, p, params, graph = previous.full_fixture(root)
    rng = np.random.default_rng(885)
    configs = {}
    for block, incoming, channels in [('enc1', 4, 16), ('enc2', 16, 32)]:
        for suffix, inputs in [('0', incoming), ('3', channels)]:
            params[block + 'Conv' + suffix] = rng.normal(0, .03, (channels, inputs, 3, 3)).astype(np.float32)
        for suffix in ('1', '4'):
            params[block + 'Gamma' + suffix] = rng.uniform(.8, 1.2, (channels, 1, 1)).astype(np.float32)
            params[block + 'Beta' + suffix] = rng.normal(0, .01, (channels, 1, 1)).astype(np.float32)
        configs[block] = {'groupNorms': [{'groups': 4, 'epsilon': float(np.float32(1e-5))}] * 2, 'gelu': p['gelu']}
    p['frontEncoders'] = configs
    c['originalObservedLayersAuditOnly'] = {origin: {'enc1.5': c['fixedWasmSkip'], **{key: value[origin] for key, value in c['features'].items()}} for origin in ('cuda', 'wasm')}
    p |= {'fullCandidateCount': 1, 'cases': [c], 'branches': m.BRANCHES, 'orderedStages': list(m.STAGES), 'savedStages': list(m.SAVED),
          'storagePolicy': m.POLICY, 'analyticalEvaluationsAllowed': {s: 1 for s in m.STAGES[:-1]} | {'total': 38},
          'singleFinalFloat32Conversions': 1, 'expectedRawCount': 1, 'expectedRawBytes': 8 * 12 * 4,
          'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
          'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0, 'valInputsAllowed': 0,
          'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0, 'actualFp32RepairOrWholeModelUnreachableProven': False,
          'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}
    return c, p, params, graph


def independent_arrays(case, p, params):
    result = {}
    def save(name, a):
        result[name] = a
        return a
    def conv(x, weight):
        padded = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
        out = np.zeros((1, weight.shape[0], *x.shape[2:]), np.float64)
        for channel in range(weight.shape[0]):
            for ky in range(3):
                for kx in range(3):
                    out[:, channel] += np.sum(padded[:, :, ky:ky+x.shape[2], kx:kx+x.shape[3]] * weight[channel, :, ky, kx].astype(np.float64)[None, :, None, None], axis=1)
        return out
    def gn(x, gamma, beta, config):
        flat = x.reshape(4, -1)
        out = np.empty_like(flat)
        for group in range(4):
            centered = flat[group] - np.mean(flat[group], dtype=np.float64)
            out[group] = centered / np.sqrt(np.mean(centered * centered, dtype=np.float64) + config['epsilon'])
        return out.reshape(x.shape) * gamma.astype(np.float64) + beta.astype(np.float64)
    def gelu(a):
        return (a * (1 + erf(a / float(np.float32(np.sqrt(2)))))) * .5
    def pool(x):
        height, width = x.shape[2] // 2, x.shape[3] // 2
        a = x[:, :, :height*2, :width*2]
        return (((a[:, :, ::2, ::2] + a[:, :, ::2, 1::2]) + a[:, :, 1::2, ::2]) + a[:, :, 1::2, 1::2]) * .25
    candidate = m.t.read_tensor(case['candidateInput'])
    a = candidate.astype(np.float64)
    skips = {}
    for block in ('enc1', 'enc2', 'enc3'):
        if block != 'enc1':
            a = save(block + 'AveragePool64', pool(a))
        prefix = 'encoder' if block == 'enc3' else block
        weight = params['firstEncoderConv' if block == 'enc3' else block + 'Conv0']
        configs = p['encoderGroupNorms'] if block == 'enc3' else p['frontEncoders'][block]['groupNorms']
        a = save(block + 'FirstConv64', conv(a, weight))
        for i, suffix, tag in [(0, '1', 'First'), (1, '4', 'Last')]:
            a = save(block + tag + 'Gn64', gn(a, params[prefix + 'Gamma' + suffix], params[prefix + 'Beta' + suffix], configs[i]))
            a = save(block + tag + 'Gelu64', gelu(a))
            if i == 0:
                a = save(block + 'SecondConv64', conv(a, params[prefix + 'Conv3']))
        skips[block] = a
    ratios = m.t.read_tensor(case['resizeRatios'])
    a = save('deepResize64', coordinates.scalar_reference(a, skips['enc2'].shape[2:], ratios))
    a = save('deepConcat64', np.concatenate((a, skips['enc2']), axis=1))
    a = save('deepConv1_64', conv(a, params['deepConv0']))
    for i, suffix in enumerate(('1', '4')):
        a = save(f'deepGn{i+1}_64', gn(a, params['deepGamma' + suffix], params['deepBeta' + suffix], p['deepGroupNorms'][i]))
        a = save(f'deepGelu{i+1}_64', gelu(a))
        if i == 0:
            a = save('deepConv2_64', conv(a, params['deepConv3']))
    a = save('resize64', coordinates.scalar_reference(a, skips['enc1'].shape[2:], ratios))
    a = save('concat64', np.concatenate((a, skips['enc1']), axis=1))
    a = save('firstConv64', conv(a, params['upstreamConvWeight']))
    a = save('firstGn64', gn(a, params['firstGamma'], params['firstBeta'], p['firstGroupNorm']))
    a = save('firstGelu64', gelu(a))
    a = save('conv64', conv(a, params['convWeight']))
    a = save('lastGn64', gn(a, params['gamma'], params['beta'], p['lastGroupNorm']))
    a = save('lastGelu64', gelu(a))
    delta = np.sum(a * params['deltaWeight'].astype(np.float64).reshape(1, -1, 1, 1), axis=1, keepdims=True) + float(params['deltaBias'][0])
    a = save('delta64', delta)
    a = save('finalMaskAdd64', (candidate[:, 3:4] * np.float32(8) - np.float32(4)).astype(np.float64) + a)
    save('mask32', a.astype(np.float32))
    return result


class FullMaskTests(unittest.TestCase):
    def test_f64_pool_preserves_sub_f32_values_and_odd_floor(self):
        x = np.arange(15, dtype=np.float64).reshape(1, 1, 3, 5)
        x[0, 0, :2, :2] = [[1 + 2**-30, 2], [3, 4]]
        out, _ = m.average_pool64(x)
        expected = float(sum((Fraction.from_float(float(v)) for v in x[0, 0, :2, :2].reshape(-1)), Fraction()) / 4)
        self.assertEqual(out[0, 0, 0, 0], expected)
        self.assertEqual(out.shape, (1, 1, 1, 2))
        self.assertNotEqual(expected, float(np.float32(expected)))
        with self.assertRaises(ValueError): m.average_pool64(x.astype(np.float32))

    def test_computed_resize_skip_and_concat_keep_f64_bits_and_original_coordinates(self):
        graph, topology = coordinates.fixture()
        x = np.arange(12, dtype=np.float64).reshape(1, 2, 2, 3) / 7 + 1e-10
        skip = np.full((1, 3, 5, 7), 1 + 2**-30, np.float64)
        ratios = np.array([0, 0, np.float32(2) / np.float32(5), np.float32(3) / np.float32(7)], np.float32)
        out, stats = m.resize64(x, skip, ratios, graph, topology)
        np.testing.assert_array_equal(out, coordinates.scalar_reference(x, (5, 7), ratios))
        cat, _ = m.concat64(out, skip)
        np.testing.assert_array_equal(cat[:, 2:], skip)
        self.assertEqual(stats['skipFeatureDomain'], 'float64')
        with self.assertRaises(ValueError): m.resize64(x, skip.astype(np.float32), ratios, graph, topology)
        with self.assertRaises(ValueError): m.concat64(out, skip.astype(np.float32))

    def test_original_front_parameters_pool_and_invalid_variants(self):
        graph = front_graph()
        params, config = m.encoder_parameters(graph)
        self.assertEqual(params['enc1Conv0'].shape, (16, 4, 3, 3))
        self.assertEqual(params['enc2Conv0'].shape, (32, 16, 3, 3))
        self.assertEqual(len(config['frontParameterBindings']), 16)
        self.assertEqual(config['frontEncoders']['enc1']['groupNorms'][0]['epsilon'], float(np.float32(1e-5)))
        bad = copy.deepcopy(graph)
        next(n for n in bad.graph.node if n.name == '/enc1/enc1.0/Conv').input.append('bias')
        with self.assertRaises(ValueError): m.encoder_parameters(bad)
        bad = copy.deepcopy(graph)
        next(a for n in bad.graph.node if n.name == 'pool1' for a in n.attribute if a.name == 'ceil_mode').i = 1
        with self.assertRaises(ValueError): m.encoder_parameters(bad)

    def test_all_39_arrays_match_independent_reference_and_full_replay_only_one_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            m.validate_contract(p)
            oracle = independent_arrays(c, p, params)
            journal = m.StageJournal(root, {}, c, m.BRANCHES[0])
            original_run = journal.run
            actual_arrays = {}
            def observe(stage, inputs, function, shape, dtype):
                def measured():
                    array, stats = function()
                    actual_arrays[stage] = array.copy()
                    return array, stats
                return original_run(stage, inputs, measured, shape, dtype)
            journal.run = observe
            actual = m.evaluate(c, p, params, graph, journal)
            self.assertEqual(list(actual_arrays), list(m.STAGES))
            for stage in m.STAGES:
                np.testing.assert_allclose(actual_arrays[stage], oracle[stage], rtol=0, atol=2e-12, err_msg=stage)
            np.testing.assert_array_equal(actual_arrays['mask32'], oracle['mask32'])
            replay = m.StageJournal(root, {}, c, m.BRANCHES[0], True)
            self.assertEqual(actual, m.evaluate(c, p, params, graph, replay))
            self.assertEqual(len(list((root / 'results').glob('*.bin'))), 1)
            self.assertEqual(len(list((root / 'events').glob('*.json'))), 78)

    def test_both_skips_are_computed_unrounded_not_original_backend_activations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            observed = []
            original = m.resize64
            def inspect(x, skip, *args):
                observed.append(skip.copy())
                return original(x, skip, *args)
            with patch.object(m, 'resize64', side_effect=inspect):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0]))
            self.assertEqual(len(observed), 2)
            oracle = independent_arrays(c, p, params)
            for array, stage in zip(observed, ('enc2LastGelu64', 'enc1LastGelu64'), strict=True):
                self.assertEqual(array.dtype, np.float64)
                self.assertGreater(float(np.abs(array - array.astype(np.float32).astype(np.float64)).max()), 0)
                np.testing.assert_allclose(array, oracle[stage], rtol=0, atol=2e-12)

    def test_unsaved_stage_hash_and_saved_mask_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0]))
            path = next((root / 'events').glob('*enc1LastGelu64-done.json'))
            original = path.read_bytes()
            value = json.loads(original); value['output']['bytesSha256'] = '0' * 64
            path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'full mask bytes'):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0], True))
            path.write_bytes(original)
            raw = next((root / 'results').glob('*.bin'))
            data = bytearray(raw.read_bytes()); data[0] ^= 1; raw.write_bytes(data)
            with self.assertRaises(ValueError):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0], True))

    def test_original_activations_are_audit_only_and_do_not_feed_mask(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = case_fixture(root)
            row = m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0]))
            final = m.t.read_tensor(row['stages'][-1]['savedRaw'])
            other = root / 'other'; other.mkdir(); (other / 'events').mkdir(); (other / 'results').mkdir()
            altered = copy.deepcopy(c)
            for origin, values in altered['originalObservedLayersAuditOnly'].items():
                for key, ref in list(values.items()):
                    array = np.full(ref['shape'], 999., np.float32)
                    values[key] = m.t.save(root / (origin + '-' + key + '-audit.bin'), array)
            second = m.evaluate(altered, p, params, graph, m.StageJournal(other, {}, altered, m.BRANCHES[0]))
            np.testing.assert_array_equal(final, m.t.read_tensor(second['stages'][-1]['savedRaw']))
            self.assertNotEqual(row['encoderBoundaryAgainstOriginalBackendsMaxAbsDiagnosticOnly'], second['encoderBoundaryAgainstOriginalBackendsMaxAbsDiagnosticOnly'])

    def test_budget_gate_role_and_branch_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            c, p, params, graph = case_fixture(Path(folder))
            m.validate_contract(p)
            for key, value in [('expectedRawCount', 2), ('expectedRawBytes', 0), ('requiredMaxAbs', .001), ('newProjectModelInputsAllowed', 1), ('savedStages', ['enc1LastGelu64', 'mask32']), ('branches', ['wasm']), ('singleFinalFloat32Conversions', 2)]:
                changed = copy.deepcopy(p); changed[key] = value
                with self.assertRaises(ValueError): m.validate_contract(changed)
            changed = copy.deepcopy(p); changed['cases'][0]['candidateIdentity']['identity']['split'] = 'val'
            with self.assertRaises(ValueError): m.validate_contract(changed)
            with self.assertRaises(ValueError): m.evaluate(c, p, params, graph, m.StageJournal(Path(folder), {}, c, 'unknown'))


if __name__ == '__main__':
    unittest.main()
