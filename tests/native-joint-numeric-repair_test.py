"""验证输入尺寸比例、分层求和及不可放宽的全候选合同。"""
import copy
import importlib.util
import unittest
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

T=Path(__file__).resolve().parents[1]/'model/training'
def load(name):
    s=importlib.util.spec_from_file_location(name,T/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
repair=load('onnx-native-joint-numeric-repair');resize=load('onnx-native-bilinear-resize');runner=load('audit-native-joint-numeric-operators')

def resize_graph():
    h=onnx.helper
    model=h.make_model(h.make_graph([h.make_node('Resize',['x','','','sizes'],['y'],name='/Resize',mode='linear',coordinate_transformation_mode='half_pixel')],'fixture',
        [h.make_tensor_value_info('x',1,[1,3,'h','w']),h.make_tensor_value_info('sizes',7,[4])],[h.make_tensor_value_info('y',1,[1,3,'oh','ow'])]),opset_imports=[h.make_opsetid('',18)])
    model.ir_version=8;resize.rewrite_model(model,('/Resize',));return model

def sum_graph():
    h=onnx.helper;p='stable_gn_209_'
    nodes=[h.make_node('ReduceSum',['x','axis2'],[p+'mean_total_sum'],name=p+'mean_total_sum',keepdims=1),h.make_node('ReduceSum',['v','axis2'],[p+'variance_total_sum'],name=p+'variance_total_sum',keepdims=1)]
    model=h.make_model(h.make_graph(nodes,'fixture',[h.make_tensor_value_info(k,1,[1,4,'n']) for k in ('x','v')],[h.make_tensor_value_info(p+k,1,[1,4,1]) for k in ('mean_total_sum','variance_total_sum')],[onnx.numpy_helper.from_array(np.array([2],np.int64),name='axis2'),onnx.numpy_helper.from_array(np.array([1e-5],np.float32),name='epsilon')]),opset_imports=[h.make_opsetid('',18)]);model.ir_version=8;return model

def session(model):
    o=ort.SessionOptions();o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;o.intra_op_num_threads=1
    return ort.InferenceSession(model.SerializeToString(),sess_options=o,providers=['CPUExecutionProvider'])

def scope():
    return {'purpose':'joint_host_float32_resize_ratios_and_last_groupnorm_hierarchical_sum_operator_gate','fullCandidateCount':68,'operatorInputsAllowedPerBackend':{'cpu':204,'wasm':204,'webgpu':204},
        'repairOperations':['resize_e3_to_e2','resize_d2_to_e1','dec1.4_group_norm'],**dict.fromkeys(('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newProjectImageInputsAllowed'),0),
        'readinessGate':{'allThreeBackendsAll68AllThreeOperatorsMaxAbs':2e-5,'formalFullModelMaxAbsUnchanged':1e-4,'formalDecodedPixelDifferencesUnchanged':0,'cpuResizeOutputsMustRemainBitwiseSameAsPriorCpuRepair':True,'noFullModelBudgetUntilOperatorGateAndSeparateNonzeroControlScope':True},
        'groupNormPolicy':{'additionalTotalSumChunkLength':128,'originalFirstChunkLength':128,'epsilon':1e-5,'otherNineGroupNormGraphsUnchanged':True},'resizePolicy':{'fullModelInputNotImplementedOrApproved':True,'pythonAndBrowserHostRatioBytesMustMatchAll68':True},'graphOptimizationLevel':'disabled','sourceRolesWeightsEpsilonAndReferencesUnchanged':True,'allOldFailuresAndConsumedBudgetsPreserved':True,'productHold':True,'formalReleaseAllowed':False}

class Tests(unittest.TestCase):
    def test_host_ratio_cpu_bitwise_odd_rectangular(self):
        base=resize_graph();patched=repair.host_resize_ratios(copy.deepcopy(base));a=session(base);b=session(patched);rng=np.random.default_rng(21)
        for shape,target in [((3,4),(7,9)),((4,3),(8,6)),((7,9),(15,19)),((1,1),(3,5))]:
            x=rng.normal(size=(1,3,*shape)).astype(np.float32);feeds={'x':x,'sizes':np.array([1,3,*target],np.int64)}
            y=a.run(None,feeds)[0];z=b.run(None,feeds|{'hostRatios':np.array([np.float32(shape[i])/np.float32(target[i]) for i in range(2)],np.float32)})[0]
            self.assertEqual(y.tobytes(),z.tobytes())

    def test_only_ratio_nodes_and_new_metadata_change(self):
        base=resize_graph();patched=repair.host_resize_ratios(copy.deepcopy(base))
        old={n.name:n.SerializeToString() for n in base.graph.node if not n.output[0].endswith(('_y_ratio','_x_ratio'))}
        self.assertEqual(old,{n.name:n.SerializeToString() for n in patched.graph.node if n.name in old})
        self.assertEqual([x.SerializeToString() for x in base.graph.initializer],[x.SerializeToString() for x in patched.graph.initializer[:-2]])
        self.assertEqual(patched.graph.input[-1].name,'hostRatios')

    def test_ratio_collision_and_missing_nodes_rejected(self):
        g=resize_graph();repair.host_resize_ratios(g)
        with self.assertRaises(ValueError):repair.host_resize_ratios(g)
        with self.assertRaises(ValueError):repair.host_resize_ratios(sum_graph())

    def test_hierarchical_padding_exact_values_and_finite(self):
        s=session(repair.hierarchical_group_sum(sum_graph()))
        for n in (1,127,128,129,513):
            x=np.arange(4*n,dtype=np.float32).reshape(1,4,n)%7;v=x*x
            y,z=s.run(None,{'x':x,'v':v})
            np.testing.assert_array_equal(y,x.sum(axis=2,keepdims=True));np.testing.assert_array_equal(z,v.sum(axis=2,keepdims=True))

    def test_sum_metadata_and_epsilon_unchanged(self):
        g=sum_graph();p=repair.hierarchical_group_sum(copy.deepcopy(g))
        self.assertEqual([x.SerializeToString() for x in g.graph.initializer],[x.SerializeToString() for x in p.graph.initializer[:2]])
        self.assertEqual([x.SerializeToString() for x in g.graph.input],[x.SerializeToString() for x in p.graph.input])
        self.assertEqual([x.SerializeToString() for x in g.graph.output],[x.SerializeToString() for x in p.graph.output])

    def test_missing_sum_target_rejected(self):
        with self.assertRaises(ValueError):repair.hierarchical_group_sum(sum_graph(),'wrong_')

    def test_all68_and_three_backends_required(self):
        runner.validate_scope(scope())
        for k,v in [('fullCandidateCount',67),('operatorInputsAllowedPerBackend',{'cpu':204,'wasm':203,'webgpu':204})]:
            p=scope();p[k]=v
            with self.assertRaises(ValueError):runner.validate_scope(p)

    def test_formal_and_diagnostic_gates_cannot_drift(self):
        for k,v in [('allThreeBackendsAll68AllThreeOperatorsMaxAbs',1e-4),('formalFullModelMaxAbsUnchanged',2e-4),('formalDecodedPixelDifferencesUnchanged',1),('cpuResizeOutputsMustRemainBitwiseSameAsPriorCpuRepair',False)]:
            p=scope();p['readinessGate'][k]=v
            with self.assertRaises(ValueError):runner.validate_scope(p)

    def test_zero_fullmodel_val_and_protected_budget(self):
        for k in ('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newProjectImageInputsAllowed'):
            p=scope();p[k]=1
            with self.assertRaises(ValueError):runner.validate_scope(p)

    def test_epsilon_other_gn_and_future_interface_guard(self):
        for section,key,value in [('groupNormPolicy','epsilon',2e-5),('groupNormPolicy','otherNineGroupNormGraphsUnchanged',False),('resizePolicy','fullModelInputNotImplementedOrApproved',False),('resizePolicy','pythonAndBrowserHostRatioBytesMustMatchAll68',False)]:
            p=scope();p[section][key]=value
            with self.assertRaises(ValueError):runner.validate_scope(p)

if __name__=='__main__':unittest.main()
