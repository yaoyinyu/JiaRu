"""原尺寸插值边界与图保真，拒绝不同坐标语义。"""
import importlib.util
import unittest
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F

s = importlib.util.spec_from_file_location('resize_test', Path(__file__).resolve().parents[1] / 'model/training/onnx-native-bilinear-resize.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


def graph(mode='half_pixel'):
    node = onnx.helper.make_node('Resize', ['x', '', '', 'sizes'], ['y'], name='/Resize', mode='linear', coordinate_transformation_mode=mode)
    g = onnx.helper.make_graph([node], 'fixture', [onnx.helper.make_tensor_value_info('x', onnx.TensorProto.FLOAT, [1, 3, 'h', 'w']),
        onnx.helper.make_tensor_value_info('sizes', onnx.TensorProto.INT64, [4])], [onnx.helper.make_tensor_value_info('y', onnx.TensorProto.FLOAT, [1, 3, 'oh', 'ow'])])
    model = onnx.helper.make_model(g, opset_imports=[onnx.helper.make_opsetid('', 18)]); model.ir_version = 8
    return model


class Tests(unittest.TestCase):
    def test_odd_even_rectangular_and_single_axis_match_torch(self):
        model = graph(); m.rewrite_model(model, ('/Resize',))
        options = ort.SessionOptions(); options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(model.SerializeToString(), sess_options=options, providers=['CPUExecutionProvider'])
        rng = np.random.default_rng(13)
        for shape, size in (((3, 4), (7, 9)), ((4, 3), (8, 6)), ((1, 1), (3, 5)), ((5, 7), (5, 7)), ((7, 9), (3, 4))):
            with self.subTest(shape=shape, size=size):
                x = rng.standard_normal((1, 3, *shape), dtype=np.float32)
                expected = F.interpolate(torch.from_numpy(x), size=size, mode='bilinear', align_corners=False).numpy()
                actual = session.run(None, {'x': x, 'sizes': np.array([1, 3, *size], np.int64)})[0]
                self.assertEqual(actual.shape, expected.shape)
                self.assertLessEqual(float(np.max(np.abs(expected - actual))), 2e-6)

    def test_unsupported_coordinate_semantics_rejected(self):
        with self.assertRaisesRegex(ValueError, 'semantics'): m.rewrite_model(graph('align_corners'), ('/Resize',))

    def test_missing_target_rejected_before_graph_mutation(self):
        model = graph(); before = model.SerializeToString()
        with self.assertRaisesRegex(ValueError, 'missing'): m.rewrite_model(model)
        self.assertEqual(model.SerializeToString(), before)

    def test_unrelated_initializer_metadata_and_outputs_preserved(self):
        model = graph(); model.doc_string = 'fixture'
        model.graph.initializer.append(onnx.numpy_helper.from_array(np.array([13.], np.float32), name='untouched'))
        before = model.SerializeToString(); old_count = len(model.graph.initializer)
        original_node = onnx.NodeProto(); original_node.CopyFrom(model.graph.node[0])
        m.rewrite_model(model, ('/Resize',))
        del model.graph.initializer[old_count:]; del model.graph.node[:]; model.graph.node.append(original_node)
        self.assertEqual(model.SerializeToString(), before)


if __name__ == '__main__': unittest.main()
