"""完整预训练原生候选导出及独立控制；冻结预算、全部RAW和只读重放。"""
import argparse
import hashlib
import importlib.util
import json
import os
import time
import traceback
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('pretrained_export_io',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def digest(state):
 return {k:hashlib.sha256(v.detach().cpu().contiguous().numpy().tobytes()).hexdigest() for k,v in state.items()}


def strict_state(model,state):
 import torch
 own=model.state_dict()
 if own.keys()!=state.keys():raise ValueError('complete model state keys mismatch')
 for k,v in state.items():
  if v.shape!=own[k].shape or v.dtype!=own[k].dtype or not torch.isfinite(v).all():raise ValueError('state domain '+k)
 model.load_state_dict(state,strict=True)
 if digest(model.state_dict())!=digest(state):raise ValueError('strict full state loading mismatch')


def model_from_plan(plan,weights):
 import torch
 net=d.load(d.checked(plan['inputs']['model']),'pretrained_export_native')
 architecture=d.read(plan['inputs']['architecture'])
 model=net.NativeConditionalMaskRefiner(net.load_stage_a_backbone(d.checked(plan['inputs']['backboneConstructorWeights']),architecture)).float()
 state=torch.load(d.checked(weights),map_location='cpu',weights_only=True)
 strict_state(model,state);model.eval().requires_grad_(False)
 if len(state)!=plan['stateTensorCount']:raise ValueError('full state tensor denominator')
 return model,net,state


def input_array(ref,h,w):
 import numpy as np
 path=d.checked(ref)
 if path.stat().st_size!=4*4*h*w or not 16<=min(h,w)<=max(h,w)<=1536:raise ValueError('native input domain')
 x=np.fromfile(path,dtype='<f4').reshape(1,4,h,w)
 if not np.isfinite(x).all() or not np.isin(x[:,3],[0,1]).all():raise ValueError('input storage domain')
 return x


class Journal:
 def __init__(self,root):
  self.root=root;self.sequence=0;self.counts={k:0 for k in ['exportTrace','cuda','cpuTorch','cpuOrt']};self.start=time.perf_counter()
  (root/'events').mkdir()
 def event(self,phase,**extra):
  self.sequence+=1
  value={'sequence':self.sequence,'phase':phase,'modelInputsStarted':dict(self.counts),'elapsedHostSeconds':time.perf_counter()-self.start,**extra}
  d.new(self.root/'events'/f'{self.sequence:06d}.json',value);return value
 def begin(self,kind,limit,**extra):
  if self.counts[kind]>=limit:raise ValueError('budget exhausted '+kind)
  self.counts[kind]+=1;self.event('model_input_started',kind=kind,**extra)


def validate(plan_path):
 import torch
 p=d.read(d.bind(plan_path))
 if p['purpose']!='pretrained_native_full_nonzero_independent_deployment_controls':raise ValueError('scope')
 if p['exporter']!=d.bind(__file__) or p['requiredAbsoluteDifference']!=1e-4 or p['requiredDecodedPixelDifference']!=0:raise ValueError('frozen interface')
 for ref in p['inputs'].values():d.checked(ref)
 if p['budget']['learnedInputs'] or p['budget']['optimizerSteps'] or p['budget']['valInputs'] or p['budget']['protectedInputs']:raise ValueError('control only scope')
 cases=p['cases'];count=len(cases)
 if [c['ordinal'] for c in cases]!=list(range(1,count+1)) or len({(c['h'],c['w']) for c in cases})!=count:raise ValueError('case denominator')
 if p['budget']['cuda']!=count or p['budget']['cpuTorch']!=count or p['budget']['cpuOrt']!=count:raise ValueError('all backend denominator')
 for c in cases:input_array(c['input'],c['h'],c['w'])
 model,net,state=model_from_plan(p,p['inputs']['independentControlWeights'])
 for name,v in state.items():
  if v.ndim>=2 and name.endswith('weight') and not torch.count_nonzero(v):raise ValueError('zero independent matrix '+name)
 if not all(torch.count_nonzero(v) for k,v in state.items() if k.startswith('semantic_projections.')):raise ValueError('zero semantic control')
 if not any(c['h']==1536 and c['w']==1536 for c in cases):raise ValueError('missing full domain control')
 return p,model,net,state


def save_heads(root,label,a,b,h,w):
 import numpy as np
 if hasattr(a,'detach'):a=a.detach().cpu().numpy();b=b.detach().cpu().numpy()
 refs={}
 # 先独占持久化原始两头，再做质量/形状判定。
 for name,value in [('mask',a),('presence',b)]:
  path=root/f'{label}-{name}.bin'
  with path.open('xb') as stream:stream.write(value.tobytes());stream.flush();os.fsync(stream.fileno())
  refs[name]={'binding':d.bind(path),'shape':list(value.shape),'dtype':str(value.dtype),'bytes':value.nbytes}
 if a.dtype!=np.float32 or b.dtype!=np.float32 or a.shape!=(1,1,h,w) or b.shape!=(1,1) or not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('float32 finite full heads')
 return refs


def read_heads(refs,h,w):
 import numpy as np
 values=[]
 for name,shape in [('mask',[1,1,h,w]),('presence',[1,1])]:
  r=refs[name];path=d.checked(r['binding']);count=int(np.prod(shape))
  if r['dtype']!='float32' or r['shape']!=shape or r['bytes']!=count*4 or path.stat().st_size!=count*4:raise ValueError('RAW binding domain')
  a=np.fromfile(path,dtype='<f4')
  if not np.isfinite(a).all():raise ValueError('nonfinite RAW')
  values.append(a)
 return values


def compare(expected,actual,h,w):
 helper=d.load(HERE/'verify-native-multiscale-browser-v2.py','pretrained_head_compare')
 return helper.compare_outputs(expected[0],expected[1],actual[0],actual[1],h,w)


def passed(stats):
 return stats['numericGatePassed'] and stats['decodedPixelGatePassed'] and stats['presenceDecisionMatched']


def execute(plan_path,root):
 import numpy as np
 import torch
 import onnx
 import onnxruntime as ort
 p,model,net,state=validate(plan_path)
 readiness=d.read(d.bind(Path(plan_path).with_name('readiness.json')))
 if not readiness['ok'] or readiness['plan']!=d.bind(plan_path):raise ValueError('readiness gate not passed')
 root.mkdir(exist_ok=False);(root/'raw').mkdir();j=Journal(root);rows=[]
 d.new(root/'attempt.json',{'plan':d.bind(plan_path),'readiness':d.bind(Path(plan_path).with_name('readiness.json')),'pid':os.getpid(),'resumeAllowed':False})
 before=digest(state);torch.set_num_threads(4);torch.set_float32_matmul_precision('highest');torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 try:
  if not torch.cuda.is_available():raise RuntimeError('strict CUDA reference unavailable')
  d.new(root/'environment.json',{'torch':torch.__version__,'onnx':onnx.__version__,'ort':ort.__version__,'cpuThreadsAfterModelConstruction':torch.get_num_threads(),'float32Matmul':torch.get_float32_matmul_precision(),'cudaTF32':torch.backends.cuda.matmul.allow_tf32,'cudnnTF32':torch.backends.cudnn.allow_tf32,'graphOptimization':'disabled','cpuOrtThreads':4,'cpuOrtExecution':'sequential','cpuTorchMkldnn':torch.backends.mkldnn.enabled})
  example=p['cases'][p['exportExampleOrdinal']-1];x=torch.from_numpy(input_array(example['input'],example['h'],example['w']))
  def trace_started(module,args):j.begin('exportTrace',p['budget']['exportTraceMax'],shape=[1,4,example['h'],example['w']])
  handle=model.register_forward_pre_hook(trace_started)
  onnx_path=root/'independent-control.onnx'
  try:
   with torch.inference_mode():
    torch.onnx.export(model,x,str(onnx_path),input_names=['candidate'],output_names=['mask_logits','presence_logit'],dynamic_axes={'candidate':{2:'height',3:'width'},'mask_logits':{2:'height',3:'width'}},opset_version=18,dynamo=False,do_constant_folding=False)
  finally:handle.remove()
  if j.counts['exportTrace']<1:raise ValueError('unobserved export trace')
  graph=onnx.load(onnx_path);onnx.checker.check_model(graph,full_check=True)
  if [v.name for v in graph.graph.input]!=['candidate'] or [v.name for v in graph.graph.output]!=['mask_logits','presence_logit']:raise ValueError('two-head exported interface')
  required=['semantic_backbone','semantic_projections.0','semantic_projections.1','semantic_projections.2','presence','delta']
  graph_names='\n'.join(n.name for n in graph.graph.node)
  if any(name.replace('.','/') not in graph_names and name not in graph_names for name in required):raise ValueError('missing complete semantic branch')
  d.new(root/'graph.json',{'onnx':d.bind(onnx_path),'nodeCount':len(graph.graph.node),'initializerCount':len(graph.graph.initializer),'requiredSemanticBranches':required,'opTypes':sorted({n.op_type for n in graph.graph.node}),'dynamicInput':str(graph.graph.input[0].type),'exportTraceCalls':j.counts['exportTrace'],'stateUnchanged':digest(model.state_dict())==before})
  options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
  session=ort.InferenceSession(str(onnx_path),sess_options=options,providers=['CPUExecutionProvider'])
  cuda=model.cuda().eval();torch.cuda.reset_peak_memory_stats()
  for case in p['cases']:
   h,w=case['h'],case['w'];x=input_array(case['input'],h,w);ordinal=case['ordinal'];captures={}
   j.begin('cuda',p['budget']['cuda'],ordinal=ordinal)
   with torch.inference_mode():a,b=cuda(torch.from_numpy(x).cuda())
   captures['cuda']=save_heads(root/'raw',f'{ordinal:03d}-cuda',a,b,h,w);j.event('model_input_confirmed',kind='cuda',ordinal=ordinal,raw=captures['cuda'])
   if torch.cuda.max_memory_allocated()>p['maxCudaAllocatedBytes']:raise MemoryError('CUDA allocation control exceeded')
   # 单个模型顺序迁移，避免两份完整1536图常驻；执行前再次冻结实际CPU线程。
   cpu=cuda.cpu().eval();torch.set_num_threads(4)
   j.begin('cpuTorch',p['budget']['cpuTorch'],ordinal=ordinal)
   with torch.inference_mode():a,b=cpu(torch.from_numpy(x))
   captures['cpuTorch']=save_heads(root/'raw',f'{ordinal:03d}-cpuTorch',a,b,h,w);j.event('model_input_confirmed',kind='cpuTorch',ordinal=ordinal,raw=captures['cpuTorch'],actualThreads=torch.get_num_threads())
   j.begin('cpuOrt',p['budget']['cpuOrt'],ordinal=ordinal);a,b=session.run(None,{'candidate':x})
   captures['cpuOrt']=save_heads(root/'raw',f'{ordinal:03d}-cpuOrt',a,b,h,w);j.event('model_input_confirmed',kind='cpuOrt',ordinal=ordinal,raw=captures['cpuOrt'])
   expected=read_heads(captures['cuda'],h,w)
   stats={k:compare(expected,read_heads(captures[k],h,w),h,w) for k in ['cpuTorch','cpuOrt']}
   if not np.any(expected[0]) or not np.any(expected[1]):raise ValueError('zero independent output control')
   rows.append({'ordinal':ordinal,'h':h,'w':w,'input':case['input'],'captures':captures,'parity':stats})
   cuda=cpu.cuda().eval();print(json.dumps({'independentControl':ordinal,'fullCount':len(p['cases']),'cpuOrtPassed':passed(stats['cpuOrt'])}),flush=True)
  if digest(cuda.state_dict())!=before:raise ValueError('control state changed')
  ok=all(passed(row['parity'][k]) for row in rows for k in ['cpuTorch','cpuOrt'])
  report={'ok':True,'decision':'full_independent_cpu_controls_pass_browser_pending' if ok else 'full_independent_cpu_controls_failed_no_browser_admission','plan':d.bind(plan_path),'exporter':d.bind(__file__),'onnx':d.bind(onnx_path),'graph':d.bind(root/'graph.json'),'environment':d.bind(root/'environment.json'),'records':rows,'actualBudget':j.counts,'stateTensorHashesBefore':before,'stateTensorHashesAfter':digest(cuda.state_dict()),'independentCpuGatePassed':ok,'learnedInputs':0,'optimizerSteps':0,'newImageDecodes':0,'peakCudaAllocatedBytes':torch.cuda.max_memory_allocated(),'formalReleaseAllowed':False,'productHold':True}
  d.new(root/'report.json',report);terminal=j.event('closed',report=d.bind(root/'report.json'),independentCpuGatePassed=ok);d.new(root/'terminal.json',terminal)
  print(json.dumps({'ok':True,'independentCpuGatePassed':ok,'actualBudget':j.counts}),flush=True)
 except BaseException as error:
  d.new(root/'failure.json',{'ok':False,'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'plan':d.bind(plan_path),'actualBudget':j.counts,'confirmedRows':rows,'resumeAllowed':False,'formalReleaseAllowed':False,'productHold':True})
  terminal=j.event('failed',failure=d.bind(root/'failure.json'));d.new(root/'terminal.json',terminal);raise


def verify(report_path,output):
 r=d.read(d.bind(report_path));p,model,net,state=validate(d.checked(r['plan']));root=Path(report_path).parent
 for ref in [r['onnx'],r['graph'],r['environment']]:d.checked(ref)
 if [row['ordinal'] for row in r['records']]!=[c['ordinal'] for c in p['cases']]:raise ValueError('full control reconstruction_mismatch')
 for row,c in zip(r['records'],p['cases'],strict=True):
  if (row['h'],row['w'],row['input'])!=(c['h'],c['w'],c['input']):raise ValueError('input identity')
  expected=read_heads(row['captures']['cuda'],c['h'],c['w'])
  for k in ['cpuTorch','cpuOrt']:
   if compare(expected,read_heads(row['captures'][k],c['h'],c['w']),c['h'],c['w'])!=row['parity'][k]:raise ValueError('parity reconstruction_mismatch')
 events=[d.read(d.bind(x)) for x in sorted((root/'events').glob('*.json'))]
 if [x['sequence'] for x in events]!=list(range(1,len(events)+1)) or events[-1]!=d.read(d.bind(root/'terminal.json')) or events[-1]['phase']!='closed':raise ValueError('event terminal')
 for kind in ['cuda','cpuTorch','cpuOrt']:
  for phase in ['model_input_started','model_input_confirmed']:
   if [x['ordinal'] for x in events if x['phase']==phase and x['kind']==kind]!=[c['ordinal'] for c in p['cases']]:raise ValueError('input event denominator')
 trace=sum(x['phase']=='model_input_started' and x['kind']=='exportTrace' for x in events)
 if not 1<=trace<=p['budget']['exportTraceMax'] or r['actualBudget']!={'exportTrace':trace,**{k:len(p['cases']) for k in ['cuda','cpuTorch','cpuOrt']}} or events[-1]['modelInputsStarted']!=r['actualBudget']:raise ValueError('actual budgets')
 if digest(state)!=r['stateTensorHashesBefore'] or r['stateTensorHashesBefore']!=r['stateTensorHashesAfter']:raise ValueError('full state reconstruction')
 gate=all(passed(row['parity'][k]) for row in r['records'] for k in ['cpuTorch','cpuOrt'])
 if gate!=r['independentCpuGatePassed']:raise ValueError('gate reconstruction_mismatch')
 result={'ok':True,'report':d.bind(report_path),'reader':d.bind(__file__),'allInputsRawMetricsBudgetsAndStateExact':True,'independentCpuGatePassed':gate,'newModelInputs':0,'formalReleaseAllowed':False,'productHold':True}
 if output.exists():
  if d.read(d.bind(output))!=result:raise ValueError('replay drift')
 else:d.new(output,result)
 print(json.dumps(result),flush=True)


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-report',type=Path);args=parser.parse_args()
 if args.verify_report:verify(args.verify_report.resolve(),args.output.resolve())
 else:execute(args.plan.resolve(),args.output.resolve())
