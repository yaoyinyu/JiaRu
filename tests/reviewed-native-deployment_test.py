"""图参数映射、完整逆变换、奇数尺寸主机比例及非零控制反例。"""
import copy
import importlib.util
import unittest
from pathlib import Path
import numpy as np
import onnx
from onnx import helper, numpy_helper, TensorProto
import torch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_deployment_tests', ROOT/'model/training/materialize-reviewed-native-deployment.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def fixture(self):
        values = {'delta.weight': np.ones((1, 1, 1, 1), np.float32), 'scale': np.ones((1, 1, 1), np.float32),
                  'bias': np.zeros((1, 1, 1), np.float32), 'presence.bias': np.ones((1, 1), np.float32)}
        nodes = [helper.make_node('Conv', ['candidate', 'delta.weight'], ['conv']),
                 helper.make_node('Mul', ['conv', 'scale'], ['scaled'], name='/enc1/enc1.1/Mul'),
                 helper.make_node('Add', ['scaled', 'bias'], ['mask_logits'], name='/enc1/enc1.1/Add'),
                 helper.make_node('Identity', ['presence.bias'], ['presence_logit'])]
        for i, node in enumerate(nodes):
            if not node.name: node.name = f'node_{i}'
        graph = helper.make_graph(nodes, 'fixture', [helper.make_tensor_value_info('candidate', TensorProto.FLOAT, [1, 1, 2, 3]),
            helper.make_tensor_value_info('resizeRatios', TensorProto.FLOAT, [4])],
            [helper.make_tensor_value_info('mask_logits', TensorProto.FLOAT, [1, 1, 2, 3]), helper.make_tensor_value_info('presence_logit', TensorProto.FLOAT, [1, 1])],
            [numpy_helper.from_array(v, name=k) for k, v in values.items()])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 18)])
        state = {'delta.weight': torch.ones(1, 1, 1, 1)*2, 'enc1.1.weight': torch.ones(1)*3,
                 'enc1.1.bias': torch.ones(1)*4, 'presence.bias': torch.ones(1, 1)*5}
        return model, state

    def test_all_parameters_mapped_by_semantics_and_reverse_exact(self):
        parent, state = self.fixture(); original = parent.SerializeToString(); mapping = m.parameter_map(parent, state)
        self.assertEqual(mapping['enc1.1.weight']['initializer'], 'scale')
        graph = m.graft(parent, state, mapping); m.verify_graft(parent, graph, state, mapping)
        self.assertEqual(parent.SerializeToString(), original)

    def test_unrelated_graph_constant_or_node_change_rejected(self):
        parent, state = self.fixture(); mapping = m.parameter_map(parent, state); graph = m.graft(parent, state, mapping)
        graph.graph.node[-1].name = 'changed_node'
        with self.assertRaises(ValueError): m.verify_graft(parent, graph, state, mapping)

    def test_wrong_affine_map_or_parameter_bytes_rejected(self):
        parent, state = self.fixture(); mapping = m.parameter_map(parent, state)
        bad = copy.deepcopy(mapping); bad['enc1.1.weight']['initializer'] = 'bias'
        with self.assertRaises(ValueError): m.graft(parent, state, bad)
        graph = m.graft(parent, state, mapping); state['presence.bias'] *= 2
        with self.assertRaises(ValueError): m.verify_graft(parent, graph, state, mapping)

    def test_wrong_parameter_dtype_rejected(self):
        parent, state = self.fixture(); state['delta.weight'] = state['delta.weight'].double()
        with self.assertRaises(ValueError): m.parameter_map(parent, state)

    def test_odd_native_host_ratios_order_and_float32(self):
        actual = m.ratios(333, 341)
        expected = np.array([83/166, 85/170, 166/333, 170/341], np.float32)
        self.assertEqual(actual.tobytes(), expected.tobytes())
        with self.assertRaises(ValueError): m.ratios(3, 100)

    def test_control_deterministic_and_both_heads_have_nonzero_weights(self):
        net = m.load(ROOT/'model/training/native-multiscale-conditional-refiner-v3.py', 'control_fixture_net')
        a = m.control_state(net); b = m.control_state(net)
        self.assertTrue(all(a[k].numpy().tobytes() == b[k].numpy().tobytes() for k in a))
        self.assertTrue(a['delta.weight'].count_nonzero() > 0); self.assertTrue(a['presence.weight'].count_nonzero() > 0)


if __name__ == '__main__': unittest.main()
