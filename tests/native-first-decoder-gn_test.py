"""首GN执行器的分母、跨域误差、阶段顺序及防重启门。"""
import copy
import importlib.util
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
import onnx
from onnx import helper, numpy_helper
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('first_gn_test',R/'model/training/audit-native-first-decoder-gn.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
s=importlib.util.spec_from_file_location('first_gn_comparison_test',R/'model/training/analyze-native-operator-stage-comparison.py');comparison=importlib.util.module_from_spec(s);s.loader.exec_module(comparison)

def scope():
    p={'purpose':'first_decoder_gn_original_then_hierarchical_patch_full68_two_origins_three_backend_isolation','candidateCount':68,'contextsPerModelPerBackend':136,'requiredBackends':['cpu','wasm','webgpu'],'modelsInOrder':['original','patched'],'originalOperatorInputsAllowed':408,'patchedOperatorInputsAllowedOnlyAfterAllOriginalGates':408,'newOnnxOperatorInputsAllowed':816,'graphOptimizationLevel':'disabled','wasmNumThreads':1,'requiredOwnInputFp64NumericDifference':1e-4,'fullModelNumericDifferenceUnchanged':1e-4,'fullModelDecodedPixelDifferencesUnchanged':0,'fullModelPresenceDecisionDifferencesUnchanged':0,'formalReleaseAllowed':False,'fullModelLearnedGatePassed':False,'productHold':True}
    for k in ('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):p[k]=0
    for k in ('originalAll408OwnInputGatesRequiredBeforePatchedStage','allNativeFloat32FiniteOutputsRequired','oldFailuresAndConsumedBudgetsPreserved'):p[k]=True
    p['patch']={'onlyFirstGnMeanAndVarianceTotalSum':True,'originalFirstChunk':128,'additionalSecondChunk':128,'originalGroupCount':4,'originalChannelCount':16,'originalParametersEpsilonAndGeluUnchanged':True,'originalLastGnAndHostRatiosNotModified':True,'reversePatchRestoresOriginalIsolatedModelBytes':True,'isolationDoesNotProveFullGraphFidelity':True}
    p['cases']=[{'contextOrdinal':(i-1)*2+j+1,'candidateOrdinal':i,'inputOrigin':origin,'candidateIdentity':{'identity':{'split':'train','fileName':str(i)}}} for i in range(1,69) for j,origin in enumerate(('wasm_dec1_0','cuda_dec1_0'))]
    return p

class Tests(unittest.TestCase):
    def test_real_stage_comparison_preserves_small_signed_information(self):
        ref=np.array([1.+2**-26,2.],np.float64);original=np.array([1.,2.+2**-21],np.float32);patched=np.array([1.,2.],np.float32)
        result=comparison.compare_pair(ref,original,patched)
        self.assertEqual(result['originalMaxAbs'],2**-21)
        self.assertEqual(result['patchedMaxAbs'],2**-26)
        self.assertEqual(result['actualOutputChangeMaxAbs'],2**-21)

    def test_real_stage_comparison_rejects_mismatched_native_outputs(self):
        ref=np.zeros((1,16,2,3),np.float64);original=ref.astype(np.float32)
        for patched in (original.astype(np.float64),original.reshape(1,16,3,2),original+np.inf):
            with self.assertRaises(ValueError):comparison.compare_pair(ref,original,patched)

    def test_fp64_reference_is_not_rounded_away(self):
        actual=np.array([1.],np.float32);ref=np.array([1.+2**-26],np.float64)
        self.assertEqual(m.differences(ref,actual)['maxAbs'],2**-26)
        self.assertEqual(float(actual[0]-ref.astype(np.float32)[0]),0.)

    def test_reject_domains_shapes_and_nonfinite(self):
        good=np.zeros((1,16,2,3),np.float32);ref=good.astype(np.float64)
        for a,b in ((good,good),(ref,ref),(ref,good.reshape(1,16,3,2)),(ref+np.inf,good)):
            with self.assertRaises(ValueError):m.differences(a,b)

    def test_full_scope_rejects_reduced_denominator_and_budget(self):
        p=scope();m.validate_scope(p)
        for key,value in (('cases',p['cases'][:-1]),('requiredOwnInputFp64NumericDifference',2e-4),('newFullModelInputsAllowed',1),('newOnnxOperatorInputsAllowed',818)):
            wrong=copy.deepcopy(p);wrong[key]=value
            with self.assertRaises(ValueError):m.validate_scope(wrong)
        wrong=copy.deepcopy(p);wrong['cases'][1]['inputOrigin']='wasm_dec1_0'
        with self.assertRaises(ValueError):m.validate_scope(wrong)

    def test_stage_gate_checks_actual_all408_not_outer_pass(self):
        rows=[{'backend':b,'ordinal':o,'numericGatePassed':True,'requiredMaxAbs':1e-4,'difference':{'maxAbs':1e-6}} for b in ('cpu','wasm','webgpu') for o in range(1,137)]
        report={'ok':True,'stage':'original','operatorInputsPerBackend':{'cpu':136,'wasm':136,'webgpu':136},'records':rows,'allOperatorNumericGatesPassed':True}
        m.require_original_gate(report)
        for kind in ('single_failure','hidden_error','duplicate','partial'):
            wrong=copy.deepcopy(report)
            if kind=='single_failure':wrong['records'][80]['numericGatePassed']=False
            elif kind=='hidden_error':wrong['records'][80]['difference']['maxAbs']=1.1e-4
            elif kind=='duplicate':wrong['records'][80]['ordinal']=1
            else:wrong['records'].pop()
            with self.assertRaises(ValueError):m.require_original_gate(wrong)

    def test_event_cannot_exchange_origins_or_candidate(self):
        case=scope()['cases'][0]|{'ordinal':1,'input':{'sha256':'a'},'ownInputFp64Reference':{'shape':[1,16,3,2]}}
        spec={'name':'first_decoder_gn_original'};page=str(uuid.uuid4())
        event={'backend':'wasm','operationIndex':0,'operation':spec['name'],'ordinal':1,'candidateOrdinal':1,'inputOrigin':'wasm_dec1_0','candidateIdentity':case['candidateIdentity'],'inputSha256':'a','targetShape':[1,16,3,2],'inputRequestId':str(uuid.uuid4()),'pageRequestId':page}
        m.validate_event(event,('wasm',0,1),case,spec,page)
        for key,value in (('inputOrigin','cuda_dec1_0'),('candidateOrdinal',2),('targetShape',[1,16,2,3]),('pageRequestId',str(uuid.uuid4()))):
            with self.assertRaises(ValueError):m.validate_event(event|{key:value},('wasm',0,1),case,spec,page)

    def test_existing_budget_rejected_before_resource_or_session(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'resources') as resources:
            with self.assertRaises(ValueError):m.prepare(Path('unused'),Path(temp),'original')
            resources.assert_not_called()

    def test_dependency_cone_keeps_boundary_and_active_initializers(self):
        shape=[1,16,'height','width'];info=lambda n:helper.make_tensor_value_info(n,onnx.TensorProto.FLOAT,shape)
        nodes=[helper.make_node('Identity',['rgb'],['boundary'],name='upstream'),helper.make_node('Add',['boundary','bias'],['output'],name='first_gn_add')]
        graph=helper.make_graph(nodes,'parent',[info('rgb')],[info('output')],[numpy_helper.from_array(np.ones((1,16,1,1),np.float32),'bias'),numpy_helper.from_array(np.array(2,np.float32),'unused')])
        parent=helper.make_model(graph,opset_imports=[helper.make_opsetid('',18)]);before=parent.SerializeToString();result=m.isolated_original(parent,'boundary','output')
        self.assertEqual(parent.SerializeToString(),before)
        self.assertEqual([n.name for n in result.graph.node],['first_gn_add'])
        self.assertEqual([i.name for i in result.graph.initializer],['bias'])
        self.assertEqual(result.graph.initializer[0].SerializeToString(),parent.graph.initializer[0].SerializeToString())

if __name__=='__main__':unittest.main()
