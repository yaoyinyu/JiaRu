"""用独立逐像素标量参考验证原F32坐标与高精度特征传播。"""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import onnx
from onnx import helper as h, numpy_helper as nh

R = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('reviewed_upstream_test', R / 'model/training/analyze-reviewed-upstream-counterfactual.py')
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def fixture():
    nodes = []
    initializers = []

    def constant(name, value, dtype):
        initializers.append(nh.from_array(np.asarray(value, dtype), name))
        return name

    def op(kind, inputs, out, **attrs):
        nodes.append(h.make_node(kind, inputs, [out], name=out, **attrs))
        return out

    op('Shape', ['deep'], 'deepShape')
    op('Shape', ['skip'], 'skipShape')
    zero = constant('zero', 0, np.int64)
    one = constant('one', 1, np.int64)
    half = constant('half', .5, np.float32)
    zero_f = constant('zeroF', 0, np.float32)
    one_f = constant('oneF', 1, np.float32)
    for axis, index, axes in [('y', 2, [0, 1, 3]), ('x', 3, [0, 1, 2])]:
        dim = constant(axis + 'dim', index, np.int64)
        incoming = op('Gather', ['deepShape', dim], axis + 'in', axis=0)
        outgoing = op('Gather', ['skipShape', dim], axis + 'out', axis=0)
        ratio = op('Gather', ['ratios', dim], axis + 'ratio', axis=0)
        indices = op('Range', [zero, outgoing, one], axis + 'index')
        f = op('Cast', [indices], axis + 'indexF', to=onnx.TensorProto.FLOAT)
        center = op('Add', [f, half], axis + 'center')
        scaled = op('Mul', [ratio, center], axis + 'scaled')
        shifted = op('Sub', [scaled, half], axis + 'shifted')
        coord = op('Max', [shifted, zero_f], axis + 'coord')
        floor = op('Floor', [coord], axis + 'floor')
        low_raw = op('Cast', [floor], axis + 'lowRaw', to=onnx.TensorProto.INT64)
        last = op('Sub', [incoming, one], axis + 'last')
        low = op('Min', [low_raw, last], 'z_' + axis + '_lower')
        up = op('Min', [op('Add', [low, one], axis + 'next'), last], 'z_' + axis + '_upper')
        low_f = op('Cast', [low], axis + 'lowF', to=onnx.TensorProto.FLOAT)
        weight1 = op('Sub', [coord, low_f], axis + 'w1')
        weight0 = op('Sub', [one_f, weight1], axis + 'w0')
        unsqueeze = constant(axis + 'axes', axes, np.int64)
        op('Unsqueeze', [weight0, unsqueeze], 'z_' + axis + '_weight0')
        op('Unsqueeze', [weight1, unsqueeze], 'z_' + axis + '_weight1')
    graph = h.make_model(h.make_graph(nodes, 'metadata', [], [], initializer=initializers))
    return graph, {'deepTensor': 'deep', 'skipTensor': 'skip', 'hostRatiosInput': 'ratios', 'resizePrefix': 'z_'}


def scalar_reference(x, size, ratios):
    result = np.empty((1, x.shape[1], *size), np.float64)

    def axis(index, incoming, ratio):
        f = np.float32(index)
        shifted = np.float32(np.float32(np.float32(f + np.float32(.5)) * ratio) - np.float32(.5))
        coord = np.float32(max(float(shifted), 0.))
        low = min(int(np.floor(coord)), incoming - 1)
        up = min(low + 1, incoming - 1)
        weight1 = np.float32(coord - np.float32(low))
        weight0 = np.float32(np.float32(1) - weight1)
        return low, up, float(weight0), float(weight1)

    for channel in range(x.shape[1]):
        for row in range(size[0]):
            y0, y1, wy0, wy1 = axis(row, x.shape[2], ratios[2])
            for col in range(size[1]):
                x0, x1, wx0, wx1 = axis(col, x.shape[3], ratios[3])
                top = wx0 * float(x[0, channel, y0, x0]) + wx1 * float(x[0, channel, y0, x1])
                bottom = wx0 * float(x[0, channel, y1, x0]) + wx1 * float(x[0, channel, y1, x1])
                result[0, channel, row, col] = wy0 * top + wy1 * bottom
    return result


def scope():
    count = 74
    return {'cases': [{'ordinal': i} for i in range(1, count + 1)], 'fullCandidateCount': count,
            'branchCandidateCount': count * 2, 'branches': list(m.BRANCHES),
            'analyticalEvaluationsAllowed': {stage: 2 * count for stage in m.STAGES} | {'total': 2 * count * len(m.STAGES)},
            'singleFinalFloat32Conversions': 2 * count, 'coordinatePolicy': m.POLICY,
            'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
            'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0,
            'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
            'productHold': True, 'formalReleaseAllowed': False, 'fullModelLearnedGatePassed': False}


