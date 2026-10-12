"""请求遥测缺失必须显式保留未知，不能伪造通过或忽略实测超限。"""
import copy,importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('whole_group_v2',R/'model/training/record-whole-source-quality-group-v2.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class ResourceTests(unittest.TestCase):
 def setUp(self):
  self.policy={'preparedRequestHardStopBytes':100000000,'batchImageFileAndPayloadLimitBytes':8388608,'allowBoundedWholeImagesWhenRequestTelemetryUnavailable':True};self.prep={'imageFileBytesTotal':1024};self.ref={'path':'fixture-prep.json','sha256':'fixture'};self.window={'ok':False,'maximumRecentCompressedBytes':None,'measuredRequestGatePassed':None,'boundedWholeImageSendingAuthorized':True,'preparation':self.ref,'boundedImageBatchBytes':1024}
 def test_explicit_unknown_kept(self):m.validate_resource_window(self.policy,self.window,self.ref,self.prep)
 def test_unknown_not_implicitly_authorized(self):
  self.policy['allowBoundedWholeImagesWhenRequestTelemetryUnavailable']=False
  with self.assertRaisesRegex(ValueError,'not authorized'):m.validate_resource_window(self.policy,self.window,self.ref,self.prep)
 def test_unknown_cannot_be_marked_passed(self):
  self.window['ok']=True
  with self.assertRaisesRegex(ValueError,'falsely marked passed'):m.validate_resource_window(self.policy,self.window,self.ref,self.prep)
 def test_measured_oversize_still_rejected(self):
  self.window={'ok':True,'maximumRecentCompressedBytes':100000000}
  with self.assertRaisesRegex(ValueError,'resource gate failed'):m.validate_resource_window(self.policy,self.window,self.ref,self.prep)
 def test_preparation_binding_required(self):
  self.window['preparation']={'path':'different','sha256':'other'}
  with self.assertRaisesRegex(ValueError,'binding mismatch'):m.validate_resource_window(self.policy,self.window,self.ref,self.prep)
 def test_budget_not_swapped(self):
  self.window['boundedImageBatchBytes']=1023
  with self.assertRaisesRegex(ValueError,'budget mismatch'):m.validate_resource_window(self.policy,self.window,self.ref,self.prep)
if __name__=='__main__':unittest.main()
