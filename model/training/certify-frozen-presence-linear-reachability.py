"""线性可分数学证书；系数仅作证书，不能初始化训练或发布。"""
import argparse,importlib.util,json,os
from pathlib import Path
import numpy as np
import torch
from scipy.optimize import linprog
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('linear_cert_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
feature_reader=d.load(HERE/'materialize-frozen-native-presence-features.py','linear_cert_feature_domain')
def solve_certificate(values,labels):
 conflicts=feature_reader.validate_features(values,labels)
 if conflicts:return {'reachable':False,'reason':'cross_class_exact_feature_conflict','solverCalls':0},None
 signed=labels.astype(np.float64)*2-1
 matrix=np.column_stack((values.astype(np.float64),np.ones(len(labels))))
 result=linprog(np.zeros(129),A_ub=-signed[:,None]*matrix,b_ub=-np.ones(len(labels)),bounds=[(None,None)]*129,method='highs')
 if not result.success:return {'reachable':False,'reason':'linear_margin_constraints_infeasible_or_solver_failed','solverCalls':1,'solverStatus':int(result.status),'solverMessage':result.message},None
 witness=result.x.astype(np.float32)
 score=torch.nn.functional.linear(torch.from_numpy(values),torch.from_numpy(witness[:-1][None]),torch.from_numpy(witness[-1:])).numpy().reshape(-1)
 if not np.isfinite(witness).all() or not np.isfinite(score).all() or not np.all(signed*score>0):return {'reachable':False,'reason':'float32_witness_margin_not_strictly_positive','solverCalls':1},None
 return {'reachable':True,'reason':'float64_lp_and_cpu_float32_margin_certificate','solverCalls':1,
  'minimumCpuFloat32SignedMargin':float((signed*score).min()),'witnessWeightNorm':float(np.linalg.norm(witness[:-1].astype(np.float64))),
  'solverStatus':int(result.status)},witness
def native_margins(values,labels,witness):
 signed=labels.astype(np.float32)*2-1
 cpu=[];cuda=[];weight=torch.from_numpy(witness[:-1][None]);bias=torch.from_numpy(witness[-1:])
 for row in values:
  x=torch.from_numpy(row[None]);cpu.append(float(torch.nn.functional.linear(x,weight,bias)[0,0]))
  cuda.append(float(torch.nn.functional.linear(x.cuda(),weight.cuda(),bias.cuda())[0,0]))
 a=np.asarray(cpu,np.float32)*signed;b=np.asarray(cuda,np.float32)*signed
 if not np.isfinite(a).all() or not np.isfinite(b).all() or not np.all(a>0) or not np.all(b>0):raise ValueError('native float32 certificate margins')
 return {'cpuSignedMargins':a.tolist(),'cudaSignedMargins':b.tolist(),
  'minimumCpuMargin':float(a.min()),'minimumCudaMargin':float(b.min()),'positiveAccepts':int(labels.sum()),'rejects':int((labels==0).sum())}
def inputs(feature_path):
 report=d.read(d.bind(feature_path));scope=d.read(report['inputs']['scope'])
 if not report['ok'] or report['featureShape']!=[68,128] or not report['all68MetricsReconstructed'] or report['optimizerSteps']:raise ValueError('feature gates')
 if [r['candidateIdentity'] for r in report['records']]!=scope['candidateIdentities'] or [r['featureIndex'] for r in report['records']]!=list(range(68)):raise ValueError('full68 feature identity')
 with np.load(d.checked(report['inputs']['featureArchive']),allow_pickle=False) as archive:values=archive['features'].copy();labels=archive['labels'].copy()
 if labels.tolist()!=[int(r['presenceTarget']) for r in report['records']] or int(labels.sum())!=66:raise ValueError('candidate targets')
 feature_reader.validate_features(values,labels)
 return report,values,labels
def certify(feature_path,root):
 report,values,labels=inputs(feature_path)
 if root.exists():raise ValueError('certificate exists')
 result,witness=solve_certificate(values,labels);root.mkdir(parents=True,exist_ok=False)
 native=None;ref=None
 if witness is not None:
  native=native_margins(values,labels,witness)
  with (root/'mathematical-witness.npz').open('xb') as stream:np.savez_compressed(stream,coefficients=witness);stream.flush();os.fsync(stream.fileno())
  ref=d.bind(root/'mathematical-witness.npz')
 output={'schemaVersion':1,'ok':True,'decision':'frozen_linear_head_reachable_certificate_only' if result['reachable'] else 'frozen_linear_head_unreachable_or_unproven_no_training',
  'inputs':{'featureReport':d.bind(feature_path),'certifier':d.bind(__file__)},'certificate':result,'nativeFloat32Margins':native,'witness':ref,
  'positiveCount':66,'rejectCount':2,'frozenMaskJointCeiling':54,'requiredJointCount':53,'ceilingToRequiredRatio':54/53,
  'maskModelForwardCalls':0,'neuralOptimizerSteps':0,'witnessNeverTrainingOrProductionWeights':True,
  'newHeadBudgetRegistered':False,'formalReleaseAllowed':False,'productHold':True}
 d.new(root/'report.json',output);print(json.dumps({'ok':True,'reachable':result['reachable'],'reason':result['reason'],
  'weightNorm':result.get('witnessWeightNorm'),'minimumCudaMargin':native['minimumCudaMargin'] if native else None,'optimizerSteps':0}))
def verify(path):
 old=d.read(d.bind(path));report,values,labels=inputs(d.checked(old['inputs']['featureReport']))
 if not old['certificate']['reachable']:raise ValueError('unreachable certificate requires its explicit solver diagnostic; no admission')
 with np.load(d.checked(old['witness']),allow_pickle=False) as archive:witness=archive['coefficients'].copy()
 if native_margins(values,labels,witness)!=old['nativeFloat32Margins']:raise ValueError('certificate replay mismatch')
 print(json.dumps({'ok':True,'reachable':True,'optimizerSteps':0,'newMaskModelCalls':0}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--features',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
 if a.verify_report:verify(a.verify_report.resolve())
 else:certify(a.features.resolve(),a.output.resolve())
