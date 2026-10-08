"""异构预算/完整组/保护血缘拒绝；模拟预测保留不同变体的实际真值分母。"""
import copy
import importlib.util
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('heterogeneous_train',R/'model/training/run-heterogeneous-quality-accounted-train-marker-probe.py')

def fixture():
 sources=[];records=[];roles=[];controls=[];members=[]
 for i,marked in enumerate([False,True,True,True,False]):
  identity={'split':'train','fileName':f'{i}.jpg','imageSha256':str(i)*64}
  image={'path':f'{i}.jpg','sha256':str(i)*64};ann={'path':f'{i}.json','sha256':'a'*64}
  truth={'annotation':ann,'imageSize':[20,20],'geometry':{'maskCount':5,'format':'original_pixel_polygon_annotation_json'}}
  role={'identity':identity,'sourceGroup':'g','sourceImage':image,'upstreamDevelopmentSplit':'train',
    'trainingUse':'prohibited','formalTrainingApproved':False,'protectedTrainConflicts':[],
    'currentSourceDisposition':'complete_masks_pass_pending_full_split','currentAndParentRoleMatches':[{'role':'developmentTrain'}],'currentTruth':truth}
  roles.append(role);members.append({'identity':identity})
  packnames=m.PACK_NAMES if marked else ['original'];names=m.NAMES if marked else ['original']
  variants={k:{'path':f'{i}-{k}.png','sha256':'b'*64} for k in packnames}
  rec={'identity':identity,'sourceGroup':'g','sourcePreserved':{'sourceImage':image,'annotation':ann,'imageSize':[20,20],'maskCount':5,
       'windows':[{'name':'marker'}] if marked else [],'sourcePreserved':{'geometry':{'format':'original_pixel_polygon_annotation_json'}}},'variants':variants}
  records.append(rec);controls.append({'identity':identity,'controlRecordPreserved':copy.deepcopy(rec),'decision':'pass','actuallyViewed':True,'toolScalingNotice':False})
  sources.append({'identity':identity,'sourceGroup':'g','sourceImage':image,'annotation':ann,'imageSize':[20,20],'completeVisibleNails':5,
      'truthFormat':'original_pixel_polygon_annotation_json','markerControlRequired':marked,'roleEvidence':copy.deepcopy(role),'trainingUse':'prohibited',
      'variants':[{'name':name,'image':variants[k]} for name,k in zip(names,packnames,strict=True)]})
 identity={'split':'train','fileName':'excluded.jpg','imageSha256':'f'*64};image={'path':'excluded.jpg','sha256':'f'*64}
 role={'identity':identity,'sourceGroup':'g','sourceImage':image,'upstreamDevelopmentSplit':'train','trainingUse':'prohibited','formalTrainingApproved':False,
       'protectedTrainConflicts':[],'currentSourceDisposition':'source_quality_excluded','currentAndParentRoleMatches':[{'role':'developmentTrain'}]}
 roles.append(role);excluded={'identity':identity,'sourceGroup':'g','sourceImage':image,'currentSourceDisposition':'source_quality_excluded'};members.append(excluded)
 plan={'contract':copy.deepcopy(m.CONTRACT),'sources':sources,'excludedMembers':[{**copy.deepcopy(excluded),'roleEvidence':copy.deepcopy(role),'trainingUse':'prohibited','inferenceUse':'prohibited'}],
       'entireFrozenGroupMembership':copy.deepcopy(members),'counts':{'wholeMembers':6,'sourceImages':5,'completeVisibleNails':25,'excludedSources':1,'markedSources':3,'originalOnlySources':2,'plannedInferenceInputs':17}}
 pack={'records':records,'entireFrozenGroupMembership':members,'excludedMembers':[excluded]}
 close={'ok':True,'inputControlsQualified':True,'wholeGroupModelMarkerQualified':False,'trainingAllowed':False,'modelCalls':0,
        'currentControlDecisions':controls,'excludedMembersPreserved':[copy.deepcopy(excluded)]}
 return plan,pack,{'records':roles},close

