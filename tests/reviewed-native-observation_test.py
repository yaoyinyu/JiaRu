"""观测图不得改原运算；全范围控制及合成基线不得混充通过。"""
import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import onnx
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('native_observation_tests',R/'model/training/prepare-reviewed-native-observation.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Tests(unittest.TestCase):
    def fixture(self):
        original=onnx.helper.make_model(onnx.helper.make_graph([
            onnx.helper.make_node('Identity',['x'],['mask_logits'],name='head'),
            onnx.helper.make_node('Identity',['x'],['presence_logit'],name='presence'),
            onnx.helper.make_node('Identity',['x'],['observation'],name='candidate')], 'fixture',
            [onnx.helper.make_tensor_value_info('x',onnx.TensorProto.FLOAT,[1,1,2,3])],
            [onnx.helper.make_tensor_value_info(n,onnx.TensorProto.FLOAT,[1,1,2,3]) for n in ('mask_logits','presence_logit')]))
        return original,[{'module':'candidate','node':'candidate','tensor':'observation','operation':'Identity'}]

    def test_add_outputs_reverses_complete_original_bytes(self):
        original,rows=self.fixture()
        with patch.object(m,'mapping',return_value=rows):
            model=m.add_outputs(original,rows); m.verify_graph(original,model,rows)
            self.assertEqual(len(model.graph.output),3)

    def test_changed_original_node_rejected(self):
        original,rows=self.fixture()
        with patch.object(m,'mapping',return_value=rows):
            model=m.add_outputs(original,rows); model.graph.node[0].name='changed'
            with self.assertRaisesRegex(ValueError,'complete graph'): m.verify_graph(original,model,rows)

    def test_removed_or_reordered_output_rejected(self):
        original,rows=self.fixture()
        with patch.object(m,'mapping',return_value=rows):
            model=m.add_outputs(original,rows); del model.graph.output[-1]
            with self.assertRaises(ValueError): m.verify_graph(original,model,rows)

    def test_actual_mapping_rejects_unknown_graph(self):
        original,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'semantic'): m.mapping(original)

    def test_independent_control_has_binary_seed_and_nonzero_rgb(self):
        a=m.independent_input(31,37,7); self.assertTrue(np.array_equal(a,m.independent_input(31,37,7)))
        self.assertEqual(set(np.unique(a[:,3])),{0.,1.}); self.assertEqual(a.dtype,np.float32)

    def test_native_shapes_preserve_odd_pooling(self):
        rows=[{'module':'enc2.0'},{'module':'enc3.0'},{'module':'dec1.4'}]
        actual=m.shapes(99,109,rows)
        self.assertEqual(actual['layer00'],[1,32,49,54]); self.assertEqual(actual['layer01'],[1,64,24,27])
        self.assertEqual(actual['layer02'],[1,16,99,109])

    def test_baseline_missing_or_failed_control_never_admits_learned(self):
        report={'ok':True,'kind':'control','allOwnHeadsBitwiseIdenticalAllBackends':True,
            'records':[{'backend':b,'ordinal':o,'ownHeadsBitwiseIdentical':True} for b in ('cpu','wasm','webgpu') for o in (1,2)]}
        m.require_fidelity(report,2,'control')
        for change in ('baseline','missing','failed'):
            bad=copy.deepcopy(report)
            if change=='baseline': bad['syntheticBaselineOnly']=True
            elif change=='missing': bad['records'].pop()
            else: bad['records'][-1]['ownHeadsBitwiseIdentical']=False
            with self.assertRaises(ValueError): m.require_fidelity(bad,2,'control')


if __name__=='__main__': unittest.main()
