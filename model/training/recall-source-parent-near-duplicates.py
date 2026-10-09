"""按冻结合同执行来源治理召回；像素结果只生成待原像素审核图对。"""
from __future__ import annotations
import argparse,hashlib,importlib.util,io,json,os,sys,time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):
 p=Path(p).resolve();return {'path':str(p),'sha256':sha(p)}
def checked(ref):
 p=Path(ref['path']);assert p.is_file() and sha(p)==ref['sha256'],'reconstruction_mismatch: file identity '+str(p);return p
def read(ref):return json.loads(checked(ref).read_bytes())
def put(p,obj):
 with Path(p).open('xb') as f:f.write((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'));f.flush();os.fsync(f.fileno())
def validate_inventory(plan,inventory,targets):
 assert len(targets['targets'])==plan['counts']['targets']==inventory['counts']['targets']
 rows=inventory['corpus'];assert len(rows)==plan['counts']['referenceByteIdentities']==inventory['counts']['referenceByteIdentities']
 assert len({r['image']['sha256'] for r in rows})==len(rows),'reconstruction_mismatch: duplicate reference identity'
 assert len({r['imageSha256'] for r in targets['targets']})==len(targets['targets']),'reconstruction_mismatch: duplicate target identity'
 assert not plan['sourceParentIndependenceQualified'] and not inventory['trainingAllowed']
 assert plan['contract']['nativeAdjudication'].startswith('all recalled pairs require')
 for row in rows: assert row['roles'] and row['sourceGroups'] and not row['trainingAllowed']

def dhash(image):
 arr=np.asarray(image.convert('L').resize((17,16),Image.Resampling.LANCZOS));bits=0
 for b in (arr[:,:-1]>arr[:,1:]).flat:bits=(bits<<1)|int(b)
 return f'{bits:064x}'
def sift(gray,c):
 h,w=gray.shape;scale=min(1.,c['maxLongSide']/max(h,w))
 if scale<1:gray=cv2.resize(gray,(int(round(w*scale)),int(round(h*scale))),interpolation=cv2.INTER_AREA)
 points,desc=cv2.SIFT_create(nfeatures=c['maxFeatures']).detectAndCompute(gray,None)
 xy=np.asarray([p.pt for p in points],np.float32).reshape(-1,2)
 return xy,desc if desc is not None else np.zeros((0,128),np.float32),np.asarray([gray.shape[1],gray.shape[0]],np.int32)
def match(q,o,c):
 qa,qd,qs=q;oa,od,_=o
 if len(qd)<2 or len(od)<2:return {'candidate':False,'ratioMatches':0,'inliers':0,'queryHullCoverage':0.}
 pairs=cv2.BFMatcher(cv2.NORM_L2).knnMatch(qd,od,k=2)
 good=[a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance<c['ratio']*b.distance]
 if len(good)<c['minimumRatioMatches']:return {'candidate':False,'ratioMatches':len(good),'inliers':0,'queryHullCoverage':0.}
 left=np.asarray([qa[m.queryIdx] for m in good],np.float32);right=np.asarray([oa[m.trainIdx] for m in good],np.float32)
 cv2.setRNGSeed(c['seed']);matrix,inliers=cv2.findHomography(left,right,cv2.RANSAC,c['ransacThresholdPixels'],maxIters=2000,confidence=.995)
 if matrix is None or inliers is None:return {'candidate':False,'ratioMatches':len(good),'inliers':0,'queryHullCoverage':0.}
 keep=inliers[:,0].astype(bool);n=int(keep.sum());area=float(cv2.contourArea(cv2.convexHull(left[keep]))) if n>=3 else 0.;coverage=area/int(qs[0]*qs[1]);fraction=n/len(good)
 return {'candidate':n>=c['minimumInliers'] and fraction>=c['minimumInlierFraction'] and coverage>=c['minimumQueryInlierHullCoverage'],'ratioMatches':len(good),'inliers':n,'inlierFraction':fraction,'queryHullCoverage':coverage}
def recall(q,o,qhash,ohash,c):
 distance=(int(qhash,16)^int(ohash,16)).bit_count(); local=match(q,o,c)
 return {'recalled':distance<=12 or local['candidate'],'dhashDistance':distance,'localFeature':local}
def transform(image,name):
 w,h=image.size
 if name=='resize075':return image.resize((max(1,round(w*.75)),max(1,round(h*.75))),Image.Resampling.LANCZOS)
 if name=='centerCrop065':
  cw,ch=round(w*.65),round(h*.65);x,y=(w-cw)//2,(h-ch)//2;return image.crop((x,y,x+cw,y+ch))
 if name=='jpeg85':
  stream=io.BytesIO();image.convert('RGB').save(stream,format='JPEG',quality=85);stream.seek(0);result=Image.open(stream);result.load();return result
 raise ValueError('unsupported transform '+name)

def run(plan_path,out):
 plan_ref=bind(plan_path);plan=read(plan_ref);inventory=read(plan['inputs']['referenceInventory']);targets=read(plan['inputs']['targets']);validate_inventory(plan,inventory,targets)
 assert out.is_absolute();out.mkdir(exist_ok=False);(out/'events').mkdir()
 start=time.monotonic();seq=0;roots=set();terminal=False
 def event(kind,**fields):
  nonlocal seq;seq+=1;put(out/'events'/f'{seq:06d}.json',{'sequence':seq,'kind':kind,'elapsedSeconds':round(time.monotonic()-start,3),**fields})
 checked(plan['inputs']['readOnlyGuard']);sp=importlib.util.spec_from_file_location('near_recall_read_only_guard',plan['inputs']['readOnlyGuard']['path']);trainer=importlib.util.module_from_spec(sp);sys.modules[sp.name]=trainer;sp.loader.exec_module(trainer)
 trainer.install_read_only_ultralytics_image_check();cv2.setNumThreads(1)
 for key in ['cycle012Materialization','cleanDevelopmentEvaluation']:roots.add(Path(read(inventory['inputs'][key])['outputDir']))
 for root in roots:trainer.remove_ultralytics_label_caches(root)
 try:
  event('started',plan=plan_ref,counts=plan['counts'],runner=bind(__file__))
  for ref in inventory['inputs'].values():checked(ref)
  images={row['image']['sha256']:row['image'] for row in inventory['corpus']}
  for row in targets['targets']:images[row['imageSha256']]=row['sourceImage']
  for ref in images.values():checked(ref)
  old=read(plan['inputs']['historicalFeatureManifest']);oldmap={item['image']['sha256']:item for item in old['items']}
  oldplan=read(old['plan']);c=plan['contract']
  for k in ['maxLongSide','maxFeatures','ratio','minimumRatioMatches','minimumInliers','minimumInlierFraction','minimumQueryInlierHullCoverage','ransacThresholdPixels','seed']:assert c[k]==oldplan['contract'][k],'reconstruction_mismatch: cached algorithm'
  features={};hashes={};feature_records=[]
  for n,(digest,ref) in enumerate(sorted(images.items()),1):
   p=checked(ref);raw=p.read_bytes()
   with Image.open(io.BytesIO(raw)) as img:img.load();hashes[digest]=dhash(img)
   if digest in oldmap:
    item=oldmap[digest];assert item['image']['sha256']==digest
    with np.load(checked(item['feature']),allow_pickle=False) as data:f=(data['points'],data['descriptors'],data['size'])
    assert f[0].shape==(item['featureCount'],2) and f[1].shape==(len(f[0]),128) and f[2].tolist()==item['resizedSize'];origin='bound_old_cache'
   else:
    gray=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_GRAYSCALE);assert gray is not None;f=sift(gray,c);origin='current_pixels'
   features[digest]=f;feature_records.append({'image':ref,'dhash256':hashes[digest],'featureCount':len(f[0]),'origin':origin})
   if n%100==0:event('feature_progress',completed=n,total=len(images));print(json.dumps({'features':n,'total':len(images)}),flush=True)
  put(out/'features.json',{'plan':plan_ref,'records':feature_records});event('features_complete',total=len(images))
  controls=[]
  for ordinal,control in enumerate(plan['positiveControls'],1):
   p=checked(control['sourceImage']);digest=control['sourceImage']['sha256']
   if control['kind']=='bound_real_child_parent':result=recall(features[digest],features[control['referenceImage']['sha256']],hashes[digest],hashes[control['referenceImage']['sha256']],c)
   else:
    with Image.open(p) as original:original.load();img=transform(original,control['transform']).convert('RGB')
    gray=cv2.cvtColor(np.asarray(img),cv2.COLOR_RGB2GRAY);result=recall(sift(gray,c),features[digest],dhash(img),hashes[digest],c)
   controls.append({'ordinal':ordinal,'control':control,'result':result,'ok':result['recalled']});event('control_checked',ordinal=ordinal,ok=result['recalled'])
  controls_ok=len(controls)==c['controlsRequiredPass'] and all(x['ok'] for x in controls)
  put(out/'controls.json',{'plan':plan_ref,'controls':controls,'ok':controls_ok});event('controls_complete',ok=controls_ok)
  results=[]
  if controls_ok:
   for ordinal,target in enumerate(targets['targets'],1):
    digest=target['imageSha256'];hits=[];self_refs=[]
    for ref in inventory['corpus']:
     other=ref['image']['sha256']
     if digest==other:self_refs.append(ref);continue
     found=recall(features[digest],features[other],hashes[digest],hashes[other],c)
     if found['recalled']:hits.append({'reference':ref,'result':found})
    row={'ordinal':ordinal,'target':target,'featureCount':len(features[digest][0]),'lowFeatureQuery':len(features[digest][0])<c['lowFeatureQueryThreshold'],'comparisons':len(inventory['corpus'])-len(self_refs),'selfReferenceBindings':self_refs,'recalledPairs':hits,'independenceApproved':False,'trainingAllowed':False}
    put(out/f'query-{ordinal:03d}.json',row);results.append({'ordinal':ordinal,'report':bind(out/f'query-{ordinal:03d}.json'),'recalledPairs':len(hits),'comparisons':row['comparisons'],'lowFeatureQuery':row['lowFeatureQuery']});event('query_complete',ordinal=ordinal,recalledPairs=len(hits),comparisons=row['comparisons']);print(json.dumps({'query':ordinal,'of':len(targets['targets']),'hits':len(hits)}),flush=True)
  summary={'schemaVersion':1,'inputs':{'plan':plan_ref,'runner':bind(__file__),'features':bind(out/'features.json'),'controls':bind(out/'controls.json')},'executionStatus':'complete' if controls_ok else 'stopped_controls_failed','ok':controls_ok and len(results)==len(targets['targets']),'decision':'candidate_recall_only_native_pair_adjudication_pending' if controls_ok else 'positive_control_failure_no_qualification_conclusion','counts':{'targetsRequired':len(targets['targets']),'targetsCompleted':len(results),'references':len(inventory['corpus']),'positiveControls':len(controls),'positiveControlsPassed':sum(x['ok'] for x in controls),'comparisons':sum(x['comparisons'] for x in results),'recalledPairs':sum(x['recalledPairs'] for x in results),'lowFeatureQueries':sum(x['lowFeatureQuery'] for x in results)},'results':results,'sourceParentIndependenceQualified':False,'trainingAllowed':False,'modelCalls':0,'optimizerSteps':0,'elapsedSeconds':round(time.monotonic()-start,3)}
  event('terminal',executionStatus=summary['executionStatus'],counts=summary['counts']);put(out/'report.json',summary);terminal=True;print(json.dumps({'report':bind(out/'report.json'),'ok':summary['ok'],'counts':summary['counts']}),flush=True)
  return 0 if summary['ok'] else 2
 except BaseException as error:
  if not terminal:put(out/'failure.json',{'executionStatus':'failed','errorType':type(error).__name__,'error':str(error),'lastPersistedSequence':seq,'modelCalls':0,'optimizerSteps':0,'trainingAllowed':False})
  raise
 finally:
  for root in roots:trainer.remove_ultralytics_label_caches(root)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();sys.exit(run(args.plan.resolve(),args.output.resolve()))
