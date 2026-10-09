"""原像素页重放：严格核对全图坐标、完整像素覆盖及实际查看绑定。"""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
from PIL import Image
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checked(ref):
 p=Path(ref['path']);assert p.is_file() and sha(p)==ref['sha256'],'reconstruction_mismatch: SHA';return p
def validate_view(record,image,report_ref):
 assert record['inputs']['reviewReport']==report_ref and record['image']==image['image'] and record['originalSize']==image['originalSize']
 decision=record['decision'];assert decision['actuallyViewed'] and decision['toolScalingNotice'] is False and decision['coordinateOriginsChecked']
 assert decision['nativeContentSummary'] and record['trainingAllowed'] is False
 assert {p['page']['sha256'] for p in record['pages']}=={p['page']['sha256'] for p in image['pages']} and len(record['pages'])==len(image['pages'])
 return True
def run(report_path,require_actual):
 ref={'path':str(report_path),'sha256':sha(report_path)};report=json.loads(report_path.read_bytes());plan=json.loads(checked(report['inputs']['plan']).read_bytes());inv=json.loads(checked(plan['inputs']['referenceInventory']).read_bytes())
 sp=importlib.util.spec_from_file_location('native_pages_audit_guard',checked(plan['inputs']['readOnlyGuard']));guard=importlib.util.module_from_spec(sp);sys.modules[sp.name]=guard;sp.loader.exec_module(guard);guard.install_read_only_ultralytics_image_check();roots=[Path(json.loads(checked(inv['inputs'][k]).read_bytes())['outputDir']) for k in ['cycle012Materialization','cleanDevelopmentEvaluation']];viewed=0;pixels=0;pages=0
 try:
  for item in report['images']:
   with Image.open(checked(item['image'])) as im:im.load();raw=im.convert('RGB')
   w,h=raw.size;assert list(raw.size)==item['originalSize'] and hashlib.sha256(raw.tobytes()).hexdigest()==item['originalRgbSha256']
   expected=[(x,y,min(w,x+660),min(h,y+800)) for y in range(0,h,800) for x in range(0,w,660)];actual=[]
   for pg in item['pages']:
    assert pg['resampling'] is False
    with Image.open(checked(pg['page'])) as im:im.load();page=im.convert('RGB')
    assert list(page.size)==pg['size'] and page.width<=1328 and page.height<=840;pages+=1
    for tile in pg['tiles']:
     box=tuple(tile['sourceBox']);actual.append(box);crop=raw.crop(box);x,y=tile['pageOrigin'];assert y==40
     assert page.crop((x,y,x+crop.width,y+crop.height)).tobytes()==crop.tobytes() and hashlib.sha256(crop.tobytes()).hexdigest()==tile['rawRgbSha256']
   assert actual==expected and item['sourcePixelCoverage']==item['tilePixelCoverage']==w*h;pixels+=w*h
   if require_actual:
    p=report_path.parent/'actual-native'/f"image-{item['imageOrdinal']:03d}.json";record=json.loads(p.read_bytes());validate_view(record,item,ref)
    for binding in record['inputs'].values():checked(binding)
    viewed+=1
  return {'ok':True,'meaning':'pixel_and_actual_binding_replay_not_replacement_for_visual_judgment','images':len(report['images']),'nativePages':pages,'sourcePixels':pixels,'actuallyViewedImages':viewed,'trainingAllowed':False}
 finally:
  for root in roots:guard.remove_ultralytics_label_caches(root)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--require-actual',action='store_true');a=ap.parse_args();print(json.dumps(run(a.report.resolve(),a.require_actual),ensure_ascii=False))
