import copy
import importlib.util
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('quality_accounted_train',R/'model/training/run-quality-accounted-train-marker-probe.py')
fixtures=load('internal_fixture_reuse',R/'tests/internal-val-marker-sensitivity-probe_test.py')
def fixture():
    p,pack,idx,c=fixtures.fixture()
    for i,(s,r) in enumerate(zip(p['sources'],idx['records'],strict=True)):
        s['identity']['split']='train';r['currentAndParentRoleMatches']=[{'role':'developmentTrain'}]
        r['currentSourceDisposition']='complete_masks_pass_pending_full_split'
        s['roleEvidence']=copy.deepcopy(r)
        c['records'][i]['identity']=copy.deepcopy(s['identity'])
        c['records'][i]['controlRecordPreserved']=copy.deepcopy(pack['records'][i])
    identity={'split':'train','fileName':'excluded.jpg','imageSha256':'c'*64}
    image={'path':'excluded.jpg','sha256':'c'*64}
    role={'identity':identity,'sourceGroup':'g','sourceImage':image,'upstreamDevelopmentSplit':'train',
        'trainingUse':'prohibited','formalTrainingApproved':False,'protectedTrainConflicts':[],
        'currentSourceDisposition':'source_quality_excluded','currentAndParentRoleMatches':[{'role':'developmentTrain'}]}
    member={'identity':identity,'sourceGroup':'g','sourceImage':image,'currentSourceDisposition':'source_quality_excluded'}
    idx['records'].append(role)
    pack['excludedMembers']=[member]
    pack['entireFrozenGroupMembership']=[{'identity':s['identity']} for s in p['sources']]+[copy.deepcopy(member)]
    p['entireFrozenGroupMembership']=copy.deepcopy(pack['entireFrozenGroupMembership'])
    p['excludedMembers']=[{**copy.deepcopy(member),'roleEvidence':copy.deepcopy(role),'trainingUse':'prohibited','inferenceUse':'prohibited'}]
    c['excludedMembersPreserved']=copy.deepcopy(pack['excludedMembers']);c['wholeSourceGroupsApproved']=False
    p['contract']=copy.deepcopy(m.CONTRACT)
    p['counts'].update({'wholeMembers':3,'excludedSources':1})
    return p,pack,idx,c
class AccountedTrainTests(unittest.TestCase):
    def test_whole_three_active_two_excluded_one_budget_is_ten_not_fifteen(self):
        self.assertEqual(m.validate_scope(*fixture()),10)
    def test_missing_excluded_or_active_group_member_rejected(self):
        for kind in ['excluded','active']:
            p,pack,idx,c=fixture()
            if kind=='excluded':p['excludedMembers']=[]
            else:p['sources'].pop();pack['records'].pop();c['records'].pop()
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_duplicate_or_overlapping_excluded_identity_rejected(self):
        for kind in ['duplicate','overlap']:
            p,pack,idx,c=fixture()
            if kind=='duplicate':p['excludedMembers'].append(copy.deepcopy(p['excludedMembers'][0]))
            else:p['excludedMembers'][0]['identity']=copy.deepcopy(p['sources'][0]['identity'])
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_only_frozen_quality_exclusion_not_marker_isolation_or_model_miss(self):
        for value in ['marker_isolated','model_missed','complete_masks_pass_pending_full_split']:
            p,pack,idx,c=fixture();idx['records'][-1]['currentSourceDisposition']=value
            p['excludedMembers'][0]['currentSourceDisposition']=value
            p['excludedMembers'][0]['roleEvidence']=copy.deepcopy(idx['records'][-1])
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_excluded_inference_or_training_permission_cannot_be_enabled(self):
        for field in ['inferenceUse','trainingUse']:
            p,pack,idx,c=fixture();p['excludedMembers'][0][field]='allowed'
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_protected_active_or_excluded_parent_and_val_role_rejected(self):
        for target in [0,-1]:
            for kind in ['parent','val']:
                p,pack,idx,c=fixture()
                if kind=='parent':idx['records'][target]['currentAndParentRoleMatches'].append({'identity':'parent','role':'consumedPositiveTest'})
                else:idx['records'][target]['upstreamDevelopmentSplit']='val'
                if target==0:p['sources'][0]['roleEvidence']=copy.deepcopy(idx['records'][0])
                else:p['excludedMembers'][0]['roleEvidence']=copy.deepcopy(idx['records'][-1])
                with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_original_only_excluded_member_cannot_be_added_to_active(self):
        p,pack,idx,c=fixture();s=copy.deepcopy(p['sources'][0]);s['identity']=copy.deepcopy(p['excludedMembers'][0]['identity']);s['variants']=s['variants'][:1]
        p['sources'].append(s)
        with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
    def test_truth_counts_or_variant_order_or_contract_drift_rejected(self):
        for kind in ['truth','counts','order','threshold']:
            p,pack,idx,c=fixture()
            if kind=='truth':p['sources'][0]['annotation']['sha256']='d'*64
            elif kind=='counts':p['counts']['plannedInferenceInputs']=15
            elif kind=='order':p['sources'][0]['variants'].reverse()
            else:p['contract']['conf']=.1
            with self.assertRaises(ValueError):m.validate_scope(p,pack,idx,c)
if __name__=='__main__':unittest.main()
