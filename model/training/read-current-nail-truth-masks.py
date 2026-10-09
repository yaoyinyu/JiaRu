"""读取现行原像素字典/坐标对及YOLO归一化真值；不改存储域或批准质量。"""
import hashlib,json,math
from pathlib import Path

def checked(ref):
 p=Path(ref['path'])
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('reconstruction_mismatch: annotation identity')
 return p

def truth_masks(source):
 from PIL import Image,ImageDraw
 import numpy as np
 p=checked(source['annotation']);w,h=source['imageSize'];fmt=source['truthFormat'];polygons=[]
 if not isinstance(w,int) or not isinstance(h,int) or min(w,h)<1:raise ValueError('invalid image domain')
 if fmt=='original_pixel_polygon_annotation_json':
  d=json.loads(p.read_bytes());image=d.get('image',{})
  if ('width' in image and image['width']!=w) or ('height' in image and image['height']!=h):raise ValueError('annotation native domain drift')
  for a in d['annotations']:
   polygon=[]
   for q in a['polygon']:
    if isinstance(q,dict) and 'x' in q and 'y' in q:x,y=q['x'],q['y']
    elif isinstance(q,(list,tuple)) and len(q)==2:x,y=q
    else:raise ValueError('unsupported native point representation')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (x,y)) or not (0<=x<=w and 0<=y<=h):raise ValueError('native coordinate outside domain')
    polygon.append((x,y))
   polygons.append(polygon)
 elif fmt=='yolo_normalized_polygon_label':
  for line in p.read_text(encoding='utf-8').splitlines():
   vals=list(map(float,line.split()))
   if len(vals)<7 or len(vals)%2!=1 or vals[0]!=0 or any(not math.isfinite(x) or not 0<=x<=1 for x in vals[1:]):raise ValueError('invalid normalized truth')
   polygons.append([(vals[j]*w,vals[j+1]*h) for j in range(1,len(vals),2)])
 else:raise ValueError('unsupported truth storage domain')
 if len(polygons)!=source['completeVisibleNails'] or not polygons:raise ValueError('truth denominator drift')
 masks=[]
 for polygon in polygons:
  if len(polygon)<3:raise ValueError('invalid polygon vertex count')
  im=Image.new('L',(w,h));ImageDraw.Draw(im).polygon(polygon,fill=255);mask=np.asarray(im)>0
  if not mask.any():raise ValueError('empty truth mask')
  masks.append(mask)
 return np.stack(masks)
