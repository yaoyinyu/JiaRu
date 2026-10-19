"""分段Conv完整9三后端控制，原严格CUDA参考及原失败不改写。"""
import argparse
import importlib.util
import json
import os
import traceback
from pathlib import Path
import onnx
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('partition_controls_base',HERE/'audit-onnx-conv-isolation.py');base=importlib.util.module_from_spec(s);s.loader.exec_module(base);d=base.d
s=importlib.util.spec_from_file_location('partition_controls_graph',HERE/'onnx-spatial-partition-convolution.py');graph=importlib.util.module_from_spec(s);s.loader.exec_module(graph)


def resources(path):
 p=d.read(d.bind(path))
 for ref in [*p['inputs'].values(),p['runner'],p['browserServer'],p['transform'],p['baseReader']]:d.checked(ref)
 if p['runner']!=d.bind(__file__) or p['transform']!=d.bind(HERE/'onnx-spatial-partition-convolution.py') or p['baseReader']!=d.bind(HERE/'audit-onnx-conv-isolation.py'):raise ValueError('partition tool version')
 parent=d.read(p['inputs']['parent']);original,cuda,old=base.resources(d.checked(p['inputs']['originalOperatorPlan']));prior=d.read(p['inputs']['originalOperatorReport']);probe=d.read(p['inputs']['deviceProbe']);proof=d.read(p['inputs']['graphProof'])
 if p['cases']!=parent['cases'] or p['cases']!=original['cases'] or p['boundary']!=original['boundary'] or len(p['cases'])!=9 or not prior['all28RawArraysCompleteFinite']:raise ValueError('complete source/denominator reconstruction_mismatch')
 if p['budget']!={'cpu-ort':9,'wasm':9,'webgpu':9,'fullModel':0,'cuda':0,'learned':0,'optimizerSteps':0,'protected':0,'newChatImages':0}:raise ValueError('fixed new27 budget')
 if probe['phase']!='closed' or probe['errors'] or probe['newModelInputs']!=0 or probe['actualOrtDevice'] or probe['grantedLimits']!=p['deviceProbeGrantedLimits'] or probe['grantedLimits']!=probe['requestedLimits']:raise ValueError('actual zero-model device probe')
 source=onnx.load(d.checked(p['inputs']['sourceIsolatedOnnx']));expected,expected_proof=graph.transform(source,p['boundary']['onnxNode'])
 if proof['proof']!=expected_proof or proof['coordinateProof']!=graph.coordinate_proof() or expected.SerializeToString()!=d.checked(p['inputs']['isolatedOnnx']).read_bytes():raise ValueError('exact partition reconstruction')
 if graph.restore(expected,proof['proof']).SerializeToString()!=source.SerializeToString() or p['deviceProbeGrantedLimits']['maxComputeWorkgroupsPerDimension']<proof['coordinateProof']['maxNchwDispatchX']:raise ValueError('graph reverse/resources')
 return p,cuda,old


def cpu(path,root):
 import onnxruntime as ort
 p,cuda,old=resources(path);ready=d.read(d.bind(path.with_name('readiness.json')))
 if not ready['ok'] or ready['plan']!=d.bind(path):raise ValueError('readiness gate')
 root.mkdir(exist_ok=False);(root/'raw').mkdir();(root/'events').mkdir();rows=[];count=0;d.new(root/'attempt.json',{'plan':d.bind(path),'pid':os.getpid(),'resumeAllowed':False})
 try:
  opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL;session=ort.InferenceSession(str(d.checked(p['inputs']['isolatedOnnx'])),sess_options=opts,providers=['CPUExecutionProvider'])
  d.new(root/'environment.json',{'onnxruntime':ort.__version__,'providers':session.get_providers(),'intraThreads':4,'interThreads':1,'graphOptimization':'disabled'})
  for c in p['cases']:
   i=c['ordinal'];x=base.input_array(c);d.new(root/'events'/f'{i:03d}-started.json',{'ordinal':i,'input':c['input'],'plan':d.bind(path)});count+=1;result=session.run(p['boundary']['outputs'],{'candidate':x})
   if len(result)!=1:raise ValueError('single restored full output')
   ref=base.a.save(root/'raw'/f'{i:03d}.bin',result[0]);stats=base.compare(ref,c,p,cuda,old,'cpu-ort');row={'ordinal':i,'input':c['input'],'raw':ref,'comparison':stats};d.new(root/'events'/f'{i:03d}-confirmed.json',row);rows.append(row);print(json.dumps({'partitionCpu':i,'passed':stats['numericGatePassed']}),flush=True)
  d.new(root/'report.json',{'ok':True,'plan':d.bind(path),'records':rows,'actualInputs':count,'full9NumericGatePassed':all(r['comparison']['numericGatePassed'] for r in rows),'formalReleaseAllowed':False,'productHold':True});d.new(root/'terminal.json',{'phase':'closed','report':d.bind(root/'report.json'),'actualInputs':count})
 except BaseException as e:
  d.new(root/'failure.json',{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc(),'actualStartedInputs':count,'resumeAllowed':False});raise


