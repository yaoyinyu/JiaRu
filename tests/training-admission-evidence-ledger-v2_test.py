import copy,importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('ledger2',R/'model/training/audit-training-admission-evidence-ledger-v2.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def source(n):return {'identity':{'split':'train','fileName':n,'imageSha256':n*64},'sourceGroup':'g','sourceImage':{'path':n,'sha256':n*64},'annotation':{'path':n+'.json','sha256':'x'},'maskCount':5}
class LegacyEvidenceTests(unittest.TestCase):
 def fixture(self):
  s=[source('a'),source('b')];members=[{'identity':x['identity'],'sourceImage':x['sourceImage'],'currentSourceDisposition':'pending'} for x in s];g={'sourceGroup':'g','activeQualificationSources':s,'entireFrozenGroupMembership':members};rows=[{'identity':x['identity'],'decision':'pass','actuallyViewed':True,'toolScalingNotice':False,'coordinateAlignmentVerified':True,'controlRecordPreserved':{'sourcePreserved':x}} for x in s];d={'sourceGroup':'g','entireFrozenGroupMembership':members,'records':rows,'ok':True,'nativeControlScopeOnly':True,'modelAblationInputsReady':True,'trainingAllowed':False,'newModelCalls':0};return g,d
 def test_legacy_full_evidence_without_new_boolean_is_counted(self):
  g,d=self.fixture();self.assertNotIn('wholeGroupInputControlsQualified',g);self.assertEqual(m.validate_legacy_native_controls(g,d),g['activeQualificationSources']);self.assertFalse(d['trainingAllowed'])
 def test_full_membership_current_identity_and_actual_pass_required(self):
  g,d=self.fixture()
  for alter in ('missing','rework','scaled','truth'):
   bad=copy.deepcopy(d)
   if alter=='missing':bad['entireFrozenGroupMembership']=bad['entireFrozenGroupMembership'][:1]
   elif alter=='rework':bad['records'][0]['decision']='rework'
   elif alter=='scaled':bad['records'][0]['toolScalingNotice']=True
   else:bad['records'][0]['controlRecordPreserved']['sourcePreserved']['maskCount']=6
   with self.assertRaises(ValueError):m.validate_legacy_native_controls(g,bad)
 def test_model_or_training_approval_cannot_be_inherited(self):
  g,d=self.fixture()
  for field in ('trainingAllowed','newModelCalls'):
   bad=copy.deepcopy(d);bad[field]=True
   with self.assertRaises(ValueError):m.validate_legacy_native_controls(g,bad)
if __name__=='__main__':unittest.main()
