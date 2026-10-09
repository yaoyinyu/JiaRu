import copy,importlib.util,tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from PIL import Image
P=Path(__file__).resolve().parents[1]/'model/training/recall-source-parent-near-duplicates.py'
sp=importlib.util.spec_from_file_location('source_parent_recall',P);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
C={'maxLongSide':640,'maxFeatures':512,'ratio':.75,'minimumRatioMatches':8,'minimumInliers':8,'minimumInlierFraction':.40,'minimumQueryInlierHullCoverage':.20,'ransacThresholdPixels':5.,'seed':1605}
class RecallTests(unittest.TestCase):
 def test_crop_positive_and_blank_cannot_manufacture_local_correspondence(self):
  rng=np.random.default_rng(1605);image=Image.fromarray(rng.integers(0,256,(320,420),dtype=np.uint8));crop=m.transform(image,'centerCrop065')
  full=m.sift(np.asarray(image),C);query=m.sift(np.asarray(crop),C);self.assertTrue(m.match(query,full,C)['candidate'])
  blank=m.sift(np.zeros((320,420),np.uint8),C);self.assertFalse(m.match(blank,full,C)['candidate'])
 def test_frozen_sha_missing_and_changed_bytes_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bound.json';p.write_bytes(b'original');ref=m.bind(p);self.assertEqual(m.checked(ref),p)
   p.write_bytes(b'changed')
   with self.assertRaises(AssertionError):m.checked(ref)
   p.unlink()
   with self.assertRaises(AssertionError):m.checked(ref)
 def test_duplicate_identity_or_unapproved_role_cannot_shrink_denominator(self):
  counts={'targets':1,'referenceByteIdentities':2};plan={'counts':counts,'sourceParentIndependenceQualified':False,'contract':{'nativeAdjudication':'all recalled pairs require raw review'}}
  rows=[{'image':{'sha256':'a'*64},'roles':['val'],'sourceGroups':['g1'],'trainingAllowed':False},{'image':{'sha256':'b'*64},'roles':['test'],'sourceGroups':['g2'],'trainingAllowed':False}]
  inv={'counts':counts,'corpus':rows,'trainingAllowed':False};targets={'targets':[{'imageSha256':'c'*64}]};m.validate_inventory(plan,inv,targets)
  bad=copy.deepcopy(inv);bad['corpus'][1]['image']['sha256']='a'*64
  with self.assertRaises(AssertionError):m.validate_inventory(plan,bad,targets)
  bad=copy.deepcopy(inv);bad['corpus'][0]['roles']=[]
  with self.assertRaises(AssertionError):m.validate_inventory(plan,bad,targets)
 def test_geometry_valid_but_inliers_below_contract_rejected(self):
  rng=np.random.default_rng(22);descriptors=rng.random((7,128),dtype=np.float32)*100;xy=np.array([[0,0],[50,0],[100,0],[0,50],[50,50],[100,50],[50,100]],np.float32)
  feature=(xy,descriptors,np.array([100,100]));self.assertFalse(m.match(feature,feature,C)['candidate'])
if __name__=='__main__':cv2.setNumThreads(1);unittest.main()
