"""宽度范围全68原像素候选零优化预检；不授予训练或正式资格。"""
import argparse,importlib.util,json,traceback
from pathlib import Path
import torch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('wide_preflight_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def build(scope_path):
 scope=d.read(d.bind(scope_path))
 if scope['purpose']!='wide_native_interfaces_and_gradient_only_no_optimizer' or scope['optimizerStepsAllowed']!=0 or scope['trainingBudgetRegistered'] or scope['variable']['newChannels']!=[32,64,128]:raise ValueError('wide zero-optimizer scope')
 for ref in scope['inputs'].values():d.checked(ref)
 trainer=d.load(d.checked(scope['inputs']['readOnlyTrainer']),'wide_readonly_trainer')
 plan,data,rows,old,metric,guard,native=trainer.resources(d.checked(scope['inputs']['baselinePlan']))
 if len(rows)!=68 or sum(r['presenceTarget'] for r in rows)!=66:raise ValueError('full68 denominator')
 wide=d.load(d.checked(scope['inputs']['modelSource']),'wide_preflight_model')
 records=[]
 try:
  samples=trainer.load_train(rows,wide);model=trainer.fresh_model(wide,plan['seed'])
  for row,(x,target,positive) in zip(rows,samples,strict=True):
   model.zero_grad(set_to_none=True);values=x.cuda();logits,presence=model(values)
   expected=values[:,3:4]*8-4
   if not torch.equal(logits,expected) or not torch.equal(presence,torch.full_like(presence,2.)):raise ValueError('wide initial native logits/presence mismatch')
   loss=trainer.loss_for(wide,logits,presence,target.cuda(),positive,plan)
   if not torch.isfinite(logits).all() or not torch.isfinite(presence).all() or not torch.isfinite(loss):raise ValueError('wide objective/output nonfinite')
   loss.backward();named=list(model.named_parameters())
   used=[(n,p.grad) for n,p in named if positive or n.startswith(('enc1.','enc2.','enc3.','presence.'))]
   unused=[(n,p.grad) for n,p in named if not positive and n.startswith(('dec1.','dec2.','delta.'))]
   if len(used)!=(34 if positive else 20) or len(unused)!=(0 if positive else 14):raise ValueError('branch contract')
   if any(g is None or not torch.isfinite(g).all() for n,g in used):raise ValueError('required finite used gradients')
   if any(g is not None and bool(g.abs().max()>0) for n,g in unused):raise ValueError('negative decoder must be unused')
   records.append({'candidateIdentity':row['candidateIdentity'],'positive':positive,'nativeShape':list(logits.shape[-2:]),
    'initialLogitDifference':0,'initialMaskPixelDifferences':0,'loss':float(loss.detach()),
    'finiteUsedGradientTensors':len(used),'nonzeroUsedGradientTensors':sum(bool(g.abs().max()>0) for n,g in used),
    'expectedUnusedParameterNames':[n for n,g in unused]})
  return {'schemaVersion':1,'ok':True,'decision':'all68_wide_native_initial_masks_and_used_gradients_verified_no_optimizer',
   'inputs':{'scope':d.bind(scope_path),'preflightSource':d.bind(__file__)},'records':records,'parameterCount':sum(p.numel() for p in model.parameters()),
   'trainGradientForwardInputs':68,'valModelInputs':0,'protectedModelInputs':0,'optimizerSteps':0,
   'initialNativeLogitDifferences':0,'initialNativeMaskPixelDifferences':0,'cudaPeakBytes':torch.cuda.max_memory_allocated(),
   'exportVerified':False,'actualBrowserVerified':False,'trainingBudgetRegistered':False,'formalReleaseAllowed':False,'productHold':True}
 finally:
  for root in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scope',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('preflight output already frozen')
 try:
  result=build(a.scope.resolve());d.new(a.output.resolve(),result)
  print(json.dumps({'ok':True,'parameterCount':result['parameterCount'],'trainInputs':68,'optimizerSteps':0}))
 except BaseException as error:
  d.new(a.output.resolve().with_name(a.output.stem+'-failure.json'),{'schemaVersion':1,'ok':False,'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'optimizerSteps':0})
  raise
