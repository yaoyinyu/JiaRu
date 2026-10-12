"""全68原像素非零控制证明训练detach不改推理值；不优化。"""
import argparse,importlib.util,json
from pathlib import Path
import torch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('detach_forward_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def audit(path):
 plan=d.read(d.bind(path));trainer=d.load(d.checked(plan['inputs']['trainer']),'detach_control_trainer')
 p,data,rows,net,metric,guard,native=trainer.resources(path)
 old=d.load(d.checked(plan['inputs']['baseArchitecture']),'detach_control_baseline')
 try:
  samples=trainer.load_train(rows,net);a=trainer.fresh_model(old,p['seed']).eval();b=trainer.fresh_model(net,p['seed']).eval()
  if list(a.state_dict())!=list(b.state_dict()) or any(not torch.equal(x,b.state_dict()[name]) for name,x in a.state_dict().items()):raise ValueError('initial parameters changed')
  for model in (a,b):
   with torch.no_grad():
    model.delta.weight.copy_(torch.linspace(-.25,.25,model.delta.weight.numel(),device='cuda').reshape_as(model.delta.weight));model.delta.bias.fill_(.1)
    model.presence.weight.copy_(torch.linspace(-.15,.15,model.presence.weight.numel(),device='cuda').reshape_as(model.presence.weight))
  records=[]
  for row,(x,truth,positive) in zip(rows,samples,strict=True):
   with torch.inference_mode():ma,pa=a(x.cuda());mb,pb=b(x.cuda())
   if not torch.isfinite(ma).all() or not torch.isfinite(pa).all() or not torch.equal(ma,mb) or not torch.equal(pa,pb):raise ValueError('full68 nonzero forward not identical')
   if torch.equal(ma,x.cuda()[:,3:4]*8-4):raise ValueError('control residual remains zero')
   records.append({'candidateIdentity':row['candidateIdentity'],'nativeShape':list(ma.shape[-2:]),'maskLogitDifference':0,'presenceDifference':0,'nonzeroControl':True})
  return {'schemaVersion':1,'ok':True,'decision':'full68_nonzero_native_forward_bitwise_identical_detach_gradient_only',
   'inputs':{'plan':d.bind(path),'auditor':d.bind(__file__)},'records':records,'initialParameterDifferences':0,
   'parameterCount':sum(p.numel() for p in b.parameters()),'trainControlInputsPerModel':68,'valModelInputs':0,
   'optimizerSteps':0,'controlWeightsNeverTrainingWeights':True,'formalReleaseAllowed':False,'productHold':True}
 finally:
  for root in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=audit(a.plan.resolve());d.new(a.output.resolve(),result);print(json.dumps({'ok':True,'controls':68,'parameterDifferences':0,'forwardDifferences':0,'optimizerSteps':0}))
