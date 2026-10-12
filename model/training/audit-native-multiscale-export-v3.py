"""未训练多尺度精修的非零控制、动态原尺寸ONNX及ORT一致性门。"""
import argparse,importlib.util,json,traceback,os
from pathlib import Path
import numpy as np
import torch
import onnx
import onnxruntime as ort
HERE=Path(__file__).resolve().parent
def module(p,n):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','multiscale_export_data')
def checked_output_error(a,p,b,q,h,w):
 if a.shape!=(1,1,h,w) or b.shape!=(1,1,h,w) or p.shape!=(1,1) or q.shape!=(1,1):raise ValueError('native ONNX output shapes')
 if any(not np.isfinite(x).all() for x in (a,p,b,q)):raise ValueError('native ONNX any output nonfinite')
 error=max(float(np.abs(a-b).max()),float(np.abs(p-q).max()))
 if error>1e-4:raise ValueError('native ONNX numerical parity')
 return error

def audit(plan_path,root):
 plan=d.read(d.bind(plan_path));source=d.checked(plan['inputs']['modelSource']);m=module(source,'multiscale_export_network')
 torch.set_num_threads(4);torch.manual_seed(plan['seed']);model=m.NativeConditionalMaskRefiner().cpu().eval();root.mkdir(parents=True,exist_ok=False)
 try:
  # 非零未训练控制，禁止参与学得质量或权重选择。
  with torch.no_grad():
   model.delta.weight.copy_(torch.linspace(-.25,.25,model.delta.weight.numel()).reshape_as(model.delta.weight));model.delta.bias.fill_(.1)
   model.presence.weight.copy_(torch.linspace(-.15,.15,model.presence.weight.numel()).reshape_as(model.presence.weight))
  sample=torch.rand(1,4,128,128);sample[:,3]=(sample[:,3]>.5).float()
  output=root/'untrained-nonzero-control.onnx'
  torch.onnx.export(model,sample,str(output),input_names=['candidate'],output_names=['mask_logits','presence_logit'],
                    dynamic_axes={'candidate':{2:'height',3:'width'},'mask_logits':{2:'height',3:'width'}},opset_version=18,dynamo=False)
  normalizer=module(d.checked(plan['inputs']['normalizationExportRewrite']),'stable_gn_export_rewrite')
  rewritten=normalizer.rewrite(output)
  graph=onnx.load(output);onnx.checker.check_model(graph,full_check=True)
  options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
  session=ort.InferenceSession(str(output),sess_options=options,providers=['CPUExecutionProvider'])
  records=[]
  for h,w in [(16,16),(31,37),(128,128),(333,341)]:
   torch.manual_seed(h*1000+w);values=torch.rand(1,4,h,w);values[:,3]=(values[:,3]>.6).float()
   with torch.inference_mode():a,p=model(values)
   b,q=session.run(None,{'candidate':values.numpy()});error=checked_output_error(a.numpy(),p.numpy(),b,q,h,w)
   if np.array_equal(a.numpy(),(values[:,3:4]*8-4).numpy()):raise ValueError('control remains zero residual')
   records.append({'shape':[h,w],'maxAbsoluteDifference':error,'nonzeroUntrainedControl':True})
  result={'schemaVersion':1,'ok':True,'decision':'native_multiscale_export_and_nonzero_control_parity_pass_untrained',
          'plan':d.bind(plan_path),'modelSource':d.bind(source),'onnx':d.bind(output),'controls':records,
          'parameterCount':sum(p.numel() for p in model.parameters()),'optimizerSteps':0,'trainingAllowed':False,
          'exportAuditorSource':d.bind(__file__),'normalizationExportRewrite':plan['inputs']['normalizationExportRewrite'],'rewrittenNormalizationNodes':rewritten,
          'allReferenceAndOrtOutputTensorsFinite':True,'controlUse':'interface_only_never_model_quality_or_initial_training_weights','formalReleaseAllowed':False,'productHold':True}
  d.new(root/'report.json',result);print(json.dumps({'ok':True,'controlShapes':4,'parameters':result['parameterCount']}))
 except BaseException as e:
  failure={'schemaVersion':1,'ok':False,'decision':'native_multiscale_export_failed_no_training_budget_consumed',
           'plan':d.bind(plan_path),'modelSource':d.bind(source),'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc(),
           'optimizerSteps':0,'trainingBudgetConsumed':False,'formalReleaseAllowed':False,'productHold':True}
  d.new(root/'failure.json',failure);print(json.dumps({'ok':False,'type':type(e).__name__,'message':str(e)[:450]}));raise
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.plan.resolve(),a.output.resolve())
if __name__=='__main__':main()
