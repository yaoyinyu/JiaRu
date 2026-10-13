"""验证完整分母、零角色预算及逐字节保真不能被近似误差覆盖。"""
import copy
import importlib.util
import unittest
from pathlib import Path

import numpy as np
import onnx

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('repaired_layer_test', ROOT / 'model/training/audit-repaired-native-browser-layerwise.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
ls = importlib.util.spec_from_file_location('layer_pure_test', ROOT / 'model/training/audit-native-layerwise-parity.py')
layer = importlib.util.module_from_spec(ls); ls.loader.exec_module(layer)


def scope():
    return {'purpose': 'repaired_graph_full68_cpu_wasm_webgpu_layerwise_localization_only',
            **dict.fromkeys(('fullCandidateCount', 'instrumentedCpuInputsAllowed', 'instrumentedWasmInputsAllowed', 'instrumentedWebgpuInputsAllowed'), 68),
            **dict.fromkeys(('newTorchInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed'), 0),
            'graphOptimizationLevel': 'disabled', 'requiredNumericDifference': 1e-4, 'requiredDecodedPixelDifferences': 0,
            **dict.fromkeys(('allFinalHeadsMustBeBitwiseIdenticalToSameBackendUninstrumentedCapturesBeforeLayerConclusions', 'addOutputsOnly', 'sameRepairedGraphAndAllLearnedParameters', 'inheritedFull68NonzeroControls', 'failedBrowserBudgetMayNotRestart', 'productHold'), True),
            'formalReleaseAllowed': False}


class Contract(unittest.TestCase):
    def test_scope_exact_denominator(self):
        m.validate_scope(scope())
        for key in ('fullCandidateCount', 'instrumentedCpuInputsAllowed', 'instrumentedWasmInputsAllowed', 'instrumentedWebgpuInputsAllowed'):
            p = scope(); p[key] = 67
            with self.assertRaises(ValueError): m.validate_scope(p)

    def test_zero_roles_and_torch(self):
        for key in ('newTorchInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed'):
            p = scope(); p[key] = 1
            with self.assertRaises(ValueError): m.validate_scope(p)

    def test_fixed_gate_and_release(self):
        for key, value in (('requiredNumericDifference', 2e-4), ('requiredDecodedPixelDifferences', 1), ('formalReleaseAllowed', True)):
            p = scope(); p[key] = value
            with self.assertRaises(ValueError): m.validate_scope(p)

    def test_start_order_and_stable_identity(self):
        c = {'candidateIdentity': {'identity': {'split': 'train', 'imageSha256': 'abc'}}}
        e = {'backend': 'wasm', 'ordinal': 40, 'candidateIdentity': copy.deepcopy(c['candidateIdentity'])}
        m.validate_event(e, ('wasm', 40), c)
        for key, value in (('ordinal', 42), ('backend', 'webgpu'), ('candidateIdentity', {'identity': {'split': 'val'}})):
            bad = copy.deepcopy(e); bad[key] = value
            with self.assertRaises(ValueError): m.validate_event(bad, ('wasm', 40), c)

    def test_full_backend_sequence(self):
        rows = [{'ordinal': i} for i in range(1, 69)]
        self.assertEqual(m.sequence(rows), [('wasm', i) for i in range(1, 69)] + [('webgpu', i) for i in range(1, 69)])

    def test_one_ulp_and_signed_zero_fail_byte_gate(self):
        a = np.array([1.0], dtype=np.float32)
        for b in (np.nextafter(a, np.float32(2)), np.array([np.nan], dtype=np.float32)):
            with self.assertRaises(ValueError): layer.exact(a, b)
        with self.assertRaises(ValueError): layer.exact(np.array([0.0], dtype=np.float32), np.array([-0.0], dtype=np.float32))
        layer.exact(a, a.copy())

    def test_output_only_instrumentation(self):
        nodes = []
        for block in ('enc1', 'enc2', 'enc3', 'dec2', 'dec1'):
            for i, op in enumerate(('Conv', 'Add', 'Mul_1', 'Conv', 'Add', 'Mul_1')):
                name = f'/{block}/{block}.{i}/{op}'
                nodes.append(onnx.helper.make_node('Identity', ['x'], [name + '_out'], name=name))
        nodes.append(onnx.helper.make_node('Identity', ['x'], ['delta'], name='/delta/Conv'))
        graph = onnx.helper.make_graph(nodes, 'fixture', [onnx.helper.make_tensor_value_info('x', onnx.TensorProto.FLOAT, [1, 1, 2, 2])], [onnx.helper.make_tensor_value_info('delta', onnx.TensorProto.FLOAT, [1, 1, 2, 2])])
        model = onnx.helper.make_model(graph); before = model.SerializeToString()
        mapping = layer.instrument(model); self.assertEqual(len(mapping), 31)
        del model.graph.output[1:]
        self.assertEqual(model.SerializeToString(), before)


if __name__ == '__main__': unittest.main()
