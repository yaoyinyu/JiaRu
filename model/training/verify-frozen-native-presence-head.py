"""只读重放新头4096更新、冻结mask及全68复合容量；不调用分割模型。"""
import argparse,importlib.util,json,hashlib
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('head_verify_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def verify(path):
 report=d.read(d.bind(path));root=path.parent;plan=d.read(report['inputs']['plan'])
 for ref in plan['inputs'].values():d.checked(ref)
 features=d.read(plan['inputs']['featureReport']);scope=d.read(features['inputs']['scope']);old=d.read(scope['inputs']['failedCapacity'])
 for ref in scope['inputs'].values():d.checked(ref)
 oldplan=d.read(scope['inputs']['priorPlan']);trainer=d.load(d.checked(oldplan['inputs']['trainer']),'head_verify_old_trainer')
 p,data,rows,net,metric,guard,native=trainer.resources(d.checked(scope['inputs']['priorPlan']))
 if [r['candidateIdentity'] for r in rows]!=[r['candidateIdentity'] for r in report['perCandidate']]:raise ValueError('all68 reconstruction_mismatch')
 events=[json.loads(f.read_bytes()) for f in sorted((root/'events').glob('*.json'))]
 if [e['sequence'] for e in events]!=list(range(1,len(events)+1)) or [e['confirmedOptimizerSteps'] for e in events if e['phase']=='optimizer_confirmed']!=list(range(1,4097)) or [e['attemptedStep'] for e in events if e['phase']=='optimizer_in_flight']!=list(range(1,4097)):raise ValueError('4096 successful head steps')
 if events[-1]!=json.loads((root/'terminal.json').read_bytes()) or events[-1]['phase']!='closed' or events[-1]['capacityOk']!=report['ok']:raise ValueError('terminal ledger')
 candidate=torch.load(d.checked(report['inputs']['candidateWeights']),map_location='cpu',weights_only=True)
 original=torch.load(d.checked(scope['inputs']['frozenModelWeights']),map_location='cpu',weights_only=True)
 hashes={k:hashlib.sha256(v.numpy().tobytes()).hexdigest() for k,v in candidate.items() if not k.startswith('presence.')}
 if hashes!=features['frozenMaskTensorHashes'] or any(not torch.equal(v,candidate[k]) for k,v in original.items() if not k.startswith('presence.')):raise ValueError('mask tensor changed')
 head=torch.load(d.checked(report['inputs']['headWeights']),map_location='cpu',weights_only=True)
 if not torch.equal(head['weight'],candidate['presence.weight']) or not torch.equal(head['bias'],candidate['presence.bias']):raise ValueError('new head/candidate binding')
 metrics=[];predictions=[];accepted=0
 try:
  for row,feature_row in zip(rows,features['records'],strict=True):
   with np.load(d.checked(feature_row['savedOutput']),allow_pickle=False) as archive:old_logits=archive['logits'].copy()
   path_npz=root/'predictions'/f'{row["ordinal"]:03d}.npz';predictions.append(d.bind(path_npz))
   with np.load(path_npz,allow_pickle=False) as archive:
    logits=archive['logits'].copy();presence=float(archive['presenceLogit'])
    if logits.dtype!=np.float32 or archive['presenceLogit'].dtype!=np.float32 or not np.array_equal(logits,old_logits):raise ValueError('stored raw mask changed')
   from PIL import Image
   with Image.open(d.checked(row['paths']['nativeTarget'])) as image:image.load();truth=np.asarray(image).copy()>=128
   prediction=net.decode(logits,presence)
   if row['presenceTarget']:
    accepted+=int(presence>=0);b=metric.boundary_stats(truth,prediction,2);iou=int((truth&prediction).sum())/max(1,int((truth|prediction).sum()))
    metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9})
   else:metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()})
  pos=[r for r in metrics if r['positive']];neg=[r for r in metrics if not r['positive']]
  summary={'positiveCount':66,'rejectCount':2,'positivePresenceAccepted':accepted,'meanIou':float(np.mean([r['iou'] for r in pos])),
   'meanBoundaryIou':float(np.mean([r['boundaryIoU'] for r in pos])),'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in pos])),
   'jointPassCount':sum(r['jointPass'] for r in pos),'jointPassRate':sum(r['jointPass'] for r in pos)/66,
   'rejectedCount':sum(r['rejected'] for r in neg),'rejectOutputPixels':sum(r['outputPixels'] for r in neg)}
  ok=summary['jointPassCount']>=53 and summary['meanIou']>=.85 and summary['meanBoundaryF1']>=.9 and summary['rejectedCount']==2 and summary['rejectOutputPixels']==0 and accepted==66
  if metrics!=report['perCandidate'] or summary!=report['metrics'] or ok!=report['ok'] or report['confirmedHeadOptimizerSteps']!=4096 or report['segmentationOptimizerSteps']!=0:raise ValueError('compound capacity reconstruction_mismatch')
  return {'schemaVersion':1,'ok':True,'decision':'head4096_mask_frozen_full68_capacity_replayed_no_new_mask_model_calls',
   'capacity':d.bind(path),'capacityOk':ok,'metrics':summary,'eventCount':len(events),'confirmedHeadOptimizerSteps':4096,
   'segmentationOptimizerSteps':0,'frozenMaskTensorHashesUnchanged':True,'nativeMaskLogitAndPixelDifferences':0,'savedOutputs':predictions,
   'oldFailurePreserved':scope['inputs']['failedCapacity'],'newMaskModelCalls':0,'newOptimizerSteps':0,'full30Allowed':False,'formalReleaseAllowed':False,'productHold':True}
 finally:
  for p in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(p))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args();result=verify(a.report.resolve())
 if a.output:d.new(a.output.resolve(),result)
 print(json.dumps({'ok':True,'capacityOk':result['capacityOk'],'metrics':result['metrics'],'headSteps':4096,'segmentationSteps':0,'events':result['eventCount']}))
