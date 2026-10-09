import copy,importlib.util,unittest
from pathlib import Path
sp=importlib.util.spec_from_file_location('native_page_audit',Path(__file__).resolve().parents[1]/'model/training/audit-native-source-review-pages.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class NativeViewTests(unittest.TestCase):
 def setUp(self):
  self.ref={'path':'bound-report.json','sha256':'a'*64};self.image={'image':{'path':'source.jpg','sha256':'b'*64},'originalSize':[800,1600],'pages':[{'page':{'sha256':'c'*64}},{'page':{'sha256':'d'*64}}]};self.record={'inputs':{'reviewReport':self.ref},'image':self.image['image'],'originalSize':[800,1600],'decision':{'actuallyViewed':True,'toolScalingNotice':False,'coordinateOriginsChecked':True,'nativeContentSummary':'完整两页原像素源图描述'},'trainingAllowed':False,'pages':self.image['pages']}
 def test_complete_view_binds_identity_and_pages(self):self.assertTrue(m.validate_view(self.record,self.image,self.ref))
 def test_missing_page_cannot_claim_complete_native_source(self):
  r=copy.deepcopy(self.record);r['pages']=r['pages'][:1]
  with self.assertRaises(AssertionError):m.validate_view(r,self.image,self.ref)
 def test_same_ordinal_other_image_or_report_rejected(self):
  for field in ['image','inputs']:
   r=copy.deepcopy(self.record)
   if field=='image':r['image']['sha256']='e'*64
   else:r['inputs']['reviewReport']['sha256']='e'*64
   with self.assertRaises(AssertionError):m.validate_view(r,self.image,self.ref)
 def test_scaled_unviewed_or_promoted_records_rejected(self):
  for field,value in [('toolScalingNotice',True),('actuallyViewed',False),('coordinateOriginsChecked',False)]:
   r=copy.deepcopy(self.record);r['decision'][field]=value
   with self.assertRaises(AssertionError):m.validate_view(r,self.image,self.ref)
  r=copy.deepcopy(self.record);r['trainingAllowed']=True
  with self.assertRaises(AssertionError):m.validate_view(r,self.image,self.ref)
if __name__=='__main__':unittest.main()
