import copy,hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
sp=importlib.util.spec_from_file_location('reuse_test',Path(__file__).resolve().parents[1]/'model/training/native-source-view-reuse.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class ReuseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'fixture.bin';self.source.write_bytes(b'identity-only-fixture');self.p1=self.root/'page1.bin';self.p1.write_bytes(b'page1-fixture');self.p2=self.root/'page2.bin';self.p2.write_bytes(b'page2-fixture');self.image={'image':self.bound(self.source),'originalSize':[800,1600],'originalRgbSha256':'a'*64,'pages':[{'page':self.bound(self.p1),'resampling':False},{'page':self.bound(self.p2),'resampling':False}]};self.prior=self.root/'report.json';self.put(self.prior,{'images':[self.image]});self.record={'inputs':{'reviewReport':self.bound(self.prior)},'image':self.image['image'],'originalSize':[800,1600],'decision':{'actuallyViewed':True,'toolScalingNotice':False,'coordinateOriginsChecked':True,'nativeContentSummary':'完整原像素描述'},'trainingAllowed':False,'pages':self.image['pages']};self.rpath=self.root/'record.json';self.put(self.rpath,self.record)
 def tearDown(self):self.tmp.cleanup()
 def bound(self,p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 def put(self,p,o):p.write_bytes(json.dumps(o,ensure_ascii=False).encode('utf-8'))
 def test_exact_identity_and_whole_view_inherit_but_not_pair_decision(self):
  result=m.validate_record(self.bound(self.rpath),self.image);self.assertNotIn('nativePairDecision',result)
 def test_truncated_page_set_cannot_inherit(self):
  r=copy.deepcopy(self.record);r['pages']=r['pages'][:1];self.put(self.rpath,r)
  with self.assertRaises(AssertionError):m.validate_record(self.bound(self.rpath),self.image)
 def test_scaled_unviewed_or_promoted_cannot_inherit(self):
  for field,value in [('toolScalingNotice',True),('actuallyViewed',False),('coordinateOriginsChecked',False)]:
   r=copy.deepcopy(self.record);r['decision'][field]=value;self.put(self.rpath,r)
   with self.assertRaises(AssertionError):m.validate_record(self.bound(self.rpath),self.image)
  r=copy.deepcopy(self.record);r['trainingAllowed']=True;self.put(self.rpath,r)
  with self.assertRaises(AssertionError):m.validate_record(self.bound(self.rpath),self.image)
 def test_alias_allowed_only_for_identical_bytes_and_rgb_domain(self):
  alias=self.root/'alias.bin';alias.write_bytes(self.source.read_bytes());item=copy.deepcopy(self.image);item['image']=self.bound(alias);self.assertEqual(m.validate_record(self.bound(self.rpath),item)['image'],self.record['image'])
  item['originalRgbSha256']='b'*64
  with self.assertRaises(AssertionError):m.validate_record(self.bound(self.rpath),item)
  self.p1.write_bytes(b'drift')
  with self.assertRaises(AssertionError):m.validate_record(self.bound(self.rpath),self.image)
if __name__=='__main__':unittest.main()
