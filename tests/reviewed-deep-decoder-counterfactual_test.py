"""深层数学链及只存边界策略的完整重算和篡改拒绝测试。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

R = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load(R / 'model/training/analyze-reviewed-deep-decoder-counterfactual.py', 'deep_decoder_test')
fixture = load(R / 'tests/reviewed-upstream-counterfactual_test.py', 'deep_resize_fixture')


def test_case(root):
    rng = np.random.default_rng(23)

    def save(name, value):
        return m.t.save(root / (name + '.bin'), value.astype(np.float32))

    h, w = 8, 12
    heads = {'mask': save('mask', np.zeros((1, 1, h, w))), 'presence': save('presence', np.ones((1, 1)))}
    candidate = rng.normal(0, .1, (1, 4, h, w))
    candidate[:, 3] = .5
    case = {'ordinal': 1, 'candidateIdentity': {'identity': {'split': 'train', 'fileName': 'fixture', 'imageSha256': 'fixture'}},
            'candidateInput': save('input', candidate), 'resizeRatios': save('ratios', np.full(4, .5)),
            'originalStrictCudaHeads': heads, 'originalCudaDelta': save('delta', np.zeros((1, 1, h, w))),
            'fixedWasmSkip': save('skip', rng.normal(size=(1, 16, h, w))), 'fixedWasmPresence': heads['presence'], 'features': {}}
    for module, shape in [('enc2.5', (1, 32, 4, 6)), ('enc3.5', (1, 64, 2, 3)), ('dec2.5', (1, 32, 4, 6))]:
        case['features'][module] = {origin: save(module + origin, rng.normal(size=shape)) for origin in ('cuda', 'wasm')}
    params = {}
    for name, shape in [('deepConv0', (32, 96, 3, 3)), ('deepConv3', (32, 32, 3, 3)),
                         ('upstreamConvWeight', (16, 48, 3, 3)), ('convWeight', (16, 16, 3, 3)), ('deltaWeight', (1, 16, 1, 1))]:
        params[name] = rng.normal(0, .01, shape).astype(np.float32)
    params['deltaBias'] = np.array([.03], np.float32)
    for suffix in ('1', '4'):
        params['deepGamma' + suffix] = np.ones((32, 1, 1), np.float32)
        params['deepBeta' + suffix] = np.zeros((32, 1, 1), np.float32)
    for prefix in ('first', ''):
        params[prefix + 'Gamma' if prefix else 'gamma'] = np.ones((16, 1, 1), np.float32)
        params[prefix + 'Beta' if prefix else 'beta'] = np.zeros((16, 1, 1), np.float32)
    graph, topology = fixture.fixture()
    eps = float(np.float32(1e-5))
    gelu = {'sqrt2FromOriginalFloat32': float(np.float32(np.sqrt(2))), 'oneFromOriginalFloat32': 1., 'halfFromOriginalFloat32': .5}
    p = {'deepTopology': topology, 'lastTopology': topology, 'maximumOutputPixelsPerChunk': 7,
         'deepGroupNorms': [{'groups': 4, 'epsilon': eps}] * 2, 'deepGelu': gelu, 'gelu': gelu,
         'firstGroupNorm': {'groups': 4, 'epsilon': eps}, 'lastGroupNorm': {'groups': 4, 'epsilon': eps}}
    return case, p, params, graph


class DeepDecoderTests(unittest.TestCase):
    def test_propagated_resize_preserves_sub_float32_values_and_scalar_order(self):
        graph, topology = fixture.fixture()
        x = np.arange(12, dtype=np.float64).reshape(1, 2, 2, 3) / 7 + 1e-10
        skip = np.zeros((1, 3, 5, 7), np.float32)
        ratios = np.array([0, 0, np.float32(2) / np.float32(5), np.float32(3) / np.float32(7)], np.float32)
        actual, stats = m.resize_propagated64(x, skip, ratios, graph, topology)
        np.testing.assert_array_equal(actual, fixture.scalar_reference(x, (5, 7), ratios))
        rounded, _ = m.resize_propagated64(x.astype(np.float32), skip, ratios, graph, topology)
        self.assertGreater(float(np.abs(actual - rounded).max()), 0)
        self.assertFalse(stats['intermediateFloat32Rounding'])

    def test_f32_resize_remains_identical_to_existing_policy(self):
        graph, topology = fixture.fixture()
        x = np.arange(6, dtype=np.float32).reshape(1, 1, 2, 3)
        skip = np.zeros((1, 1, 3, 5), np.float32)
        ratios = np.array([0, 0, 2/3, 3/5], np.float32)
        new, _ = m.resize_propagated64(x, skip, ratios, graph, topology)
        original, _ = m.u.resize64(x, skip, ratios, graph, topology)
        m.m.same_bytes(new, original)
        with self.assertRaises(ValueError):
            m.resize_propagated64(x, skip, ratios.astype(np.float64), graph, topology)

    def test_96_channel_deep_conv_respects_order_and_padding(self):
        x = np.arange(576, dtype=np.float64).reshape(1, 96, 2, 3) / 11
        weight = np.zeros((32, 96, 3, 3), np.float32)
        weight[:, 64, 1, 1] = .5
        weight[:, 0, 0, 1] = -.25
        actual, _ = m.m.decoder.conv64(x, weight, 2)
        expected = np.repeat(x[:, 64:65] * .5, 32, axis=1)
        expected[:, :, 1, :] -= x[:, 0:1, 0, :] * .25
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-14)

    def test_complete_streamed_chain_replays_every_stage_with_only_two_raws(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = test_case(root)
            journal = m.StageJournal(root, {'path': 'fixture', 'sha256': 'fixture'}, c, m.BRANCHES[0])
            actual = m.evaluate(c, p, params, graph, journal)
            replay = m.StageJournal(root, journal.execution_ref, c, journal.branch, True)
            self.assertEqual(actual, m.evaluate(c, p, params, graph, replay))
            self.assertEqual([r['stage'] for r in actual['stages']], list(m.STAGES))
            self.assertEqual(len(list((root / 'results').glob('*.bin'))), 2)
            self.assertEqual(len(list((root / 'events').glob('*.json'))), 2 * len(m.STAGES))
            self.assertEqual([r['stage'] for r in actual['stages'] if 'savedRaw' in r], list(m.SAVED))

    def test_unsaved_intermediate_hash_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = test_case(root)
            j = m.StageJournal(root, {}, c, m.BRANCHES[0]); m.evaluate(c, p, params, graph, j)
            path = next((root / 'events').glob('*deepGn1_64-done.json'))
            value = json.loads(path.read_bytes()); value['output']['bytesSha256'] = '0' * 64
            path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'full stage bytes'):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0], True))

    def test_saved_boundary_tamper_and_missing_event_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = test_case(root)
            j = m.StageJournal(root, {}, c, m.BRANCHES[0]); m.evaluate(c, p, params, graph, j)
            path = next((root / 'results').glob('*deepGelu2_64.bin'))
            old = path.read_bytes(); path.write_bytes(b'\0' * len(old))
            with self.assertRaises(ValueError):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0], True))
            path.write_bytes(old)
            next((root / 'events').glob('*deepConv2_64-start.json')).unlink()
            with self.assertRaises(FileNotFoundError):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, m.BRANCHES[0], True))

    def test_order_shape_finite_and_consumed_start_cannot_be_bypassed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            j = m.StageJournal(root, {}, {'ordinal': 1, 'candidateIdentity': {}}, 'fixture')
            with self.assertRaises(ValueError):
                j.run('mask32', {}, lambda: (np.ones(1), {}), (1,), 'float64')
            with self.assertRaises(ValueError):
                j.run(m.STAGES[0], {}, lambda: (np.ones(2), {}), (1,), 'float64')
            with self.assertRaises(FileExistsError):
                j.run(m.STAGES[0], {}, lambda: (np.ones(1), {}), (1,), 'float64')
            with self.assertRaises(ValueError): m.descriptor(np.array([np.nan]))
            with self.assertRaises(ValueError): m.descriptor(np.array([1], np.int64))

    def test_descriptors_bind_shape_dtype_and_complete_bytes(self):
        a = np.arange(6, dtype=np.float64).reshape(2, 3)
        original = m.descriptor(a)
        self.assertNotEqual(original, m.descriptor(a.reshape(3, 2)))
        self.assertNotEqual(original, m.descriptor(a.astype(np.float32)))
        b = a.copy(); b[-1, -1] += 1e-12
        self.assertNotEqual(original['bytesSha256'], m.descriptor(b)['bytesSha256'])


if __name__ == '__main__':
    unittest.main()
