"""独立全68精度归因；旧CUDA存档保留，不改权重、阈值或旧结果。"""
import argparse,importlib.util,json
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('precision_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
compare=d.load(HERE/'verify-native-multiscale-browser-v2.py','precision_compare')
def audit(plan_path,output):
 plan=d.read(d.bind(plan_path))
 if plan['purpose']!='trained_native_all68_precision_diagnostic_no_optimizer':raise ValueError('precision contract')
 for ref in plan['inputs'].values():d.checked(ref)
 old=d.read(plan['inputs']['cpuFailure']);scope=d.read(old['inputs']['scope']);capacity=d.read(scope['inputs']['capacity'])
 headplan=d.read(capacity['inputs']['plan']);features=d.read(headplan['inputs']['featureReport']);prior_scope=d.read(features['inputs']['scope']);prior_plan=d.read(prior_scope['inputs']['priorPlan'])
 trainer=d.load(d.checked(prior_plan['inputs']['trainer']),'precision_role_trainer')
 p,data,rows,net,metric,guard,native=trainer.resources(d.checked(prior_scope['inputs']['priorPlan']))
 if [r['candidateIdentity'] for r in old['records']]!=scope['candidateIdentities'] or len(rows)!=68:raise ValueError('full68 reconstruction')
 original_policy={'cudnnAllowTf32':torch.backends.cudnn.allow_tf32,'matmulAllowTf32':torch.backends.cuda.matmul.allow_tf32}
 torch.backends.cudnn.allow_tf32=False;torch.backends.cuda.matmul.allow_tf32=False;torch.set_num_threads(4)
 state=torch.load(d.checked(scope['inputs']['trainedWeights']),map_location='cpu',weights_only=True)
 cpu=net.NativeConditionalMaskRefiner().cpu().eval();cpu.requires_grad_(False);cpu.load_state_dict(state,strict=True)
 gpu=net.NativeConditionalMaskRefiner().cuda().eval();gpu.requires_grad_(False);gpu.load_state_dict(state,strict=True)
 records=[]
 try:
  for row in old['records']:
   h,w=row['h'],row['w'];paths=row['paths']
   def values(name,count):
    ref=paths[name];path=d.checked({k:ref[k] for k in ('path','sha256')})
    if path.stat().st_size!=count*4:raise ValueError('float32 buffer byte cardinality')
    array=np.fromfile(path,np.float32)
    if not np.isfinite(array).all():raise ValueError('finite reference buffer')
    return array
   x=values('input',4*h*w).reshape(1,4,h,w);old_mask=values('mask',h*w);old_presence=values('presence',1)
   ort_mask=values('cpu-mask',h*w);ort_presence=values('cpu-presence',1)
   with torch.inference_mode():c,qc=cpu(torch.from_numpy(x));g,qg=gpu(torch.from_numpy(x).cuda())
   c=c.numpy().reshape(-1);qc=qc.numpy().reshape(1);g=g.cpu().numpy().reshape(-1);qg=qg.cpu().numpy().reshape(1)
   records.append({'candidateIdentity':row['candidateIdentity'],'ordinal':row['ordinal'],'h':h,'w':w,
    'cpuTorchVsOrt':compare.compare_outputs(c,qc,ort_mask,ort_presence,h,w),
    'strictCudaVsOrt':compare.compare_outputs(g,qg,ort_mask,ort_presence,h,w),
    'oldCudaVsStrictCuda':compare.compare_outputs(old_mask,old_presence,g,qg,h,w)})
  for name,value in cpu.state_dict().items():
   if not torch.equal(value,state[name]) or not torch.equal(gpu.state_dict()[name].cpu(),state[name]):raise ValueError('parameters changed')
  summary={}
  for label in ('cpuTorchVsOrt','strictCudaVsOrt','oldCudaVsStrictCuda'):
   summary[label]={'maxAbs':max(r[label]['maxAbsoluteDifference'] for r in records),
    'numericFailed':sum(not r[label]['numericGatePassed'] for r in records),
    'pixelDifferences':sum(r[label]['decodedMaskPixelDifference'] for r in records),
    'presenceFailed':sum(not r[label]['presenceDecisionMatched'] for r in records)}
  result={'schemaVersion':1,'ok':True,'decision':'all68_precision_attribution_only_original_failure_preserved',
   'inputs':{'plan':d.bind(plan_path),'auditor':d.bind(__file__)},'originalProcessPolicy':original_policy,
   'strictDiagnosticPolicy':{'cudnnAllowTf32':False,'matmulAllowTf32':False},'records':records,'summary':summary,
   'cpuTorchInputs':68,'strictCudaInputs':68,'optimizerSteps':0,'trainedWeightsUnmodified':True,
   'oldDeploymentFailurePreserved':plan['inputs']['cpuFailure'],'formalReleaseAllowed':False,'productHold':True}
  d.new(output,result);print(json.dumps({'ok':True,'summary':summary,'optimizerSteps':0}))
 finally:
  torch.backends.cudnn.allow_tf32=original_policy['cudnnAllowTf32'];torch.backends.cuda.matmul.allow_tf32=original_policy['matmulAllowTf32']
  for path in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.plan.resolve(),a.output.resolve())
