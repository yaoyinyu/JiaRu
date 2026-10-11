import copy,hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('whole_fixture',ROOT/'model/training/native-source-page-layout.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class WholePageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.raw=Image.new('RGB',(125,1000));self.raw.putdata([(i%251,(i//125)%253,(i*7)%255) for i in range(125000)]);self.source=self.root/'source.png';self.raw.save(self.source)
  self.item={'image':m.bind(self.source),'originalSize':[125,1000],'originalRgbSha256':hashlib.sha256(self.raw.tobytes()).hexdigest(),'sourcePixelCoverage':125000,'tilePixelCoverage':125000,'nativeLayout':'whole'};self.page=self.root/'whole.png';self.item['pages']=[m.whole_page(self.item,self.page)]
 def tearDown(self):self.tmp.cleanup()
 def test_whole_keeps_every_rgb_pixel_above_old_panel_height(self):
  self.assertEqual(m.check_pixels(self.item),125000);self.assertEqual(self.item['pages'][0]['tiles'][0]['pageOrigin'],[0,0]);self.assertEqual(m.load_rgb(m.bind(self.page)).tobytes(),self.raw.tobytes())
 def test_rebound_page_pixel_drift_or_resize_rejected(self):
  for raw in [self.raw.resize((124,1000)),self.raw.copy()]:
   if raw.size==self.raw.size:raw.putpixel((0,0),(255,255,255))
   raw.save(self.page);bad=copy.deepcopy(self.item);bad['pages'][0]['page']=m.bind(self.page)
   with self.assertRaises(AssertionError):m.check_pixels(bad)
 def test_wrong_full_extent_origin_mode_or_duplicate_page_rejected(self):
  variants=[]
  a=copy.deepcopy(self.item);a['pages'][0]['tiles'][0]['sourceBox'][3]=999;variants.append(a)
  a=copy.deepcopy(self.item);a['pages'][0]['tiles'][0]['pageOrigin']=[0,40];variants.append(a)
  a=copy.deepcopy(self.item);a['pages']*=2;variants.append(a)
  a=copy.deepcopy(self.item);a['nativeLayout']='unknown';variants.append(a)
  a=copy.deepcopy(self.item);a['pages'][0]['resampling']=True;variants.append(a)
  for a in variants:
   with self.assertRaises(AssertionError):m.check_pixels(a)
 def test_legacy_tiles_preserve_coverage_and_reject_missing_or_reordered(self):
  a=copy.deepcopy(self.item);a['nativeLayout']='tiles';a['pages']=[]
  for n,box in enumerate([(0,0,125,800),(0,800,125,1000)]):
   crop=self.raw.crop(box);pg=Image.new('RGB',(crop.width,crop.height+40));pg.paste(crop,(0,40));p=self.root/f'tile-{n}.png';pg.save(p);a['pages'].append({'page':m.bind(p),'size':list(pg.size),'tiles':[{'sourceBox':list(box),'pageOrigin':[0,40],'rawRgbSha256':hashlib.sha256(crop.tobytes()).hexdigest()}],'resampling':False})
  self.assertEqual(m.check_pixels(a),125000)
  for pages in [a['pages'][:1],list(reversed(a['pages']))]:
   bad=copy.deepcopy(a);bad['pages']=pages
   with self.assertRaises(AssertionError):m.check_pixels(bad)
 def test_guard_install_failure_precedes_pixel_decode(self):
  guard=self.root/'guard.py';guard.write_text("def install_read_only_ultralytics_image_check():\n raise RuntimeError('guard unavailable')\n",encoding='utf-8');plan=self.root/'plan.json';inv=self.root/'inventory.json';inv.write_text('{}',encoding='utf-8');plan.write_text(json.dumps({'inputs':{'referenceInventory':m.bind(inv),'readOnlyGuard':m.bind(guard)}}),encoding='utf-8')
  with patch.object(m.Image,'open') as opened:
   with self.assertRaisesRegex(RuntimeError,'guard unavailable'):
    with m.guarded_pixels({'inputs':{'plan':m.bind(plan)}}):m.check_pixels(self.item)
   opened.assert_not_called()
 def test_report_helper_binding_drift_precedes_pixel_decode(self):
  sp=importlib.util.spec_from_file_location('whole_report_fixture',ROOT/'model/training/audit-native-source-review-pages-v3.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
  p=self.root/'bad-report.json';p.write_text(json.dumps({'schemaVersion':3,'trainingAllowed':False,'sourceParentIndependenceQualified':False,'nativeVisualApproved':False,'images':[],'inputs':{'missingHelper':{'path':str(self.root/'missing.py'),'sha256':'0'*64}}}),encoding='utf-8')
  with patch.object(a.layout.Image,'open') as opened:
   with self.assertRaisesRegex(AssertionError,'reconstruction_mismatch'):a.run(p)
   opened.assert_not_called()
if __name__=='__main__':unittest.main()
