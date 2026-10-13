"""导出实际学得原像素候选，全68存档Torch/CPU ORT严格门；无权重替换。"""
import argparse,importlib.util,json,os,traceback
from pathlib import Path
import numpy as np
import torch
import onnx
import onnxruntime as ort
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('trained_export_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
compare=d.load(HERE/'verify-native-multiscale-browser-v2.py','trained_output_compare')
def export(scope_path,root):
 scope=d.read(d.bind(scope_path))
 if scope['purpose']!='trained_native_candidate_deployment_verification_only' or scope['optimizerStepsAllowed'] or scope['valInputsAllowed'] or len(scope['candidateIdentities'])!=68:raise ValueError('trained scope')
 for ref in scope['inputs'].values():d.checked(ref)
 if root.exists():raise ValueError('trained export output exists; do not rerun writer')
 capacity=d.read(scope['inputs']['capacity']);head_plan=d.read(capacity['inputs']['plan']);features=d.read(head_plan['inputs']['featureReport']);old_scope=d.read(features['inputs']['scope']);old_plan=d.read(old_scope['inputs']['priorPlan'])
 trainer=d.load(d.checked(old_plan['inputs']['trainer']),'trained_export_trainer')
 plan,data,rows,net,metric,guard,native=trainer.resources(d.checked(old_scope['inputs']['priorPlan']))
 if [r['candidateIdentity'] for r in rows]!=scope['candidateIdentities'] or [r['candidateIdentity'] for r in scope['savedOutputs']]!=scope['candidateIdentities']:raise ValueError('all68 identity reconstruction_mismatch')
 root.mkdir(parents=True,exist_ok=False);(root/'buffers').mkdir();records=[]
 try:
  torch.set_num_threads(4);model=net.NativeConditionalMaskRefiner().cpu().eval();model.requires_grad_(False)
  state=torch.load(d.checked(scope['inputs']['trainedWeights']),map_location='cpu',weights_only=True);model.load_state_dict(state,strict=True)
  for name,value in state.items():
   if not torch.equal(value,model.state_dict()[name]):raise ValueError('learned weight loading')
  sample=torch.zeros(1,4,128,128);onnx_path=root/'trained-candidate.onnx'
  torch.onnx.export(model,sample,str(onnx_path),input_names=['candidate'],output_names=['mask_logits','presence_logit'],
   dynamic_axes={'candidate':{2:'height',3:'width'},'mask_logits':{2:'height',3:'width'}},opset_version=18,dynamo=False)
  rewrite=d.load(d.checked(scope['inputs']['normalizationExportRewrite']),'trained_stable_gn');converted=rewrite.rewrite(onnx_path)
  onnx.checker.check_model(onnx.load(onnx_path),full_check=True)
  options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
  session=ort.InferenceSession(str(onnx_path),sess_options=options,providers=['CPUExecutionProvider'])
  model.cuda().eval();samples=trainer.load_train(rows,net)
  for row,(x,target,positive),saved_row in zip(rows,samples,scope['savedOutputs'],strict=True):
   with np.load(d.checked(saved_row['output']),allow_pickle=False) as archive:expected_mask=archive['logits'].copy();expected_presence=archive['presenceLogit'].copy().reshape(1)
   with torch.inference_mode():actual_torch_mask,actual_torch_presence=model(x.cuda())
   if not np.array_equal(actual_torch_mask[0,0].cpu().numpy(),expected_mask) or not np.array_equal(actual_torch_presence.cpu().numpy().reshape(1),expected_presence):raise ValueError('trained checkpoint vs frozen Torch outputs reconstruction_mismatch')
   h,w=expected_mask.shape;actual_mask,actual_presence=session.run(None,{'candidate':x.numpy()})
   if actual_mask.shape!=(1,1,h,w) or actual_presence.shape!=(1,1):raise ValueError('native CPU ORT shape')
   stats=compare.compare_outputs(expected_mask.reshape(-1),expected_presence,actual_mask.reshape(-1),actual_presence.reshape(-1),h,w)
   paths={}
   for name,value in (('input',x.numpy()),('mask',expected_mask),('presence',expected_presence),('cpu-mask',actual_mask),('cpu-presence',actual_presence)):
    p=root/'buffers'/f'{row["ordinal"]:03d}-{name}.bin'
    with p.open('xb') as stream:stream.write(value.astype(np.float32).tobytes());stream.flush();os.fsync(stream.fileno())
    paths[name]={'file':str(p.relative_to(root)).replace('\\','/'),**d.bind(p)}
   records.append({'candidateIdentity':row['candidateIdentity'],'ordinal':row['ordinal'],'h':h,'w':w,'positive':positive,
    'torchFrozenOutputDifferences':0,'paths':paths,'cpuOrt':stats})
   if len(records)%16==0:print(json.dumps({'nativeInputs':len(records),'optimizerSteps':0}),flush=True)
  for name,value in model.state_dict().items():
   if not torch.equal(value.cpu(),state[name]):raise ValueError('trained parameters changed during export')
  ok=all(r['cpuOrt']['numericGatePassed'] and r['cpuOrt']['decodedPixelGatePassed'] and r['cpuOrt']['presenceDecisionMatched'] for r in records)
  report={'schemaVersion':1,'ok':ok,'decision':'trained_native_cpu68_parity_pass_browser_pending' if ok else 'trained_native_cpu68_parity_failed_no_browser_admission',
   'inputs':{'scope':d.bind(scope_path),'exporter':d.bind(__file__),'trainedWeights':scope['inputs']['trainedWeights'],'onnx':d.bind(onnx_path)},
   'records':records,'nativeInputs':68,'trainedWeightsUnmodified':True,'allTorchFrozenOutputsIdentical':True,
   'requiredTolerance':1e-4,'requiredDecodedPixelDifference':0,'normalizationRewrite':converted,
   'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'browserVerified':False,'releaseIdentityRegistered':False,'formalReleaseAllowed':False,'productHold':True}
  d.new(root/'report.json',report)
  print(json.dumps({'ok':ok,'nativeInputs':68,'cpuMaxAbs':max(r['cpuOrt']['maxAbsoluteDifference'] for r in records),
   'pixelDifferences':sum(r['cpuOrt']['decodedMaskPixelDifference'] for r in records),'failedInputs':sum(not(r['cpuOrt']['numericGatePassed'] and r['cpuOrt']['decodedPixelGatePassed'] and r['cpuOrt']['presenceDecisionMatched']) for r in records),'optimizerSteps':0}))
 except BaseException as error:
  d.new(root/'failure.json',{'schemaVersion':1,'ok':False,'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),
   'scope':d.bind(scope_path),'completedNativeInputs':len(records),'optimizerSteps':0,'formalReleaseAllowed':False,'productHold':True});raise
 finally:
  for path in native['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scope',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();export(a.scope.resolve(),a.output.resolve())
