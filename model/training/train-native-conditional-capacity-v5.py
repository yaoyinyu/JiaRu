"""新原像素精修容量实验；全train一次预算、最终轮评估、逐优化步留证。"""
from __future__ import annotations
import argparse,importlib.util,json,os,time,traceback,hashlib,math
from pathlib import Path
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
HERE=Path(__file__).resolve().parent
def module(p,n):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','native_capacity_data')
def resources(plan_path):
 plan=d.read(d.bind(plan_path))
 for ref in plan['inputs'].values():d.checked(ref)
 if plan['purpose']!='fresh_native_conditioned_train_only_capacity' or plan['budget']!={'maximumAttempts':1,'epochs':64,'expectedOptimizerSteps':1088,'oldBudgetsMayResume':False}:raise ValueError('fresh capacity contract')
 data=d.read(plan['inputs']['materialization']);zero=d.read(plan['inputs']['nativeZeroStep']);input_plan=d.read(data['plan'])
 if not zero['ok'] or zero['optimizerSteps'] or not data['ok'] or not data['allOriginalTruthPixelsPreserved']:raise ValueError('input/zero gates')
 rows=[r for r in data['records'] if r['split']=='train']
 if [r['candidateIdentity'] for r in rows]!=plan['candidateIdentities'] or len(rows)!=68 or sum(r['presenceTarget'] for r in rows)!=66:raise ValueError('full train identity denominator')
 if any(r['candidateIdentity']['identity']['split']!='train' for r in rows):raise ValueError('val backflow')
 native=d.read(input_plan['inputs']['trainingContract']);d.validate(native)
 for row in rows:
  for k in ('nativeRgb','nativeCoarse','nativeTarget'):d.checked(row['paths'][k])
 net=module(d.checked(plan['inputs']['modelSource']),'fresh_native_capacity_model')
 roi=module(d.checked(input_plan['inputs']['roiHelper']),'fresh_native_capacity_metrics')
 guard=d.load(d.checked(input_plan['inputs']['readOnlyGuard']),'fresh_native_capacity_guard');guard.install_read_only_ultralytics_image_check()
 return plan,data,rows,net,roi,guard,native
def load_train(rows,net):
 samples=[]
 for row in rows:
  values={}
  for k in ('nativeRgb','nativeCoarse','nativeTarget'):
   with Image.open(d.checked(row['paths'][k])) as im:im.load();values[k]=np.asarray(im).copy()
  truth=values['nativeTarget']>=128
  if int(truth.sum())!=row['nativeTargetPixels'] or bool(truth.any())!=row['presenceTarget']:raise ValueError('native target pixels/presence')
  samples.append((torch.from_numpy(net.pack(values['nativeRgb'],values['nativeCoarse']))[None],torch.from_numpy(truth.astype(np.float32))[None,None],row['presenceTarget']))
 return samples
def loss_for(net,logits,presence,truth,positive,plan):
 flag=torch.tensor([positive],dtype=torch.float32,device=truth.device)
 if not positive:
  if plan['loss'].get('rejectPixelBceWeight')!=0:raise ValueError('rejection-only objective contract')
  return .5*plan['loss']['rejectPresenceWeight']*F.binary_cross_entropy_with_logits(presence.reshape(-1).float(),flag)
 original=net.candidate_loss(logits,presence,truth,flag)
 if plan['loss'].get('nativeBoundaryBandBce')!={'radiusOriginalPixels':4,'coefficient':2.0}:raise ValueError('fixed positive band BCE contract')
 band=module(HERE/'native-boundary-band-bce.py','capacity_band_bce')
 original=original+2.0*band.boundary_band_bce(logits,truth,4)
 p_loss=F.binary_cross_entropy_with_logits(presence.reshape(-1).float(),flag)
 weight=plan['loss']['positivePresenceWeight'] if positive else plan['loss']['rejectPresenceWeight']
 return original+.5*(weight-1)*p_loss
def fresh_model(net,seed):
 torch.manual_seed(seed);torch.set_num_threads(4)
 model=net.NativeConditionalMaskRefiner().cuda().train();model.requires_grad_(True);return model
