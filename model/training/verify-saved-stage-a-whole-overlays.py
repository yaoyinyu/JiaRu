"""无输出图片的整幅预测页像素重建；全源角色先核验，最后清理扫描缓存。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageDraw
HERE=Path(__file__).resolve().parent
def module(path,name):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','whole_overlay_verifier_data')
COLORS=[(255,30,180),(0,210,255),(255,130,0),(170,60,255),(0,180,130),(255,220,0),(70,70,255),(200,30,30),(170,140,60),(30,150,255)]
def render(raw,source,masks,scores,number):
 w,h=raw.size;page=raw.copy();painter=ImageDraw.Draw(page)
 for polygon in source['polygons']:painter.line([*polygon,polygon[0]],fill=(20,255,30),width=1)
 for j,mask in enumerate(masks):
  boundary=mask & ~cv2.erode(mask.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
  y,x=np.where(boundary);pixels=np.asarray(page).copy();pixels[y,x]=COLORS[j];page=Image.fromarray(pixels)
  contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
  if contours:
   biggest=max(contours,key=cv2.contourArea);px,py=map(int,biggest[0,0]);ImageDraw.Draw(page).text((max(0,min(w-65,px)),max(0,min(h-14,py))),f'P{j+1}:{float(scores[j]):.2f}',fill=COLORS[j],stroke_width=1,stroke_fill=(0,0,0))
 canvas=Image.new('RGB',(w,h+64),(24,24,24));canvas.paste(page,(0,0));legend=ImageDraw.Draw(canvas)
 legend.text((8,h+4),f'{number:02d} {source["identity"]["split"]} GT={source["maskCount"]} P={len(masks)} native={w}x{h} GREEN=GT',fill='white')
 for j in range(len(masks)):legend.text((8+(j%5)*max(55,w//5),h+20+(j//5)*16),f'P{j+1}',fill=COLORS[j])
 return canvas
def verify(path):
 manifest=d.read(d.bind(path));diag=d.read(manifest['report']);ex=d.read(diag['execution']);plan=d.read(ex['inputs']['plan']);contract=d.read(plan['inputs']['contract'])
 sources=d.validate(contract)
 if [s['identity'] for s in sources]!=[p['identity'] for p in manifest['pages']]:raise ValueError('reconstruction_mismatch: complete ordered source cohort')
 if len(sources)!=20 or manifest['fileBytes']!=sum(p['fileBytes'] for p in manifest['pages']):raise ValueError('page denominator')
 helper=module(d.checked(ex['inputs']['predictionHelper']),'whole_overlay_saved_prediction')
 guard=d.load(d.checked(plan['inputs']['readOnlyGuard']),'whole_overlay_guard');guard.install_read_only_ultralytics_image_check()
 try:
  for number,(s,pred,page) in enumerate(zip(sources,diag['records'],manifest['pages'],strict=True),1):
   if pred['identity']!=s['identity'] or page['prediction']!=pred['prediction'] or page['ordinal']!=number:raise ValueError('page prediction identity')
   if page['sourceBox']!=[0,0,*s['size']] or page['pageOrigin']!=[0,0] or page['resampling']:raise ValueError('whole source region')
   with Image.open(d.checked(s['sourceImage'])) as im:im.load();raw=im.convert('RGB')
   if hashlib.sha256(raw.tobytes()).hexdigest()!=page['sourceRgbSha256']:raise ValueError('source RGB storage domain')
   _,scores,_,masks=helper.load_prediction(pred['prediction'],s['size']);expected=render(raw,s,masks,scores,number)
   with Image.open(d.checked(page['page'])) as actual:actual.load();actual=actual.convert('RGB')
   if actual.size!=expected.size or actual.tobytes()!=expected.tobytes():raise ValueError('reconstruction_mismatch: native whole overlay pixels')
  return {'ok':True,'pages':20,'newChatImageInputs':0,'additionalSourceInferenceInputs':0,'optimizerSteps':0}
 finally:
  for root in contract['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();print(json.dumps(verify(a.manifest)))
