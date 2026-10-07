"""存档原图候选的硬保真、一一ROI/提示上限；零模型调用、无训练晋升。"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

def bind(p):
    p=Path(p).resolve();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def checked(ref):
    if bind(ref['path'])!=ref:raise ValueError('reconstruction_mismatch: '+ref['path'])
    return Path(ref['path'])
def read(ref):return json.loads(checked(ref).read_bytes())
def module(ref,name):
    p=checked(ref);sys.path.insert(0,str(p.parent));s=importlib.util.spec_from_file_location(name,p)
    m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def key(i):return tuple(i[k] for k in ('split','fileName','imageSha256'))

def joint_oracle(valid,ious):
    """合法边优先的一一见证，不复用一候选覆盖多真值。"""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    if valid.shape!=ious.shape:raise ValueError('matrix dimensions')
    scores=valid.astype('float64')*(min(valid.shape)+1)+ious
    rows,cols=linear_sum_assignment(-scores) if scores.size else ([],[])
    return [{'truthIndex':int(i)+1,'predictionIndex':int(j)+1,'conditionallyValid':bool(valid[i,j]),
        'coarseMaskIoU':float(ious[i,j])} for i,j in zip(rows,cols,strict=True) if ious[i,j]>0]

def rebuild_original(source,old,helper,truthHelper):
    checked(source['sourceImage']);checked(source['annotation'])
    truth=truthHelper.truth_masks(source)
    boxes,conf,classes,masks=helper.load_prediction(old['prediction'],source['imageSize'])
    restored={'prediction':old['prediction'],'boxesXyxy':boxes.tolist(),'confidence':conf.tolist(),
        'classes':classes.tolist(),'instanceCount':len(masks),**helper.match_masks(masks,truth,.75)}
    if restored!=old:raise ValueError('reconstruction_mismatch: original candidates/assignment '+source['identity']['fileName'])
    return truth,boxes,conf,classes,masks

def variant_stats(selected,coverage,ious,valid,original,roi):
    import numpy as np
    assignment=original['assignment'];chosen=set(selected)
    primary=[]
    for a in assignment:
        i,j=a['truthIndex']-1,a['predictionIndex']-1
        kept=j in chosen
        primary.append({**a,'candidateKept':kept,'completeTruthCoverage':bool(kept and coverage[i,j]==1),
            'conditionallyValid':bool(kept and valid[i,j])})
    geo=roi.oracle_allocation(coverage[:,selected],ious[:,selected])
    joint=joint_oracle(valid[:,selected],ious[:,selected])
    for collection in (geo,joint):
        for a in collection:a['predictionIndex']=selected[a['predictionIndex']-1]+1
    return {'selectedPredictionIndices':[j+1 for j in selected],'primaryAssignmentPreserved':primary,
        'geometryOracleAssignment':geo,'conditionalOracleAssignment':joint,
        'primaryFullCoverageNails':sum(a['completeTruthCoverage'] for a in primary),
        'primaryConditionalValidNails':sum(a['conditionallyValid'] for a in primary),
        'oracleFullCoverageNails':sum(a['completeTruthCoverage'] for a in geo),
        'oracleConditionalValidNails':sum(a['conditionallyValid'] for a in joint),
        'unresolvedOriginalTruthIndices':[a['truthIndex'] for a in primary if not a['conditionallyValid']]}

def analyze(executionRef):
    e=read(executionRef);refs=e['inputs']
    if checked(refs['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity')
    p=read(refs['plan'])
    if p['contract']!=e['contractPreserved']:raise ValueError('reconstruction_mismatch: frozen policy')
    for ref in p['inputs'].values():checked(ref)
    guard=module(p['inputs']['readOnlyGuard'],'cohort_roi_guard');guard.install_read_only_ultralytics_image_check()
    roots={Path(s['sourcePreserved']['sourceImage']['path']).parents[2] for s in p['sources']}
    try:
        import numpy as np
        from PIL import Image
        helper=module(refs['predictionHelper'],'cohort_saved_prediction_helper')
        if helper.environment()!=read(refs['environment']):raise ValueError('reconstruction_mismatch: frozen environment')
        truthHelper=module(refs['truthHelper'],'cohort_saved_truth_helper')
        roi=module(p['inputs']['roiHelper'],'cohort_roi_geometry')
        prompt=module(p['inputs']['conditionalHelper'],'cohort_prompt_geometry')
        dedup=module(p['inputs']['dedupHelper'],'cohort_proposal_dedup')
        idx=read(p['inputs']['currentIndex']);lookup={key(r['identity']):r for r in idx['records']}
        if len(lookup)!=len(idx['records']):raise ValueError('duplicate current index')
        sourceIds=[key(s['identity']) for s in p['sources']]
        if len(set(sourceIds))!=len(sourceIds):raise ValueError('duplicate cohort identity')
        markerLookup={}
        expectedSourceOrder=[]
        for probeRef in [p['inputs']['valProbe'],p['inputs']['trainProbe']]:
            probe=read(probeRef);ex=read(probe['execution']);probePlan=read(ex['inputs']['plan'])
            expectedSourceOrder.extend(key(r['identity']) for r in probe['records'])
            pack=read(probePlan['inputs']['variantPack'])
            for r in pack['records']:
                marker=r.get('markerBox') or r['sourcePreserved']['markerBox']
                markerLookup[key(r['identity'])]=marker
        if sourceIds!=expectedSourceOrder or set(markerLookup)!=set(sourceIds):
            raise ValueError('reconstruction_mismatch: complete frozen cohort/order')
        # Complete cohort reconstruction precedes any coverage or attribution computation.
        decoded=[]
        for item in p['sources']:
            s=item['sourcePreserved'];role=lookup[key(item['identity'])]
            if item['identity']!=s['identity'] or item['currentRolePreserved']!=role or s['roleEvidence']!=role:
                raise ValueError('reconstruction_mismatch: roles')
            allowed={'developmentTrain'} if s['identity']['split']=='train' else {'developmentTrain','currentHistoricalRoiValidation'}
            if s['identity']['split'] not in ('train','val') or role['upstreamDevelopmentSplit']!='train' or role['protectedTrainConflicts'] or not role['currentAndParentRoleMatches'] or any(r['role'] not in allowed for r in role['currentAndParentRoleMatches']):
                raise ValueError('protected role or parent')
            if role['trainingUse']!='prohibited' or role['formalTrainingApproved']:raise ValueError('unexpected promotion')
            probe=read(item['recordedProbe']);matching=[r for r in probe['records'] if key(r['identity'])==key(s['identity'])]
            if len(matching)!=1:raise ValueError('reconstruction_mismatch: original source identity')
            record=matching[0]
            if record['predictions']['original']!=item['originalPredictionPreserved']:raise ValueError('reconstruction_mismatch: frozen original row')
            values=rebuild_original(s,item['originalPredictionPreserved'],helper,truthHelper)
            decoded.append((item,*values))
        counts={'sources':len(decoded),'trainSources':sum(i['identity']['split']=='train' for i,*_ in decoded),
            'internalValSources':sum(i['identity']['split']=='val' for i,*_ in decoded),
            'truthNails':sum(len(t) for i,t,*_ in decoded),'originalCandidates':sum(len(m) for *_,m in decoded),
            'originalIoU075Matches':sum(len(i['originalPredictionPreserved']['matches']) for i,*_ in decoded)}
        if counts!=p['counts']:raise ValueError('reconstruction_mismatch: complete denominator')
        conditionalPolicy=read(p['inputs']['frozenConditionalPolicy'])['contract']
        dedupPolicy=read(p['inputs']['frozenDedupPolicy'])['contract']
        if conditionalPolicy['maximumProposalsPerImage']!=10 or [dedupPolicy[k] for k in ('maskIoUThreshold','smallerMaskContainmentThreshold','moreCompleteScoreTolerance','maximumProposalsPerImage')]!=[.6,.85,.12,10]:
            raise ValueError('frozen proposal budget/duplicate policy drift')
        records=[]
        for item,truth,boxes,conf,classes,masks in decoded:
            s=item['sourcePreserved'];original=item['originalPredictionPreserved']
            crops,coverage=roi.coverage_matrix(truth,boxes,p['contract']['cropPolicy'])
            ious=np.asarray(original['iouMatrix'],np.float64)
            w,h=s['imageSize'];m=markerLookup[key(s['identity'])]
            halo=[max(0,m[0]-10),max(0,m[1]-10),min(w,m[2]+10),min(h,m[3]+10)]
            intersections=np.array([[int((t&mask).sum()) for mask in masks] for t in truth],np.int64)
            dominant=np.zeros(coverage.shape,bool)
            for i in range(len(truth)):
                for j in range(len(masks)):dominant[i,j]=prompt.seed_identity(intersections[:,j].tolist(),i)['strictlyTargetDominant']
            safety=np.array([c is not None and prompt.overlap_area(c,halo)==0 for c in crops],bool)
            valid=(coverage==1)&(ious>0)&dominant&safety[None,:]
            rawIndices=list(range(len(masks)));capped=prompt.capped_indices(conf,10)
            selected,allDedup,events=dedup.select_masks(conf,masks)
            stages={name:variant_stats(ids,coverage,ious,valid,original,roi) for name,ids in [
                ('raw_uncapped',rawIndices),('direct_cap10',capped),('dedup_before_cap10',selected)]}
            candidates=[]
            # Existing original PNG carries exactly the frozen probe RGB pixel domain.
            originalImage=next(v['image'] for v in s['variants'] if v['name']=='original')
            with Image.open(checked(originalImage)) as im:rgb=im.convert('RGB')
            if list(rgb.size)!=s['imageSize']:raise ValueError('RGB native pixel dimensions')
            owners={a['predictionIndex']-1:a['truthIndex']-1 for a in original['assignment']}
            for j,crop in enumerate(crops):
                row={'predictionIndex':j+1,'confidence':float(conf[j]),'cropBox':list(crop) if crop else None,
                    'coarseTruthIntersectionPixels':intersections[:,j].tolist(),'registeredMarkerHaloIntersectionArea':prompt.overlap_area(crop,halo) if crop else None,
                    'originalAssignedTruthIndex':owners[j]+1 if j in owners else None,
                    'nativeOriginalAssignedPromptUnique':bool(dominant[owners[j],j]) if j in owners else None}
                if crop:
                    a=np.asarray(rgb.crop(crop).resize((384,384),Image.Resampling.BILINEAR)).copy()
                    seed=np.asarray(Image.fromarray(masks[j].astype('uint8')*255).crop(crop).resize((384,384),Image.Resampling.NEAREST)).copy()
                    packed=prompt.pack_input(a,seed)
                    projected=[]
                    for t in truth:
                        target=np.asarray(Image.fromarray(t.astype('uint8')*255).crop(crop).resize((384,384),Image.Resampling.NEAREST))>0
                        projected.append(int((target&(seed>0)).sum()))
                    row.update({'packed384InputSha256':hashlib.sha256(packed.astype('<f4',copy=False).tobytes()).hexdigest(),
                        'packed384TruthSeedIntersectionPixels':projected,
                        'packed384OriginalAssignedPromptUnique':prompt.seed_identity(projected,owners[j])['strictlyTargetDominant'] if j in owners else None,
                        'packedDomain':'uint8_RGB_BILINEAR_uint8_L_NEAREST_384_then_float64_ImageNet_to_float32_CHW4_diagnostic_only'})
                candidates.append(row)
            records.append({'identity':item['identity'],'sourceGroup':item['sourceGroup'],'source':s,
                'originalPrediction':original['prediction'],'originalMatchingPreserved':original,
                'coverageMatrixNative':coverage.tolist(),'seedIoUMatrixNative':ious.tolist(),
                'registeredMarkerHalo':halo,'candidates':candidates,'stages':stages,
                'dedupSuppressionEvents':events,'deduplicatedPredictionIndicesBeforeCap':[i+1 for i in allDedup],
                'trainingUse':'prohibited'})
        aggregates={}
        for name in ('raw_uncapped','direct_cap10','dedup_before_cap10'):
            values=[r['stages'][name] for r in records]
            aggregates[name]={k:sum(v[k] for v in values) for k in ('primaryFullCoverageNails','primaryConditionalValidNails','oracleFullCoverageNails','oracleConditionalValidNails')}
            aggregates[name].update({'selectedCandidates':sum(len(v['selectedPredictionIndices']) for v in values),
                'fullyCoveredImagesPrimary':sum(v['primaryFullCoverageNails']==r['source']['completeVisibleNails'] for v,r in zip(values,records,strict=True)),
                'fullyConditionalValidImagesPrimary':sum(v['primaryConditionalValidNails']==r['source']['completeVisibleNails'] for v,r in zip(values,records,strict=True)),
                'fullyConditionalValidImagesOracle':sum(v['oracleConditionalValidNails']==r['source']['completeVisibleNails'] for v,r in zip(values,records,strict=True))})
        gates=p['contract']['geometryNecessaryGatesOnly']
        if gates!={'instanceCoverageCeilingMinimum':.9,'fullyCoveredImageFractionMinimum':.9}:
            raise ValueError('reconstruction_mismatch: geometry gate contract')
        best=aggregates['dedup_before_cap10'];need=math.ceil(counts['truthNails']*gates['instanceCoverageCeilingMinimum']);needImages=math.ceil(counts['sources']*gates['fullyCoveredImageFractionMinimum'])
        necessary=best['oracleConditionalValidNails']>=need and best['fullyConditionalValidImagesOracle']>=needImages
        full=best['primaryConditionalValidNails']==counts['truthNails']
        return {'schemaVersion':1,'execution':executionRef,'inputs':refs,'contract':p['contract'],'executionAddendum':e['addendum'],
            'ok':bool(necessary),'decision':'necessary_roi_prompt_geometry_pass_pending_full_qualification' if necessary else 'unreachable_under_frozen_roi_prompt_geometry',
            'acceptedCandidateReconstructionIdentical':True,'conclusionsAllowed':True,'counts':counts,'records':records,
            'aggregateByPolicy':aggregates,'allBudgetedPrimaryConditionalInputsValid':bool(full),
            'reachability':{'requiredConditionalCoverageCount':need,'requiredFullyCoveredImageCount':needImages,
                'budgetedConditionalCeiling':best['oracleConditionalValidNails'],
                'ceilingToRequiredRatio':best['oracleConditionalValidNails']/need,
                'scope':'necessary_exact_whole_truth_roi_prompt_geometry_only_not_final_mask_quality'},
            'packed384UniqueOriginalPrompts':sum(c.get('packed384OriginalAssignedPromptUnique') is True for r in records for c in r['candidates']),
            'suppressedCandidates':sum(len(r['dedupSuppressionEvents']) for r in records),
            'newModelCalls':0,'optimizerSteps':0,'trainingAllowed':False,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
            'limitations':['Diagnostic512 previously seen developer cohorts; not deployed640/full140/source independence.',
                'Complete ROI containment and unique prompt do not prove precise segmentation or shortcut absence.',
                'Suppression/cap outputs require native semantic review; unassigned targets are never auto-empty.',
                'Native and packed384 intersection metrics use distinct pixel domains; no rewritten historical masks.']}
    finally:
        for root in roots:guard.remove_ultralytics_label_caches(root)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execution',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--verify-report',type=Path);a=ap.parse_args()
    if a.verify_report:
        old=json.loads(a.verify_report.read_bytes());new=analyze(old['execution'])
        if new!=old:raise ValueError('reconstruction_mismatch: report')
        print(json.dumps({'ok':True,'decision':'saved_roi_replay_identical','additionalModelCalls':0}));return
    if not a.execution or not a.output:ap.error('--execution/--output required')
    try:r=analyze(bind(a.execution))
    except (ValueError,AssertionError,KeyError) as err:
        r={'schemaVersion':1,'execution':bind(a.execution),'ok':False,'decision':'reconstruction_mismatch',
            'conclusionsAllowed':False,'errorType':type(err).__name__,'message':str(err),'newModelCalls':0,'trainingAllowed':False}
    with a.output.open('xb') as f:f.write((json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'report':bind(a.output),'ok':r['ok'],'decision':r['decision'],
        'counts':r.get('counts'),'aggregateByPolicy':r.get('aggregateByPolicy'),'conclusionsAllowed':r['conclusionsAllowed']},ensure_ascii=False))
    if not r['conclusionsAllowed']:raise SystemExit(1)
if __name__=='__main__':main()
