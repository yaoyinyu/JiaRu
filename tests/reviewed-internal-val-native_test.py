"""内部val全分母、严格双头、实际控制前置门与预算保护。"""
import copy
import importlib.util
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('internal_val_test',R/'model/training/audit-reviewed-internal-val-native.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Tests(unittest.TestCase):
    def test_all224_controls_required_not_outer_ok(self):
        parity={k:True for k in ('numericGatePassed','decodedPixelGatePassed','presenceDecisionMatched','allReferenceAndCapturedHeadsFinite')}
        r={'ok':True,'kind':'control','allThreeBackendStageGatesPassed':True,'modelInputsConsumedPerBackend':{b:56 for b in ('strict_cuda','cpu','wasm','webgpu')},'records':[{'backend':b,'ordinal':o,'gatePassed':True,'parity':copy.deepcopy(parity)} for b in ('strict_cuda','cpu','wasm','webgpu') for o in range(1,57)]};m.require_control_gate(r)
        for key in parity:
            bad=copy.deepcopy(r);bad['records'][160]['parity'][key]=False
            with self.assertRaises(ValueError):m.require_control_gate(bad)
        for bad in (r|{'records':r['records'][:-1]},r|{'kind':'learned'},r|{'modelInputsConsumedPerBackend':{'cpu':56,'wasm':56,'webgpu':56}}):
            with self.assertRaises(ValueError):m.require_control_gate(bad)

    def test_stage_reentry_stops_before_any_model_resources(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'resources') as resources:
            with self.assertRaises(ValueError):m.prepare(Path('unused'),Path(temp),'learned')
            resources.assert_not_called()

    def test_native_shapes_before_flatten(self):
        refs={h:{'shape':shape,'dtype':'float32'} for h,shape in (('mask',[1,1,2,3]),('presence',[1,1]))};bad=copy.deepcopy(refs);bad['mask']['shape']=[1,2,3,1]
        with patch.object(m,'tensor') as tensor:
            with self.assertRaises(ValueError):m.compare({'h':2,'w':3,'references':{'control':refs}},'control',bad,object())
            tensor.assert_not_called()

    def test_presence_nonfinite_cannot_hide_behind_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs={'mask':m.save(root/'mask',np.zeros((1,1,2,3),np.float32)),'presence':m.save(root/'presence',np.ones((1,1),np.float32))};bad=root/'nan';bad.write_bytes(np.array([np.nan],np.float32).tobytes())
            outputs=refs|{'presence':m.d.bind(bad)|{'shape':[1,1],'dtype':'float32'}}
            with self.assertRaises(ValueError):m.compare({'h':2,'w':3,'references':{'control':refs}},'control',outputs,object())

    def test_event_stage_source_ratio_and_request_identity(self):
        c={'ordinal':1,'h':3,'w':2,'candidateIdentity':{'identity':{'split':'val'}},'input':{'sha256':'input'},'resizeRatios':{'sha256':'ratio'}};page=str(uuid.uuid4());ev=m.event('control','wasm',c,page)|{'inputRequestId':str(uuid.uuid4())};m.validate_event(ev,'control','wasm',c,page)
        for key,value in (('kind','learned'),('backend','cpu'),('resizeRatiosSha256','other'),('targetShape',[1,1,2,3]),('inputRequestId','invalid')):
            with self.assertRaises(ValueError):m.validate_event(ev|{key:value},'control','wasm',c,page)

    def test_full50_truths_with_missing_not49_denominator(self):
        positives=[]
        for i in range(49):
            identity={'split':'val','fileName':str(i//5),'imageSha256':str(i//5)}
            positives.append({'identity':identity,'truthIndex':i%5+1,'presenceTarget':True,'presenceAccepted':True,'iou075Passed':True,'jointBoundaryPassed':True,'maskIou':1.,'boundary':{'boundaryIoU':1.,'boundaryF1':1.}})
        missing=[{'identity':{'split':'val','fileName':'9','imageSha256':'9'},'truthIndex':5}];rejects=[{'presenceTarget':False,'predictionPixels':0} for _ in range(7)]
        r=m.quality_summary(positives+rejects,missing,50,10)
        self.assertEqual(r['jointBoundaryRateFullTruth'],.98);self.assertEqual(r['meanMaskIouFullTruth'],.98);self.assertEqual(r['zeroOutputRejectCount'],7);self.assertEqual(r['sourcesWithJointBoundaryFailure'],1)
        with self.assertRaises(ValueError):m.quality_summary(positives+rejects,missing,49,10)
        with self.assertRaises(ValueError):m.quality_summary(positives+rejects,missing+missing,51,10)

    def test_stable_source_identity_not_local_truth_index(self):
        rows=[{'identity':{'split':'val','fileName':name,'imageSha256':name},'truthIndex':1,'presenceTarget':True,'presenceAccepted':True,'iou075Passed':True,'jointBoundaryPassed':True,'maskIou':1.,'boundary':{'boundaryIoU':1.,'boundaryF1':1.}} for name in ('a','b')]
        self.assertEqual(m.quality_summary(rows,[],2,2)['jointBoundaryCount'],2)
        with self.assertRaises(ValueError):m.quality_summary(rows+rows,[],4,2)

    def test_wilson_full_denominator_bounds(self):
        lo,hi=m.wilson(49,50);self.assertLess(lo,.98);self.assertGreater(hi,.98)
        self.assertLess(m.wilson(0,50)[1],.1)
        with self.assertRaises(ValueError):m.wilson(51,50)

    def test_strict_reference_nonzero_control_and_all56(self):
        c={'ordinal':1,'h':2,'w':3,'candidateIdentity':{'identity':{'split':'val'}},'input':{'sha256':'input'},'resizeRatios':{'sha256':'ratio'}}
        cases=[c|{'ordinal':o} for o in range(1,57)]
        outputs={'mask':{'dtype':'float32','shape':[1,1,2,3]},'presence':{'dtype':'float32','shape':[1,1]}}
        rows=[m.event('control','strict_cuda',item)|{'outputs':outputs,'nonzeroControlDeltaMaxAbs':.1} for item in cases]
        with patch.object(m,'tensor',return_value=np.ones(1,np.float32)):
            actual=m.attach_references({'cases':cases},rows,'control');self.assertEqual(len(actual['cases']),56)
            with self.assertRaises(ValueError):m.attach_references({'cases':cases},rows[:-1],'control')
            bad=copy.deepcopy(rows);bad[10]['nonzeroControlDeltaMaxAbs']=0
            with self.assertRaises(ValueError):m.attach_references({'cases':cases},bad,'control')

    def test_quality_decodes_presence_rejection_and_preserves_missing_truth(self):
        from PIL import Image
        spec=importlib.util.spec_from_file_location('quality_boundary_test',R/'model/training/analyze-saved-nail-roi-coverage.py');boundary=importlib.util.module_from_spec(spec);spec.loader.exec_module(boundary)
        guard=SimpleNamespace(install_read_only_ultralytics_image_check=lambda:None,remove_ultralytics_label_caches=lambda p:None)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);truth=np.zeros((8,8),np.uint8);truth[2:6,2:6]=255;Image.fromarray(truth).save(root/'truth.png');Image.fromarray(np.zeros_like(truth)).save(root/'empty.png')
            identity={'split':'val','fileName':'fixture','imageSha256':'fixture'};ci={'identity':identity,'predictionIndex':1};target={'kind':'complete_reviewed_nail_mask','truthIndex':1}
            c={'ordinal':1,'h':8,'w':8,'candidateIdentity':ci,'presenceTarget':True,'nativeTargetPixels':16,'target':target,'cropBox':[0,0,8,8],'originalNativeAssets':{'nativeTarget':m.d.bind(root/'truth.png')}}
            reject=c|{'ordinal':2,'candidateIdentity':ci|{'predictionIndex':2},'presenceTarget':False,'nativeTargetPixels':0,'target':{'kind':'reject_same_candidate_only','truthIndex':None,'emptyTargetIsNotNoNailsInRgbRoi':True},'originalNativeAssets':{'nativeTarget':m.d.bind(root/'empty.png')}}
            caps=[]
            for case,presence in ((c,-1),(reject,1)):
                caps.append({'ordinal':case['ordinal'],'candidateIdentity':case['candidateIdentity'],'outputs':{'mask':m.save(root/f"{case['ordinal']}-mask",np.ones((1,1,8,8),np.float32)),'presence':m.save(root/f"{case['ordinal']}-presence",np.array([[presence]],np.float32))}})
            p={'sources':{'readOnlyGuard':m.d.bind(root/'empty.png'),'boundaryMetric':m.d.bind(root/'empty.png')},'inputs':{'trainingContract':{}},'cases':[c,reject],'qualityDiagnostics':{'presenceAcceptanceLogit':0.,'maskAcceptanceLogit':0.,'boundaryToleranceOriginalPixels':2,'maskIou':.75,'boundaryIou':.75,'boundaryF1':.9,'fullTruthDenominator':2,'sourceDenominator':1},'unpairedFullTruthAssets':[{'identity':identity,'truthIndex':2,'fullNativeTruth':m.d.bind(root/'truth.png'),'truthPixels':16,'inferenceUse':'prohibited_gt_only_no_candidate'}]}
            with patch.object(m.d,'load',side_effect=[guard,boundary]),patch.object(m.d,'read',return_value={'cacheCleanupRoots':[]}):r=m.quality_diagnostics(p,{'strict_cuda':caps})
            result=r['perBackend']['strict_cuda'];self.assertEqual(result['summary']['jointBoundaryCount'],0);self.assertEqual(result['summary']['fullTruthDenominator'],2);self.assertEqual(result['summary']['nonzeroOutputRejectCount'],1);self.assertEqual(result['records'][0]['predictionPixels'],0);self.assertTrue(result['records'][1]['emptyTargetDoesNotMeanNoNailsInRgbRoi']);self.assertFalse(result['missingTruths'][0]['modelInputCreated'])

if __name__=='__main__':unittest.main()
