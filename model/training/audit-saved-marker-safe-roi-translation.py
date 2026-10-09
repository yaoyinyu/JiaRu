"""冻结存档全量重建后验证同尺寸ROI避标平移；零推理，不晋升模型质量。"""
import argparse,hashlib,importlib.util,json,math,sys
from pathlib import Path

def bind(p):
 p=Path(p).resolve();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def checked(ref):
 if bind(ref['path'])!=ref:raise ValueError('reconstruction_mismatch: '+ref['path'])
 return Path(ref['path'])
def read(ref):return json.loads(checked(ref).read_bytes())
def module(ref,name):
 p=checked(ref);sys.path.insert(0,str(p.parent));sp=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def require_identical_baseline(prior,rebuilt):
 if prior!=rebuilt:raise ValueError('reconstruction_mismatch: full frozen baseline')
 if not prior.get('acceptedCandidateReconstructionIdentical') or not prior.get('conclusionsAllowed'):raise ValueError('reconstruction_mismatch: baseline fidelity not established')

def analyze(executionRef):
 e=read(executionRef);refs=e['inputs'];translation=module(refs['translationHelper'],'translation')
 if e['contract']!=translation.POLICY:raise ValueError('reconstruction_mismatch: translation policy')
 baseline=read(refs['baselineReport']);legacy=module(refs['baselineAnalyzer'],'baseline_roi');require_identical_baseline(baseline,legacy.analyze(baseline['execution']))
 if baseline['counts']!=e['counts']:raise ValueError('reconstruction_mismatch: denominator')
 guard=module(refs['readOnlyGuard'],'translation_guard');guard.install_read_only_ultralytics_image_check()
 roots={Path(r['source']['sourceImage']['path']).parents[2] for r in baseline['records']}
 try:
  import numpy as np
  from PIL import Image
  helper=module(refs['predictionHelper'],'prediction');truthHelper=module(refs['truthHelper'],'truth');prompt=module(refs['conditionalHelper'],'prompt');roi=module(refs['roiHelper'],'roi')
  records=[];changed=[];unreachable=[]
  for old in baseline['records']:
   s=old['source'];truth,boxes,conf,classes,masks=legacy.rebuild_original(s,old['originalMatchingPreserved'],helper,truthHelper);w,h=s['imageSize'];halos=old['registeredMarkerHalos'];ious=np.asarray(old['seedIoUMatrixNative'],np.float64)
   intersections=np.asarray([c['coarseTruthIntersectionPixels'] for c in old['candidates']],np.int64).T
   if not np.array_equal(intersections,np.asarray([[int((t&m).sum()) for m in masks] for t in truth])):raise ValueError('reconstruction_mismatch: original native intersections')
   originalRGB=next(v['image'] for v in s['variants'] if v['name']=='original')
   with Image.open(checked(originalRGB)) as im:rgb=im.convert('RGB')
   if list(rgb.size)!=s['imageSize']:raise ValueError('RGB dimension drift')
   owners={a['predictionIndex']-1:a['truthIndex']-1 for a in old['originalMatchingPreserved']['assignment']};coverage=np.zeros((len(truth),len(masks)),np.float64);dominant=np.zeros_like(coverage,dtype=bool);safe=[];candidates=[]
   for j,c in enumerate(old['candidates']):
    base=c['cropBox'];anchor=None;result={'decision':'unreachable','cropBox':None,'translation':None}
    if base is not None:
     # 仅模型候选框与原ROI可见粗mask；真值只在位置冻结后作审核。
     bx=[max(0,math.floor(float(boxes[j][0]))),max(0,math.floor(float(boxes[j][1]))),min(w,math.ceil(float(boxes[j][2]))),min(h,math.ceil(float(boxes[j][3])))];x0,y0,x1,y1=base;ys,xs=np.nonzero(masks[j][y0:y1,x0:x1]);anchor=bx
     if len(xs):anchor=[min(bx[0],int(xs.min())+x0),min(bx[1],int(ys.min())+y0),max(bx[2],int(xs.max())+x0+1),max(bx[3],int(ys.max())+y0+1)]
     result=translation.translate_crop(base,anchor,halos,w,h)
    crop=result['cropBox'];area=None if crop is None else sum(translation.overlap_area(crop,b) for b in halos);safe.append(crop is not None and area==0)
    row={'predictionIndex':j+1,'originalCropBox':base,'anchorBox':anchor,'translationResult':result,'cropBox':crop,'originalMarkerHaloIntersectionArea':c['registeredMarkerHaloIntersectionArea'],'markerHaloIntersectionArea':area,'originalCandidatePreserved':c,'originalAssignedTruthIndex':c['originalAssignedTruthIndex']}
    for ti in range(len(truth)):dominant[ti,j]=prompt.seed_identity(intersections[:,j].tolist(),ti)['strictlyTargetDominant']
    if crop is not None:
     if [crop[2]-crop[0],crop[3]-crop[1]]!=[base[2]-base[0],base[3]-base[1]]:raise ValueError('crop size drift')
     x0,y0,x1,y1=crop
     for ti,t in enumerate(truth):coverage[ti,j]=int(t[y0:y1,x0:x1].sum())/int(t.sum())
     seed=np.asarray(Image.fromarray(masks[j].astype('uint8')*255).crop(crop).resize((384,384),Image.Resampling.NEAREST));a=np.asarray(rgb.crop(crop).resize((384,384),Image.Resampling.BILINEAR));packed=prompt.pack_input(a,seed);projected=[]
     for t in truth:
      target=np.asarray(Image.fromarray(t.astype('uint8')*255).crop(crop).resize((384,384),Image.Resampling.NEAREST))>0;projected.append(int((target&(seed>0)).sum()))
     packedHash=hashlib.sha256(packed.astype('<f4',copy=False).tobytes()).hexdigest();unique=prompt.seed_identity(projected,owners[j])['strictlyTargetDominant'] if j in owners else None
     row.update({'packed384InputSha256':packedHash,'packed384TruthSeedIntersectionPixels':projected,'packed384OriginalAssignedPromptUnique':unique,'nativeOriginalAssignedPromptUnique':bool(dominant[owners[j],j]) if j in owners else None,'oldVisibleCoarsePixels':int(masks[j][base[1]:base[3],base[0]:base[2]].sum()),'newVisibleCoarsePixels':int(masks[j][y0:y1,x0:x1].sum())})
     if result['decision']=='unchanged' and (packedHash!=c['packed384InputSha256'] or projected!=c['packed384TruthSeedIntersectionPixels']):raise ValueError('reconstruction_mismatch: unchanged packed pixels')
    if result['decision']=='translated':changed.append({'identity':old['identity'],**row})
    if result['decision']=='unreachable':unreachable.append({'identity':old['identity'],'predictionIndex':j+1})
    candidates.append(row)
   valid=(coverage==1)&(ious>0)&dominant&np.asarray(safe,bool)[None,:]
   stages={name:legacy.variant_stats([j-1 for j in v['selectedPredictionIndices']],coverage,ious,valid,old['originalMatchingPreserved'],roi) for name,v in old['stages'].items()}
   for name,stage in stages.items():
    if stage['selectedPredictionIndices']!=old['stages'][name]['selectedPredictionIndices']:raise ValueError('accepted candidate set drift')
   records.append({'identity':old['identity'],'sourceGroup':old['sourceGroup'],'source':s,'originalMatchingPreserved':old['originalMatchingPreserved'],'candidates':candidates,'stages':stages,'coverageMatrixNative':coverage.tolist(),'seedIoUMatrixNative':old['seedIoUMatrixNative'],'registeredMarkerBoxes':old['registeredMarkerBoxes'],'registeredMarkerHalos':halos,'dedupSuppressionEvents':old['dedupSuppressionEvents'],'deduplicatedPredictionIndicesBeforeCap':old['deduplicatedPredictionIndicesBeforeCap'],'trainingUse':'prohibited'})
  aggregate={}
  for name in baseline['aggregateByPolicy']:
   vals=[r['stages'][name] for r in records];aggregate[name]={k:sum(v[k] for v in vals) for k in ('primaryFullCoverageNails','primaryConditionalValidNails','oracleFullCoverageNails','oracleConditionalValidNails')};aggregate[name].update({'selectedCandidates':sum(len(v['selectedPredictionIndices']) for v in vals),'fullyConditionalValidImagesPrimary':sum(v['primaryConditionalValidNails']==r['source']['completeVisibleNails'] for v,r in zip(vals,records,strict=True))})
  packed=sum(c.get('packed384OriginalAssignedPromptUnique') is True for r in records for c in r['candidates']);n=baseline['counts']['truthNails'];full=aggregate['dedup_before_cap10']['primaryConditionalValidNails']==n and packed==n and not unreachable
  return {'schemaVersion':1,'execution':executionRef,'inputs':refs,'contract':e['contract'],'ok':full,'decision':'all_saved_conditional_input_geometry_repaired_not_model_quality_pass' if full else 'translation_failed_full_input_admission','conclusionsAllowed':True,'fullFrozenBaselineReplayIdentical':True,'acceptedCandidateSetsAndOriginalMatchingPreserved':True,'counts':baseline['counts'],'historicalAggregateByPolicyPreserved':baseline['aggregateByPolicy'],'aggregateByPolicy':aggregate,'packed384UniqueOriginalPrompts':packed,'translatedCandidates':changed,'unreachableCandidates':unreachable,'records':records,'trainingAllowed':False,'formalTrainingApprovedImages':0,'newModelCalls':0,'optimizerSteps':0,'full30PilotAllowed':False,'productHold':True}
 finally:
  for root in roots:guard.remove_ultralytics_label_caches(root)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execution',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--verify-report',type=Path);a=ap.parse_args()
 if a.verify_report:
  old=json.loads(a.verify_report.read_bytes());new=analyze(old['execution'])
  if old!=new:raise ValueError('reconstruction_mismatch: report')
  print(json.dumps({'ok':True,'decision':'saved_translation_replay_identical','newModelCalls':0}));return
 if not a.execution or not a.output:ap.error('--execution and --output required')
 try:r=analyze(bind(a.execution))
 except (ValueError,AssertionError,KeyError,TypeError) as err:r={'schemaVersion':1,'execution':bind(a.execution),'ok':False,'decision':'reconstruction_mismatch','conclusionsAllowed':False,'errorType':type(err).__name__,'message':str(err),'newModelCalls':0,'trainingAllowed':False}
 with a.output.open('xb') as f:f.write((json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'report':bind(a.output),'ok':r['ok'],'decision':r['decision'],'counts':r.get('counts'),'aggregates':r.get('aggregateByPolicy'),'translations':len(r.get('translatedCandidates',[]))},ensure_ascii=False))
 if not r['conclusionsAllowed']:raise SystemExit(1)
if __name__=='__main__':main()