def preflight(plan_path,output):
 plan,data,rows,net,roi,guard,native=resources(plan_path)
 try:
  samples=load_train(rows,net);model=fresh_model(net,plan['seed']);events=[]
  for row,(x,t,positive) in zip(rows,samples,strict=True):
   model.zero_grad(set_to_none=True);logits,presence=model(x.cuda());loss=loss_for(net,logits,presence,t.cuda(),positive,plan)
   if not torch.isfinite(loss) or not torch.isfinite(logits).all() or not torch.isfinite(presence).all():raise ValueError('balanced objective/output finite')
   loss.backward();grad=[p.grad for p in model.parameters()]
   named=list(model.named_parameters())
   needed=[(name,p.grad) for name,p in named if positive or name.startswith(('enc1.','enc2.','enc3.','presence.'))]
   unused=[name for name,p in named if not positive and name.startswith(('dec1.','dec2.','delta.'))]
   if any(g is None or not torch.isfinite(g).all() for name,g in needed):raise ValueError('objective required branch gradients')
   if any(p.grad is not None and p.grad.abs().max()>0 for name,p in named if name in unused):raise ValueError('unexpected negative decoder gradient')
   events.append({'candidateIdentity':row['candidateIdentity'],'loss':float(loss.detach()),'finiteUsedGradientTensors':len(needed),
                  'nonzeroGradientTensors':sum(bool(g.abs().max()>0) for name,g in needed),'expectedUnusedDecoderParameters':unused})
  result={'schemaVersion':1,'ok':True,'decision':'all68_native_balanced_objective_gradients_finite_no_optimizer',
          'plan':d.bind(plan_path),'records':events,'optimizerSteps':0,'trainGradientForwardInputs':68,'valModelInputs':0,
          'parameterCount':sum(p.numel() for p in model.parameters()),'cudaPeakBytes':torch.cuda.max_memory_allocated(),
          'formalReleaseAllowed':False,'productHold':True}
  d.new(output,result);print(json.dumps({'ok':True,'trainInputs':68,'optimizerSteps':0,'parameterCount':result['parameterCount']}))
 finally:
  for root in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))
