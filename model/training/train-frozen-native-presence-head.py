"""冻结分割、新初始化线性头一次预算；只优化129头参数，最终全68重验。"""
import argparse,hashlib,importlib.util,json,os,time,traceback
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('head_fit_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
reader=d.load(HERE/'materialize-frozen-native-presence-features.py','head_frozen_feature_reader')
def exact_head_parameters(head,parameters):
 selected=list(parameters)
 if len(selected)!=2 or {id(x) for x in selected}!={id(x) for x in head.parameters()}:raise ValueError('optimizer must contain only fresh head2 tensors')
 return selected
def fresh_head():
 torch.manual_seed(20261012);torch.set_num_threads(4);head=torch.nn.Linear(128,1)
 with torch.no_grad():head.weight.zero_();head.bias.fill_(2.)
 return head
def cached(plan_path):
 plan=d.read(d.bind(plan_path))
 for ref in plan['inputs'].values():d.checked(ref)
 if plan['purpose']!='frozen_mask_fresh_presence_head_once' or plan['budget']!={'maximumAttempts':1,'optimizerSteps':4096,'segmentationOptimizerSteps':0,'oldBudgetsMayResume':False}:raise ValueError('head once budget')
 report=d.read(plan['inputs']['featureReport']);scope=d.read(report['inputs']['scope']);cert=d.read(plan['inputs']['linearCertificate'])
 if not cert['certificate']['reachable'] or not cert['witnessNeverTrainingOrProductionWeights'] or report['optimizerSteps'] or not report['all68MetricsReconstructed']:raise ValueError('feature/certificate gate')
 if cert['inputs']['featureReport']!=plan['inputs']['featureReport'] or [r['candidateIdentity'] for r in report['records']]!=scope['candidateIdentities']:raise ValueError('all68 identity')
 with np.load(d.checked(report['inputs']['featureArchive']),allow_pickle=False) as archive:x=archive['features'].copy();labels=archive['labels'].copy()
 if reader.validate_features(x,labels) or x.shape!=(68,128) or int(labels.sum())!=66:raise ValueError('fixed feature domain/classes')
 return plan,report,scope,torch.from_numpy(x),torch.from_numpy(labels.astype(np.float32)).reshape(-1,1)
def balanced_loss(head,x,y):
 weight=torch.where(y>0,torch.full_like(y,68/132),torch.full_like(y,17.))
 return .5*(F.binary_cross_entropy_with_logits(head(x),y,reduction='none')*weight).mean()
def preflight(path,output):
 plan,features,scope,x,y=cached(path);head=fresh_head();loss=balanced_loss(head,x,y);loss.backward()
 if not torch.isfinite(loss) or any(p.grad is None or not torch.isfinite(p.grad).all() for p in head.parameters()):raise ValueError('head gradient finite')
 exact_head_parameters(head,head.parameters())
 result={'schemaVersion':1,'ok':True,'decision':'fresh129_head_all68_balanced_gradient_gate_no_optimizer',
  'plan':d.bind(path),'initialWeightSha256':hashlib.sha256(head.weight.detach().numpy().tobytes()).hexdigest(),
  'initialBias':2.,'parameterCount':129,'finiteUsedGradientTensors':2,'initialLoss':float(loss.detach()),
  'maskParametersInOptimizer':0,'oldOptimizerRead':False,'certificateCoefficientsReadForTraining':False,'optimizerSteps':0,
  'formalReleaseAllowed':False,'productHold':True}
 d.new(output,result);print(json.dumps({'ok':True,'headParameters':129,'optimizerSteps':0}))
def native_postflight(head,scope,features):
 oldplan=d.read(scope['inputs']['priorPlan']);trainer=d.load(d.checked(oldplan['inputs']['trainer']),'head_postflight_trainer')
 plan,data,rows,net,metric,guard,native=trainer.resources(d.checked(scope['inputs']['priorPlan']))
 try:
  samples=trainer.load_train(rows,net);model=net.NativeConditionalMaskRefiner().cpu().eval();model.requires_grad_(False)
  model.load_state_dict(torch.load(d.checked(scope['inputs']['frozenModelWeights']),map_location='cpu',weights_only=True),strict=True)
  before={k:v for k,v in reader.tensors_sha(model).items() if not k.startswith('presence.')}
  if before!=features['frozenMaskTensorHashes']:raise ValueError('frozen mask tensors before combination')
  model.presence=head;model.cuda().eval();model.requires_grad_(False);metrics=[];predictions=[];accepted=0
  for row,(x,t,positive) in zip(rows,samples,strict=True):
   with torch.inference_mode():logits,p=model(x.cuda())
   a=logits[0,0].float().cpu().numpy();q=np.float32(float(p[0,0]));truth=t[0,0].numpy()>0
   saved=Path(scope['inputs']['failedCapacity']['path']).parent/'predictions'/f'{row["ordinal"]:03d}.npz'
   with np.load(saved,allow_pickle=False) as archive:
    if not np.array_equal(a,archive['logits']):raise ValueError('frozen mask logits changed')
   prediction=net.decode(a,float(q));predictions.append((row['ordinal'],a.copy(),q))
   if positive:
    accepted+=int(q>=0);b=metric.boundary_stats(truth,prediction,2);iou=int((truth&prediction).sum())/max(1,int((truth|prediction).sum()))
    metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9})
   else:metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()})
  after={k:v for k,v in reader.tensors_sha(model).items() if not k.startswith('presence.')}
  if after!=before:raise ValueError('mask weights changed during head training')
  pos=[r for r in metrics if r['positive']];neg=[r for r in metrics if not r['positive']]
  summary={'positiveCount':66,'rejectCount':2,'positivePresenceAccepted':accepted,'meanIou':float(np.mean([r['iou'] for r in pos])),
   'meanBoundaryIou':float(np.mean([r['boundaryIoU'] for r in pos])),'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in pos])),
   'jointPassCount':sum(r['jointPass'] for r in pos),'jointPassRate':sum(r['jointPass'] for r in pos)/66,
   'rejectedCount':sum(r['rejected'] for r in neg),'rejectOutputPixels':sum(r['outputPixels'] for r in neg)}
  return model,metrics,summary,predictions
 finally:
  for path in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))
