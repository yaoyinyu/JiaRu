import importlib.util,unittest
from pathlib import Path
import cv2,numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('registration_fixture',R/'model/training/native-source-registration-diagnostic.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class RegistrationTests(unittest.TestCase):
 def setUp(self):
  rng=np.random.default_rng(40);src=rng.integers(0,256,(240,180,3),dtype=np.uint8);src=cv2.GaussianBlur(src,(3,3),0)
  for i in range(30):cv2.circle(src,(int(rng.integers(12,168)),int(rng.integers(12,228))),int(rng.integers(3,10)),tuple(int(v) for v in rng.integers(0,256,3)),-1)
  self.source=Image.fromarray(src);self.background=Image.fromarray(rng.integers(0,256,(720,720,3),dtype=np.uint8))
  self.spec={'seed':20261010,'maxFeatures':3000,'workingSize':[180,240],'ratioTest':.75,'minimumMatches':20,'ransacThresholdTargetPixels':3,'minimumInliers':12,'minimumInlierRatio':.5,'maximumMedianTargetReprojection':2,'minimumSourceFeatureHull':.2,'minimumTargetAreaFraction':.05,'maximumTargetAreaFraction':.2,'minimumSourceVisibleFraction':.9,'maximumMaeNormalizedRgb':12/255,'minimumWrongLocationControls':2,'maximumBestToWrongRatio':.5}
 def test_known_translation_full_footprint_pass_and_inputs_unchanged(self):
  target=self.background.copy();target.paste(self.source,(340,80));before=target.tobytes();r=m.register_positive(target,self.source,self.spec)
  self.assertTrue(r['positiveControlPassed']);self.assertEqual(r['selectedPassingOrientation'],'original');self.assertEqual(target.tobytes(),before);self.assertFalse(r['nativeVisualApproved']);self.assertEqual(r['candidateSourceCount'],0)
 def test_mirror_has_explicit_transform_and_no_native_approval(self):
  target=self.background.copy();target.paste(self.source.transpose(Image.Transpose.FLIP_LEFT_RIGHT),(340,80));r=m.register_positive(target,self.source,self.spec)
  self.assertTrue(r['positiveControlPassed']);self.assertEqual(r['selectedPassingOrientation'],'mirror_x');self.assertFalse(r['trainingAllowed'])
 def test_unrelated_source_rejects_and_never_scores_candidates(self):
  r=m.register_positive(self.background,self.source,self.spec);self.assertFalse(r['positiveControlPassed']);self.assertFalse(r['candidateComparisonComputed'])
 def test_geometry_rejects_collapse_and_outside(self):
  self.assertFalse(m.footprint(np.zeros((3,3)),(180,240),(720,720))['valid'])
  self.assertFalse(m.footprint(np.float64([[1,0,700],[0,1,700],[0,0,1]]),(180,240),(720,720))['valid'])
 def test_requires_explicit_rgb_and_preserves_error_threshold(self):
  with self.assertRaises(ValueError):m.register_positive(self.background.convert('L'),self.source,self.spec)
  target=self.background.copy();target.paste(self.source,(340,80));s=dict(self.spec,maximumMaeNormalizedRgb=-1);r=m.register_positive(target,self.source,s)
  self.assertFalse(r['positiveControlPassed']);self.assertTrue(any(x.get('pixelGates',{}).get('maximumMaeUnchanged') is False for x in r['variants']))
if __name__=='__main__':unittest.main()