def verify(path,root,output):
 p,cuda,old=resources(path);cr=d.read(d.bind(root/'cpu/report.json'));term=d.read(d.bind(root/'cpu/terminal.json'));rows=[]
 if cr['plan']!=d.bind(path) or cr['actualInputs']!=9 or len(cr['records'])!=9 or term!={'phase':'closed','report':d.bind(root/'cpu/report.json'),'actualInputs':9}:raise ValueError('CPU complete terminal')
 for c,row in zip(p['cases'],cr['records'],strict=True):
  i=c['ordinal'];stats=base.compare(row['raw'],c,p,cuda,old,'cpu-ort')
  if row!={'ordinal':i,'input':c['input'],'raw':row['raw'],'comparison':stats} or d.read(d.bind(root/'cpu/events'/f'{i:03d}-confirmed.json'))!=row or d.read(d.bind(root/'cpu/events'/f'{i:03d}-started.json'))!={'ordinal':i,'input':c['input'],'plan':d.bind(path)}:raise ValueError('CPU event/RAW consistency')
  rows.append({'backend':'cpu-ort','ordinal':i,'raw':row['raw'],'comparison':stats})
 br=root/'browser';bp=d.read(d.bind(br/'plan.json'));live=d.read(d.bind(br/'capture/live-browser.json'));claim=d.read(d.bind(br/'claim.json'));expected=[(b,i) for b in ['wasm','webgpu'] for i in range(1,10)]
 if bp['operatorPlan']!=d.bind(path) or bp['scope']!='main' or bp['server']!=p['browserServer'] or live['phase']!='closed' or live['errors'] or live['virtualTime'] or not live['crossOriginIsolated'] or live['planSha256']!=d.bind(br/'plan.json')['sha256'] or live['claim']!=claim['claim']:raise ValueError('browser terminal scope')
 if live['userAgent']!=bp['expectedUserAgent'] or live['adapterInfo']!=bp['expectedAdapter'] or live['webgpuDevice']['grantedLimits']!=p['deviceProbeGrantedLimits'] or live['webgpuDevice']['adapterLimits']!=d.read(p['inputs']['deviceProbe'])['adapterLimits']:raise ValueError('actual ORT device fidelity')
 if [(r['backend'],r['ordinal']) for r in live['records']]!=expected or [(r['backend'],r['ordinal']) for r in live['started']]!=expected or len(list((br/'started').glob('*.json')))!=18 or len(list((br/'capture').glob('*.bin')))!=18:raise ValueError('full18 browser denominator')
 for row in live['records']:
  b,i=row['backend'],row['ordinal'];c=p['cases'][i-1];rid=claim['claim']+'-'+b+'-'+str(i);event=d.read(d.bind(br/'started'/f'{b}-{i}.json'));shape=[1,16,c['h'],c['w']];raw=br/'capture'/f'{b}-{i}.bin';ref={'binding':d.bind(raw),'shape':shape,'dtype':'float32','bytes':raw.stat().st_size}
  if row['requestId']!=rid or event!={'claim':claim['claim'],'requestId':rid,'backend':b,'ordinal':i,'h':c['h'],'w':c['w'],'inputSha256':c['input']['sha256']} or row['output']!={'shape':shape,'dtype':'float32','sha256':ref['binding']['sha256'],'bytes':ref['bytes']}:raise ValueError('browser raw metadata/input')
  rows.append({'backend':b,'ordinal':i,'raw':ref,'comparison':base.compare(ref,c,p,cuda,old,b)})
 files=[br/'claim.json',*sorted((br/'started').glob('*.json')),*sorted((br/'capture').glob('*'))];events=[d.read(d.bind(f)) for f in (br/'http-events').glob('*.json')];ids=set()
 for file in files:
  meta=d.read(d.bind(br/'metadata'/f'{file.parent.name}-{file.name}.json'));matching=[e for e in events if e['requestId']==meta['requestId']];expected_path='/claim' if file.name=='claim.json' else '/started/'+file.stem.replace('-','/') if file.parent.name=='started' else '/capture/'+file.name
  if not 1<=len(matching)<=2 or meta['sha256']!=d.bind(file)['sha256'] or meta['bytes']!=file.stat().st_size or any(e['declaredSha256']!=meta['sha256'] or e['declaredBytes']!=meta['bytes'] or e['path']!=expected_path for e in matching):raise ValueError('transport full identity')
  ids.add(meta['requestId'])
 if len(files)!=38 or ids!={e['requestId'] for e in events} or len(rows)!=27:raise ValueError('full27 transport denominator')
 summary={b:{'inputs':len(rr),'passed':sum(x['comparison']['numericGatePassed'] for x in rr),'maxAbsoluteDifference':max(x['comparison']['maxAbsoluteDifference'] for x in rr)} for b in ['cpu-ort','wasm','webgpu'] for rr in [[x for x in rows if x['backend']==b]]};gate=all(x['comparison']['numericGatePassed'] for x in rows)
 result={'ok':True,'decision':'partition_operator_all27_pass_full_model_pending' if gate else 'partition_operator_numeric_failure_preserved','reader':d.bind(__file__),'plan':d.bind(path),'cpuReport':d.bind(root/'cpu/report.json'),'browserLive':d.bind(br/'capture/live-browser.json'),'records':rows,'summary':summary,'all27CompleteFinite':True,'partitionOperatorGatePassed':gate,'actualOrtDeviceLimits':live['webgpuDevice'],'httpAttempts':len(events),'uniquePayloads':len(files),'actualNetworkBytes':None,'newModelInputs':0,'learnedInputs':0,'formalReleaseAllowed':False,'productHold':True}
 if output.exists():
  if d.read(d.bind(output))!=result:raise ValueError('immutable replay drift')
 else:d.new(output,result)
 print(json.dumps({'ok':True,'summary':summary,'partitionOperatorGatePassed':gate,'newModelInputs':0}),flush=True)


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['cpu','verify']);a.add_argument('--plan',type=Path,required=True);a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path);v=a.parse_args()
 if v.mode=='cpu':cpu(v.plan.resolve(),v.root.resolve())
 else:verify(v.plan.resolve(),v.root.resolve(),v.output.resolve())
