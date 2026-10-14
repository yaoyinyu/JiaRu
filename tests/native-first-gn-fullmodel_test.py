"""首GN完整图的全清单、非零控制、两头有限与禁止重启门。"""
import copy
import importlib.util
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('first_full_gn_test',R/'model/training/audit-native-first-gn-fullmodel.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def scope():
    p={'purpose':'first_gn_only_fullgraph_nonzero_control_then_learned_full68_three_backend','candidateCount':68,'requiredBackends':['cpu','wasm','webgpu'],'stagesInOrder':['control','learned'],'controlInputsPerBackendAllowed':68,'learnedInputsPerBackendAllowedOnlyAfterAllControlGates':68,'newFullModelInputsAllowed':408,'requiredNumericDifference':1e-4,'requiredDecodedPixelDifferences':0,'requiredPresenceDecisionDifferences':0,'graphOptimizationLevel':'disabled','wasmNumThreads':1,'formalReleaseAllowed':False,'fullModelLearnedGatePassed':False,'productHold':True,'firstGnPrefixes':{'control':'stable_gn_205_','learned':'stable_gn_191_'},'patch':{'onlyFirstGnMeanAndVarianceAdditionalSumChunk':128,'originalFirstChunk':128,'allOriginalParametersEpsilonOtherGnAndHostRatiosUnchanged':True,'reversePatchRestoresEachParentGraphBytes':True}}
    for k in ('newTorchInputsAllowed','newOnnxOperatorInputsAllowed','optimizerStepsAllowed','valInputsAllowed','protectedInputsAllowed','newChatImageInputsAllowed'):p[k]=0
    for k in ('all204NonzeroControlsMustPassBeforeAnyLearnedInput','oldFailuresAndConsumedBudgetsPreserved','internalValRequiresSeparateScopeAfterFullGate'):p[k]=True
    p['cases']=[{'ordinal':o,'candidateIdentity':{'identity':{'split':'train','fileName':str(o)}}} for o in range(1,69)];p['candidateIdentities']=[c['candidateIdentity'] for c in p['cases']]
    return p

class Tests(unittest.TestCase):
    def test_scope_rejects_shrunk_denominator_and_relaxed_gates(self):
        p=scope();m.validate_scope(p)
        for key,value in (('cases',p['cases'][:-1]),('requiredNumericDifference',1.1e-4),('newFullModelInputsAllowed',410),('valInputsAllowed',1),('requiredDecodedPixelDifferences',1)):
            with self.assertRaises(ValueError):m.validate_scope(p|{key:value})
        wrong=copy.deepcopy(p);wrong['cases'][2]['candidateIdentity']['identity']['split']='val'
        with self.assertRaises(ValueError):m.validate_scope(wrong)

    def test_control_gate_checks_each_input_and_both_heads(self):
        parity={k:True for k in ('numericGatePassed','decodedPixelGatePassed','presenceDecisionMatched','allReferenceAndCapturedHeadsFinite')}
        report={'ok':True,'kind':'control','allThreeBackendStageGatesPassed':True,'modelInputsConsumedPerBackend':{'cpu':68,'wasm':68,'webgpu':68},'records':[{'backend':b,'ordinal':o,'gatePassed':True,'parity':copy.deepcopy(parity)} for b in ('cpu','wasm','webgpu') for o in range(1,69)]}
        m.require_control_gate(report)
        for key in parity:
            wrong=copy.deepcopy(report);wrong['records'][100]['parity'][key]=False
            with self.assertRaises(ValueError):m.require_control_gate(wrong)
        wrong=copy.deepcopy(report);wrong['records'][68]['ordinal']=2
        with self.assertRaises(ValueError):m.require_control_gate(wrong)

    def test_compare_rejects_native_shape_before_flattening(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs={'mask':m.save(root/'mask.bin',np.zeros((1,1,2,3),np.float32)),'presence':m.save(root/'presence.bin',np.ones((1,1),np.float32))};c={'h':2,'w':3,'references':{'control':refs}}
            outputs=copy.deepcopy(refs);outputs['mask']['shape']=[1,2,3,1]
            with patch.object(m,'tensor') as tensor:
                with self.assertRaises(ValueError):m.compare(c,'control',outputs,object())
                tensor.assert_not_called()

    def test_presence_nan_cannot_hide_behind_good_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs={'mask':m.save(root/'mask.bin',np.zeros((1,1,2,3),np.float32)),'presence':m.save(root/'presence.bin',np.ones((1,1),np.float32))};bad=root/'bad.bin';bad.write_bytes(np.array([np.nan],np.float32).tobytes());outputs=refs|{'presence':m.d.bind(bad)|{'shape':[1,1],'dtype':'float32'}}
            with self.assertRaises(ValueError):m.compare({'h':2,'w':3,'references':{'control':refs}},'control',outputs,object())

    def test_existing_stage_rejected_before_model_resources(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'resources') as resources:
            with self.assertRaises(ValueError):m.prepare(Path('unused'),Path(temp),'learned')
            resources.assert_not_called()

    def test_control_semantic_prefix_cannot_use_learned_index(self):
        p=scope();p['firstGnPrefixes']['control']='stable_gn_191_'
        with self.assertRaises(ValueError):m.validate_scope(p)

    def test_event_cannot_exchange_host_ratios_or_stage(self):
        c={'ordinal':1,'h':3,'w':2,'candidateIdentity':{'identity':{'split':'train'}},'input':{'sha256':'a'},'resizeRatios':{'sha256':'b'}};page=str(uuid.uuid4());ev=m.event('control','wasm',c,page)|{'inputRequestId':str(uuid.uuid4())};m.validate_event(ev,'control','wasm',c,page)
        for key,value in (('kind','learned'),('resizeRatiosSha256','changed'),('targetShape',[1,1,2,3]),('inputRequestId','not-an-UUID')):
            with self.assertRaises(ValueError):m.validate_event(ev|{key:value},'control','wasm',c,page)

if __name__=='__main__':unittest.main()
