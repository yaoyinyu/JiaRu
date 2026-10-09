import copy,importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('album_delta',R/'model/training/recall-source-album-delta.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def fixture():
    contract={k:1 for k in m.KEYS};controls=[{'ordinal':i} for i in range(12)]
    plan={'contract':contract,'positiveControls':controls,'counts':{'newTargets':1,'references':1},'trainingAllowed':False,'newModelCalls':0,'optimizerSteps':0}
    old={'contract':copy.deepcopy(contract),'positiveControls':copy.deepcopy(controls)}
    report={'ok':True,'counts':{'positiveControlsPassed':12,'targetsCompleted':1}}
    oldtargets={'targets':[{'imageSha256':'old'}]};targets={'targets':[{'imageSha256':'new'}]};inventory={'corpus':[{'image':{'sha256':'ref'},'roles':['consumedPositiveTest'],'sourceGroups':['protected'],'trainingAllowed':False}]}
    return [plan,old,report,oldtargets,targets,inventory,copy.deepcopy(old)]
class DeltaTests(unittest.TestCase):
    def test_only_new_cohort_accepted_without_mutation(self):
        f=fixture();before=copy.deepcopy(f);self.assertTrue(m.validate(*f));self.assertEqual(f,before)
    def test_old_target_never_requeried(self):
        f=fixture();f[4]['targets'][0]['imageSha256']='old'
        with self.assertRaises(ValueError):m.validate(*f)
    def test_duplicate_or_empty_target_rejected(self):
        for rows in [[],[{'imageSha256':'new'}]*2]:
            f=fixture();f[4]['targets']=rows
            with self.assertRaises(ValueError):m.validate(*f)
    def test_algorithm_or_cached_algorithm_drift_rejected(self):
        for pos in [1,6]:
            f=fixture();f[pos]['contract']['ratio']=.5
            with self.assertRaises(ValueError):m.validate(*f)
    def test_prior_controls_or_denominator_failure_rejected(self):
        for field in ['positiveControlsPassed','targetsCompleted']:
            f=fixture();f[2]['counts'][field]=0
            with self.assertRaises(ValueError):m.validate(*f)
        f=fixture();f[0]['positiveControls'].pop()
        with self.assertRaises(ValueError):m.validate(*f)
    def test_protected_reference_role_and_permission_preserved(self):
        for field,value in [('roles',[]),('sourceGroups',[]),('trainingAllowed',True)]:
            f=fixture();f[5]['corpus'][0][field]=value
            with self.assertRaises(ValueError):m.validate(*f)
    def test_source_scan_never_authorizes_training_or_neural_budget(self):
        for field in ['trainingAllowed','newModelCalls','optimizerSteps']:
            f=fixture();f[0][field]=1
            with self.assertRaises(ValueError):m.validate(*f)
if __name__=='__main__':unittest.main()
