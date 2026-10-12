"""只读冻结mask权重，全68原像素前向与存档同构后采集存在性特征。"""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('frozen_feature_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def tensors_sha(model):
 return {name:hashlib.sha256(value.detach().cpu().numpy().tobytes()).hexdigest() for name,value in model.state_dict().items()}
def validate_features(values,labels):
 if values.dtype!=np.float32 or values.ndim!=2 or values.shape[1]!=128 or not np.isfinite(values).all():raise ValueError('float32 finite128 feature domain')
 if labels.dtype!=np.uint8 or labels.shape!=(values.shape[0],) or not set(labels.tolist()).issubset({0,1}):raise ValueError('candidate labels')
 conflicts=[]
 for i in range(len(labels)):
  for j in range(i+1,len(labels)):
   if labels[i]!=labels[j] and np.array_equal(values[i],values[j]):conflicts.append([i,j])
 return conflicts
def materialize(plan_path,root):
 plan=d.read(d.bind(plan_path));scope=d.read(plan['inputs']['scope'])
 for ref in plan['inputs'].values():d.checked(ref)
 if plan['purpose']!='frozen_native_presence_features_no_optimizer' or d.checked(plan['inputs']['materializer'])!=Path(__file__).resolve():raise ValueError('feature contract')
 if scope['optimizerStepsAllowed']!=0 or scope['featureForwardInputsAllowed']!=68 or scope['newHeadBudgetRegistered']:raise ValueError('zero optimizer scope')
 for ref in scope['inputs'].values():d.checked(ref)
 failed=d.read(scope['inputs']['failedCapacity']);oldplan=d.read(scope['inputs']['priorPlan'])
 trainer=d.load(d.checked(oldplan['inputs']['trainer']),'frozen_feature_trainer')
 p,data,rows,net,metric,guard,native=trainer.resources(d.checked(scope['inputs']['priorPlan']))
 if [r['candidateIdentity'] for r in rows]!=scope['candidateIdentities']:raise ValueError('all68 identities')
 if root.exists():raise ValueError('feature package exists; no replay writer')
 features=[];records=[];metrics=[]
 try:
  samples=trainer.load_train(rows,net);model=net.NativeConditionalMaskRefiner().cuda().eval();model.requires_grad_(False);torch.set_num_threads(4)
  model.load_state_dict(torch.load(d.checked(scope['inputs']['frozenModelWeights']),map_location='cuda',weights_only=True),strict=True)
  before=tensors_sha(model);captured=[]
  handle=model.presence.register_forward_pre_hook(lambda module,args:captured.append(args[0].detach().cpu().numpy().copy()))
  try:
   for row,(x,target,positive) in zip(rows,samples,strict=True):
    captured.clear()
    with torch.inference_mode():logits,presence=model(x.cuda())
    a=logits[0,0].float().cpu().numpy();q=np.float32(float(presence[0,0]));truth=target[0,0].numpy()>0
    saved=Path(scope['inputs']['failedCapacity']['path']).parent/'predictions'/f'{row["ordinal"]:03d}.npz'
    with np.load(saved,allow_pickle=False) as z:
     if not np.array_equal(a,z['logits']) or q!=z['presenceLogit'] or z['logits'].dtype!=np.float32:raise ValueError('reconstruction_mismatch: frozen mask/presence forward')
    if len(captured)!=1 or captured[0].shape!=(1,128):raise ValueError('presence feature hook cardinality')
    prediction=net.decode(a,float(q))
    if positive:
     b=metric.boundary_stats(truth,prediction,2);iou=int((truth&prediction).sum())/max(1,int((truth|prediction).sum()))
     metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9})
    else:metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()})
    features.append(captured[0][0]);records.append({'candidateIdentity':row['candidateIdentity'],'presenceTarget':positive,
     'featureIndex':len(features)-1,'nativeShape':list(a.shape),'savedOutput':d.bind(saved),
     'maskLogitDifference':0,'maskPixelDifferences':0,'oldPresenceLogitDifference':0})
  finally:handle.remove()
  if metrics!=failed['perCandidate'] or before!=tensors_sha(model):raise ValueError('frozen metrics/weights reconstruction_mismatch')
  matrix=np.stack(features).astype(np.float32);labels=np.array([r['presenceTarget'] for r in rows],dtype=np.uint8);conflicts=validate_features(matrix,labels)
  root.mkdir(parents=True,exist_ok=False)
  with (root/'features.npz').open('xb') as stream:np.savez_compressed(stream,features=matrix,labels=labels);stream.flush();os.fsync(stream.fileno())
  report={'schemaVersion':1,'ok':True,'decision':'all68_frozen_masks_and_metrics_identical_features_materialized_no_optimizer',
   'inputs':{'plan':d.bind(plan_path),'scope':plan['inputs']['scope'],'featureArchive':d.bind(root/'features.npz')},
   'records':records,'featureShape':[68,128],'featureStorage':'float32','positiveCount':66,'rejectCount':2,
   'crossClassExactFeatureConflicts':conflicts,'all68MetricsReconstructed':True,'allModelTensorHashesUnchanged':True,
   'frozenMaskTensorHashes':{k:v for k,v in before.items() if not k.startswith('presence.')},
   'modelForwardInputs':68,'valModelInputs':0,'protectedModelInputs':0,'optimizerSteps':0,'oldOptimizerStateRead':False,
   'maskLogitDifferences':0,'maskPixelDifferences':0,'formalReleaseAllowed':False,'productHold':True}
  d.new(root/'report.json',report);print(json.dumps({'ok':True,'shape':[68,128],'conflicts':len(conflicts),'maskDifferences':0,'optimizerSteps':0}))
 finally:
  for path in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();materialize(a.plan.resolve(),a.output.resolve())
