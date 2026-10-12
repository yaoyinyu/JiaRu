"""按存档同候选身份物化原像素条件输入；不向审核模型发送ROI，不批准训练。"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
def module(path,name):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','stage_b_material_data')
def identity(row):return d.key(row)
def validate(plan):
 for ref in plan['inputs'].values():d.checked(ref)
 if plan['purpose']!='new_stage_a_conditioned_stage_b_input_pixel_preflight_only' or plan['newInferenceCallsAllowed'] or plan['optimizerStepsAllowed'] or plan['oldConsumedBudgetsMayResume']:
  raise ValueError('zero-model materialization contract')
 if plan['reachability'].get('trainRatio')!=1 or plan['reachability'].get('internalValRatio')!=.98 or 'ratio' in plan['reachability']:raise ValueError('ambiguous geometric ratios')
 contract=d.read(plan['inputs']['trainingContract']);sources=d.validate(contract);diag=d.read(plan['inputs']['diagnostic']);visual=d.read(plan['inputs']['wholeVisual'])
 if [s['identity'] for s in sources]!=[r['identity'] for r in diag['records']]:raise ValueError('source denominator')
 source_map={identity(s['identity']):s for s in sources}; expected=[];missing=[]
 for s,r,v in zip(sources,diag['records'],visual['records'],strict=True):
  if s['identity']!=r['identity'] or v['identity']!=s['identity']:raise ValueError('source role identity')
  assigned={a['predictionIndex']:a for a in r['primaryAssignment']}; used={a['truthIndex'] for a in assigned.values()}
  missing.extend((identity(s['identity']),i) for i in range(1,s['maskCount']+1) if i not in used)
  for j in range(1,r['candidates']+1):
   pair=assigned.get(j); expected.append((identity(s['identity']),j,pair['truthIndex'] if pair else None))
   if not pair and j not in v['backgroundFalsePositiveCandidateIndices']+v['duplicateOrContaminatedCandidateIndices']:raise ValueError('unreviewed candidate rejection')
 observed=[(identity(r['candidateIdentity']['identity']),r['candidateIdentity']['predictionIndex'],r['target']['truthIndex']) for r in plan['records']]
 if observed!=expected or len(observed)!=len(set((k,j) for k,j,_ in observed)) or len(observed)!=124:raise ValueError('all-candidate reconstruction_mismatch')
 if [(identity(r['identity']),r['truthIndex']) for r in plan['missingTruthsPreserved']]!=missing:raise ValueError('missing truth denominator changed')
 for row in plan['records']:
  s=source_map[identity(row['candidateIdentity']['identity'])]
  if row['annotation']!=s['annotation'] or row['sourceImage']!=s['sourceImage'] or row['sourceGroup']!=s['sourceGroup'] or row['currentSplit']!=s['identity']['split']:raise ValueError('source/annotation/role drift')
  if row['currentSplit']=='val' and row['trainingUse']!='prohibited':raise ValueError('val backflow')
  d.checked(row['visualEvidence']); d.checked(row['candidateIdentity']['prediction'])
 return contract,sources,source_map
def crop_values(rgb,coarse,target,box,presence):
 x0,y0,x1,y1=box
 if not(0<=x0<x1<=rgb.shape[1] and 0<=y0<y1<=rgb.shape[0]):raise ValueError('native crop outside image')
 r=rgb[y0:y1,x0:x1].copy(); c=coarse[y0:y1,x0:x1].astype(np.uint8)*255;t=target[y0:y1,x0:x1].astype(np.uint8)*255
 if not c.any():raise ValueError('empty same-candidate seed')
 if presence and int((t>0).sum())!=int(target.sum()):raise ValueError('complete nail pixels lost')
 if not presence and t.any():raise ValueError('rejection target contains nail pixels')
 return r,c,t
def build(plan_path,root,replay=False):
 plan=d.read(d.bind(plan_path));contract,sources,source_map=validate(plan)
 helper=module(d.checked(plan['inputs']['predictionHelper']),'stage_b_prediction_reader');roi=module(d.checked(plan['inputs']['roiHelper']),'stage_b_roi_reader')
 evaluator=module(HERE/'evaluate-reviewed-stage-a.py','stage_b_native_truth_reader')
 guard=d.load(d.checked(plan['inputs']['readOnlyGuard']),'stage_b_native_guard');guard.install_read_only_ultralytics_image_check()
 rows=[];decoded={};files=[];unpaired=[]
 try:
  if not replay:root.mkdir(parents=True,exist_ok=False)
  for number,row in enumerate(plan['records'],1):
   ci=row['candidateIdentity'];key=identity(ci['identity']);s=source_map[key]
   if key not in decoded:
    with Image.open(d.checked(s['sourceImage'])) as im:im.load();rgb=np.asarray(im.convert('RGB')).copy()
    boxes,conf,classes,masks=helper.load_prediction(ci['prediction'],s['size']);truth=evaluator.truths(s)
    decoded[key]=(rgb,boxes,masks,truth)
   rgb,boxes,masks,truth=decoded[key]; j=ci['predictionIndex']-1
   if hashlib.sha256(masks[j].tobytes()).hexdigest()!=ci['coarseMaskSha256']:raise ValueError('same candidate seed drift')
   box=roi.crop_box(boxes[j],*s['size'],plan['roiPolicy'])
   if box is None:raise ValueError('invalid ROI')
   positive=row['target']['kind']=='complete_reviewed_nail_mask'
   target=truth[row['target']['truthIndex']-1] if positive else np.zeros(rgb.shape[:2],bool)
   if positive and hashlib.sha256(target.tobytes()).hexdigest()!=row['target']['truthMaskSha256']:raise ValueError('original truth storage domain')
   nr,nc,nt=crop_values(rgb,masks[j],target,box,positive)
   values={'nativeRgb':Image.fromarray(nr),'nativeCoarse':Image.fromarray(nc),'nativeTarget':Image.fromarray(nt),
           'rgb384':Image.fromarray(nr).resize((384,384),Image.Resampling.BILINEAR),
           'coarse384':Image.fromarray(nc).resize((384,384),Image.Resampling.NEAREST),
           'target384':Image.fromarray(nt).resize((384,384),Image.Resampling.BILINEAR)}
   paths={}
   for name,value in values.items():
    path=root/f'{number:03d}-{name}.png'
    if replay:
     with Image.open(path) as saved:saved.load();actual=np.asarray(saved).copy()
     if not np.array_equal(actual,np.asarray(value)):raise ValueError('native/384 pixel reconstruction_mismatch')
    else:
     with path.open('xb') as f:value.save(f,format='PNG');f.flush();os.fsync(f.fileno())
    paths[name]=d.bind(path);files.append(paths[name])
   rows.append({'ordinal':number,'candidateIdentity':ci,'split':row['currentSplit'],'target':row['target'],'cropBox':list(box),
                'nativeSize':[nr.shape[1],nr.shape[0]],'presenceTarget':positive,'paths':paths,
                'rgbNativeBytesSha256':hashlib.sha256(nr.tobytes()).hexdigest(),'coarseNativeBytesSha256':hashlib.sha256(nc.tobytes()).hexdigest(),
                'targetNativeBytesSha256':hashlib.sha256(nt.tobytes()).hexdigest(),'nativeTargetPixels':int((nt>0).sum()),
                'sourceTruthPixels':int(target.sum()),'sourceTruthPixelsLost':0,
                'candidateRejectIsNotEmptyRgb':not positive,'sourceRolePreserved':True})
  for number,missing in enumerate(plan['missingTruthsPreserved'],1):
   key=identity(missing['identity']);truth=decoded[key][3][missing['truthIndex']-1]
   path=root/f'missing-truth-{number:03d}.png';expected=truth.astype(np.uint8)*255
   if replay:
    with Image.open(path) as saved:saved.load();actual=np.asarray(saved).copy()
    if not np.array_equal(actual,expected):raise ValueError('unpaired full truth pixels changed')
   else:
    with path.open('xb') as f:Image.fromarray(expected).save(f,format='PNG');f.flush();os.fsync(f.fileno())
   ref=d.bind(path);files.append(ref)
   unpaired.append({**missing,'fullNativeTruth':ref,'truthPixels':int(truth.sum()),'inferenceUse':'prohibited_gt_only_no_candidate','trainingUse':'prohibited'})
  result={'schemaVersion':1,'ok':True,'decision':'native_stage_b_inputs_pixel_exact_training_capacity_pending',
          'plan':d.bind(plan_path),'materializer':d.bind(__file__),'root':str(root.resolve()),'records':rows,'files':files,
          'counts':plan['counts'],'sourceTruthDenominator':plan['sourceTruthDenominator'],'missingTruthsPreserved':plan['missingTruthsPreserved'],
          'candidateInputs':124,'generatedFiles':len(files),'candidateFiles':744,'unpairedFullTruthAssets':unpaired,'allOriginalTruthPixelsPreserved':True,
          'inputPixelsNeverGeneratedOrUpscaledForNative':True,'reference384IsNotNativeQualityEvidence':True,
          'nativeLayout':{'sourceCoordinateMapping':'integer crop origin plus unscaled local coordinates','padding':0},
          'newChatImageInputs':0,'sourceInferenceInputs':0,'optimizerSteps':0,'trainingAllowed':False,'formalReleaseAllowed':False,'productHold':True}
  if not replay:d.new(root/'materialization.json',result)
  else:
   if json.loads((root/'materialization.json').read_bytes())!=result:raise ValueError('materialization report drift')
   if {p.resolve() for p in root.iterdir() if p.is_file()}!={Path(f['path']) for f in files}|{(root/'materialization.json').resolve()}:raise ValueError('full dataset tree drift')
  return result
 finally:
  decoded.clear()
  for path in contract['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
 if a.verify_report:old=json.loads(a.verify_report.read_bytes());r=build(Path(old['plan']['path']),a.verify_report.parent,True)
 else:r=build(a.plan.resolve(),a.output.resolve())
 print(json.dumps({k:r[k] for k in ('ok','decision','candidateInputs','generatedFiles','counts','trainingAllowed')}))
if __name__=='__main__':main()
