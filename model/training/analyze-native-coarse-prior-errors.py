"""从原像素存档输出定位粗种子边缘残留；不修改logits或扫描阈值。"""
import argparse,importlib.util,json
from pathlib import Path
import cv2,numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('prior_error_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def error_partition(truth,coarse,prediction):
 if truth.dtype!=bool or coarse.dtype!=bool or prediction.dtype!=bool or not truth.shape==coarse.shape==prediction.shape:raise ValueError('native mask domain')
 prior=coarse^truth;final=prediction^truth
 edge=coarse & ~cv2.erode(coarse.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
 strips={}
 for radius in (1,2,4,8):
  near=cv2.dilate(edge.astype(np.uint8),np.ones((2*radius+1,2*radius+1),np.uint8)).astype(bool)
  strips[str(radius)]={'pixels':int(near.sum()),'finalErrorPixels':int((final&near).sum()),
   'persistentPriorErrorPixels':int((final&prior&near).sum()),'newErrorPixels':int((final&~prior&near).sum())}
 return {'coarseErrorPixels':int(prior.sum()),'finalErrorPixels':int(final.sum()),
  'correctedPriorErrorPixels':int((prior&~final).sum()),'persistentPriorErrorPixels':int((prior&final).sum()),
  'newErrorPixels':int((~prior&final).sum()),'seedEdgeOriginalPixelStrips':strips}
def analyze(path):
 plan=d.read(d.bind(path))
 if plan['contract']!={'candidateCount':68,'positiveCount':66,'rejectCount':2,'radiiOriginalPixels':[1,2,4,8],'newModelCalls':0,'optimizerSteps':0,'logitsModified':False,'thresholdScanAllowed':False}:raise ValueError('contract')
 for ref in plan['inputs'].values():d.checked(ref)
 if d.checked(plan['inputs']['analyzer'])!=Path(__file__).resolve():raise ValueError('analyzer binding')
 capacity=d.read(plan['inputs']['capacity']);cp=d.read(capacity['inputs']['plan']);data=d.read(cp['inputs']['materialization']);ip=d.read(data['plan'])
 rows=[r for r in data['records'] if r['split']=='train']
 if len(rows)!=68 or sum(r['presenceTarget'] for r in rows)!=66 or [r['candidateIdentity'] for r in rows]!=cp['candidateIdentities']:raise ValueError('candidate denominator')
 net=d.load(d.checked(cp['inputs']['modelSource']),'prior_error_net');roi=d.load(d.checked(ip['inputs']['roiHelper']),'prior_error_metric')
 guard=d.load(d.checked(ip['inputs']['readOnlyGuard']),'prior_error_guard');guard.install_read_only_ultralytics_image_check()
 metrics=[];records=[]
 try:
  for row in rows:
   images={}
   for name in ('nativeTarget','nativeCoarse'):
    with Image.open(d.checked(row['paths'][name])) as image:image.load();images[name]=np.asarray(image).copy()
   truth=images['nativeTarget']>=128;coarse=images['nativeCoarse']>0
   with np.load(d.checked(plan['predictions'][str(row['ordinal'])]),allow_pickle=False) as z:
    logits=z['logits'].copy();presence=float(z['presenceLogit'])
    if logits.dtype!=np.float32 or logits.shape!=truth.shape or z['presenceLogit'].dtype!=np.float32 or set(z.files)!={'logits','presenceLogit'}:raise ValueError('saved storage')
   prediction=net.decode(logits,presence)
   if row['presenceTarget']:
    b=roi.boundary_stats(truth,prediction,2);iou=int((truth&prediction).sum())/max(1,int((truth|prediction).sum()))
    metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9})
    value=error_partition(truth,coarse,prediction);delta=logits-(coarse.astype(np.float32)*8-4)
    persistent=(coarse^truth)&(prediction^truth)
    value['persistentPriorErrorAbsDeltaPercentiles']=np.percentile(np.abs(delta[persistent]),[0,25,50,75,100]).tolist() if persistent.any() else []
    records.append({'candidateIdentity':row['candidateIdentity'],'presenceAccepted':presence>=0,**value})
   else:metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()})
  if metrics!=capacity['perCandidate']:raise ValueError('reconstruction_mismatch: full68 frozen metrics')
  total=sum(r['finalErrorPixels'] for r in records);strips={}
  for radius in ('1','2','4','8'):
   near=sum(r['seedEdgeOriginalPixelStrips'][radius]['finalErrorPixels'] for r in records)
   strips[radius]={'errorPixels':near,'fraction':near/max(1,total)}
  return {'schemaVersion':1,'ok':True,'decision':'same68_frozen_metrics_coarse_edge_error_attribution_diagnostic',
   'plan':d.bind(path),'records':records,'all68MetricsReconstructed':True,
   'summary':{'coarseErrorPixels':sum(r['coarseErrorPixels'] for r in records),'finalErrorPixels':total,
    'correctedPriorErrorPixels':sum(r['correctedPriorErrorPixels'] for r in records),
    'persistentPriorErrorPixels':sum(r['persistentPriorErrorPixels'] for r in records),
    'newErrorPixels':sum(r['newErrorPixels'] for r in records),'seedEdgeStrips':strips,
    'positivePresenceRejectedCount':sum(not r['presenceAccepted'] for r in records)},
   'meaning':'粗边缘位置相关仅是局部先验变量的待测依据，不证明因果、质量通过或删除目标资格',
   'newModelCalls':0,'optimizerSteps':0,'logitsModified':False,'formalReleaseAllowed':False,'productHold':True}
 finally:
  for root in d.read(ip['inputs']['trainingContract'])['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args();result=analyze(a.plan.resolve())
 if a.verify_report and result!=d.read(d.bind(a.verify_report)):raise ValueError('attribution replay mismatch')
 if a.output:d.new(a.output.resolve(),result)
 print(json.dumps({'ok':True,'summary':result['summary']}))
