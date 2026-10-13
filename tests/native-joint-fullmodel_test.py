"""完整图回剥、四比例顺序和阶段/两头门禁的稳定小型fixture。"""
import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import onnx
import onnxruntime as ort

T=Path(__file__).resolve().parents[1]/'model/training'
def load(name):
    s=importlib.util.spec_from_file_location(name,T/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
rewriter=load('onnx-native-joint-fullmodel-v2');isolated=load('onnx-native-joint-numeric-repair');runner=load('audit-native-joint-fullmodel');compare=load('verify-native-multiscale-browser-v2')

RATIOS=[f'native_bilinear_{i}_{a}_ratio' for i in (272,376) for a in ('y','x')];TOTALS=['stable_gn_209_'+a+'_total_sum' for a in ('mean','variance')];CONTRACT={'ratioOutputs':RATIOS,'groupNormPrefix':'stable_gn_209_','groupNormNormalizedOutput':'/dec1/dec1.4/InstanceNormalization_output_0'}

def graph():
    h=onnx.helper;nodes=[];init=[];outputs=[]
    for i,name in enumerate(RATIOS):
        a=f'a{i}';b=f'b{i}';init.extend([onnx.numpy_helper.from_array(np.array(7+i,np.float32),name=a),onnx.numpy_helper.from_array(np.array(15+i,np.float32),name=b)])
        nodes.append(h.make_node('Div',[a,b],[name],name=name));outputs.append(h.make_tensor_value_info(name,1,[]))
    init.append(onnx.numpy_helper.from_array(np.array([2],np.int64),name='axis2'));init.append(onnx.numpy_helper.from_array(np.array([1e-5],np.float32),name='epsilon'))
    for name,value in zip(TOTALS,('x','v'),strict=True):nodes.append(h.make_node('ReduceSum',[value,'axis2'],[name],name=name,keepdims=1));outputs.append(h.make_tensor_value_info(name,1,[1,4,1]))
    nodes.append(h.make_node('Div',TOTALS,[CONTRACT['groupNormNormalizedOutput']],name='stable_gn_209_normalized'))
    nodes.append(h.make_node('Identity',['x'],['untouched'],name='other_gn_control'));outputs.append(h.make_tensor_value_info('untouched',1,[1,4,'n']))
    model=h.make_model(h.make_graph(nodes,'fixture',[h.make_tensor_value_info(k,1,[1,4,'n']) for k in ('x','v')],outputs,init),opset_imports=[h.make_opsetid('',18)]);model.ir_version=8;model.doc_string='original fixture';return model

def scope():
    return {'purpose':'joint_fullmodel_nonzero_controls_then_learned_full68_three_backend_gate','fullCandidateCount':68,'requiredBackends':['cpu','wasm','webgpu'],'controlInputsPerBackendAllowed':68,'learnedInputsPerBackendAllowedOnlyAfterAllThreeControlGates':68,'requiredNumericDifference':1e-4,'requiredDecodedPixelDifferences':0,'requiredPresenceDecisionDifferences':0,'graphOptimizationLevel':'disabled','wasmNumThreads':1,
        **dict.fromkeys(('newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'),0),'formalReleaseAllowed':False,'productHold':True,
        **dict.fromkeys(('all204NonzeroControlsMustPassBeforeAnyLearnedInput','allBothHeadsNativeShapeFloat32Finite','implementationExecutionMustBeFrozenBeforeAnyModelBudget','controlsReferenceOriginalDeterministicNonzeroUntrainedTorchOnly','controlCannotSelectQuality','learnedReferenceOriginalStrictCudaOnly','oldFailuresAndConsumedBudgetsPreserved','internalValStillProhibitedUntilNewFullGateAndSeparateScope','productionManifestAndReleaseIdentityUnchanged'),True),
        'newInput':{'name':'resizeRatios','shape':[4],'dtype':'float32','order':'resize_e3_to_e2 y,x; resize_d2_to_e1 y,x','fromOriginalDimensionsOnly':True,'actualBrowserFullVectorMustMatchFrozenBytesBeforeEveryInput':True},
        'patch':{'replaceOnlyFourRatioDivWithGather':True,'onlyLastGroupNormAdditionalSumChunk':128,'originalFirstChunk':128,'groupNormEpsilon':1e-5,'otherNineGroupNormAndAllLearningParametersUnchanged':True,'reversePatchMustRestoreEachOriginalGraphByteForByte':True}}

class Tests(unittest.TestCase):
    def test_roundtrip_all_original_metadata_and_nodes(self):
        base=graph();m=rewriter.rewrite_model(copy.deepcopy(base),isolated,CONTRACT);rewriter.verify_patch(base,m,CONTRACT)
        self.assertEqual(m.graph.input[-1].name,'resizeRatios');self.assertEqual(list(m.graph.input[-1].type.tensor_type.shape.dim)[0].dim_value,4)
        self.assertEqual(next(n for n in base.graph.node if n.name=='other_gn_control').SerializeToString(),next(n for n in m.graph.node if n.name=='other_gn_control').SerializeToString())

    def test_reverse_guard_detects_weight_epsilon_and_metadata_drift(self):
        base=graph();m=rewriter.rewrite_model(copy.deepcopy(base),isolated,CONTRACT)
        for change in ('parameter','epsilon','metadata','unrelated_node'):
            bad=copy.deepcopy(m)
            if change in ('parameter','epsilon'):
                target=bad.graph.initializer[0] if change=='parameter' else next(v for v in bad.graph.initializer if v.name=='epsilon');target.CopyFrom(onnx.numpy_helper.from_array(np.array([2.],np.float32),name=target.name))
            elif change=='metadata':bad.doc_string='changed'
            else:next(n for n in bad.graph.node if n.name=='other_gn_control').name='changed'
            with self.assertRaises(ValueError):rewriter.verify_patch(base,bad,CONTRACT)

    def test_four_ratios_have_exact_order_and_sum_padding(self):
        base=graph();m=rewriter.rewrite_model(copy.deepcopy(base),isolated,CONTRACT);o=ort.SessionOptions();o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;o.log_severity_level=3;o.intra_op_num_threads=1;s=ort.InferenceSession(m.SerializeToString(),sess_options=o,providers=['CPUExecutionProvider'])
        x=np.arange(4*129,dtype=np.float32).reshape(1,4,129)%7;v=x*x;ratios=np.array([np.float32(7+i)/np.float32(15+i) for i in range(4)],np.float32);y=s.run(None,{'x':x,'v':v,'resizeRatios':ratios})
        for i in range(4):self.assertEqual(y[i].tobytes(),ratios[i].tobytes())
        np.testing.assert_array_equal(y[4],x.sum(2,keepdims=True));np.testing.assert_array_equal(y[5],v.sum(2,keepdims=True));np.testing.assert_array_equal(y[6],x)

    def test_missing_ratio_and_duplicate_input_rejected(self):
        m=graph();m.graph.node[0].output[0]='wrong'
        with self.assertRaises(ValueError):rewriter.rewrite_model(m,isolated,CONTRACT)
        m=rewriter.rewrite_model(graph(),isolated,CONTRACT)
        with self.assertRaises(ValueError):rewriter.rewrite_model(m,isolated,CONTRACT)

    def test_denominator_quality_and_forbidden_budgets(self):
        runner.validate_scope(scope())
        for k,v in [('fullCandidateCount',67),('requiredNumericDifference',2e-4),('requiredDecodedPixelDifferences',1),('requiredPresenceDecisionDifferences',1),('valInputsAllowed',1),('protectedInputsAllowed',1),('newTorchInputsAllowed',1),('optimizerStepsAllowed',1)]:
            p=scope();p[k]=v
            with self.assertRaises(ValueError):runner.validate_scope(p)

    def test_all_backend_control_gate_before_any_learned_input(self):
        good={'kind':'control','allThreeBackendStageGatesPassed':True,'modelInputsConsumedPerBackend':{'cpu':68,'wasm':68,'webgpu':68}}
        for bad in [good|{'allThreeBackendStageGatesPassed':False},good|{'modelInputsConsumedPerBackend':{'cpu':68,'wasm':68,'webgpu':67}},good|{'kind':'learned'}]:
            with patch.object(runner,'reconstruct',return_value=bad),patch.object(runner.d,'bind',return_value={'path':'fixture','sha256':'fixture'}),patch.object(runner.d,'read',return_value=bad):
                with self.assertRaises(ValueError):runner.control_gate({'controlRoot':'fixture'})
        p=scope();p['all204NonzeroControlsMustPassBeforeAnyLearnedInput']=False
        with self.assertRaises(ValueError):runner.validate_scope(p)

    def test_decoded_and_presence_gates_independent_of_small_numeric_error(self):
        a=np.array([1e-7],np.float32);b=-a;presence=np.array([1.],np.float32);stats=compare.compare_outputs(a,presence,b,presence,1,1)
        self.assertTrue(stats['numericGatePassed']);self.assertFalse(runner.passed(stats))
        stats=compare.compare_outputs(a,a,a,b,1,1);self.assertFalse(stats['presenceDecisionMatched']);self.assertFalse(runner.passed(stats))
        with self.assertRaises(ValueError):compare.compare_outputs(a,presence,np.array([np.nan],np.float32),presence,1,1)

    def test_event_binds_four_ratio_bytes_and_candidate_identity(self):
        c={'ordinal':1,'candidateIdentity':{'identity':{'split':'train','imageSha256':'source'}},'input':{'sha256':'input'},'resizeRatios':{'sha256':'ratios'},'h':129,'w':131};e=runner.event('control','wasm',c,'page')|{'inputRequestId':'00000000-0000-4000-8000-000000000001'};runner.validate_event(e,'control','wasm',c,'page')
        for k,v in [('resizeRatiosSha256','other'),('inputSha256','other'),('kind','learned'),('ordinal',2),('targetShape',[1,1,128,131]),('candidateIdentity',{'identity':{'split':'val'}})]:
            bad=copy.deepcopy(e);bad[k]=v
            with self.assertRaises(ValueError):runner.validate_event(bad,'control','wasm',c,'page')

if __name__=='__main__':unittest.main()
