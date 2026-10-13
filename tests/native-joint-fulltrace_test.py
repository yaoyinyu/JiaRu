"""逐层捕获不能越过控制、字节保真和输出存储域门。"""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('fulltrace_test',R/'model/training/audit-native-joint-fulltrace.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class FullTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def raw(self,name,values):
        return m.save(self.root/name,np.asarray(values,dtype=np.float32))
    def test_all_actual_layers_keep_order_without_old_output_count(self):
        mapping=[{'tensor':'v'+str(i),'module':'m'+str(i)} for i in range(37)]
        actual=m.outputs_for(mapping)
        self.assertEqual(len(actual),39)
        self.assertEqual([r['shapeKey'] for r in actual[2:]],[r['module'] for r in mapping])
        self.assertEqual(len({r['key'] for r in actual}),39)
    def test_fidelity_uses_own_kind_backend_and_both_head_bytes(self):
        mask=self.raw('mask.bin',[1,2]);presence=self.raw('presence.bin',[3]);other=self.raw('other.bin',[4])
        c={'ownUninstrumentedHeads':{'control':{'wasm':{'mask':mask,'presence':presence},'webgpu':{'mask':mask,'presence':other}}}}
        self.assertTrue(m.fidelity(c,'control','wasm',{'mask':mask,'presence':presence}))
        self.assertFalse(m.fidelity(c,'control','webgpu',{'mask':mask,'presence':presence}))
    def test_signed_zero_is_not_byte_fidelity(self):
        positive=self.raw('positive.bin',[0.]);negative=self.raw('negative.bin',[-0.]);presence=self.raw('presence.bin',[1.])
        c={'ownUninstrumentedHeads':{'learned':{'cpu':{'mask':positive,'presence':presence}}}}
        self.assertFalse(m.fidelity(c,'learned','cpu',{'mask':negative,'presence':presence}))
    def test_every_tensor_rejects_nonfinite_and_wrong_cardinality(self):
        p=self.root/'nan.bin';np.asarray([np.nan],np.float32).tofile(p)
        with self.assertRaises(ValueError):m.tensor(m.d.bind(p)|{'dtype':'float32','shape':[1]})
        p2=self.root/'finite.bin';np.asarray([1],np.float32).tofile(p2)
        with self.assertRaises(ValueError):m.tensor(m.d.bind(p2)|{'dtype':'float32','shape':[2]})
    def test_failed_control_stops_before_stage_directory_or_session(self):
        target=self.root/'learned'
        with patch.object(m,'resources',return_value=({}, {}, {}, None)),patch.object(m,'control_gate',side_effect=ValueError('all204 control missing')),patch.object(m.ort,'InferenceSession',side_effect=RuntimeError('forbidden inference')) as session:
            with self.assertRaisesRegex(ValueError,'all204'):m.prepare(self.root/'execution.json',target,'learned')
            session.assert_not_called()
            self.assertFalse(target.exists())
    def test_consumed_stage_rejected_before_resources(self):
        target=self.root/'consumed';target.mkdir()
        with patch.object(m,'resources',side_effect=RuntimeError('forbidden resource path')) as resources:
            with self.assertRaisesRegex(ValueError,'consumed'):m.prepare(self.root/'execution.json',target,'control')
            resources.assert_not_called()

if __name__=='__main__':unittest.main()
