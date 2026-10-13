"""合成可观测性控制必须保留固定范围、身份及正式质量边界。"""
import copy
import importlib.util
import unittest
from pathlib import Path

R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('observability_control_test',R/'model/training/audit-native-trace-observability-copy-control.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def scope():
    return {'purpose':'synthetic_nonzero_resize_trace_observability_control_only','controlOperatorInputsPerBackendAllowed':{'cpu':6,'wasm':6,'webgpu':6},
            'models':[{'variantIndex':i,'name':name,'outputNames':['y']*count} for i,(name,count) in enumerate([('baseline',1),('identity_vector_copies',5),('add_zero_vector_copies',5)])],
            'cases':[{'ordinal':i,'identity':f'control_{i}','noProjectImageOrLearnedInput':True,'targetShape':[1,32,23,27],'variantOutputNames':[['y'],['y','observation_native_y_shifted','observation_native_y_lambda1','observation_native_x_shifted','observation_native_x_lambda1'],['y','observation_native_y_shifted','observation_native_y_lambda1','observation_native_x_shifted','observation_native_x_lambda1']]} for i in (1,2)],
            **dict.fromkeys(('learnedInputsAllowed','newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newProjectImageInputsAllowed'),0),
            **dict.fromkeys(('noModelQualityOrCudaRootCauseClaimFromSyntheticControls','finalOutputMustMatchSameBackendBaselineBitwise','allVariantsMustPreserveOriginalNodesInitializersInputsAndFinalOutput','newLearnedFull68TraceRequiresSeparateScopeAndWholeDenominatorFidelity','jointWasmAndWebgpuFailureStillMustCloseBeforeFullModelOrVal','diagnosticCopyNodesOnlyAllowed','copiesNeverFeedOriginalNodes','copyValuesNotAutomaticallyOriginalRuntimeValues','productHold'),True),
            'graphOptimizationLevel':'disabled','fullModelRequiredNumericDifference':1e-4,'fullModelRequiredDecodedPixelDifferences':0,'formalReleaseAllowed':False}


class Contract(unittest.TestCase):
    def test_budget_denominator_and_roles(self):
        p=scope();m.validate_scope(p)
        for key in ('learnedInputsAllowed','newFullModelInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newProjectImageInputsAllowed'):
            q=copy.deepcopy(p);q[key]=1
            with self.assertRaises(ValueError):m.validate_scope(q)
        q=scope();q['controlOperatorInputsPerBackendAllowed']['wasm']=7
        with self.assertRaises(ValueError):m.validate_scope(q)

    def test_observation_variants_and_stable_identity(self):
        for change in ('variant','ordinal','identity'):
            q=scope()
            if change=='variant':q['models'][2]['outputNames'].pop()
            elif change=='ordinal':q['cases'][1]['ordinal']=1
            else:q['cases'][1]['identity']=q['cases'][0]['identity']
            with self.assertRaises(ValueError):m.validate_scope(q)

    def test_quality_and_synthetic_boundaries(self):
        for key,value in [('noModelQualityOrCudaRootCauseClaimFromSyntheticControls',False),('finalOutputMustMatchSameBackendBaselineBitwise',False),('newLearnedFull68TraceRequiresSeparateScopeAndWholeDenominatorFidelity',False),('fullModelRequiredNumericDifference',2e-4),('fullModelRequiredDecodedPixelDifferences',1),('formalReleaseAllowed',True)]:
            q=scope();q[key]=value
            with self.assertRaises(ValueError):m.validate_scope(q)

    def test_scalar_vector_shapes_and_full_sequence(self):
        case=scope()['cases'][0]
        self.assertEqual(m.shapes(case,0),[[1,32,23,27]])
        self.assertEqual(m.shapes(case,1),[[1,32,23,27],[23],[23],[27],[27]])
        self.assertEqual(m.shapes(case,2),[[1,32,23,27],[23],[23],[27],[27]])
        self.assertEqual(m.sequence(scope(),['wasm','webgpu']),[(b,i,o) for b in ('wasm','webgpu') for i in range(3) for o in (1,2)])

    def test_event_refuses_input_identity_drift(self):
        case={'candidateIdentity':{'syntheticControl':'control_1'},'operations':[{'input':{'sha256':'tensor'},'expected':{'shape':[1,32,23,27]}}]}
        event={'backend':'wasm','operationIndex':0,'operation':'baseline','ordinal':1,'candidateIdentity':case['candidateIdentity'],'inputSha256':'tensor','targetShape':[1,32,23,27],'inputRequestId':'00000000-0000-4000-8000-000000000001','pageRequestId':'page'}
        m.validate_event(event,('wasm',0,1),case,{'name':'baseline'},'page')
        for key,value in [('inputSha256','other'),('candidateIdentity',{'syntheticControl':'other'}),('targetShape',[1,32,22,27]),('pageRequestId','other')]:
            q=copy.deepcopy(event);q[key]=value
            with self.assertRaises(ValueError):m.validate_event(q,('wasm',0,1),case,{'name':'baseline'},'page')


if __name__=='__main__':unittest.main()
