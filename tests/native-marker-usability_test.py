import copy,importlib.util
from pathlib import Path
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
builder=load('marker_builder','model/training/build-native-marker-variants.py')
audit=load('marker_audit','model/training/audit-native-marker-usability.py')

class MarkerUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.record={'ordinal':1,'fileName':'nail.jpg','sourceGroup':'group','sourceImage':{'path':'source','sha256':'a'*64},
                     'annotation':{'path':'annotation','sha256':'b'*64},'completeVisibleNails':2,
                     'reviewPages':[{'path':'page','sha256':'c'*64}],'variants':{'original':{},'remove':{},'move_marker':{}},
                     'variantPixelEvidence':{'crop12_native':{'nailPixelsLost':0,'protectedPixelsLost':0}},
                     'cropDiagnosticEligible':True}
        self.decision={k:copy.deepcopy(self.record[k]) for k in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails')}
        self.decision.update(trainingUse='prohibited',viewedPages=self.record['reviewPages'],localControlsDecision='diagnostic_candidate',
                             failedVariants=[],reason='Original pixels reviewed',cropDecision='pixel_preserving_crop_candidate_context_confounding')

    def test_boxes_reject_overlap_or_protected_pixels(self):
        row={'badgeBox':[1,1,5,5],'blankControlBox':[6,1,10,5],'relocationBox':[11,1,15,5]}
        protected=np.zeros((20,20),bool);builder.validate_boxes(row,20,20,protected)
        protected[2,2]=True
        with self.assertRaises(ValueError):builder.validate_boxes(row,20,20,protected)
        d=copy.deepcopy(row);d['blankControlBox']=[2,2,6,6]
        with self.assertRaises(ValueError):builder.validate_boxes(d,20,20,np.zeros((20,20),bool))

    def test_matched_windows_require_same_size_and_inside_source(self):
        row={'badgeBox':[1,1,5,5],'blankControlBox':[6,1,9,5],'relocationBox':[11,1,15,5]}
        with self.assertRaises(ValueError):builder.validate_boxes(row,20,20,np.zeros((20,20),bool))
        row['blankControlBox']=[21,1,25,5]
        with self.assertRaises(ValueError):builder.validate_boxes(row,20,20,np.zeros((20,20),bool))

    def test_missing_reordered_or_duplicate_sources_rejected(self):
        audit.summarize([self.record],[self.decision],1)
        with self.assertRaises(ValueError):audit.summarize([self.record],[self.decision],2)
        with self.assertRaises(ValueError):audit.summarize([self.record,self.record],[self.decision,self.decision],2)
        d=copy.deepcopy(self.decision);d['ordinal']=2
        with self.assertRaises(ValueError):audit.summarize([self.record],[d],1)

    def test_crop_guard_loss_cannot_pass_even_with_no_mask_loss(self):
        r=copy.deepcopy(self.record);r['variantPixelEvidence']['crop12_native']['protectedPixelsLost']=1
        with self.assertRaises(ValueError):audit.summarize([r],[self.decision],1)
        r['cropDiagnosticEligible']=False;d=copy.deepcopy(self.decision);d['cropDecision']='reject_protected_pixel_loss'
        result=audit.summarize([r],[d],1)
        self.assertEqual(result['cropUnsafe'][0]['nailPixelsLost'],0)
        self.assertEqual(result['cropSafeOrdinals'],[])

    def test_failed_visual_record_limits_ceiling_without_reducing_cohort(self):
        second=copy.deepcopy(self.record);second['ordinal']=2
        d=copy.deepcopy(self.decision);d['ordinal']=2;d['localControlsDecision']='rework';d['failedVariants']=['remove']
        result=audit.summarize([self.record,second],[self.decision,d],2)
        self.assertEqual(result['ceiling']['maxInterpretableLocalSourceFraction'],.5)
        self.assertEqual(result['ceiling']['missingSources'],1)
        self.assertEqual(result['acceptedOrdinals'],[1])
        d['localControlsDecision']='diagnostic_candidate'
        with self.assertRaises(ValueError):audit.summarize([second],[d],1)

    def test_changed_identity_missing_page_and_training_promotion_rejected(self):
        for key,value in [('sourceGroup','different'),('viewedPages',[]),('trainingUse','allowed')]:
            d=copy.deepcopy(self.decision);d[key]=value
            with self.assertRaises(ValueError):audit.summarize([self.record],[d],1)

if __name__=='__main__':unittest.main()
