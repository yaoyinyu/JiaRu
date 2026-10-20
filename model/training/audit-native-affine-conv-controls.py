"""完整图全9独立控制：原两头参考、原始数组和后端迁移均可重放。"""
import argparse
import importlib.util
import json
import os
import traceback
from pathlib import Path
import numpy as np
import onnx
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('fullgraph_control_partition',HERE/'audit-partitioned-conv-controls.py');part=importlib.util.module_from_spec(s);s.loader.exec_module(part);d=part.d
s=importlib.util.spec_from_file_location('fullgraph_control_heads',HERE/'export-pretrained-native-candidate-v2.py');heads=importlib.util.module_from_spec(s);s.loader.exec_module(heads)


def resources(path):
 p=d.read(d.bind(path))
 assert p['purpose']=='channel_affine_convolution_controls'
 assert p['runner']==d.bind(__file__)
 for ref in [*p['inputs'].values(),p['runner'],p['browserServer'],p['partitionReader'],p['headReader'],p['headComparator']]:d.checked(ref)
 assert p['headReader']==d.bind(HERE/'export-pretrained-native-candidate-v2.py')
 assert p['headComparator']==d.bind(HERE/'verify-native-multiscale-browser-v2.py')
 proof=d.read(p['inputs']['graphProof']);source=onnx.load(d.checked(proof['originalGraph']))
 graph=d.load(d.checked(proof['transform']),'fullresolution_proof_transform')
 current,detail=graph.transform(source,proof['sourceNodes'])
 assert detail==proof['proof'] and current.SerializeToString()==d.checked(p['inputs']['onnx']).read_bytes()
 assert graph.restore(current,detail).SerializeToString()==source.SerializeToString() and proof['originalGraphBytesRestored']
 assert p['outputs']=={'mask':'mask_logits','presence':'presence_logit'}
 assert [x.name for x in current.graph.output]==list(p['outputs'].values())
 assert p['budget']==dict(cpuOrt=9,wasm=9,webgpu=9,cuda=0,exportTrace=0,learned=0,optimizerSteps=0,protected=0,newChatImages=0)
 cuda=d.read(p['inputs']['strictCuda']);oldcpu=d.read(p['inputs']['oldCpu']);oldbrowser=d.read(p['inputs']['oldBrowser'])
 assert p['cases']==proof['cases'] and len(p['cases'])==len(cuda['records'])==len(oldcpu['records'])==9
 assert [c['ordinal'] for c in p['cases']]==list(range(1,10))
 assert len(proof['sourceNodes'])==16 and proof['allOriginalParameterBytesPreserved']
 assert p['deviceProbeGrantedLimits']['maxComputeWorkgroupsPerDimension']==65535
 for c,ref,old in zip(p['cases'],cuda['records'],oldcpu['records'],strict=True):
  assert ref['ordinal']==old['ordinal']==c['ordinal'] and ref['input']==old['input']==c['input']
  heads.input_array(c['input'],c['h'],c['w']);heads.read_heads(ref['raw'],c['h'],c['w']);heads.read_heads(old['raw'],c['h'],c['w'])
  for b in ['wasm','webgpu']:
   rr=[r for r in oldbrowser['records'] if r['backend']==b and r['ordinal']==c['ordinal']]
   assert len(rr)==1 and rr[0]['input']==c['input'];heads.read_heads(rr[0]['raw'],c['h'],c['w'])
 return p,cuda,oldcpu,oldbrowser


def stats(ref,c,cuda,previous):
 h,w=c['h'],c['w'];actual=heads.read_heads(ref,h,w);expected=heads.read_heads(cuda,h,w);prior=heads.read_heads(previous,h,w);parity=heads.compare(expected,actual,h,w)
 per_head={name:float(np.abs(x-y).max()) for name,x,y in zip(['mask','presence'],expected,actual,strict=True)}
 migration={'sameBackendHeadsByteExact':{name:ref[name]['binding']['sha256']==previous[name]['binding']['sha256'] for name in ['mask','presence']},'maxAbsoluteChangeFromOldBackend':{name:float(np.abs(x-y).max()) for name,x,y in zip(['mask','presence'],prior,actual,strict=True)},'oldParityAgainstSameCuda':heads.compare(expected,prior,h,w),'newParityAgainstSameCuda':parity}
 return {'parity':parity,'headMaxAbsoluteDifference':per_head,'migration':migration}


