"""直连坐标的完整消费者绑定与可逆性反例。"""
import copy
import importlib.util
from pathlib import Path
import unittest
import onnx

R = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


g = load(R / 'model/training/prepare-native-coordinate-graph-v3.py', 'direct_coordinate_graph')
fixture = load(R / 'tests/native-coordinate-graph_test.py', 'original_coordinate_fixture').fixture


def original():
    graph = fixture()
    # 保留实际被消费的两个轴下标，避免只测未使用的输入声明。
    graph.graph.node.extend([
        onnx.helper.make_node('Cast', ['native_bilinear_0_y_lower'], ['used_y'], name='used_y', to=onnx.TensorProto.FLOAT),
        onnx.helper.make_node('Cast', ['native_bilinear_1_x_upper'], ['used_x'], name='used_x', to=onnx.TensorProto.FLOAT)])
    return graph


class Tests(unittest.TestCase):
    def test_direct_all_consumers_and_reverse(self):
        before = original(); raw = before.SerializeToString()
        model, mapping = g.transform(before)
        self.assertEqual(len(model.graph.node), len(before.graph.node) - 16)
        self.assertEqual(len(mapping['consumerSites']), 2)
        hosts = {r['inputName'] for r in mapping['endpoints']}
        self.assertFalse(any(n.op_type == 'Identity' and n.input[0] in hosts for n in model.graph.node))
        g.verify(before, model, mapping)
        self.assertEqual(before.SerializeToString(), raw)

    def test_consumer_and_mapping_tamper_rejected(self):
        before = original(); model, mapping = g.transform(before)
        bad = copy.deepcopy(model)
        next(n for n in bad.graph.node if n.name == 'used_y').input[0] = 'nativeCoord_dec2_y_upper'
        with self.assertRaisesRegex(ValueError, 'consumer'): g.verify(before, bad, mapping)
        wrong = copy.deepcopy(mapping); wrong['consumerSites'].pop()
        with self.assertRaisesRegex(ValueError, 'mapping'): g.verify(before, model, wrong)

    def test_type_and_unrelated_weight_tamper_rejected(self):
        before = original(); model, mapping = g.transform(before)
        bad = copy.deepcopy(model); bad.graph.input[2].type.tensor_type.elem_type = onnx.TensorProto.INT32
        with self.assertRaisesRegex(ValueError, 'type/shape'): g.verify(before, bad, mapping)
        bad = copy.deepcopy(model); bad.graph.output[1].name = 'changed_presence'
        with self.assertRaisesRegex(ValueError, 'reconstruction_mismatch'): g.verify(before, bad, mapping)


if __name__ == '__main__': unittest.main()
