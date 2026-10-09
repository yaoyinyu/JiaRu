import importlib.util,unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('glyph',R/'model/training/glyph-local-marker-controls.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class GlyphTests(unittest.TestCase):
 def fixture(self):
  rgb=np.full((96,128,3),225,np.uint8);rgb[12:24,12:14]=30;rgb[22:24,12:25]=30;rgb[46:49,12:16]=180;return rgb,[8,8,32,32],[8,40,32,64],[80,40,104,64]
 def test_fixed_support_captures_dark_strokes(self):
  rgb,M,C,D=self.fixture();s=m.support_mask(rgb,M);self.assertTrue(s[12:24,12:14].all());self.assertFalse(s[:8].any());self.assertLess(int(s.sum()),24*24)
 def test_sparse_changes_native_pixels_and_pair_background_are_preserved(self):
  rgb,M,C,D=self.fixture();before=rgb.copy();s=m.support_mask(rgb,M);variants,masks=m.build_variants(rgb,s,M,C,D);self.assertTrue(np.array_equal(rgb,before));self.assertEqual(int(masks['M'].sum()),int(masks['C'].sum()));self.assertEqual(int(masks['M'].sum()),int(masks['D'].sum()))
  for name,allowed in [('remove',masks['M']),('blank_remove_control',masks['C']),('move_marker',masks['M']|masks['D']),('blank_move_control',masks['M']|masks['D'])]:self.assertTrue(np.array_equal(variants[name][allowed==0],rgb[allowed==0]))
  self.assertTrue(np.array_equal(variants['move_marker'][masks['D']==0],variants['blank_move_control'][masks['D']==0]));self.assertGreater(int(variants['remove'][14,12,0]),30)
 def test_overlapping_support_and_registration_size_drift_rejected(self):
  rgb,M,C,D=self.fixture();s=m.support_mask(rgb,M)
  with self.assertRaisesRegex(ValueError,'overlap'):m.build_variants(rgb,s,M,M,D)
  with self.assertRaisesRegex(ValueError,'size drift'):m.translate_support(s,M,[8,40,30,64])
 def test_box_overlap_is_allowed_only_for_disjoint_actual_support(self):
  rgb=np.full((96,128,3),225,np.uint8);s=np.zeros((96,128),np.uint8);s[10:12,10:12]=1;rgb[s>0]=20;variants,masks=m.build_variants(rgb,s,[0,0,40,40],[50,0,90,40],[0,30,40,70]);self.assertFalse((masks['M']&masks['D']).any());self.assertEqual(len(variants),5)
 def test_invalid_or_empty_input_rejected(self):
  rgb,M,C,D=self.fixture()
  with self.assertRaises(ValueError):m.support_mask(np.zeros((96,128),np.uint8),M)
  with self.assertRaisesRegex(ValueError,'empty'):m.support_mask(np.full_like(rgb,225),M)
  with self.assertRaises(ValueError):m.build_variants(rgb,np.zeros((96,128),np.uint8),M,C,D)
if __name__=='__main__':unittest.main()
