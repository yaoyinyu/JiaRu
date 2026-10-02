import copy,importlib.util,json,tempfile
from pathlib import Path
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe',ROOT/'model/training/run-train-role-marker-sensitivity-probe.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MarkerProbeTests(unittest.TestCase):
    def test_native_mask_storage_roundtrip_including_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in (0,2):
                masks=np.zeros((n,7,9),bool)
                if n:masks[0,1:4,2:5]=True;masks[1,4:7,5:9]=True
                boxes=np.ones((n,4),np.float32);conf=np.full(n,.7,np.float32);classes=np.zeros(n,np.float32)
                ref=m.save_prediction(Path(tmp)/f'{n}.npz',boxes,conf,classes,masks)
                result=m.load_prediction(ref,[9,7]);self.assertTrue(np.array_equal(result[3],masks));self.assertTrue(np.array_equal(result[1],conf))
                with self.assertRaises(ValueError):m.load_prediction(ref,[7,9])
    def test_non_native_or_class_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):m.save_prediction(Path(tmp)/'bad.npz',np.zeros((1,4)),np.ones(1),np.ones(1),np.zeros((1,4,4),bool))
            with self.assertRaises(ValueError):m.match_masks(np.zeros((1,4,4),bool),np.zeros((1,4,5),bool))
    def test_one_to_one_matching_keeps_all_truths_and_spurious(self):
        truth=np.zeros((2,6,6),bool);truth[0,:2,:2]=True;truth[1,4:,4:]=True
        pred=np.stack([truth[1],truth[1]])
        r=m.match_masks(pred,truth);self.assertEqual(len(r['matches']),1);self.assertEqual(r['missedTruthIndices'],[1]);self.assertEqual(len(r['unmatchedPredictionIndices']),1)
        empty=m.match_masks(np.zeros((0,6,6),bool),truth);self.assertEqual(empty['missedTruthIndices'],[1,2])
    def test_instance_migration_not_just_net_count(self):
        a={'missedTruthIndices':[1],'matches':[{'truthIndex':2}]};b={'missedTruthIndices':[2],'matches':[{'truthIndex':1}]}
        masks=np.zeros((1,3,3),bool);r=m.comparison(a,b,masks,masks)
        self.assertEqual(r['matchedNailDelta'],0);self.assertEqual(r['newMissedTruthIndices'],[2]);self.assertEqual(r['recoveredTruthIndices'],[1])
    def test_journal_never_overwrites_even_with_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);m.journal(p,1,{'phase':'start'})
            with (p/'000001.json').open('rb') as reader:
                with self.assertRaises(FileExistsError):m.journal(p,1,{'phase':'replace'})
                m.journal(p,2,{'phase':'complete'});self.assertIn(b'start',reader.read())
            self.assertEqual(json.loads((p/'000002.json').read_text())['sequence'],2)
    def test_cohort_role_parent_and_variant_budget_fidelity(self):
        r={'ordinal':1,'fileName':'source','sourceGroup':'g','sourceImage':{},'annotation':{},'completeVisibleNails':2,
           'currentSplit':'train','upstreamDevelopmentSplit':'train','parents':[],'trainingUse':'prohibited','variants':{k:{} for k in m.NAMES}}
        plan={'contract':{'variantOrder':m.NAMES,'oneInferencePerVariant':True},'sources':[r],
              'counts':{'sourceImages':1,'completeVisibleNails':2,'plannedInferenceInputs':7}}
        pack={'records':[copy.deepcopy(r)]};m.validate_scope(plan,pack)
        for field,value in [('currentSplit','val'),('parents',[{'protected':True}]),('trainingUse','allowed')]:
            changed=copy.deepcopy(plan);changed['sources'][0][field]=value
            with self.assertRaises(ValueError):m.validate_scope(changed,pack)
        changed=copy.deepcopy(plan);changed['counts']['plannedInferenceInputs']=6
        with self.assertRaises(ValueError):m.validate_scope(changed,pack)
if __name__=='__main__':unittest.main()
