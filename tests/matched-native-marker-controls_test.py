import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('matched_controls',ROOT/'model/training/build-matched-native-marker-controls.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MatchedControlsTests(unittest.TestCase):
    def test_repair_never_mutates_original_or_outside_target(self):
        arr=np.full((30,30,3),40,np.uint8);arr[20:26,20:26]=200;original=arr.copy()
        repaired=m.replace_background(arr,[20,20,26,26],[20,10,26,16])
        self.assertTrue(np.array_equal(original,arr));self.assertTrue((repaired==40).all())
        allowed=np.zeros((30,30),bool);allowed[20:26,20:26]=True
        self.assertFalse((np.any(repaired!=original,axis=-1)&~allowed).any())
    def test_patch_shape_overlap_and_edge_fail_closed(self):
        arr=np.zeros((30,30,3),np.uint8)
        for target,donor in [([20,20,26,26],[20,10,25,16]),([20,20,26,26],[21,21,27,27]),([0,20,6,26],[20,10,26,16])]:
            with self.assertRaises(ValueError):m.replace_background(arr,target,donor)
    def test_relocation_pair_only_differs_in_destination(self):
        original=np.zeros((30,30,3),np.uint8);original[20:26,20:26]=200
        base=np.full_like(original,10);saved=base.copy()
        marked=m.relocate(base,original,[20,20,26,26],[2,2,8,8]);blank=m.relocate(base,original,[20,10,26,16],[2,2,8,8])
        self.assertTrue(np.array_equal(base,saved));delta=np.any(marked!=blank,axis=-1)
        self.assertEqual(int(delta.sum()),36);self.assertTrue(delta[2:8,2:8].all());self.assertFalse(delta[8:,:].any())
        with self.assertRaises(ValueError):m.relocate(base,original,[20,20,26,26],[2,2,7,8])
    def fixture(self):
        r={'ordinal':1,'fileName':'source','sourceGroup':'group','sourceImage':{'path':'source','sha256':'a'*64},'annotation':{'path':'a','sha256':'b'*64},'completeVisibleNails':2,'reviewPages':[{'path':'panel','sha256':'c'*64}],'variants':{'remove':{},'blank_move_control':{}}}
        d={k:copy.deepcopy(r[k]) for k in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails')}
        d.update(viewedPages=r['reviewPages'],trainingUse='prohibited',decision='local_controls_visual_pass',failedVariants=[],reason='reviewed')
        return r,d
    def test_failed_or_missing_source_cannot_shrink_denominator(self):
        r,d=self.fixture();r2=copy.deepcopy(r);d2=copy.deepcopy(d);r2['ordinal']=d2['ordinal']=2
        d2.update(decision='rework',failedVariants=['remove'])
        result=m.visual_summary([r,r2],[d,d2]);self.assertEqual(result['ceiling']['maxInterpretableSourceFraction'],.5)
        with self.assertRaises(ValueError):m.visual_summary([r,r2],[d])
        with self.assertRaises(ValueError):m.visual_summary([r,r],[d,d])
    def test_identity_missing_page_and_training_promotion_rejected(self):
        r,d=self.fixture()
        for k,v in [('sourceGroup','other'),('viewedPages',[]),('trainingUse','allowed'),('failedVariants',['remove'])]:
            changed=copy.deepcopy(d);changed[k]=v
            with self.assertRaises(ValueError):m.visual_summary([r],[changed])
if __name__=='__main__':unittest.main()
