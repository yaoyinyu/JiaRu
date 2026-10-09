"""将来源图对完整源图按原像素分片重排，复用图片页但保留每个图对。"""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
from PIL import Image,ImageDraw
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(ref):
 p=Path(ref['path']);assert p.is_file() and sha(p)==ref['sha256'],'reconstruction_mismatch: image/report SHA';return p
def enc(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def write(p,x):
 with p.open('xb') as f:f.write(enc(x));f.flush();os.fsync(f.fileno())
def build(queue_path,plan_path,output,target_hashes):
 queue_ref=bind(queue_path);queue=json.loads(queue_path.read_bytes());plan_ref=bind(plan_path);plan=json.loads(plan_path.read_bytes());inventory=json.loads(checked(plan['inputs']['referenceInventory']).read_bytes())
 assert len(queue['pairs'])==queue['counts']['uniqueUnorderedPairs']
 all_targets={o['target']['imageSha256'] for pair in queue['pairs'] for o in pair['observations']};assert target_hashes and len(target_hashes)==len(set(target_hashes)) and set(target_hashes)<=all_targets
 selected=[];images={}
 for ordinal,pair in enumerate(queue['pairs'],1):
  observations=[o for o in pair['observations'] if o['target']['imageSha256'] in target_hashes]
  if not observations:continue
  selected.append({'queueOrdinal':ordinal,'pairIdentity':pair['pairIdentity'],'observations':observations,'nativeDecision':'pending'})
  for o in observations:
   for ref,kind in [(o['target']['sourceImage'],'target'),(o['reference']['image'],'reference')]:
    image=images.setdefault(ref['sha256'],{'image':ref,'kinds':[]});assert image['image']['sha256']==ref['sha256']
    if kind not in image['kinds']:image['kinds'].append(kind)
 expected=sum(any(o['target']['imageSha256'] in target_hashes for o in p['observations']) for p in queue['pairs']);assert len(selected)==expected
 for image in images.values():checked(image['image'])
 checked(plan['inputs']['readOnlyGuard']);sp=importlib.util.spec_from_file_location('native_pair_guard',plan['inputs']['readOnlyGuard']['path']);guard=importlib.util.module_from_spec(sp);sys.modules[sp.name]=guard;sp.loader.exec_module(guard);guard.install_read_only_ultralytics_image_check()
 roots=[Path(json.loads(checked(inventory['inputs'][k]).read_bytes())['outputDir']) for k in ['cycle012Materialization','cleanDevelopmentEvaluation']]
 output.mkdir(exist_ok=False);pages=output/'pages';pages.mkdir();records=[]
 try:
  for number,(digest,item) in enumerate(sorted(images.items(),key=lambda p:(p[0] not in target_hashes,p[0])),1):
   with Image.open(checked(item['image'])) as im:im.load();original=im.convert('RGB')
   w,h=original.size;tiles=[(x,y,min(w,x+660),min(h,y+800)) for y in range(0,h,800) for x in range(0,w,660)];page_refs=[]
   for part in range(0,len(tiles),2):
    entries=tiles[part:part+2];pw=sum(box[2]-box[0] for box in entries)+8*(len(entries)-1);ph=40+max(box[3]-box[1] for box in entries);page=Image.new('RGB',(pw,ph),'#222222');draw=ImageDraw.Draw(page);offset=0;layout=[]
    for box in entries:
     crop=original.crop(box);page.paste(crop,(offset,40));draw.text((offset+4,4),f'I{number:03d} {digest[:12]} RAW {box} {item["kinds"]}',fill='white')
     assert page.crop((offset,40,offset+crop.width,40+crop.height)).tobytes()==crop.tobytes();layout.append({'sourceBox':list(box),'pageOrigin':[offset,40],'rawRgbSha256':hashlib.sha256(crop.tobytes()).hexdigest()});offset+=crop.width+8
    p=pages/f'image-{number:03d}-page-{part//2+1:02d}.png';page.save(p);page_refs.append({'page':bind(p),'size':list(page.size),'tiles':layout,'resampling':False})
   records.append({'imageOrdinal':number,**item,'originalSize':[w,h],'originalRgbSha256':hashlib.sha256(original.tobytes()).hexdigest(),'pages':page_refs,'sourcePixelCoverage':w*h,'tilePixelCoverage':sum((b[2]-b[0])*(b[3]-b[1]) for b in tiles),'nativeViewed':False});assert records[-1]['sourcePixelCoverage']==records[-1]['tilePixelCoverage']
  report={'schemaVersion':1,'inputs':{'queue':queue_ref,'plan':plan_ref,'writer':bind(__file__)},'selectedTargetHashes':target_hashes,'counts':{'wholeQueuePairs':len(queue['pairs']),'selectedTargets':len(target_hashes),'selectedPairs':len(selected),'uniqueImages':len(records),'nativePages':sum(len(r['pages']) for r in records)},'pairs':selected,'images':records,'pixelFidelityOk':True,'nativeVisualApproved':False,'trainingAllowed':False,'sourceParentIndependenceQualified':False}
  write(output/'report.json',report);print(json.dumps({'report':bind(output/'report.json'),'counts':report['counts'],'images':[{'ordinal':r['imageOrdinal'],'sha':r['image']['sha256'][:12],'size':r['originalSize'],'pages':len(r['pages']),'kinds':r['kinds']} for r in records]},ensure_ascii=False))
 finally:
  for root in roots:guard.remove_ultralytics_label_caches(root)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--queue',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--target-sha',action='append',required=True);a=ap.parse_args();build(a.queue.resolve(),a.plan.resolve(),a.output.resolve(),a.target_sha)