def train(plan_path,preflight_ref,root):
 plan,data,rows,net,roi,guard,native=resources(plan_path);pre=d.read(preflight_ref)
 if not pre['ok'] or pre['plan']!=d.bind(plan_path) or pre['optimizerSteps'] or [r['candidateIdentity'] for r in pre['records']]!=plan['candidateIdentities']:raise ValueError('all68 training objective gate')
 root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir();(root/'predictions').mkdir()
 d.new(root/'attempt.json',{'plan':d.bind(plan_path),'objectivePreflight':preflight_ref,'attemptConsumed':True,'resumeAllowed':False,'pid':os.getpid()})
 steps=epochs=sequence=0;in_flight=False;started=time.monotonic()
 def event(phase,**extra):
  nonlocal sequence
  sequence+=1;state={'sequence':sequence,'phase':phase,'completedEpochs':epochs,'confirmedOptimizerSteps':steps,'optimizerStepInFlight':in_flight,'elapsedSeconds':time.monotonic()-started,**extra}
  d.new(root/'events'/f'{sequence:06d}.json',state);return state
 try:
  event('claimed');samples=load_train(rows,net);model=fresh_model(net,plan['seed']);optimizer=torch.optim.AdamW(model.parameters(),lr=plan['training']['lr'],weight_decay=plan['training']['weightDecay'])
  generator=torch.Generator().manual_seed(plan['seed']+1);event('training_started')
  for epoch in range(64):
   order=torch.randperm(len(samples),generator=generator).tolist();epoch_loss=0.;model.train()
   for start in range(0,len(order),4):
    optimizer.zero_grad(set_to_none=True);window=order[start:start+4]
    for index in window:
     x,target,positive=samples[index];logits,presence=model(x.cuda());loss=loss_for(net,logits,presence,target.cuda(),positive,plan)
     if not torch.isfinite(loss):raise ValueError('nonfinite native loss')
     (loss/len(window)).backward();epoch_loss+=float(loss.detach())
    torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True)
    in_flight=True;event('optimizer_in_flight',attemptedStep=steps+1)
    optimizer.step();torch.cuda.synchronize();steps+=1;in_flight=False;event('optimizer_confirmed')
   epochs=epoch+1;event('epoch_completed',meanLoss=epoch_loss/len(samples))
   if epochs%8==0:
    with (root/f'forensic-epoch-{epochs:03d}.pt').open('xb') as f:
     torch.save({'model':model.state_dict(),'optimizer':optimizer.state_dict(),'samplerRng':generator.get_state(),'torchRng':torch.get_rng_state(),'cudaRng':torch.cuda.get_rng_state_all(),
                 'completedEpochs':epochs,'confirmedOptimizerSteps':steps,'plan':d.bind(plan_path),'use':'forensic_no_resume_authority'},f);f.flush();os.fsync(f.fileno())
   if epochs%8==0:print(json.dumps({'epochs':epochs,'steps':steps,'loss':epoch_loss/len(samples)}),flush=True)
  model.eval();metrics=[];event('final_evaluation_started')
  for row,(x,target,positive) in zip(rows,samples,strict=True):
   with torch.inference_mode():logits,presence=model(x.cuda())
   a=logits[0,0].float().cpu().numpy();p=float(presence[0,0]);prediction=net.decode(a,p);truth=target[0,0].numpy()>0
   with (root/'predictions'/f'{row["ordinal"]:03d}.npz').open('xb') as f:np.savez_compressed(f,logits=a,presenceLogit=np.float32(p));f.flush();os.fsync(f.fileno())
   if positive:
    b=roi.boundary_stats(truth,prediction,2);iou=int((truth&prediction).sum())/max(1,int((truth|prediction).sum()))
    metric={'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9}
   else:metric={'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()}
   metrics.append(metric)
  pos=[r for r in metrics if r['positive']];neg=[r for r in metrics if not r['positive']]
  summary={'positiveCount':len(pos),'rejectCount':len(neg),'meanIou':float(np.mean([r['iou'] for r in pos])),
           'meanBoundaryIou':float(np.mean([r['boundaryIoU'] for r in pos])),'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in pos])),
           'jointPassCount':sum(r['jointPass'] for r in pos),'jointPassRate':sum(r['jointPass'] for r in pos)/66,'rejectedCount':sum(r['rejected'] for r in neg),
           'rejectOutputPixels':sum(r['outputPixels'] for r in neg)}
  ok=summary['jointPassRate']>=.8 and summary['meanIou']>=.85 and summary['meanBoundaryF1']>=.9 and summary['rejectedCount']==2 and summary['rejectOutputPixels']==0
  if steps!=1088 or epochs!=64:raise ValueError('full capacity execution budget')
  with (root/'final-weights.pt').open('xb') as f:torch.save(model.state_dict(),f);f.flush();os.fsync(f.fileno())
  result={'schemaVersion':1,'ok':ok,'decision':'native_capacity_pass_full30_eligibility_pending' if ok else 'native_capacity_failed_no_full30',
          'inputs':{'plan':d.bind(plan_path),'objectivePreflight':preflight_ref,'weights':d.bind(root/'final-weights.pt')},'metrics':summary,'perCandidate':metrics,
          'completedEpochs':epochs,'confirmedOptimizerSteps':steps,'trainCandidateInputs':68,'valModelInputs':0,'optimizerAttemptConsumed':True,
          'resumeAllowed':False,'full30Allowed':False,'formalReleaseAllowed':False,'productHold':True}
  d.new(root/'capacity-report.json',result);terminal=event('closed',capacityOk=ok);d.new(root/'terminal.json',terminal)
  print(json.dumps({'ok':ok,'decision':result['decision'],'metrics':summary}),flush=True)
 except BaseException as error:
  d.new(root/'termination-report.json',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'confirmedOptimizerSteps':steps,'completedEpochs':epochs,'optimizerStepInFlight':in_flight,'resumeAllowed':False})
  terminal=event('failed');d.new(root/'terminal.json',terminal);raise
 finally:
  for path in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--preflight-output',type=Path);p.add_argument('--objective-preflight',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 if a.preflight_output:preflight(a.plan.resolve(),a.preflight_output.resolve())
 else:train(a.plan.resolve(),d.bind(a.objective_preflight),a.output.resolve())
if __name__=='__main__':main()
