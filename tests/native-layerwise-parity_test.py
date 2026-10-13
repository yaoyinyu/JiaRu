"""数值诊断不得解释插桩改变后的输出、缺层或弱化合同。"""
import copy
import importlib.util
import unittest
from pathlib import Path

import numpy as np
import onnx

s = importlib.util.spec_from_file_location('layerwise_test', Path(__file__).resolve().parents[1] / 'model/training/audit-native-layerwise-parity.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Tests(unittest.TestCase):
    def test_instrumentation_only_appends_outputs(self):
        nodes = []
        for block in ('enc1', 'enc2', 'enc3', 'dec2', 'dec1'):
            for index, operation in enumerate(('Conv', 'Add', 'Mul_1', 'Conv', 'Add', 'Mul_1')):
                name = f'/{block}/{block}.{index}/{operation}'
                nodes.append(onnx.helper.make_node('Identity', ['input'], [name + '_output_0'], name=name))
        nodes.append(onnx.helper.make_node('Identity', ['input'], ['delta'], name='/delta/Conv'))
        value = onnx.helper.make_tensor_value_info('input', onnx.TensorProto.FLOAT, [1, 1, 3, 3])
        output = onnx.helper.make_tensor_value_info('delta', onnx.TensorProto.FLOAT, [1, 1, 3, 3])
        graph = onnx.helper.make_model(onnx.helper.make_graph(nodes, 'fixture', [value], [output]))
        before = graph.SerializeToString()
        mapping = m.instrument(graph)
        self.assertEqual(len(mapping), 31)
        self.assertEqual(len(graph.graph.output), 32)
        del graph.graph.output[1:]
        self.assertEqual(graph.SerializeToString(), before)

    def test_numeric_small_but_bitwise_changed_head_is_rejected(self):
        a = np.array([1.], np.float32)
        b = np.nextafter(a, np.float32(2))
        with self.assertRaisesRegex(ValueError, 'instrumented final'):
            m.exact(a, b)

    def test_signed_zero_change_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'instrumented final'):
            m.exact(np.array([0.], np.float32), np.array([-0.], np.float32))

    def test_nonfinite_layers_or_heads_on_either_side_are_rejected(self):
        for bad in (np.nan, np.inf, -np.inf):
            for reverse in (False, True):
                values = [np.array([bad], np.float32), np.array([0.], np.float32)]
                if reverse: values.reverse()
                with self.subTest(bad=bad, reverse=reverse), self.assertRaisesRegex(ValueError, 'nonfinite'):
                    m.differences(*values)

    def test_shape_mismatch_is_rejected_before_broadcast(self):
        with self.assertRaisesRegex(ValueError, 'shape'):
            m.differences(np.ones((1, 2), np.float32), np.ones((2,), np.float32))

    def test_scope_rejects_partial_denominator_and_optimization(self):
        plan = {'purpose': 'full68_layerwise_numeric_localization_zero_optimizer',
                'requiredFullCandidateDenominator': 68, 'cpuTorchNativeInputsAllowed': 68,
                'strictCudaNativeInputsAllowed': 68, 'instrumentedOrtNativeInputsAllowed': 68,
                'optimizerStepsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0}
        partial = copy.deepcopy(plan); partial['instrumentedOrtNativeInputsAllowed'] = 2
        with self.assertRaisesRegex(ValueError, 'complete denominator'): m.validate_scope(partial)
        optimized = copy.deepcopy(plan); optimized['optimizerStepsAllowed'] = 1
        with self.assertRaisesRegex(ValueError, 'zero optimization'): m.validate_scope(optimized)


if __name__ == '__main__':
    unittest.main()
