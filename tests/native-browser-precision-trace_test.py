"""追踪保真失败必须拒绝结论；统计不能替代原参考。"""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx

R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('precision_trace_test',R/'model/training/audit-native-browser-precision-trace.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def scope():
    return {'purpose':'full68_resize_coordinate_and_groupnorm_statistics_trace_only','cases':[{'ordinal':i,'operations':[{'expected':{'shape':[1,32,13,17]}},{'expected':{'shape':[1,16,13,17]}}]} for i in range(1,69)],
            'traceOperatorInputsPerBackendAllowed':{'cpu':136,'wasm':136,'webgpu':136},'newAnalyticalFp64StatisticsAllowed':68,
            **dict.fromkeys(('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed'),0),
            'groupNorm':{'groups':4,'channels':16,'epsilon':1e-5},'graphOptimizationLevel':'disabled','fullModelRequiredNumericDifference':1e-4,'fullModelRequiredDecodedPixelDifferences':0,
            'traceOperations':[{'operationIndex':0,'operation':'resize_d2_to_e1_repaired','additionalOutputs':['a']*10},{'operationIndex':1,'operation':'dec1.4_group_norm','additionalOutputs':['b']*6}],
            **dict.fromkeys(('addOutputsOnly','allFinalOperatorOutputsMustMatchSameBackendUninstrumentedCapturesBitwiseBeforeAnyConclusion','finalReferenceMustComeFromOriginalOperatorReport','freezeNativeShapesFloat32FiniteAndStableIdentities','fp64StatisticsDiagnosticOnlyNotReplacementCudaReference','webgpuOnlyResizeRepairCannotCloseExistingWasmFailure','newFull68NonzeroControlsAndAllBackendModelGatesRequiredAfterRepair','allOldFailuresAndMissingWasm22LayerOutputsPreserved','productHold'),True),'formalReleaseAllowed':False}


class Contract(unittest.TestCase):
    def test_budget_and_roles(self):
        p=scope();m.validate_scope(p)
        for key,value in [('traceOperatorInputsPerBackendAllowed',{'cpu':136,'wasm':135,'webgpu':136}),('newAnalyticalFp64StatisticsAllowed',67),('newFullModelInputsAllowed',1),('newTorchInputsAllowed',1),('valInputsAllowed',1),('protectedInputsAllowed',1)]:
            changed=copy.deepcopy(p);changed[key]=value
            with self.assertRaises(ValueError):m.validate_scope(changed)

    def test_reference_and_quality_guards(self):
        p=scope()
        for key,value in [('groupNorm',{'groups':4,'channels':16,'epsilon':2e-5}),('fullModelRequiredNumericDifference',2e-4),('fullModelRequiredDecodedPixelDifferences',1),('allFinalOperatorOutputsMustMatchSameBackendUninstrumentedCapturesBitwiseBeforeAnyConclusion',False),('fp64StatisticsDiagnosticOnlyNotReplacementCudaReference',False),('formalReleaseAllowed',True)]:
            changed=copy.deepcopy(p);changed[key]=value
            with self.assertRaises(ValueError):m.validate_scope(changed)

    def test_sequence_and_scalar_shapes(self):
        p=scope();self.assertEqual(len(m.sequence(p,['wasm','webgpu'])),272)
        for case in p['cases']:
            self.assertEqual(len(m.shapes(case,0)),11);self.assertEqual(m.shapes(case,0)[1],[])
            self.assertEqual(m.shapes(case,1)[1:],[ [1], *[[1,4,1] for _ in range(5)] ])

    def test_added_outputs_only(self):
        h=onnx.helper
        model=h.make_model(h.make_graph([h.make_node('Identity',['x'],['y'])],'fixture',[h.make_tensor_value_info('x',onnx.TensorProto.FLOAT,[1])],[h.make_tensor_value_info('y',onnx.TensorProto.FLOAT,[1])]),opset_imports=[h.make_opsetid('',18)])
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.onnx';b=Path(folder)/'b.onnx';onnx.save(model,a)
            model.graph.output.append(h.make_tensor_value_info('x',onnx.TensorProto.FLOAT,[1]));onnx.save(model,b)
            spec={'originalGraph':m.d.bind(a),'instrumentedGraph':m.d.bind(b),'originalFinalOutput':'y','additionalOutputs':['x'],'operation':'fixture','operationIndex':1}
            m.graph_guard(spec)
            model.graph.node[0].op_type='Neg';onnx.save(model,b);spec['instrumentedGraph']=m.d.bind(b)
            with self.assertRaises(ValueError):m.graph_guard(spec)

    def test_final_bitwise_rejection_including_signed_zero(self):
        class Layer:
            def read_tensor(self,precision,ref):return ref
            def exact(self,a,b):
                if a.shape!=b.shape or a.tobytes()!=b.tobytes():raise ValueError('reconstruction_mismatch')
        a=np.array([0,1],np.float32);m.exact_final(Layer(),None,a,a.copy())
        for b in (np.array([-0.,1],np.float32),np.array([0,np.nextafter(np.float32(1),np.float32(2))],np.float32)):
            with self.assertRaises(ValueError):m.exact_final(Layer(),None,a,b)


if __name__=='__main__':unittest.main()