def cpu(path,root):
 import onnxruntime as ort
 p,cuda,oldcpu,_=resources(path);ready=d.read(d.bind(path.with_name('readiness.json')))
 if not ready['ok'] or ready['plan']!=d.bind(path):raise ValueError('full graph machine readiness gate')
 root.mkdir(exist_ok=False);(root/'raw').mkdir();(root/'events').mkdir();rows=[];count=0;d.new(root/'attempt.json',{'plan':d.bind(path),'pid':os.getpid(),'resumeAllowed':False})
 try:
  opts=ort.SessionOptions();opts.log_severity_level=3;opts.intra_op_num_threads=4;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
  session=ort.InferenceSession(str(d.checked(p['inputs']['onnx'])),sess_options=opts,providers=['CPUExecutionProvider']);d.new(root/'environment.json',{'onnxruntime':ort.__version__,'providers':session.get_providers(),'intraThreads':4,'interThreads':1,'graphOptimization':'disabled'})
  for c,ref,old in zip(p['cases'],cuda['records'],oldcpu['records'],strict=True):
   i=c['ordinal'];h,w=c['h'],c['w'];x=heads.input_array(c['input'],h,w);d.new(root/'events'/f'{i:03d}-started.json',{'ordinal':i,'input':c['input'],'plan':d.bind(path)});count+=1;out=session.run(list(p['outputs'].values()),{'candidate':x})
   if len(out)!=2:raise ValueError('both original final heads required')
   raw=heads.save_heads(root/'raw',f'{i:03d}',out[0],out[1],h,w);row={'ordinal':i,'input':c['input'],'raw':raw,**stats(raw,c,ref['raw'],old['raw'])};d.new(root/'events'/f'{i:03d}-confirmed.json',row);rows.append(row);print(json.dumps({'fullCpu':i,'passed':heads.passed(row['parity']),'maxAbs':row['parity']['maxAbsoluteDifference']}),flush=True)
  gate=all(heads.passed(r['parity']) for r in rows);d.new(root/'report.json',{'ok':True,'plan':d.bind(path),'records':rows,'actualInputs':count,'full9CpuGatePassed':gate,'formalReleaseAllowed':False,'productHold':True});d.new(root/'terminal.json',{'phase':'closed','report':d.bind(root/'report.json'),'actualInputs':count})
 except BaseException as e:
  d.new(root/'failure.json',{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc(),'actualStartedInputs':count,'resumeAllowed':False});raise


def cpu_reconstruct(path,root):
 p,cuda,oldcpu,oldbrowser=resources(path);r=d.read(d.bind(root/'report.json'));term=d.read(d.bind(root/'terminal.json'))
 if r['plan']!=d.bind(path) or len(r['records'])!=9 or r['actualInputs']!=9 or term!={'phase':'closed','report':d.bind(root/'report.json'),'actualInputs':9} or len(list((root/'raw').glob('*.bin')))!=18:raise ValueError('complete CPU terminal/arrays')
 for c,ref,old,row in zip(p['cases'],cuda['records'],oldcpu['records'],r['records'],strict=True):
  i=c['ordinal'];expected={'ordinal':i,'input':c['input'],'raw':row['raw'],**stats(row['raw'],c,ref['raw'],old['raw'])}
  if row!=expected or d.read(d.bind(root/'events'/f'{i:03d}-confirmed.json'))!=row or d.read(d.bind(root/'events'/f'{i:03d}-started.json'))!={'ordinal':i,'input':c['input'],'plan':d.bind(path)}:raise ValueError('full9 CPU RAW/events reconstruction_mismatch')
 if r['full9CpuGatePassed']!=all(heads.passed(x['parity']) for x in r['records']):raise ValueError('CPU gate drift')
 return p,cuda,oldbrowser,r


def verify_cpu(path,root,output):
 p,cuda,oldbrowser,r=cpu_reconstruct(path,root);value={'ok':True,'reader':d.bind(__file__),'plan':d.bind(path),'cpuReport':d.bind(root/'report.json'),'full9CpuGatePassed':r['full9CpuGatePassed'],'full18CpuArraysReplayed':True,'newModelInputs':0,'formalReleaseAllowed':False,'productHold':True};write_replay(output,value);print(json.dumps({'ok':True,'full9CpuGatePassed':r['full9CpuGatePassed'],'newModelInputs':0}),flush=True)


def write_replay(output,value):
 if output.exists():
  if d.read(d.bind(output))!=value:raise ValueError('immutable replay drift')
 else:d.new(output,value)