class HeterogeneousTests(unittest.TestCase):
 def test_exact_six_members_five_inputs_roles_and_seventeen_budget(self):self.assertEqual(m.validate_scope(*fixture()),17)
 def test_uniform_twentyfive_budget_rejected(self):
  p,pk,i,c=fixture();p['counts']['plannedInferenceInputs']=25
  with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_omitting_original_only_or_excluded_rejected(self):
  for case in ['original','excluded']:
   p,pk,i,c=fixture()
   if case=='original':p['sources'].pop(0);pk['records'].pop(0);c['currentControlDecisions'].pop(0)
   else:p['excludedMembers']=[]
   with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_registered_mark_cannot_be_relabelled_original_only(self):
  p,pk,i,c=fixture();p['sources'][1]['markerControlRequired']=False
  with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_protected_parent_or_upstream_val_on_active_and_excluded_rejected(self):
  for target in [0,-1]:
   for case in ['parent','val']:
    p,pk,i,c=fixture();r=i['records'][target]
    if case=='parent':r['currentAndParentRoleMatches'].append({'role':'consumedPositiveTest'})
    else:r['upstreamDevelopmentSplit']='val'
    (p['sources'][0] if target==0 else p['excludedMembers'][0])['roleEvidence']=copy.deepcopy(r)
    with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_active_marker_isolation_or_changed_truth_storage_rejected(self):
  for case in ['isolated','truth']:
   p,pk,i,c=fixture();r=i['records'][0]
   if case=='isolated':r['currentSourceDisposition']='source_marker_isolated'
   else:r['currentTruth']['geometry']['format']='yolo_normalized_polygon_label'
   p['sources'][0]['roleEvidence']=copy.deepcopy(r)
   with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_rework_false_visual_or_model_promotion_rejected(self):
  for case in ['rework','unviewed','model']:
   p,pk,i,c=fixture()
   if case=='rework':c['currentControlDecisions'][0]['decision']='rework'
   elif case=='unviewed':c['currentControlDecisions'][0]['actuallyViewed']=False
   else:c['wholeGroupModelMarkerQualified']=True
   with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_variant_order_and_excluded_permission_rejected(self):
  for case in ['order','permission']:
   p,pk,i,c=fixture()
   if case=='order':p['sources'][1]['variants'].reverse()
   else:p['excludedMembers'][0]['inferenceUse']='allowed'
   with self.assertRaises(ValueError):m.validate_scope(p,pk,i,c)
 def test_original_only_rows_stay_in_full_denominator_and_not_paired_comparison(self):
  import numpy as np
  p,_,_,_=fixture();sources=p['sources']
  class Truth:
   @staticmethod
   def truth_masks(s):return np.ones((5,20,20),bool)
  class Helper:
   @staticmethod
   def load_prediction(ref,size):return np.zeros((5,4)),np.ones(5),np.zeros(5),np.ones((5,20,20),bool)
   @staticmethod
   def match_masks(mask,truth,threshold):return {'matches':[{}]*5,'missedTruthIndices':[],'unmatchedPredictionIndices':[]}
   @staticmethod
   def comparison(*args):return {'candidateCountDelta':0,'newMissedTruthIndices':[],'recoveredTruthIndices':[],'unionSymmetricDifferencePixels':0}
  predictions={(m.key(s['identity']),v['name']):{} for s in sources for v in s['variants']}
  rows,agg,summary,pattern=m.summarize(sources,predictions,Helper,Truth,.75)
  self.assertEqual((agg['original']['sourceImages'],agg['original']['truthNails']),(5,25))
  self.assertEqual((agg['marker_removed']['sourceImages'],agg['marker_removed']['truthNails']),(3,15))
  self.assertEqual(rows[0]['comparisons'],{})
  self.assertTrue(all(v['sourcesCompared']==3 for v in summary.values()))
  self.assertEqual(pattern['pairedCandidateOrMatchMigrationSources'],0)
if __name__=='__main__':unittest.main()
