import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('internal_val_marker',R/'model/training/run-internal-val-marker-sensitivity-probe.py')
h=load('internal_val_prediction_fixture',R/'model/training/run-train-role-marker-sensitivity-probe.py')
t=load('internal_val_truth_fixture',R/'model/training/run-variable-train-role-marker-probe.py')
def fixture():
    sources=[];records=[];roles=[];reviews=[]
    for i in range(2):
        identity={'split':'val','fileName':f'image{i}.jpg','imageSha256':str(i)*64}
        image={'path':f'image{i}.jpg','sha256':str(i)*64};ann={'path':f'ann{i}.json','sha256':'a'*64}
        role={'identity':identity,'sourceGroup':'g','sourceImage':image,'upstreamDevelopmentSplit':'train',
            'trainingUse':'prohibited','formalTrainingApproved':False,'protectedTrainConflicts':[],
            'currentAndParentRoleMatches':[{'role':'developmentTrain'},{'role':'currentHistoricalRoiValidation'}]}
        variants={k:{'path':f'{i}-{k}.png','sha256':'b'*64} for k in m.PACK_NAMES}
        s={'identity':identity,'ordinal':1,'sourceGroup':'g','sourceImage':image,'annotation':ann,'imageSize':[8,8],
            'completeVisibleNails':1,'roleEvidence':copy.deepcopy(role),'trainingUse':'prohibited',
            'variants':[{'name':n,'image':variants[v]} for n,v in zip(m.NAMES,m.PACK_NAMES,strict=True)]}
        p={'identity':identity,'sourceImage':image,'annotation':ann,'sourceGroup':'g',
            'sourcePreserved':{'maskCount':1,'imageSize':[8,8]},'variants':variants}
        sources.append(s);records.append(p);roles.append(role)
        reviews.append({'identity':identity,'controlRecordPreserved':copy.deepcopy(p),'decision':'pass',
            'actuallyViewed':True,'toolScalingNotice':False})
    plan={'sources':sources,'contract':copy.deepcopy(m.CONTRACT),'counts':{'sourceImages':2,'completeVisibleNails':2,'plannedInferenceInputs':10}}
    pack={'records':records,'entireFrozenGroupMembership':[{'identity':s['identity']} for s in sources]}
    index={'records':roles};close={'ok':True,'nativeControlScopeOnly':True,'modelAblationInputsReady':True,
        'markerDebtCleared':False,'trainingAllowed':False,'modelAblationExecuted':False,'records':reviews}
    return plan,pack,index,close
class ProbeTests(unittest.TestCase):
    def test_only_internal_val_pair_allowed_and_local_ordinals_do_not_collide(self):
        self.assertEqual(m.validate_scope(*fixture()),10)
    def test_train_role_or_upstream_val_is_rejected(self):
        for field,value in [('identity',{'split':'train','fileName':'image0.jpg','imageSha256':'0'*64}),('upstreamDevelopmentSplit','val')]:
            p,pack,idx,c=fixture();idx['records'][0][field]=value;p['sources'][0]['roleEvidence']=copy.deepcopy(idx['records'][0])
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_protected_parent_or_current_role_cannot_be_authorized_by_copying_into_plan(self):
        for field,value in [('protectedTrainConflicts',[{'identity':'parent','role':'frozenReleaseTest'}]),
            ('currentAndParentRoleMatches',[{'role':'developmentTrain'},{'role':'consumedPositiveTest','identity':'parent'}])]:
            p,pack,idx,c=fixture();idx['records'][0][field]=value;p['sources'][0]['roleEvidence']=copy.deepcopy(idx['records'][0])
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_omitted_group_member_and_duplicate_identity_rejected(self):
        for kind in ['omitted','duplicate']:
            p,pack,idx,c=fixture()
            if kind=='omitted':p['sources'].pop();pack['records'].pop();c['records'].pop()
            else:p['sources'][1]['identity']=copy.deepcopy(p['sources'][0]['identity'])
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_truth_variant_or_count_drift_rejected(self):
        for kind in ['truth','variant','count']:
            p,pack,idx,c=fixture()
            if kind=='truth':p['sources'][0]['annotation']['sha256']='c'*64
            elif kind=='variant':p['sources'][0]['variants'].reverse()
            else:p['counts']['plannedInferenceInputs']=11
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_visual_rework_and_promotion_rejected(self):
        for kind in ['rework','promotion']:
            p,pack,idx,c=fixture()
            if kind=='rework':c['records'][0]['decision']='rework'
            else:c['trainingAllowed']=True
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_square_contract_cannot_silently_change_to_rectangular_or_threshold_scan(self):
        for field,value in [('rect',True),('conf',.1),('imgsz',640)]:
            p,pack,idx,c=fixture();p['contract'][field]=value
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_empty_output_preserves_all_truth_and_instance_migration(self):
        p,_,_,_=fixture();predictions={}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i,s in enumerate(p['sources']):
                ann=root/f'{i}.json';ann.write_text(json.dumps({'annotations':[{'polygon':[{'x':1,'y':1},{'x':4,'y':1},{'x':4,'y':4},{'x':1,'y':4}]}]}))
                s['annotation']=m.bind(ann);s['truthFormat']='original_pixel_polygon_annotation_json'
                truth=t.truth_masks(s)
                for v in s['variants']:
                    mask=np.zeros((0,8,8),bool) if v['name']=='marker_removed' else truth
                    n=len(mask)
                    predictions[(m.key(s['identity']),v['name'])]=h.save_prediction(root/f'{i}-{v["name"]}.npz',np.zeros((n,4),np.float32),np.full(n,.7,np.float32),np.zeros(n,np.float32),mask)
            rows,agg,summary,pattern=m.summarize(p['sources'],predictions,h,t,.75)
            self.assertEqual(agg['marker_removed']['truthNails'],2)
            self.assertEqual(agg['marker_removed']['missedNails'],2)
            self.assertEqual(rows[0]['comparisons']['original__marker_removed']['newMissedTruthIndices'],[1])
            self.assertEqual(pattern['pairedCandidateOrMatchMigrationSources'],2)
            self.assertEqual(pattern['interpretation'],'paired_candidate_or_match_migration_context_not_excluded')
if __name__=='__main__':unittest.main()
