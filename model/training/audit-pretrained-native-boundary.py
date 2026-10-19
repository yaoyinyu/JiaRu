"""完整候选的只读卷积边界；全范围最终头字节保真后才允许层比较。"""
import argparse
import copy
import importlib.util
import json
import os
import traceback
from pathlib import Path
import numpy as np
import onnx
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('pretrained_boundary_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def instrument(model,boundary):
 original=model.SerializeToString();result=copy.deepcopy(model)
 nodes=[n for n in result.graph.node if n.name==boundary['onnxNode']]
 if len(nodes)!=1 or nodes[0].op_type!='Conv' or list(nodes[0].input)!=boundary['inputs'] or list(nodes[0].output)!=boundary['outputs']:raise ValueError('actual boundary node mismatch')
 name=boundary['outputs'][0]
 if any(v.name==name for v in result.graph.output):raise ValueError('boundary already output')
 result.graph.output.append(onnx.helper.make_tensor_value_info(name,onnx.TensorProto.FLOAT,[1,boundary['channels'],'height','width']))
 restored=copy.deepcopy(result);del restored.graph.output[-1:]
 if restored.SerializeToString()!=original:raise ValueError('output strip must restore complete original graph bytes')
 onnx.checker.check_model(result,full_check=True);return result


def tensor(ref,shape):
 path=d.checked(ref['binding']);count=int(np.prod(shape))
 if ref['shape']!=shape or ref['dtype']!='float32' or ref['bytes']!=count*4 or path.stat().st_size!=count*4:raise ValueError('full tensor storage domain')
 value=np.fromfile(path,dtype='<f4').reshape(shape)
 if not np.isfinite(value).all():raise ValueError('nonfinite complete tensor')
 return value


def save(path,value):
 with path.open('xb') as stream:stream.write(value.tobytes());stream.flush();os.fsync(stream.fileno())
 return {'binding':d.bind(path),'shape':list(value.shape),'dtype':str(value.dtype),'bytes':value.nbytes}


def resources(plan_path):
 p=d.read(d.bind(plan_path))
 if p['purpose']!='full9_pretrained_boundary_capture_fidelity' or p['runner']!=d.bind(__file__):raise ValueError('boundary capture scope')
 for ref in p['inputs'].values():d.checked(ref)
 for ref in p['modelSources'].values():d.checked(ref)
 old=d.read(p['inputs']['originalCuda']);browser=d.read(p['inputs']['originalBrowser']);parent=d.read(p['inputs']['parent'])
 if p['cases']!=parent['cases'] or len(p['cases'])!=9 or [c['ordinal'] for c in p['cases']]!=list(range(1,10)):raise ValueError('complete9 source denominator')
 if p['budget']!={'cuda':9,'wasm':9,'webgpu':9,'exportTraces':0,'learned':0,'optimizerSteps':0,'val':0,'protected':0,'newChatImages':0}:raise ValueError('frozen complete budget')
 helper=d.load(d.checked(p['inputs']['exporter']),'pretrained_boundary_helper')
 original=onnx.load(d.checked(p['inputs']['originalOnnx']));expected=instrument(original,p['boundary'])
 if expected.SerializeToString()!=onnx.load(d.checked(p['inputs']['diagnosticOnnx'])).SerializeToString():raise ValueError('complete diagnostic graph reconstruction')
 for c,row in zip(p['cases'],old['records'],strict=True):
  if c['ordinal']!=row['ordinal'] or c['input']!=row['input']:raise ValueError('source reference input identity')
  helper.input_array(c['input'],c['h'],c['w']);helper.read_heads(row['captures']['cuda'],c['h'],c['w'])
  for b in ['wasm','webgpu']:
   rr=[r for r in browser['records'] if r['backend']==b and r['ordinal']==c['ordinal']]
   if len(rr)!=1:raise ValueError('prior browser denominator')
   helper.read_heads(rr[0]['raw'],c['h'],c['w'])
 return p,old,browser,helper


def cuda(plan_path,root):
 import torch
 p,old,browser,helper=resources(plan_path);ready=d.read(d.bind(Path(plan_path).with_name('readiness.json')))
 if not ready['ok'] or ready['plan']!=d.bind(plan_path):raise ValueError('readiness gate')
 constructor=d.read(p['inputs']['constructorPlan']);model,net,state=helper.model_from_plan(constructor,p['inputs']['independentWeights']);model=model.cuda().eval();model.requires_grad_(False)
 torch.set_num_threads(4);torch.set_float32_matmul_precision('highest');torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False;torch.cuda.reset_peak_memory_stats()
 root.mkdir(exist_ok=False);(root/'raw').mkdir();j=helper.Journal(root);j.counts={'cuda':0};rows=[];held=[]
 def capture(module,args,output):held.append(output.detach())
 handle=model.get_submodule(p['boundary']['module']).register_forward_hook(capture)
 d.new(root/'attempt.json',{'plan':d.bind(plan_path),'pid':os.getpid(),'resumeAllowed':False});before=helper.digest(state)
 try:
  d.new(root/'environment.json',{'torch':torch.__version__,'threadsAfterModelConstructionAndDevice':torch.get_num_threads(),'float32Matmul':torch.get_float32_matmul_precision(),'cudaTF32':torch.backends.cuda.matmul.allow_tf32,'cudnnTF32':torch.backends.cudnn.allow_tf32,'autocast':False})
  for c,baseline in zip(p['cases'],old['records'],strict=True):
   h,w=c['h'],c['w'];i=c['ordinal'];held.clear();x=torch.from_numpy(helper.input_array(c['input'],h,w)).cuda();j.begin('cuda',9,ordinal=i)
   with torch.inference_mode():a,b=model(x)
   refs=helper.save_heads(root/'raw',f'{i:03d}',a,b,h,w)
   if len(held)!=1:raise ValueError('one boundary invocation expected')
   boundary=held[0].cpu().numpy();refs['boundary']=save(root/'raw'/f'{i:03d}-boundary.bin',boundary);tensor(refs['boundary'],[1,p['boundary']['channels'],h,w]);j.event('model_input_confirmed',kind='cuda',ordinal=i,raw=refs)
   same={k:refs[k]['binding']['sha256']==baseline['captures']['cuda'][k]['binding']['sha256'] for k in ['mask','presence']};rows.append({'ordinal':i,'h':h,'w':w,'input':c['input'],'raw':refs,'finalHeadsByteExact':same})
   if torch.cuda.max_memory_allocated()>p['maxCudaAllocatedBytes']:raise MemoryError('fixed CUDA allocation bound')
   print(json.dumps({'cudaBoundary':i,'finalHeadsByteExact':all(same.values())}),flush=True)
  if helper.digest(model.state_dict())!=before:raise ValueError('independent state changed')
  gate=all(all(r['finalHeadsByteExact'].values()) for r in rows);r={'ok':True,'decision':'cuda_full9_fidelity_pass_browser_pending' if gate else 'reconstruction_mismatch','plan':d.bind(plan_path),'records':rows,'cudaFidelityPassed':gate,'actualBudget':j.counts,'stateTensorHashes':before,'allStateUnchanged':True,'peakCudaAllocatedBytes':torch.cuda.max_memory_allocated(),'learnedInputs':0,'optimizerSteps':0,'formalReleaseAllowed':False,'productHold':True};d.new(root/'report.json',r);terminal=j.event('closed',report=d.bind(root/'report.json'));d.new(root/'terminal.json',terminal)
  print(json.dumps({'ok':True,'cudaFidelityPassed':gate}),flush=True)
 except BaseException as error:
  d.new(root/'failure.json',{'ok':False,'plan':d.bind(plan_path),'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'actualBudget':j.counts,'resumeAllowed':False,'formalReleaseAllowed':False,'productHold':True});terminal=j.event('failed',failure=d.bind(root/'failure.json'));d.new(root/'terminal.json',terminal);raise
 finally:handle.remove();held.clear()


def cuda_reconstruct(plan_path,root):
 p,old,browser,helper=resources(plan_path);r=d.read(d.bind(root/'report.json'))
 if r['plan']!=d.bind(plan_path) or len(r['records'])!=9:raise ValueError('cuda full9 reconstruction_mismatch')
 for c,baseline,row in zip(p['cases'],old['records'],r['records'],strict=True):
  if row['ordinal']!=c['ordinal'] or row['input']!=c['input'] or (row['h'],row['w'])!=(c['h'],c['w']):raise ValueError('cuda source identity')
  helper.read_heads(row['raw'],c['h'],c['w']);tensor(row['raw']['boundary'],[1,p['boundary']['channels'],c['h'],c['w']])
  same={k:row['raw'][k]['binding']['sha256']==baseline['captures']['cuda'][k]['binding']['sha256'] for k in ['mask','presence']}
  if same!=row['finalHeadsByteExact']:raise ValueError('cuda output fidelity drift')
 events=[d.read(d.bind(path)) for path in sorted((root/'events').glob('*.json'))]
 if [e['sequence'] for e in events]!=list(range(1,len(events)+1)) or events[-1]!=d.read(d.bind(root/'terminal.json')) or events[-1]['phase']!='closed':raise ValueError('cuda terminal/events')
 for phase in ['model_input_started','model_input_confirmed']:
  if [e['ordinal'] for e in events if e['phase']==phase]!=list(range(1,10)):raise ValueError('cuda input count')
 gate=all(all(x['finalHeadsByteExact'].values()) for x in r['records'])
 if gate!=r['cudaFidelityPassed'] or r['actualBudget']!={'cuda':9}:raise ValueError('cuda budget/gate')
 return p,r,gate


def verify_cuda(plan_path,root,output):
 p,r,gate=cuda_reconstruct(plan_path,root);result={'ok':True,'reader':d.bind(__file__),'plan':d.bind(plan_path),'cudaReport':d.bind(root/'report.json'),'full9FinalHeadsBoundaryAndEventsExact':True,'cudaFidelityPassed':gate,'newModelInputs':0,'formalReleaseAllowed':False,'productHold':True}
 if output.exists():
  if d.read(d.bind(output))!=result:raise ValueError('cuda replay drift')
 else:d.new(output,result)
 print(json.dumps({'ok':True,'cudaFidelityPassed':gate,'newModelInputs':0}),flush=True)


def verify_all(plan_path,cuda_root,browser_root,output):
 p,cuda_report,cuda_gate=cuda_reconstruct(plan_path,cuda_root);_,old,prior,helper=resources(plan_path);bp=d.read(d.bind(browser_root/'plan.json'));live=d.read(d.bind(browser_root/'capture/live-browser.json'));rows=[]
 if bp['capturePlan']!=d.bind(plan_path) or live['planSha256']!=d.bind(browser_root/'plan.json')['sha256'] or live['errors'] or live['phase']!='closed' or live['virtualTime']:raise ValueError('complete browser terminal scope')
 expected=[(b,i) for b in ['wasm','webgpu'] for i in range(1,10)]
 if [(r['backend'],r['ordinal']) for r in live['records']]!=expected or [(r['backend'],r['ordinal']) for r in live['started']]!=expected:raise ValueError('full18 browser scope')
 if len(list((browser_root/'started').glob('*.json')))!=18:raise ValueError('browser actual event denominator')
 for live_row in live['records']:
  b,i=live_row['backend'],live_row['ordinal'];c=p['cases'][i-1];h,w=c['h'],c['w'];event=d.read(d.bind(browser_root/'started'/f'{b}-{i}.json'))
  if event['ordinal']!=i or event['backend']!=b or event['requestId']!=live_row['requestId'] or event['inputSha256']!=c['input']['sha256']:raise ValueError('browser stable start identity')
  refs={}
  for name,shape in [('mask',[1,1,h,w]),('presence',[1,1]),('boundary',[1,p['boundary']['channels'],h,w])]:
   path=browser_root/'capture'/f'{b}-{i}-{name}.bin';meta=live_row['outputs'][name]
   if meta['shape']!=shape or meta['dtype']!='float32':raise ValueError('browser actual tensor shape')
   refs[name]={'binding':d.bind(path),'shape':shape,'dtype':'float32','bytes':path.stat().st_size}
   if refs[name]['binding']['sha256']!=meta['sha256']:raise ValueError('browser raw SHA')
   tensor(refs[name],shape)
  baseline=next(r for r in prior['records'] if r['backend']==b and r['ordinal']==i)
  same={name:refs[name]['binding']['sha256']==baseline['raw'][name]['binding']['sha256'] for name in ['mask','presence']};rows.append({'backend':b,'ordinal':i,'raw':refs,'finalHeadsByteExact':same})
 gate=cuda_gate and all(all(r['finalHeadsByteExact'].values()) for r in rows);analysis=None
 # 仅全27输入/81张量完整有限且54最终头均字节保真时，才计算/暴露层级结论。
 if gate:
  analysis=[]
  for r in rows:
   i=r['ordinal'];c=p['cases'][i-1];shape=[1,p['boundary']['channels'],c['h'],c['w']];a=tensor(cuda_report['records'][i-1]['raw']['boundary'],shape);b=tensor(r['raw']['boundary'],shape);delta=np.abs(a-b)
   analysis.append({'backend':r['backend'],'ordinal':i,'boundaryMaxAbsoluteDifference':float(delta.max()),'boundaryValuesAbove1e4':int((delta>1e-4).sum()),'boundaryValues':int(delta.size),'boundaryByteExact':r['raw']['boundary']['binding']['sha256']==cuda_report['records'][i-1]['raw']['boundary']['binding']['sha256']})
 result={'ok':True,'decision':'full27_fidelity_pass_boundary_diagnostic_only' if gate else 'reconstruction_mismatch','reader':d.bind(__file__),'plan':d.bind(plan_path),'cudaReport':d.bind(cuda_root/'report.json'),'browserPlan':d.bind(browser_root/'plan.json'),'live':d.bind(browser_root/'capture/live-browser.json'),'records':rows,'all27Inputs81TensorsCompleteFinite':True,'allFinalHeadsByteExactAcross9And3Backends':gate,'layerAttributionAllowed':gate,'boundaryStatistics':analysis,'newModelInputs':0,'learnedInputs':0,'formalReleaseAllowed':False,'productHold':True}
 if output.exists():
  if d.read(d.bind(output))!=result:raise ValueError('full replay drift')
 else:d.new(output,result)
 print(json.dumps({'ok':True,'decision':result['decision'],'allFinalHeadsByteExact':gate,'boundaryStatistics':analysis}),flush=True)


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['cuda','verify-cuda','verify-all']);a.add_argument('--plan',type=Path,required=True);a.add_argument('--cuda-root',type=Path,required=True);a.add_argument('--browser-root',type=Path);a.add_argument('--output',type=Path);v=a.parse_args()
 if v.mode=='cuda':cuda(v.plan.resolve(),v.cuda_root.resolve())
 elif v.mode=='verify-cuda':verify_cuda(v.plan.resolve(),v.cuda_root.resolve(),v.output.resolve())
 else:verify_all(v.plan.resolve(),v.cuda_root.resolve(),v.browser_root.resolve(),v.output.resolve())
