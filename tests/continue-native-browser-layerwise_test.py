"""续接合同拒绝预算重用、缺层伪造和文件冲突。"""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('continue_layer_test',ROOT/'model/training/continue-native-browser-layerwise.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def scope():
    return {'purpose':'continue_only_unconsumed_layerwise_inputs_after_transport_failure','fullCandidateCount':68,'newWasmOrdinalsAllowed':list(range(23,69)),'newWebgpuOrdinalsAllowed':list(range(1,69)),'newBrowserInputsAllowed':114,
            **dict.fromkeys(('newCpuInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed'),0),
            'graphOptimizationLevel':'disabled','requiredNumericDifference':1e-4,'requiredDecodedPixelDifferences':0,'maximumUploadAttemptsPerTensor':3,
            'missingWasm22Outputs':['dec1.4','dec1.5','delta'],'lastThreeLayerDenominatorAfterCompletion':{'cpu':68,'wasm':67,'webgpu':68},
            'inheritedCpuOrdinals':list(range(1,69)),'inheritedWasmFinalHeadOrdinals':list(range(1,23)),'inheritedWasmCompleteLayerOrdinals':list(range(1,22)),'inheritedWasmPartialOrdinal':22,
            **dict.fromkeys(('requireFull68FinalHeadBitwiseParityBeforeAnyLayerConclusion','full31AllBackendConclusionProhibited','firstCrossingNotRootCauseProof','allOriginalFailuresAndConsumedBudgetsPreserved','failedBrowserBudgetMayNotRestart','inheritedNonzeroControls','uploadRetryMustNotReexecuteModel','uploadAcknowledgmentsMustBindSha256AndByteCount','consumeResponseBodies','strictGetStatusBeforeUploadOnlyRetry','productHold'),True),'formalReleaseAllowed':False}


class Contract(unittest.TestCase):
    def test_exact_remaining_budget(self):
        m.validate_scope(scope());self.assertEqual(len(m.ordered_pairs(scope())),114)
        for key,value in (('newWasmOrdinalsAllowed',list(range(22,69))),('newWebgpuOrdinalsAllowed',list(range(2,69))),('newBrowserInputsAllowed',115)):
            p=scope();p[key]=value
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_zero_training_and_protected_roles(self):
        for key in ('newCpuInputsAllowed','newTorchInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed'):
            p=scope();p[key]=1
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_missing_layers_never_filled(self):
        for key,value in (('missingWasm22Outputs',[]),('lastThreeLayerDenominatorAfterCompletion',{'cpu':68,'wasm':68,'webgpu':68}),('full31AllBackendConclusionProhibited',False)):
            p=scope();p[key]=value
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_quality_and_recovery_not_weakened(self):
        for key,value in (('requiredNumericDifference',2e-4),('requiredDecodedPixelDifferences',1),('uploadRetryMustNotReexecuteModel',False),('strictGetStatusBeforeUploadOnlyRetry',False),('formalReleaseAllowed',True)):
            p=scope();p[key]=value
            with self.assertRaises(ValueError):m.validate_scope(p)

    def test_start_uuid_identity_and_page_claim(self):
        c={'candidateIdentity':{'identity':{'split':'train','fileName':'fixture','imageSha256':'abc'}}}
        event={'backend':'wasm','ordinal':23,'candidateIdentity':copy.deepcopy(c['candidateIdentity']),'inputRequestId':'00000000-0000-4000-8000-000000000001','pageRequestId':'claim'}
        m.validate_event(event,('wasm',23),c,'claim')
        for key,value in (('ordinal',22),('pageRequestId','another-page'),('inputRequestId','not-uuid'),('candidateIdentity',{'identity':{'split':'val'}})):
            e=copy.deepcopy(event);e[key]=value
            with self.assertRaises(ValueError):m.validate_event(e,('wasm',23),c,'claim')

    def test_duplicate_upload_inherits_only_identical_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tensor.bin';body=b'\x00\x00\x80\x3f'
            self.assertTrue(m.write_exact(path,body));self.assertFalse(m.write_exact(path,body))
            with self.assertRaises(ValueError):m.write_exact(path,body+b'\x00')
            self.assertEqual(path.read_bytes(),body)


if __name__=='__main__':unittest.main()
