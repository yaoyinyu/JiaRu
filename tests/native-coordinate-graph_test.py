"""主机坐标图逆变换与新增输入元数据反例，使用稳定小fixture。"""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import onnx
from onnx import helper, numpy_helper, TensorProto

R = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_coordinate_graph_test', R / 'model/training/prepare-native-coordinate-graph-v2.py')
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


def fixture():
    nodes = []
    tensors = [numpy_helper.from_array(np.zeros((1, 1, 1, 1), np.float32), 'zero'),
               numpy_helper.from_array(np.ones((1, 2, 1, 1), np.float32), 'weight'),
               numpy_helper.from_array(np.ones((1, 1), np.float32), 'presence')]
    current = 'candidate'
    for n, block in enumerate(['dec2', 'dec1']):
        prefix = f'native_bilinear_{n}_'
        for axis in ['y', 'x']:
            for field in ['lower', 'upper', 'weight0', 'weight1']:
                a = np.zeros((2,), np.int64 if field in ['lower', 'upper'] else np.float32)
                nodes.append(helper.make_node('Constant', [], [prefix + axis + '_' + field], name=prefix + axis + '_' + field, value=numpy_helper.from_array(a)))
        nodes.append(helper.make_node('Add', [current, 'zero'], [prefix + 'output'], name=prefix + 'output'))
        nodes.append(helper.make_node('Concat', [prefix + 'output', current], [block + '_concat'], axis=1))
        nodes.append(helper.make_node('Conv', [block + '_concat', 'weight'], [block + '_value'], name=f'/{block}/{block}.0/Conv'))
        current = block + '_value'
    nodes.append(helper.make_node('Identity', [current], ['mask_logits']))
    nodes.append(helper.make_node('Identity', ['presence'], ['presence_logit']))
    graph = helper.make_graph(nodes, 'tiny_native_coordinate_graph',
        [helper.make_tensor_value_info('candidate', TensorProto.FLOAT, [1, 1, 2, 3]), helper.make_tensor_value_info('resizeRatios', TensorProto.FLOAT, [4])],
        [helper.make_tensor_value_info('mask_logits', TensorProto.FLOAT, [1, 1, 2, 3]), helper.make_tensor_value_info('presence_logit', TensorProto.FLOAT, [1, 1])], tensors)
    return helper.make_model(graph, opset_imports=[helper.make_opsetid('', 18)])


class Tests(unittest.TestCase):
    def test_all16_inputs_and_exact_reverse(self):
        original = fixture(); before = original.SerializeToString()
        actual, mapping = g.transform(original)
        self.assertEqual(len(actual.graph.input), 18)
        g.verify(original, actual, mapping)
        self.assertEqual(original.SerializeToString(), before)

    def test_new_input_type_or_shape_tamper_rejected(self):
        original = fixture(); actual, mapping = g.transform(original)
        bad = copy.deepcopy(actual); bad.graph.input[2].type.tensor_type.elem_type = TensorProto.INT32
        with self.assertRaisesRegex(ValueError, 'type/shape'): g.verify(original, bad, mapping)
        bad = copy.deepcopy(actual); bad.graph.input[4].type.tensor_type.shape.dim[2].dim_param = 'wrong_axis'
        with self.assertRaisesRegex(ValueError, 'type/shape'): g.verify(original, bad, mapping)

    def test_unrelated_weight_or_head_change_rejected(self):
        original = fixture(); actual, mapping = g.transform(original)
        bad = copy.deepcopy(actual); bad.graph.initializer[1].raw_data = np.zeros((1, 2, 1, 1), np.float32).tobytes()
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): g.verify(original, bad, mapping)
        bad = copy.deepcopy(actual); bad.graph.output[1].name = 'other_head'
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): g.verify(original, bad, mapping)


if __name__ == '__main__': unittest.main()
