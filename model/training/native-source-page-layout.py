"""整图/旧分块页的严格RGB保真与只读解码守卫。"""
import contextlib,hashlib,importlib.util,json,sys
from pathlib import Path
from PIL import Image
R=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(ref):
 p=Path(ref['path']);assert p.is_file() and sha(p)==ref['sha256'],'reconstruction_mismatch: SHA';return p
def read(ref):return json.loads(checked(ref).read_bytes())
@contextlib.contextmanager
def guarded_pixels(report):
 plan=read(report['inputs']['plan']);inv=read(plan['inputs']['referenceInventory']);p=checked(plan['inputs']['readOnlyGuard']);sys.path.insert(0,str(p.parent))
 sp=importlib.util.spec_from_file_location('whole_native_guard',p);guard=importlib.util.module_from_spec(sp);sys.modules[sp.name]=guard;sp.loader.exec_module(guard)
 guard.install_read_only_ultralytics_image_check()
 roots=[Path(read(inv['inputs'][k])['outputDir']) for k in ['cycle012Materialization','cleanDevelopmentEvaluation']]
 try:yield
 finally:
  for root in roots:guard.remove_ultralytics_label_caches(root)
def load_rgb(ref):
 with Image.open(checked(ref)) as im:im.load();return im.convert('RGB')
def whole_page(item,path):
 raw=load_rgb(item['image']);assert list(raw.size)==item['originalSize'];digest=hashlib.sha256(raw.tobytes()).hexdigest();assert digest==item['originalRgbSha256']
 assert not path.exists();raw.save(path);w,h=raw.size
 return {'page':bind(path),'size':[w,h],'tiles':[{'sourceBox':[0,0,w,h],'pageOrigin':[0,0],'rawRgbSha256':digest}],'resampling':False}
def check_pixels(item):
 raw=load_rgb(item['image']);w,h=raw.size;assert list(raw.size)==item['originalSize'] and hashlib.sha256(raw.tobytes()).hexdigest()==item['originalRgbSha256']
 mode=item.get('nativeLayout','tiles');assert mode in {'tiles','whole'}
 expected=[(0,0,w,h)] if mode=='whole' else [(x,y,min(w,x+660),min(h,y+800)) for y in range(0,h,800) for x in range(0,w,660)]
 if mode=='whole':assert len(item['pages'])==1
 actual=[]
 for pg in item['pages']:
  assert pg['resampling'] is False;page=load_rgb(pg['page']);assert list(page.size)==pg['size']
  if mode=='whole':assert page.size==raw.size and len(pg['tiles'])==1
  else:assert page.width<=1328 and page.height<=840
  for tile in pg['tiles']:
   box=tuple(tile['sourceBox']);actual.append(box);x,y=tile['pageOrigin'];crop=raw.crop(box)
   if mode=='whole':assert [x,y]==[0,0]
   else:assert y==40
   assert page.crop((x,y,x+crop.width,y+crop.height)).tobytes()==crop.tobytes() and hashlib.sha256(crop.tobytes()).hexdigest()==tile['rawRgbSha256']
 assert actual==expected and item['sourcePixelCoverage']==item['tilePixelCoverage']==w*h
 return w*h