def train(path,preflight_path,root):
 plan,features,scope,x,y=cached(path);pre=d.read(d.bind(preflight_path))
 if not pre['ok'] or pre['plan']!=d.bind(path) or pre['optimizerSteps'] or pre['maskParametersInOptimizer']:raise ValueError('head preflight')
 root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'predictions').mkdir()
 d.new(root/'attempt.json',{'plan':d.bind(path),'preflight':d.bind(preflight_path),'pid':os.getpid(),'attemptConsumed':True,'resumeAllowed':False})
 head=fresh_head();parameters=exact_head_parameters(head,head.parameters());optimizer=torch.optim.AdamW(parameters,lr=.1,weight_decay=0)
 sequence=steps=0;in_flight=False;started=time.monotonic()
 def event(phase,**fields):
  nonlocal sequence
  sequence+=1;record={'sequence':sequence,'phase':phase,'confirmedOptimizerSteps':steps,'optimizerStepInFlight':in_flight,'elapsedSeconds':time.monotonic()-started,**fields};d.new(root/'events'/f'{sequence:06d}.json',record);return record
 try:
  event('claimed');event('head_training_started')
  for index in range(4096):
   optimizer.zero_grad(set_to_none=True);loss=balanced_loss(head,x,y)
   if not torch.isfinite(loss):raise ValueError('head loss nonfinite')
   loss.backward();torch.nn.utils.clip_grad_norm_(parameters,1.,error_if_nonfinite=True);in_flight=True;event('optimizer_in_flight',attemptedStep=steps+1)
   optimizer.step();steps+=1;in_flight=False;event('optimizer_confirmed')
   if steps%512==0:
    event('head_progress',loss=float(loss.detach()));print(json.dumps({'headSteps':steps,'loss':float(loss.detach()),'segmentationSteps':0}),flush=True)
  event('native_full68_postflight_started');model,metrics,summary,predictions=native_postflight(head,scope,features)
  for ordinal,a,q in predictions:
   with (root/'predictions'/f'{ordinal:03d}.npz').open('xb') as stream:np.savez_compressed(stream,logits=a,presenceLogit=q);stream.flush();os.fsync(stream.fileno())
  for filename,state in (('head-weights.pt',head.state_dict()),('candidate-model.pt',model.state_dict())):
   with (root/filename).open('xb') as stream:torch.save(state,stream);stream.flush();os.fsync(stream.fileno())
  ok=summary['jointPassCount']>=53 and summary['meanIou']>=.85 and summary['meanBoundaryF1']>=.9 and summary['rejectedCount']==2 and summary['rejectOutputPixels']==0 and summary['positivePresenceAccepted']==66
  result={'schemaVersion':1,'ok':ok,'decision':'frozen_mask_new_head_capacity_pass_full30_eligibility_pending' if ok else 'frozen_mask_new_head_capacity_failed_no_full30',
   'inputs':{'plan':d.bind(path),'preflight':d.bind(preflight_path),'candidateWeights':d.bind(root/'candidate-model.pt'),'headWeights':d.bind(root/'head-weights.pt')},
   'metrics':summary,'perCandidate':metrics,'confirmedHeadOptimizerSteps':steps,'segmentationOptimizerSteps':0,
   'frozenMaskTensorHashesUnchanged':True,'nativeMaskLogitAndPixelDifferences':0,'nativePostflightInputs':68,'valModelInputs':0,
   'oldOptimizerRead':False,'certificateCoefficientsUsedForTraining':False,'resumeAllowed':False,'full30Allowed':False,'formalReleaseAllowed':False,'productHold':True}
  d.new(root/'capacity-report.json',result);d.new(root/'terminal.json',event('closed',capacityOk=ok));print(json.dumps({'ok':ok,'decision':result['decision'],'metrics':summary}),flush=True)
 except BaseException as error:
  d.new(root/'termination-report.json',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'confirmedHeadOptimizerSteps':steps,'optimizerStepInFlight':in_flight,'resumeAllowed':False})
  d.new(root/'terminal.json',event('failed'));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--preflight-output',type=Path);p.add_argument('--preflight',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 if a.preflight_output:preflight(a.plan.resolve(),a.preflight_output.resolve())
 else:train(a.plan.resolve(),a.preflight.resolve(),a.output.resolve())
