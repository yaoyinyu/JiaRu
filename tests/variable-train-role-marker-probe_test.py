import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('variable_probe',ROOT/'model/training/run-variable-train-role-marker-probe.py')
h=load('probe_helper',ROOT/'model/training/run-train-role-marker-sensitivity-probe.py')
den=load('denominator_auditor',ROOT/'model/training/audit-marker-probe-denominator-contract.py')

def fixture():
    sources=[];pack=[];roles=[]
    for i,marked in enumerate([True,False]):
        identity={'split':'train','fileName':f'source{i}.jpg','imageSha256':str(i)*64}
        image={'path':f'source{i}.jpg','sha256':str(i)*64};annotation={'path':f'source{i}.json','sha256':'a'*64}
        role={'identity':identity,'sourceGroup':'g','sourceImage':image,'upstreamDevelopmentSplit':'train','trainingUse':'prohibited',
              'formalTrainingApproved':False,'protectedTrainConflicts':[],'parents':[],
              'currentAndParentRoleMatches':[{'role':'developmentTrain'}]}
        variants=[{'name':n,'image':{'path':f'{i}-{n}.png','sha256':'b'*64}} for n in (m.NAMES if marked else ['original'])]
        sources.append({'identity':identity,'ordinal':1,'sourceGroup':'g','sourceImage':image,'annotation':annotation,'imageSize':[8,8],
                        'completeVisibleNails':1,'roleEvidence':copy.deepcopy(role),'trainingUse':'prohibited','variants':variants})
        pack.append({'sourceRecordPreserved':{'identity':identity,'sourceGroup':'g','sourceImage':image,'markerControlRequired':marked,
                     'currentTruth':{'annotation':annotation,'imageSize':[8,8]}},'sourceNails':1,'variants':copy.deepcopy(variants)})
        roles.append(role)
    return ({'sources':sources,'contract':{'variantOrder':m.NAMES,'oneInferencePerVariant':True},
             'counts':{'sourceImages':2,'completeVisibleNails':2,'markedSources':1,'plannedInferenceInputs':10}}, {'records':pack}, {'records':roles})

class VariableProbeTests(unittest.TestCase):
    def test_original_only_members_do_not_inflate_paired_denominator(self):
        plan,_,_=fixture();plan['sources'][1]['completeVisibleNails']=10
        d=den.denominators(plan);self.assertEqual(d['originalAll']['truthNails'],11)
        self.assertEqual(d['originalMarked']['truthNails'],1);self.assertEqual(d['byVariant']['marker_removed']['truthNails'],1)
    def test_incorrect_preregistered_text_refuses_interpretation(self):
        plan,_,_=fixture();plan['preregisteredInterpretation']=['原图全2/2和配对原图1/2分母分别报告，其他变体1/2。']
        r=den.audit(plan);self.assertEqual(r['decision'],'reconstruction_mismatch');self.assertFalse(r['interpretationConclusionsAllowed'])
    def test_machine_contract_is_checked_against_source_exposure(self):
        plan,_,_=fixture();plan['comparisonDenominators']=den.denominators(plan)
        self.assertTrue(den.audit(plan)['ok']);plan['comparisonDenominators']['originalMarked']['truthNails']=2
        self.assertEqual(den.audit(plan)['decision'],'reconstruction_mismatch')
    def test_stable_identity_allows_same_local_ordinal_and_variable_budget(self):
        plan,pack,index=fixture();self.assertEqual(m.validate_scope(plan,pack,index),10)
        plan['counts']['plannedInferenceInputs']=18
        with self.assertRaises(ValueError):m.validate_scope(plan,pack,index)
    def test_omitting_original_only_group_member_rejected(self):
        plan,pack,index=fixture();plan['sources']=plan['sources'][:1];pack['records']=pack['records'][:1]
        with self.assertRaisesRegex(ValueError,'whole source group'):m.validate_scope(plan,pack,index)
    def test_protected_parent_and_role_rejected_even_if_copied_to_plan(self):
        for field,value in [('protectedTrainConflicts',[{'parent':'protected'}]),('upstreamDevelopmentSplit','val'),
                            ('currentAndParentRoleMatches',[{'role':'frozenReleaseTest'}])]:
            plan,pack,index=fixture();index['records'][0][field]=value;plan['sources'][0]['roleEvidence']=copy.deepcopy(index['records'][0])
            with self.assertRaises(ValueError):m.validate_scope(plan,pack,index)
    def test_truth_identity_and_variant_order_drift_rejected(self):
        for change in ['truth','order','duplicate']:
            plan,pack,index=fixture()
            plan=copy.deepcopy(plan)
            if change=='truth':plan['sources'][0]['annotation']['sha256']='c'*64
            elif change=='order':plan['sources'][0]['variants'][1:3]=reversed(plan['sources'][0]['variants'][1:3])
            else:plan['sources'][1]['identity']=plan['sources'][0]['identity']
            with self.assertRaises(ValueError):m.validate_scope(plan,pack,index)
    def test_json_and_normalized_label_truths_keep_storage_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ann.json';p.write_text(json.dumps({'annotations':[{'polygon':[{'x':0,'y':0},{'x':4,'y':0},{'x':4,'y':4},{'x':0,'y':4}]}]}))
            q=Path(tmp)/'label.txt';q.write_text('0 0 0 .5 0 .5 .5 0 .5\n')
            base={'imageSize':[8,8],'completeVisibleNails':1}
            a=m.truth_masks({**base,'annotation':m.bind(p),'truthFormat':'original_pixel_polygon_annotation_json'})
            b=m.truth_masks({**base,'annotation':m.bind(q),'truthFormat':'yolo_normalized_polygon_label'})
            self.assertTrue(np.array_equal(a,b))
            q.write_text('0 0 0 2 0 .5 .5 0 .5\n')
            with self.assertRaises(ValueError):m.truth_masks({**base,'annotation':m.bind(q),'truthFormat':'yolo_normalized_polygon_label'})
    def test_per_variant_denominators_and_match_migration_are_explicit(self):
        plan,_,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);predictions={}
            for i,s in enumerate(plan['sources']):
                p=folder/f'{i}.json';p.write_text(json.dumps({'annotations':[{'polygon':[{'x':0,'y':0},{'x':3,'y':0},{'x':3,'y':3},{'x':0,'y':3}]}]}))
                s['annotation']=m.bind(p);s['truthFormat']='original_pixel_polygon_annotation_json'
                truth=m.truth_masks(s)
                for v in s['variants']:
                    mask=np.zeros((0,8,8),bool) if v['name']=='marker_removed' else truth
                    n=len(mask);ref=h.save_prediction(folder/f'{i}-{v["name"]}.npz',np.zeros((n,4),np.float32),np.full(n,.7,np.float32),np.zeros(n,np.float32),mask)
                    predictions[(m.key(s['identity']),v['name'])]=ref
            rows,aggregate,paired,summary=m.summarize_rows(plan['sources'],predictions,h,.75)
            self.assertEqual(aggregate['original']['truthNails'],2);self.assertEqual(aggregate['marker_removed']['truthNails'],1)
            self.assertEqual(paired['truthNails'],1);self.assertEqual(paired['matchedNails'],1)
            self.assertEqual(rows[0]['comparisons']['original__marker_removed']['newMissedTruthIndices'],[1])
            self.assertEqual(summary['marker_removed__blank_removed']['sourcesWithTruthMatchMigration'],1)

if __name__=='__main__':unittest.main()