def verify(path,root,output):
 p,cuda,oldbrowser,cr=cpu_reconstruct(path,root/'cpu');br=root/'browser';bp=d.read(d.bind(br/'plan.json'));live=d.read(d.bind(br/'capture/live-browser.json'));claim=d.read(d.bind(br/'claim.json'));expected=[(b,i) for b in ['wasm','webgpu'] for i in range(1,10)];rows=[{'backend':'cpuOrt',**x} for x in cr['records']]
 if bp['operatorPlan']!=d.bind(path) or bp['scope']!='main' or bp['server']!=p['browserServer'] or live['phase']!='closed' or live['errors'] or live['virtualTime'] or not live['crossOriginIsolated'] or live['planSha256']!=d.bind(br/'plan.json')['sha256'] or live['claim']!=claim['claim']:raise ValueError('complete full browser terminal')
 if live['userAgent']!=bp['expectedUserAgent'] or live['adapterInfo']!=bp['expectedAdapter'] or live['webgpuDevice']['grantedLimits']!=p['deviceProbeGrantedLimits']:raise ValueError('actual full backend device scope')
 if [(r['backend'],r['ordinal']) for r in live['records']]!=expected or [(r['backend'],r['ordinal']) for r in live['started']]!=expected or len(list((br/'started').glob('*.json')))!=18 or len(list((br/'capture').glob('*.bin')))!=36:raise ValueError('full9 x2 backends/2 heads denominator')
 for row in live['records']:
  b,i=row['backend'],row['ordinal'];c=p['cases'][i-1];h,w=c['h'],c['w'];rid=claim['claim']+'-'+b+'-'+str(i);event=d.read(d.bind(br/'started'/f'{b}-{i}.json'));raw={}
  if row['requestId']!=rid or event!={'claim':claim['claim'],'requestId':rid,'backend':b,'ordinal':i,'h':h,'w':w,'inputSha256':c['input']['sha256']}:raise ValueError('browser stable input identity')
  for name,shape in [('mask',[1,1,h,w]),('presence',[1,1])]:
   file=br/'capture'/f'{b}-{i}-{name}.bin';raw[name]={'binding':d.bind(file),'shape':shape,'dtype':'float32','bytes':file.stat().st_size}
   if row['outputs'][name]!={'shape':shape,'dtype':'float32','sha256':raw[name]['binding']['sha256'],'bytes':raw[name]['bytes']}:raise ValueError('full browser raw shape/hash')
  old=next(x for x in oldbrowser['records'] if x['backend']==b and x['ordinal']==i);rows.append({'backend':b,'ordinal':i,'input':c['input'],'raw':raw,**stats(raw,c,cuda['records'][i-1]['raw'],old['raw'])})
 files=[br/'claim.json',*sorted((br/'started').glob('*.json')),*sorted((br/'capture').glob('*'))];events=[d.read(d.bind(f)) for f in (br/'http-events').glob('*.json')];ids=set()
 for file in files:
  meta=d.read(d.bind(br/'metadata'/f'{file.parent.name}-{file.name}.json'));matching=[e for e in events if e['requestId']==meta['requestId']];expected_path='/claim' if file.name=='claim.json' else '/started/'+file.stem.replace('-','/') if file.parent.name=='started' else '/capture/'+file.name
  if not 1<=len(matching)<=2 or meta['sha256']!=d.bind(file)['sha256'] or meta['bytes']!=file.stat().st_size or any(e['declaredSha256']!=meta['sha256'] or e['declaredBytes']!=meta['bytes'] or e['path']!=expected_path for e in matching):raise ValueError('full transport exact request')
  ids.add(meta['requestId'])
 if len(files)!=56 or ids!={e['requestId'] for e in events} or len(rows)!=27:raise ValueError('full27/54 arrays transport cardinality')
 summary={b:{'inputs':len(rr),'passed':sum(heads.passed(x['parity']) for x in rr),'numericFailed':sum(not x['parity']['numericGatePassed'] for x in rr),'maxAbsoluteDifference':max(x['parity']['maxAbsoluteDifference'] for x in rr),'decodedPixelDifferences':[x['parity']['decodedMaskPixelDifference'] for x in rr],'presenceDecisionsAllMatched':all(x['parity']['presenceDecisionMatched'] for x in rr)} for b in ['cpuOrt','wasm','webgpu'] for rr in [[x for x in rows if x['backend']==b]]};gate=all(heads.passed(x['parity']) for x in rows)
 value={'ok':True,'decision':'full_partitioned_independent_controls_pass' if gate else 'full_partitioned_independent_control_failure_preserved','reader':d.bind(__file__),'plan':d.bind(path),'cpuReport':d.bind(root/'cpu/report.json'),'browserPlan':d.bind(br/'plan.json'),'browserLive':d.bind(br/'capture/live-browser.json'),'records':rows,'summary':summary,'all27Inputs54HeadsCompleteFinite':True,'independentFullGraphGatePassed':gate,'actualOrtDevice':live['webgpuDevice'],'httpAttempts':len(events),'uniquePayloads':len(files),'actualNetworkBytes':None,'newModelInputs':0,'learnedInputs':0,'formalReleaseAllowed':False,'productHold':True};write_replay(output,value);print(json.dumps({'ok':True,'summary':summary,'independentFullGraphGatePassed':gate,'newModelInputs':0}),flush=True)


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['cpu','verify-cpu','verify']);a.add_argument('--plan',type=Path,required=True);a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path);v=a.parse_args()
 if v.mode=='cpu':cpu(v.plan.resolve(),v.root.resolve())
 elif v.mode=='verify-cpu':verify_cpu(v.plan.resolve(),v.root.resolve(),v.output.resolve())
 else:verify(v.plan.resolve(),v.root.resolve(),v.output.resolve())
