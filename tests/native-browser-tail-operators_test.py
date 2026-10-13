"""三算子合同不得缩小分母、放宽数值门或漂移存档输入。"""
import copy
import importlib.util
import unittest
from pathlib import Path

R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('tail_operator_test',R/'model/training/audit-native-browser-tail-operators.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def scope():
    return {'purpose':'full68_same_saved_strictCuda_input_browser_tail_operator_attribution','fullCandidateCount':68,'operatorInputsAllowedPerBackend':{'cpu':204,'wasm':204,'webgpu':204},
            **dict.fromkeys(('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed'),0),
            'operations':[{'name':n,'inputLayer':x,'diagnosticMaxAbs':limit} for n,x,limit in [('resize_d2_to_e1_repaired','dec2.5',2e-5),('dec1.4_group_norm','dec1.3',1e-4),('delta_conv','dec1.5',1e-4)]],
            'groupNorm':{'groups':4,'channels':16,'epsilon':1e-5},'graphOptimizationLevel':'disabled','requiredFullModelNumericDifference':1e-4,'requiredFullModelDecodedPixelDifferences':0,
            **dict.fromkeys(('learnedAffineAndConvParametersUnchanged','sameStoredInputForEveryBackend','referenceOutputsMustRemainBoundToOriginalTorchCalls','nativeTensorShapeFloat32AndAllFiniteRequired','layerFirstCrossingNotRootCauseProof','oldFailuresAndWasm22MissingOutputsPreserved','all68FinalModelParityRequiredAfterAnyExpressionRepair','nonzeroUntrainedFullModelControlRequiredAfterAnyExpressionRepair','productHold'),True),'formalReleaseAllowed':False}


class Contract(unittest.TestCase):
    def test_exact_denominator_and_budgets(self):
        m.validate_scope(scope())
        for key,value in [('fullCandidateCount',67),('operatorInputsAllowedPerBackend',{'cpu':204,'wasm':201,'webgpu':204})]:
            p=scope();p[key]=value
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_operator_only_and_roles(self):
        for key in ('newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed'):
            p=scope();p[key]=1
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_math_contract_and_gate(self):
        for key,value in [('groupNorm',{'groups':4,'channels':16,'epsilon':2e-5}),('requiredFullModelNumericDifference',2e-4),('requiredFullModelDecodedPixelDifferences',1),('formalReleaseAllowed',True)]:
            p=scope();p[key]=value
            with self.assertRaises(ValueError):m.validate_scope(p)
        p=scope();p['operations'][0]['diagnosticMaxAbs']=1e-4
        with self.assertRaises(ValueError):m.validate_scope(p)

    def test_proof_guards(self):
        for key in ('sameStoredInputForEveryBackend','referenceOutputsMustRemainBoundToOriginalTorchCalls','oldFailuresAndWasm22MissingOutputsPreserved','all68FinalModelParityRequiredAfterAnyExpressionRepair','nonzeroUntrainedFullModelControlRequiredAfterAnyExpressionRepair'):
            p=scope();p[key]=False
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_sequence_full_all_operations(self):
        p={'cases':[{'ordinal':i} for i in range(1,69)]}
        expected=[(b,j,i) for b in ('wasm','webgpu') for j in range(3) for i in range(1,69)]
        self.assertEqual(m.sequence(p,['wasm','webgpu']),expected)

    def test_event_identity_input_and_shape(self):
        case={'candidateIdentity':{'identity':{'split':'train','imageSha256':'abc'}},'operations':[{'input':{'sha256':'tensor'},'expected':{'shape':[1,32,9,11]}}]}
        spec={'name':'resize_d2_to_e1_repaired'}
        event={'backend':'wasm','operationIndex':0,'operation':spec['name'],'ordinal':1,'candidateIdentity':copy.deepcopy(case['candidateIdentity']),'inputSha256':'tensor','targetShape':[1,32,9,11],'inputRequestId':'00000000-0000-4000-8000-000000000001','pageRequestId':'page'}
        m.validate_event(event,('wasm',0,1),case,spec,'page')
        for key,value in [('inputSha256','other'),('targetShape',[1,32,8,11]),('ordinal',2),('operationIndex',1),('pageRequestId','another-page'),('candidateIdentity',{'identity':{'split':'val'}})]:
            e=copy.deepcopy(event);e[key]=value
            with self.assertRaises(ValueError):m.validate_event(e,('wasm',0,1),case,spec,'page')


if __name__=='__main__':unittest.main()
