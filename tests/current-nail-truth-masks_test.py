import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('truth',R/'model/training/read-current-nail-truth-masks.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class TruthTests(unittest.TestCase):
 def setUp(self):
  root=R/'model/reviews/test-temp';root.mkdir(exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=root);self.root=Path(self.tmp.name)
 def tearDown(self):
  assert self.root.resolve().is_relative_to((R/'model/reviews/test-temp').resolve())
  self.tmp.cleanup()
 def source(self,value,fmt='original_pixel_polygon_annotation_json',count=1):
  p=self.root/('label.txt' if 'yolo' in fmt else 'annotation.json');p.write_bytes((value if isinstance(value,str) else json.dumps(value)).encode());return {'annotation':{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()},'imageSize':[16,16],'truthFormat':fmt,'completeVisibleNails':count}
 def test_dict_pair_and_normalized_masks_are_pixel_identical(self):
  pts=[[4,4],[12,4],[12,12],[4,12]];d=m.truth_masks(self.source({'annotations':[{'polygon':[dict(x=x,y=y) for x,y in pts]}]}));a=m.truth_masks(self.source({'image':{'width':16,'height':16},'annotations':[{'polygon':pts}]}));b=m.truth_masks(self.source('0 .25 .25 .75 .25 .75 .75 .25 .75','yolo_normalized_polygon_label'));self.assertTrue(np.array_equal(d,a));self.assertTrue(np.array_equal(a,b));self.assertEqual(int(a.sum()),81)
 def test_mixed_point_representation_preserves_order(self):
  s=self.source({'annotations':[{'polygon':[[4,4],{'x':12,'y':4},[12,12],{'x':4,'y':12}]}]});self.assertEqual(int(m.truth_masks(s).sum()),81)
 def test_hash_drift_refused_without_rewriting_file(self):
  s=self.source({'annotations':[{'polygon':[[4,4],[12,4],[12,12]]}]});p=Path(s['annotation']['path']);p.write_bytes(b'changed');before=p.read_bytes()
  with self.assertRaisesRegex(ValueError,'reconstruction_mismatch'):m.truth_masks(s)
  self.assertEqual(p.read_bytes(),before)
 def test_bad_domain_point_count_and_empty_masks_refused(self):
  bad=[({'image':{'width':15},'annotations':[{'polygon':[[1,1],[3,1],[3,3]]}]},1),({'annotations':[{'polygon':[[1,1],[3,1],[float('nan'),3]]}]},1),({'annotations':[{'polygon':[[1,1],[3,1],[-1,3]]}]},1),({'annotations':[{'polygon':[[1,1],[3,1],[3,3]]}]},2),({'annotations':[{'polygon':[[1,1,5],[3,1],[3,3]]}]},1)]
  for data,count in bad:
   with self.assertRaises(ValueError):m.truth_masks(self.source(data,count=count))
if __name__=='__main__':unittest.main()