class UpstreamMathTests(unittest.TestCase):
    def test_odd_asymmetric_resize_exactly_matches_scalar(self):
        graph, topology = fixture()
        x = (np.arange(12, dtype=np.float32).reshape(1, 2, 2, 3) - 3) / np.float32(7)
        skip = np.zeros((1, 3, 5, 7), np.float32)
        ratios = np.asarray([0., 0., np.float32(2) / np.float32(5), np.float32(3) / np.float32(7)], np.float32)
        x.flags.writeable = False
        actual, stats = m.resize64(x, skip, ratios, graph, topology)
        np.testing.assert_array_equal(actual, scalar_reference(x, (5, 7), ratios))
        self.assertEqual(stats['coveredNativePixelsPerChannel'], 35)
        self.assertFalse(stats['actualResizeCaptureClaimed'])
        self.assertEqual(stats['coordinateBindings']['y']['weight0']['dtype'], 'float32')
        self.assertFalse(x.flags.writeable)

    def test_singleton_axes_and_sub_float32_feature_information(self):
        graph, topology = fixture()
        x = np.array([[[[1., 1. + 2**-23]]]], np.float32)
        skip = np.zeros((1, 1, 1, 3), np.float32)
        ratios = np.array([0., 0., 1., np.float32(2) / np.float32(3)], np.float32)
        value, _ = m.resize64(x, skip, ratios, graph, topology)
        np.testing.assert_array_equal(value, scalar_reference(x, (1, 3), ratios))
        self.assertNotEqual(value[0, 0, 0, 1], float(np.float32(value[0, 0, 0, 1])))

    def test_concat_keeps_native_order_and_original_skip_bytes(self):
        resized = np.array([[[[1., 1. + 1e-9]]]], np.float64)
        skip = np.array([[[[3., 4.]], [[5., 6.]]]], np.float32)
        before = skip.tobytes()
        joined, stats = m.concat64(resized, skip)
        np.testing.assert_array_equal(joined[:, :1], resized)
        np.testing.assert_array_equal(joined[:, 1:], skip.astype(np.float64))
        self.assertEqual(skip.tobytes(), before)
        self.assertEqual(stats['orderedInputs'], ['upsampledDeep', 'originalSkip'])
        with self.assertRaises(ValueError):
            m.concat64(resized.astype(np.float32), skip)

    def test_metadata_rejects_neural_unknown_cast_and_cycle(self):
        for node in [h.make_node('Conv', [], ['target']), h.make_node('Cast', ['x'], ['target'], to=onnx.TensorProto.FLOAT16), h.make_node('Add', ['target', 'x'], ['target'])]:
            graph = h.make_model(h.make_graph([node], 'reject', [], []))
            with self.assertRaises(ValueError):
                m.metadata_value(graph, {'x': np.zeros((1,), np.float32)}, 'target')

    def test_invalid_feature_storage_and_nonfinite_rejected(self):
        graph, topology = fixture()
        x = np.ones((1, 1, 1, 1), np.float32)
        ratios = np.ones((4,), np.float32)
        for bad in (x.astype(np.float64), x * np.nan):
            with self.assertRaises(ValueError):
                m.resize64(bad, x, ratios, graph, topology)

    def test_complete_budget_rejects_68_old_tail_and_relaxed_gates(self):
        p = scope()
        m.validate_contract(p)
        for key, value in [('fullCandidateCount', 68), ('analyticalEvaluationsAllowed', {stage: 148 for stage in m.m.STAGES} | {'total': 1036}),
                           ('coordinatePolicy', 'float64_coordinates'), ('requiredMaxAbs', .001),
                           ('requiredDecodedPixelDifferences', 1), ('requiredPresenceDecisionDifferences', 1),
                           ('newProjectModelInputsAllowed', 1), ('protectedInputsAllowed', 1), ('formalReleaseAllowed', True)]:
            bad = copy.deepcopy(p)
            bad[key] = value
            with self.assertRaises(ValueError):
                m.validate_contract(bad)

    def test_48_channel_first_conv_preserves_channel_and_kernel_order(self):
        x = np.arange(192, dtype=np.float64).reshape(1, 48, 2, 2) / 7 + 1e-9
        kernel = np.zeros((16, 48, 3, 3), np.float32)
        kernel[:, 32, 1, 1] = .5
        kernel[:, 0, 0, 1] = -.25
        actual, _ = m.m.decoder.conv64(x, kernel, 3)
        expected = np.repeat(x[:, 32:33] * .5, 16, axis=1)
        expected[:, :, 1, :] -= x[:, 0:1, 0, :] * .25
        np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-15)


if __name__ == '__main__':
    unittest.main()
