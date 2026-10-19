"""同输入单卷积隔离；原节点和权重保持精确绑定，完整数组只读重放。"""
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
s=importlib.util.spec_from_file_location('conv_isolation_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
s=importlib.util.spec_from_file_location('conv_isolation_tensor',HERE/'audit-pretrained-native-boundary.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)


def isolate(model,boundary):
 nodes=[n for n in model.graph.node if n.name==boundary['onnxNode']]
 if len(nodes)!=1:raise ValueError('one actual Conv required')
 node=nodes[0]
 attrs={x.name:onnx.helper.get_attribute_value(x) for x in node.attribute}
 if node.op_type!='Conv' or list(node.input)!=boundary['inputs'] or list(node.output)!=boundary['outputs'] or attrs!=boundary['attributes'] or len(node.input)!=2:raise ValueError('exact original no-bias Conv')
 weights=[x for x in model.graph.initializer if x.name==node.input[1]]
 inputs=[x for x in model.graph.input if x.name==node.input[0]]
 if len(weights)!=1 or len(inputs)!=1 or list(weights[0].dims)!=boundary['weightShape']:raise ValueError('actual Conv initializer/input')
 graph=onnx.helper.make_graph([copy.deepcopy(node)],'isolated_original_conv',[copy.deepcopy(inputs[0])],[onnx.helper.make_tensor_value_info(node.output[0],onnx.TensorProto.FLOAT,[1,boundary['channels'],'height','width'])],[copy.deepcopy(weights[0])])
 result=onnx.helper.make_model(graph,opset_imports=[copy.deepcopy(x) for x in model.opset_import]);result.ir_version=model.ir_version
 if result.graph.node[0].SerializeToString()!=node.SerializeToString() or result.graph.initializer[0].SerializeToString()!=weights[0].SerializeToString():raise ValueError('node/initializer byte identity')
 onnx.checker.check_model(result,full_check=True);return result


def input_array(c):
 path=d.checked(c['input']);shape=[1,4,c['h'],c['w']]
 if path.stat().st_size!=int(np.prod(shape))*4:raise ValueError('input bytes')
 x=np.fromfile(path,dtype='<f4').reshape(shape)
 if not np.isfinite(x).all():raise ValueError('input nonfinite')
 return x


def resources(path):
 p=d.read(d.bind(path));parent=d.read(p['inputs']['parent']);oldplan=d.read(p['inputs']['priorCapturePlan']);old=d.read(p['inputs']['fullFidelity']);cuda=d.read(p['inputs']['cudaReference'])
 for ref in [*p['inputs'].values(),p['runner'],p['browserServer'],p['boundaryReader']]:d.checked(ref)
 if p['runner']!=d.bind(__file__) or p['cases']!=parent['cases'] or p['cases']!=oldplan['cases'] or len(p['cases'])!=9 or [c['ordinal'] for c in p['cases']]!=list(range(1,10)):raise ValueError('full9 source reconstruction_mismatch')
 if not old['all27Inputs81TensorsCompleteFinite'] or not old['allFinalHeadsByteExactAcross9And3Backends'] or not old['layerAttributionAllowed']:raise ValueError('original global fidelity not approved')
 if p['boundary']!=parent['boundary'] or p['boundary']!=oldplan['boundary']:raise ValueError('actual boundary contract')
 original=onnx.load(d.checked(p['inputs']['originalOnnx']));expected=isolate(original,p['boundary'])
 if expected.SerializeToString()!=d.checked(p['inputs']['isolatedOnnx']).read_bytes():raise ValueError('isolated graph reconstruction_mismatch')
 if p['budget']!={'cpu-ort':9,'wasm':9,'webgpu-main':9,'webgpu-fresh':1,'fullModel':0,'cuda':0,'learned':0,'optimizerSteps':0,'protected':0,'newChatImages':0}:raise ValueError('complete fixed budget')
 for c,row in zip(p['cases'],cuda['records'],strict=True):
  if c['ordinal']!=row['ordinal'] or c['input']!=row['input']:raise ValueError('original CUDA input identity')
  input_array(c);a.tensor(row['raw']['boundary'],[1,p['boundary']['channels'],c['h'],c['w']])
 if p['memoryAndStorage']['expectedRawBytes']!=sum(c['h']*c['w']*p['boundary']['channels']*4 for c in p['cases'])*3+1536*1536*16*4:raise ValueError('full28 storage schedule')
 return p,cuda,old


def compare(ref,c,p,cuda,old,backend):
 shape=[1,p['boundary']['channels'],c['h'],c['w']];x=a.tensor(ref,shape);base=cuda['records'][c['ordinal']-1]['raw']['boundary'];y=a.tensor(base,shape);delta=np.abs(x-y)
 out={'maxAbsoluteDifference':float(delta.max()),'valuesAbove1e4':int((delta>1e-4).sum()),'values':int(delta.size),'numericGatePassed':bool(delta.max()<=1e-4),'byteExactToCuda':ref['binding']['sha256']==base['binding']['sha256']}
 if backend in ['wasm','webgpu']:
  matches=[r for r in old['records'] if r['backend']==backend and r['ordinal']==c['ordinal']]
  if len(matches)!=1:raise ValueError('original backend boundary denominator')
  prior=matches[0]['raw']['boundary'];z=a.tensor(prior,shape);change=np.abs(x-z)
  out['sameBackendFullGraph']={'byteExact':ref['binding']['sha256']==prior['binding']['sha256'],'maxAbsoluteDifference':float(change.max()),'changedValues':int((x!=z).sum()),'reference':prior['binding']}
 return out


def cpu(path,root):
 import onnxruntime as ort
 p,cuda,old=resources(path);ready=d.read(d.bind(Path(path).with_name('readiness.json')))
 if not ready['ok'] or ready['plan']!=d.bind(path):raise ValueError('machine readiness gate')
 root.mkdir(exist_ok=False);(root/'raw').mkdir();(root/'events').mkdir();rows=[];count=0
 d.new(root/'attempt.json',{'plan':d.bind(path),'pid':os.getpid(),'resumeAllowed':False})
 try:
  opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
  session=ort.InferenceSession(str(d.checked(p['inputs']['isolatedOnnx'])),sess_options=opts,providers=['CPUExecutionProvider'])
  d.new(root/'environment.json',{'onnxruntime':ort.__version__,'providers':session.get_providers(),'intraThreads':4,'interThreads':1,'graphOptimization':'disabled'})
  for c in p['cases']:
   i=c['ordinal'];x=input_array(c);d.new(root/'events'/f'{i:03d}-started.json',{'ordinal':i,'input':c['input'],'plan':d.bind(path)});count+=1
   result=session.run(p['boundary']['outputs'],{'candidate':x})
   if len(result)!=1:raise ValueError('one operator output required')
   ref=a.save(root/'raw'/f'{i:03d}.bin',result[0]);a.tensor(ref,[1,p['boundary']['channels'],c['h'],c['w']])
   row={'ordinal':i,'input':c['input'],'raw':ref,'comparison':compare(ref,c,p,cuda,old,'cpu-ort')};d.new(root/'events'/f'{i:03d}-confirmed.json',row);rows.append(row)
   print(json.dumps({'isolatedCpu':i,'numericGatePassed':row['comparison']['numericGatePassed']}),flush=True)
  d.new(root/'report.json',{'ok':True,'plan':d.bind(path),'records':rows,'actualInputs':count,'full9NumericGatePassed':all(r['comparison']['numericGatePassed'] for r in rows),'formalReleaseAllowed':False,'productHold':True});d.new(root/'terminal.json',{'phase':'closed','report':d.bind(root/'report.json'),'actualInputs':count})
 except BaseException as error:
  d.new(root/'failure.json',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'actualStartedInputs':count,'resumeAllowed':False});raise


def verify(path,root,output):
 p,cuda,old=resources(path);cr=d.read(d.bind(root/'cpu/report.json'));terminal=d.read(d.bind(root/'cpu/terminal.json'));rows=[]
 if cr['plan']!=d.bind(path) or len(cr['records'])!=9 or cr['actualInputs']!=9 or terminal!={'phase':'closed','report':d.bind(root/'cpu/report.json'),'actualInputs':9}:raise ValueError('CPU full9 terminal')
 for c,r in zip(p['cases'],cr['records'],strict=True):
  i=c['ordinal']
  if r['ordinal']!=i or r['input']!=c['input'] or d.read(d.bind(root/'cpu/events'/f'{i:03d}-confirmed.json'))!=r or d.read(d.bind(root/'cpu/events'/f'{i:03d}-started.json'))!={'ordinal':i,'input':c['input'],'plan':d.bind(path)}:raise ValueError('CPU event/input fidelity')
  stats=compare(r['raw'],c,p,cuda,old,'cpu-ort')
  if stats!=r['comparison']:raise ValueError('CPU complete RAW metrics drift')
  rows.append({'scope':'cpu','backend':'cpu-ort','ordinal':i,'raw':r['raw'],'comparison':stats})
 browser_claims=[];time_origins=[]
 for scope in ['main','fresh']:
  br=root/scope;bp=d.read(d.bind(br/'plan.json'));live=d.read(d.bind(br/'capture/live-browser.json'));claim=d.read(d.bind(br/'claim.json'));expected=bp['schedule'];browser_claims.append(claim['claim']);time_origins.append(live['timeOrigin'])
  if bp['operatorPlan']!=d.bind(path) or bp['scope']!=scope or bp['server']!=p['browserServer'] or live['phase']!='closed' or live['errors'] or live['virtualTime'] or not live['crossOriginIsolated'] or live['planSha256']!=d.bind(br/'plan.json')['sha256'] or live['claim']!=claim['claim']:raise ValueError('browser terminal/scope')
  if live['userAgent']!=bp['expectedUserAgent'] or live['adapterInfo']!=bp['expectedAdapter']:raise ValueError('browser same environment')
  if [(r['backend'],r['ordinal']) for r in live['records']]!=[(r['backend'],r['ordinal']) for r in expected] or live['started']!=[{'backend':r['backend'],'ordinal':r['ordinal'],'requestId':claim['claim']+'-'+r['backend']+'-'+str(r['ordinal'])} for r in expected]:raise ValueError('browser exact input denominator')
  if len(list((br/'started').glob('*.json')))!=len(expected):raise ValueError('actual starts')
  if len(list((br/'capture').glob('*.bin')))!=len(expected):raise ValueError('actual raw denominator')
  for row,cfg in zip(live['records'],expected,strict=True):
   b,i=row['backend'],row['ordinal'];c=p['cases'][i-1];rid=claim['claim']+'-'+b+'-'+str(i);event=d.read(d.bind(br/'started'/f'{b}-{i}.json'))
   if event!={'claim':claim['claim'],'requestId':rid,'backend':b,'ordinal':i,'h':c['h'],'w':c['w'],'inputSha256':c['input']['sha256']} or row['requestId']!=rid:raise ValueError('browser actual input identity')
   shape=[1,p['boundary']['channels'],c['h'],c['w']];raw=br/'capture'/f'{b}-{i}.bin';ref={'binding':d.bind(raw),'shape':shape,'dtype':'float32','bytes':raw.stat().st_size}
   if row['output']!={'shape':shape,'dtype':'float32','sha256':ref['binding']['sha256'],'bytes':ref['bytes']}:raise ValueError('browser full raw metadata')
   rows.append({'scope':scope,'backend':b,'ordinal':i,'raw':ref,'comparison':compare(ref,c,p,cuda,old,b)})
  # 同一请求只允许同长度/同SHA继承，逐HTTP事件保留实际尝试，不冒充网络测量。
  actual_files=[br/'claim.json',*sorted((br/'started').glob('*.json')),*sorted((br/'capture').glob('*'))];events=[d.read(d.bind(f)) for f in (br/'http-events').glob('*.json')];ids=set()
  for file in actual_files:
   meta=d.read(d.bind(br/'metadata'/f'{file.parent.name}-{file.name}.json'));matching=[x for x in events if x['requestId']==meta['requestId']]
   if not 1<=len(matching)<=2 or meta['sha256']!=d.bind(file)['sha256'] or meta['bytes']!=file.stat().st_size:raise ValueError('transport metadata')
   expected_path='/claim' if file.name=='claim.json' else '/started/'+file.stem.replace('-','/') if file.parent.name=='started' else '/capture/'+file.name
   if any(e['declaredSha256']!=meta['sha256'] or e['declaredBytes']!=meta['bytes'] or e['path']!=expected_path for e in matching):raise ValueError('transport request identity')
   ids.add(meta['requestId'])
  if ids!={x['requestId'] for x in events} or len(actual_files)!=2+len(expected)*2:raise ValueError('transport full denominator')
 if len(set(browser_claims))!=2 or len(set(time_origins))!=2 or len(rows)!=28:raise ValueError('separate realm and full28 denominator')
 # 显式按scope/backend分别计算，避免把主序列和fresh的ordinal9合并。
 summary={key:{'inputs':len(rr),'passed':sum(r['comparison']['numericGatePassed'] for r in rr),'maxAbsoluteDifference':max(r['comparison']['maxAbsoluteDifference'] for r in rr)} for key,scope,b in [('cpu','cpu','cpu-ort'),('main-wasm','main','wasm'),('main-webgpu','main','webgpu'),('fresh-webgpu','fresh','webgpu')] for rr in [[r for r in rows if r['scope']==scope and r['backend']==b]]}
 result={'ok':True,'decision':'full28_single_operator_diagnostic_complete_no_release','reader':d.bind(__file__),'plan':d.bind(path),'cpuReport':d.bind(root/'cpu/report.json'),'mainLive':d.bind(root/'main/capture/live-browser.json'),'freshLive':d.bind(root/'fresh/capture/live-browser.json'),'records':rows,'summary':summary,'all28RawArraysCompleteFinite':True,'separateFreshClaim':True,'actualNetworkBytes':None,'newModelInputs':0,'learnedInputs':0,'formalReleaseAllowed':False,'productHold':True}
 if output.exists():
  if d.read(d.bind(output))!=result:raise ValueError('immutable replay drift')
 else:d.new(output,result)
 print(json.dumps({'ok':True,'summary':summary,'newModelInputs':0}),flush=True)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['cpu','verify']);p.add_argument('--plan',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path);v=p.parse_args()
 if v.mode=='cpu':cpu(v.plan.resolve(),v.root.resolve())
 else:verify(v.plan.resolve(),v.root.resolve(),v.output.resolve())
