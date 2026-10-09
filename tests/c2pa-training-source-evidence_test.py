import copy
import importlib.util
import unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('c2pa_evidence',R/'model/training/audit-c2pa-training-source-evidence.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def fixture():
    return {'active_manifest':'fixture','manifests':{'fixture':{'label':'fixture','ingredients':[],
            'assertions':[{'label':'c2pa.actions.v2','data':{'allActionsIncluded':True,'actions':[{'action':'c2pa.created'}]}}]}},
            'validation_state':'Trusted','validation_results':{'activeManifest':{'success':[{'code':x} for x in m.REQUIRED],'failure':[],'informational':[]}}}
class EvidenceTests(unittest.TestCase):
    def test_valid_credential_never_grants_source_or_training_approval(self):
        value=fixture();out=m.summarize(value);self.assertTrue(out['credentialValidationQualified'])
        for field in ['completeParentChainProven','sourceParentIndependenceQualified','modelShortcutExclusionProven','trainingAllowed']:self.assertFalse(out[field])
    def test_individual_signature_success_cannot_override_sdk_failure(self):
        value=fixture();value['validation_state']='Invalid';value['validation_results']['activeManifest']['failure']=[{'code':'signingCredential.invalid'}];out=m.summarize(value)
        self.assertFalse(out['credentialValidationQualified']);self.assertTrue(out['signatureAndAssetHashIndividuallyValidated']['claimSignature'])
    def test_top_level_failure_or_missing_hard_binding_cannot_pass(self):
        value=fixture();value['validation_status']=[{'code':'assertion.dataHash.mismatch'}];self.assertFalse(m.summarize(value)['credentialValidationQualified'])
        value=fixture();value['validation_results']['activeManifest']['success'].pop();self.assertFalse(m.summarize(value)['credentialValidationQualified'])
    def test_missing_or_false_all_actions_and_zero_ingredients_remain_incomplete(self):
        for included in [False,None]:
            value=fixture();data=value['manifests']['fixture']['assertions'][0]['data']
            if included is None:del data['allActionsIncluded']
            else:data['allActionsIncluded']=included
            out=m.summarize(value);self.assertFalse(out['allActionsIncluded']);self.assertTrue(out['zeroDeclaredIngredientsNeverProvesNoReferenceInputs']);self.assertFalse(out['completeParentChainProven'])
    def test_watermark_action_retained_even_without_visible_marker(self):
        value=fixture();action={'action':'c2pa.watermarked.unbound'};value['manifests']['fixture']['assertions'][0]['data']['actions'].append(action)
        self.assertEqual(m.summarize(value)['declaredWatermarkActions'],[action])
    def test_untrusted_timestamp_not_promoted(self):
        value=fixture();value['validation_results']['activeManifest']['informational']=[{'code':'timeStamp.untrusted'}]
        self.assertFalse(m.summarize(value)['timestampTrusted'])
    def test_missing_active_scope_or_multiple_actions_refused(self):
        for mutation in ['active','scope','duplicate']:
            value=fixture()
            if mutation=='active':value['active_manifest']='other'
            elif mutation=='scope':del value['validation_results']['activeManifest']
            else:value['manifests']['fixture']['assertions']*=2
            with self.assertRaises(ValueError):m.summarize(value)
    def test_original_metadata_preserved(self):
        value=fixture();before=copy.deepcopy(value);m.summarize(value);self.assertEqual(value,before)
if __name__=='__main__':unittest.main()
