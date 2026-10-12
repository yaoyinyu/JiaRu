"""从存档logits、原像素真值和不可覆盖事件重放容量失败；不前向模型。"""
import argparse,importlib.util,json,hashlib,math
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
def module(p,n):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','native_verify_data')
def verify(path):
 report=d.read(d.bind(path));root=path.parent;plan=d.read(report['inputs']['plan']);data=d.read(plan['inputs']['materialization']);input_plan=d.read(data['plan'])
 for ref in plan['inputs'].values():d.checked(ref)
 d.checked(report['inputs']['weights']);rows=[r for r in data['records'] if r['split']=='train']
 if [r['candidateIdentity'] for r in rows]!=plan['candidateIdentities']:raise ValueError('train candidate identities')
 events=[json.loads(p.read_bytes()) for p in sorted((root/'events').glob('*.json'))]
 if [r['sequence'] for r in events]!=list(range(1,len(events)+1)):raise ValueError('event sequence')
 if [r['confirmedOptimizerSteps'] for r in events if r['phase']=='optimizer_confirmed']!=list(range(1,1089)):raise ValueError('1088 confirmed steps')
 if [r['attemptedStep'] for r in events if r['phase']=='optimizer_in_flight']!=list(range(1,1089)):raise ValueError('1088 attempts')
 if [r['completedEpochs'] for r in events if r['phase']=='epoch_completed']!=list(range(1,65)):raise ValueError('64 epochs')
 if events[-1]!=json.loads((root/'terminal.json').read_bytes()) or events[-1]['phase']!='closed':raise ValueError('terminal journal')
 if report['completedEpochs']!=64 or report['confirmedOptimizerSteps']!=1088 or report['trainCandidateInputs']!=68 or report['valModelInputs']!=0 or events[-1]['capacityOk']!=report['ok']:raise ValueError('capacity budget/meta reconstruction_mismatch')
 net=module(d.checked(plan['inputs']['modelSource']),'native_verify_model');roi=module(d.checked(input_plan['inputs']['roiHelper']),'native_verify_metric')
 guard=d.load(d.checked(input_plan['inputs']['readOnlyGuard']),'native_verify_guard');guard.install_read_only_ultralytics_image_check()
 metrics=[];attributions=[];missing_deltas=[];saved_outputs=[]
 scale=plan.get('priorChange',{}).get('newScale',8)
 if scale not in (8,2):raise ValueError('unsupported frozen coarse prior scale')
 try:
  for row in rows:
   with Image.open(d.checked(row['paths']['nativeTarget'])) as im:im.load();truth=np.asarray(im).copy()>=128
   with Image.open(d.checked(row['paths']['nativeCoarse'])) as im:im.load();coarse=np.asarray(im).copy()>0
   prediction_path=root/'predictions'/f'{row["ordinal"]:03d}.npz'
   saved_outputs.append(d.bind(prediction_path))
   with np.load(prediction_path,allow_pickle=False) as z:
    if set(z.files)!={'logits','presenceLogit'} or z['logits'].dtype!=np.float32 or z['logits'].shape!=truth.shape:raise ValueError('native prediction storage')
    a=z['logits'].copy();presence=float(z['presenceLogit'])
   prediction=net.decode(a,presence)
   delta=a-(coarse.astype(np.float32)*scale-scale/2)
   if row['presenceTarget']:
    b=roi.boundary_stats(truth,prediction,2);iou=int((truth&prediction).sum())/max(1,int((truth|prediction).sum()))
    metric={'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9}
    missed=truth&~coarse;missing_deltas.extend(delta[missed].tolist())
    attributions.append({'candidateIdentity':row['candidateIdentity'],'coarseIoU':int((truth&coarse).sum())/max(1,int((truth|coarse).sum())),
                         'finalIoU':iou,'changedMaskPixels':int(((a>=0)!=coarse).sum()),'missingCoarseTruePixels':int(missed.sum()),
                         'missingTruePixelsNotCrossingPrior':int((missed&(delta<scale/2)).sum())})
   else:metric={'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()}
   metrics.append(metric)
  pos=[r for r in metrics if r['positive']];neg=[r for r in metrics if not r['positive']]
  summary={'positiveCount':len(pos),'rejectCount':len(neg),'meanIou':float(np.mean([r['iou'] for r in pos])),
           'meanBoundaryIou':float(np.mean([r['boundaryIoU'] for r in pos])),'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in pos])),
           'jointPassCount':sum(r['jointPass'] for r in pos),'jointPassRate':sum(r['jointPass'] for r in pos)/66,
           'rejectedCount':sum(r['rejected'] for r in neg),'rejectOutputPixels':sum(r['outputPixels'] for r in neg)}
  ok=summary['jointPassRate']>=.8 and summary['meanIou']>=.85 and summary['meanBoundaryF1']>=.9 and summary['rejectedCount']==2 and summary['rejectOutputPixels']==0
  if metrics!=report['perCandidate'] or summary!=report['metrics'] or ok!=report['ok']:raise ValueError('capacity reconstruction_mismatch')
  return {'schemaVersion':1,'ok':True,'decision':'capacity_report_and_all_gates_replayed_no_new_model_calls',
          'capacity':d.bind(path),'capacityOk':ok,'metrics':summary,'events':len(events),'confirmedOptimizerSteps':1088,'epochs':64,
          'attributions':attributions,'coarsePriorAttribution':{'meanCoarseIou':float(np.mean([r['coarseIoU'] for r in attributions])),
           'meanFinalIou':summary['meanIou'],'missingTruePixelDeltaPercentiles':np.percentile(missing_deltas,[0,25,50,75,100]).tolist(),
           'initialAbsentPixelThresholdMargin':scale/2,'meaning':'optimization_prior_hypothesis_not_causal_or_representation_impossibility_proof'},
          'sourceModelForwardCallsInReplay':0,'optimizerStepsInReplay':0,'frozenSavedOutputs':saved_outputs,'originalCapacityOutcomeAndConsumedBudgetPreserved':True,'formalReleaseAllowed':False,'productHold':True}
 finally:
  for p in d.read(input_plan['inputs']['trainingContract'])['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(p))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args();r=verify(a.report.resolve())
 if a.output:d.new(a.output.resolve(),r)
 print(json.dumps({k:r[k] for k in ('ok','capacityOk','metrics','coarsePriorAttribution')}))
