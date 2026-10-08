"""异构整组train诊断显式记账质量排除及原图-only成员；不推理排除成员或晋升训练。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

NAMES=['original','marker_removed','blank_removed','marker_moved','blank_moved']
PAIRS=[('original',n) for n in NAMES[1:]]+[
    ('marker_removed','blank_removed'),('marker_moved','blank_moved')]
PACK_NAMES=['original','remove','blank_remove_control','move_marker','blank_move_control']
CONTRACT={'variantOrder':NAMES,'oneInferencePerVariant':True,'imgsz':512,'conf':.25,
    'iou':.7,'device':'cpu','retinaMasks':True,'rect':False,
    'usage':'heterogeneous_upstream_current_train_quality_excluded_members_accounted_stage_a_diagnostic_only',
    'unmarkedOriginalOnly':True,
    'qualityExcludedMembersNeverInferOrTrain':True,
    'neverSelectThresholdOrFormalCandidate':True}

def bind(p):
    p=Path(p).resolve();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def checked(ref):
    p=Path(ref['path']).resolve()
    if not p.is_file() or bind(p)!=ref:raise ValueError('reconstruction_mismatch: '+str(p))
    return p
def read(ref):return json.loads(checked(ref).read_bytes())
def module(ref,name):
    p=checked(ref);sys.path.insert(0,str(p.parent))
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
def key(i):return tuple(i[n] for n in ('split','fileName','imageSha256'))

def validate_scope(plan,pack,index,close):
    if plan['contract']!=CONTRACT:raise ValueError('fixed contract drift')
    if not close['ok'] or not close['inputControlsQualified']:
        raise ValueError('native control gate')
    if close['wholeGroupModelMarkerQualified'] or close['trainingAllowed'] or close['modelCalls']:
        raise ValueError('unexpected upstream promotion')
    src=plan['sources'];ids=[key(s['identity']) for s in src]
    idx={key(r['identity']):r for r in index['records']}
    if len(idx)!=len(index['records']) or len(ids)!=len(set(ids)):raise ValueError('duplicate stable identity')
    groups={s['sourceGroup'] for s in src}
    excluded=plan['excludedMembers'];excludedIds=[key(x['identity']) for x in excluded]
    if len(excludedIds)!=len(set(excludedIds)) or set(ids)&set(excludedIds):raise ValueError('duplicate or active excluded identity')
    whole={k for k,r in idx.items() if r['sourceGroup'] in groups}
    if set(ids)|set(excludedIds)!=whole:
        raise ValueError('incomplete whole source group')
    if ids!=[key(r['identity']) for r in pack['records']] or ids!=[key(r['identity']) for r in close['currentControlDecisions']]:
        raise ValueError('source order or membership drift')
    if whole!={key(r['identity']) for r in pack['entireFrozenGroupMembership']} or whole!={key(r['identity']) for r in plan['entireFrozenGroupMembership']}:
        raise ValueError('frozen group membership drift')
    if len(pack['entireFrozenGroupMembership'])!=len(whole) or len(plan['entireFrozenGroupMembership'])!=len(whole):
        raise ValueError('duplicate frozen membership')
    if plan['entireFrozenGroupMembership']!=pack['entireFrozenGroupMembership'] or pack['excludedMembers']!=close['excludedMembersPreserved']:
        raise ValueError('excluded membership binding drift')
    if set(excludedIds)!={key(r['identity']) for r in pack['excludedMembers']}:raise ValueError('excluded identity drift')
    for x in excluded:
        role=idx[key(x['identity'])]
        if x['roleEvidence']!=role or role['sourceGroup'] not in groups or x['sourceImage']!=role['sourceImage']:
            raise ValueError('excluded role or image identity drift')
        if role['identity']['split']!='train' or role['upstreamDevelopmentSplit']!='train':raise ValueError('excluded role isolation')
        if role['currentSourceDisposition']!='source_quality_excluded' or x['currentSourceDisposition']!='source_quality_excluded':
            raise ValueError('only frozen source-quality exclusions allowed')
        if role['trainingUse']!='prohibited' or role['formalTrainingApproved'] or x['trainingUse']!='prohibited' or x['inferenceUse']!='prohibited':
            raise ValueError('excluded member must never train or infer')
        if role['protectedTrainConflicts'] or not role['currentAndParentRoleMatches'] or any(r['role']!='developmentTrain' for r in role['currentAndParentRoleMatches']):
            raise ValueError('protected excluded current or parent role')
    for s,p,c in zip(src,pack['records'],close['currentControlDecisions'],strict=True):
        role=idx[key(s['identity'])]
        if s['roleEvidence']!=role or role['sourceImage']!=s['sourceImage'] or role['sourceGroup']!=s['sourceGroup']:
            raise ValueError('role or source drift')
        if s['identity']['split']!='train' or role['upstreamDevelopmentSplit']!='train':
            raise ValueError('only upstream/current train diagnostic allowed')
        if role['currentSourceDisposition'] in ('source_quality_excluded','source_marker_isolated'):
            raise ValueError('excluded or isolated member in active inputs')
        if role['trainingUse']!='prohibited' or role['formalTrainingApproved'] or s['trainingUse']!='prohibited':
            raise ValueError('unexpected training promotion')
        allowed={'developmentTrain'}
        if role['protectedTrainConflicts'] or not role['currentAndParentRoleMatches'] or any(r['role'] not in allowed for r in role['currentAndParentRoleMatches']):
            raise ValueError('protected current or parent role')
        source=p['sourcePreserved']
        if source['sourceImage']!=s['sourceImage'] or source['annotation']!=s['annotation'] or p['sourceGroup']!=s['sourceGroup']:
            raise ValueError('source/truth identity drift')
        if source['maskCount']!=s['completeVisibleNails'] or source['imageSize']!=s['imageSize']:
            raise ValueError('truth denominator or pixel domain drift')
        truth=role['currentTruth']
        if (truth['annotation']!=s['annotation'] or truth['imageSize']!=s['imageSize']
                or truth['geometry']['maskCount']!=s['completeVisibleNails'] or truth['geometry']['format']!=s['truthFormat']
                or source['sourcePreserved']['geometry']['format']!=s['truthFormat']):
            raise ValueError('authoritative truth storage domain drift')
        if c['controlRecordPreserved']!=p or c['decision']!='pass' or not c['actuallyViewed'] or c['toolScalingNotice']:
            raise ValueError('visual binding drift')
        marked=bool(source['windows'])
        if s['markerControlRequired']!=marked:raise ValueError('registered marker scope drift')
        names=NAMES if marked else ['original'];packNames=PACK_NAMES if marked else ['original']
        if list(p['variants'])!=packNames:raise ValueError('native variant scope drift')
        expected=[{'name':n,'image':p['variants'][v]} for n,v in zip(names,packNames,strict=True)]
        if s['variants']!=expected:raise ValueError('variant order or identity drift')
    expected={'wholeMembers':len(whole),'sourceImages':len(src),'completeVisibleNails':sum(s['completeVisibleNails'] for s in src),
        'excludedSources':len(excluded),'markedSources':sum(s['markerControlRequired'] for s in src),
        'originalOnlySources':sum(not s['markerControlRequired'] for s in src),
        'plannedInferenceInputs':sum(len(s['variants']) for s in src)}
    if plan['counts']!=expected:raise ValueError('inference budget or denominator drift')
    return expected['plannedInferenceInputs']

def resources(executionRef):
    e=read(executionRef);i=e['inputs']
    if checked(i['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity drift')
    for source in i.get('runtimeSources',{}).values():checked(source)
    h=module(i['predictionHelper'],'internal_val_prediction_helper')
    truth=module(i['truthHelper'],'internal_val_truth_helper')
    p=read(i['plan']);pack=read(p['inputs']['variantPack']);index=read(p['inputs']['truthRoleIndex']);close=read(p['inputs']['nativeControlCloseout'])
    n=validate_scope(p,pack,index,close)
    scope=read(p['inputs']['currentQualificationScope'])
    for name in {s['sourceGroup'] for s in p['sources']}:
        group=next(g for g in scope['groups'] if g['sourceGroup']==name)
        if group.get('prospectiveTrainingCandidateExcluded') or not group.get('wholeGroupInputControlsQualified'):
            raise ValueError('group quarantined or input controls not closed')
        if {key(s['identity']) for s in p['sources'] if s['sourceGroup']==name}!={key(s['identity']) for s in group['activeQualificationSources']}:
            raise ValueError('qualification cohort drift')
    checked(p['inputs']['frozenWeight'])
    for excluded in p['excludedMembers']:checked(excluded['sourceImage'])
    frozenCohort=read(p['inputs']['pairedInputContract'])
    if p['sources']!=frozenCohort['sources'] or p['excludedMembers']!=frozenCohort['excludedMembers'] or p['entireFrozenGroupMembership']!=frozenCohort['entireFrozenGroupMembership']:
        raise ValueError('frozen pre-inference source disposition drift')
    den=module(i['denominatorAuditor'],'internal_val_denominator_auditor')
    d=read(i['denominatorAudit'])
    if den.audit(p)!= {k:v for k,v in d.items() if k!='inputs'} or not d['ok'] or d['inputs']['plan']!=i['plan']:
        raise ValueError('reconstruction_mismatch: denominator audit')
    if 'preflight' in i:
        pre=read(i['preflight']);base=read(pre['execution'])
        if not pre['ok'] or pre['counts']!=p['counts'] or base!={**e,'inputs':{k:v for k,v in i.items() if k!='preflight'}}:
            raise ValueError('preflight-to-execution identity drift')
    guard=module(i['readOnlyGuard'],'internal_val_guard');guard.install_read_only_ultralytics_image_check()
    return e,p,pack,h,truth,guard,n

def preflight(executionRef):
    e,p,pack,h,t,g,n=resources(executionRef)
    try:
        import cv2
        import numpy as np
        from ultralytics.data.augment import LetterBox
        if h.environment()!=read(e['inputs']['environment']):raise ValueError('environment drift')
        lb=LetterBox(new_shape=(512,512),auto=False,scale_fill=False,scaleup=True,stride=32)
        rows=[]
        for s,pixel in zip(p['sources'],pack['records'],strict=True):
            checked(s['sourceImage']);truth=t.truth_masks(s)
            if len(truth)!=s['completeVisibleNails']:raise ValueError('truth count drift')
            protected=cv2.dilate(np.any(truth,axis=0).astype('uint8'),np.ones((21,21),np.uint8))>0
            raw={v['name']:cv2.imdecode(np.frombuffer(checked(v['image']).read_bytes(),np.uint8),cv2.IMREAD_COLOR) for v in s['variants']}
            if any(a is None or list(a.shape[:2][::-1])!=s['imageSize'] for a in raw.values()):raise ValueError('native dimensions')
            if any(np.any(a!=raw['original'],axis=-1)[protected].any() for a in raw.values()):raise ValueError('protected nail pixels changed')
            images={k:lb(image=a) for k,a in raw.items()}
            if any(a.shape!=(512,512,3) for a in images.values()):raise ValueError('square letterbox contract')
            delta={f'{a}__{b}':int(np.any(images[a]!=images[b],axis=-1).sum()) for a,b in PAIRS if a in images and b in images}
            rows.append({'identity':s['identity'],'sourceGroup':s['sourceGroup'],'truthNails':len(truth),
                'preprocessedImages':{k:hashlib.sha256(a.tobytes()).hexdigest() for k,a in images.items()},
                'squareInputChangedPixels':delta,'nativeProtectedPixelsChanged':0,
                'markerControlRequired':s['markerControlRequired'],
                'interventionDistinguishableAtModelInput':delta['original__marker_removed']>0 and delta['marker_moved__blank_moved']>0 if s['markerControlRequired'] else None})
        marked=[r for r in rows if r['markerControlRequired']]
        ceiling=sum(r['interventionDistinguishableAtModelInput'] for r in marked)
        ok=bool(marked) and ceiling==len(marked)
        return {'schemaVersion':1,'ok':ok,'decision':'input_contrast_reachable' if ok else 'unreachable',
            'execution':executionRef,'inputs':e['inputs'],'records':rows,'counts':p['counts'],
            'reachability':{'kind':'input_contrast_only_not_mask_quality','idealDistinguishableSourceCeiling':ceiling,
                'requiredDistinguishableSources':len(marked),'originalAllSources':len(rows),
                'originalOnlySources':len(rows)-len(marked),'currentValidatedDistinguishableSourcesBeforeThisAudit':0,
                'requiredGain':len(marked),'ceilingGainToRequiredGainRatio':ceiling/len(marked) if marked else None},
            'roleAndWholeGroupFidelity':True,'modelCalls':0,'optimizerSteps':0,'trainingAllowed':False}
    finally:g.remove_ultralytics_label_caches(Path(e['datasetRoot']))

def summarize(sources,predictions,h,t,threshold):
    rows=[]
    aggregates={n:{'sourceImages':0,'truthNails':0,'matchedNails':0,'missedNails':0,'missedImages':0,'candidateCount':0,'unmatchedPredictions':0} for n in NAMES}
    for s in sources:
        truth=t.truth_masks(s);rp={};masks={}
        for v in s['variants']:
            name=v['name'];ref=predictions[(key(s['identity']),name)]
            boxes,conf,classes,mask=h.load_prediction(ref,s['imageSize']);masks[name]=mask
            match=h.match_masks(mask,truth,threshold)
            rp[name]={'prediction':ref,'boxesXyxy':boxes.tolist(),'confidence':conf.tolist(),'classes':classes.tolist(),'instanceCount':len(mask),**match}
            count={'sourceImages':1,'truthNails':len(truth),'matchedNails':len(match['matches']),
                'missedNails':len(match['missedTruthIndices']),'missedImages':int(bool(match['missedTruthIndices'])),
                'candidateCount':len(mask),'unmatchedPredictions':len(match['unmatchedPredictionIndices'])}
            for k,value in count.items():aggregates[name][k]+=value
        comparisons={f'{a}__{b}':h.comparison(rp[a],rp[b],masks[a],masks[b]) for a,b in PAIRS if a in rp and b in rp}
        rows.append({'identity':s['identity'],'sourceGroup':s['sourceGroup'],'sourceNails':len(truth),
            'predictions':rp,'comparisons':comparisons,'trainingUse':'prohibited'})
    summary={}
    for a,b in PAIRS:
        name=f'{a}__{b}';vs=[r['comparisons'][name] for r in rows if name in r['comparisons']]
        summary[name]={'sourcesCompared':len(vs),'sourcesWithCandidateCountChange':sum(v['candidateCountDelta']!=0 for v in vs),
            'sourcesWithTruthMatchMigration':sum(bool(v['newMissedTruthIndices'] or v['recoveredTruthIndices']) for v in vs),
            'sourcesWithAnyUnionMaskDifference':sum(v['unionSymmetricDifferencePixels']!=0 for v in vs),
            'totalUnionDifferentPixels':sum(v['unionSymmetricDifferencePixels'] for v in vs)}
    # No numerical quality or small-sample relative promotion gate is introduced.
    pattern={'candidateOrMatchMigrationSources':sum(any(v['candidateCountDelta'] or v['newMissedTruthIndices'] or v['recoveredTruthIndices'] for v in r['comparisons'].values()) for r in rows),
        'pairedCandidateOrMatchMigrationSources':sum(any(r['comparisons'][name]['candidateCountDelta'] or r['comparisons'][name]['newMissedTruthIndices'] or r['comparisons'][name]['recoveredTruthIndices'] for name in ('marker_removed__blank_removed','marker_moved__blank_moved') if name in r['comparisons']) for r in rows),
        'anyMaskSensitivitySources':sum(any(v['unionSymmetricDifferencePixels'] for v in r['comparisons'].values()) for r in rows)}
    pattern['interpretation']='paired_candidate_or_match_migration_context_not_excluded' if pattern['pairedCandidateOrMatchMigrationSources'] else 'mask_sensitivity_only_not_causal_proof' if pattern['anyMaskSensitivitySources'] else 'no_detected_effect_not_shortcut_absence'
    return rows,aggregates,summary,pattern

def reconstruct(executionRef,output):
    e,p,pack,h,t,g,n=resources(executionRef)
    try:
        claimRef=read(bind(output/'budget-claim-reference.json'))['claim'];claim=read(claimRef)
        if claim!={'execution':executionRef,'plannedInputs':n,'resumingAllowed':False}:raise ValueError('budget claim drift')
        events=[]
        for seq,path in enumerate(sorted((output/'events').glob('*.json')),1):
            d=json.loads(path.read_bytes())
            if d['sequence']!=seq or path.name!=f'{seq:06d}.json':raise ValueError('event gap')
            events.append(d['value'])
        if len(events)!=n*2+2 or events[0]!={'phase':'prepared','completedInputs':0,'attemptedInputs':0} or events[-1]!={'phase':'complete','completedInputs':n,'attemptedInputs':n}:
            raise ValueError('incomplete inference budget')
        predictions={};number=0
        for s in p['sources']:
            checked(s['sourceImage']);checked(s['annotation'])
            for v in s['variants']:
                number+=1;started,done=events[2*number-1:2*number+1]
                for ev in (started,done):
                    if ev['inputIndex']!=number or ev['identity']!=s['identity'] or ev['variant']!=v['name'] or ev['input']!=v['image'] or ev['attemptedInputs']!=number:
                        raise ValueError('event input identity drift')
                if started['phase']!='input_started' or done['phase']!='input_complete' or started['completedInputs']!=number-1 or done['completedInputs']!=number:
                    raise ValueError('confirmation drift')
                if checked(done['prediction'])!=(output/'predictions'/f'{number:03d}-{v["name"]}.npz').resolve():raise ValueError('prediction slot drift')
                checked(v['image']);predictions[(key(s['identity']),v['name'])]=done['prediction']
        rows,agg,summary,pattern=summarize(p['sources'],predictions,h,t,e['controls']['truthIoUThreshold'])
        markedOriginal={k:sum(({ 'sourceImages':1,'truthNails':r['sourceNails'],
            'matchedNails':len(r['predictions']['original']['matches']),
            'missedNails':len(r['predictions']['original']['missedTruthIndices']),
            'missedImages':int(bool(r['predictions']['original']['missedTruthIndices'])),
            'candidateCount':r['predictions']['original']['instanceCount'],
            'unmatchedPredictions':len(r['predictions']['original']['unmatchedPredictionIndices'])}[k])
            for r in rows if len(r['predictions'])>1) for k in agg['original']}
        return {'schemaVersion':1,'ok':True,'decision':'heterogeneous_quality_accounted_train_stage_a_marker_sensitivity_diagnostic_only',
            'execution':executionRef,'inputs':e['inputs'],'contract':p['contract'],'records':rows,
            'counts':{**p['counts'],'confirmedInferenceInputs':n,'progressEvents':len(events)},
            'aggregateByVariant':agg,'markedSourceOriginalAggregate':markedOriginal,
            'comparisonSummary':summary,'diagnosticPattern':pattern,'recordedModelCalls':n,'optimizerSteps':0,
            'excludedMembersPreserved':p['excludedMembers'],'excludedModelCalls':0,
            'wholeSourceGroupsApproved':False,'independentShortcutExclusionProven':False,
            'dualPathStageBQualityEvaluated':False,'trainingAllowed':False,'formalTrainingApprovedImages':0,
            'full30PilotAllowed':False,'formalIndependentValAllowed':False,'currentValMayReturnToTrain':False,
            'limitations':['Previously trained Stage A weight at diagnostic512; not deployment640 or new Stage B quality.',
                'No effect does not prove shortcut absence; mask sensitivity does not prove semantic dependence.',
                'Unmatched predictions are not automatically false positives; preserve all one-to-one assignments.',
                'Source and local context confounds persist; no relative quality promotion or threshold selection.']}
    finally:g.remove_ultralytics_label_caches(Path(e['datasetRoot']))

def run(path):
    ref=bind(path);e,p,pack,h,t,g,n=resources(ref)
    output=Path(e['outputRoot']);completed=attempted=seq=0;claimed=False;start=time.monotonic()
    try:
        if h.environment()!=read(e['inputs']['environment']):raise ValueError('environment drift')
        pre=read(e['inputs']['preflight'])
        if preflight(pre['execution'])!=pre or not pre['ok']:raise ValueError('reconstruction_mismatch: preflight')
        if e['controls']!={'truthIoUThreshold':.75,'cpuThreads':4,'seed':0,'maxDet':300}:raise ValueError('execution controls drift')
        if output.exists():raise FileExistsError(output)
        claimPath=checked(e['inputs']['plan']).parent/('heterogeneous-quality-accounted-train-marker-probe-budget-'+e['inputs']['plan']['sha256']+'.json')
        h.durable_new(claimPath,{'execution':ref,'plannedInputs':n,'resumingAllowed':False});claimed=True
        output.mkdir();(output/'events').mkdir();(output/'predictions').mkdir()
        h.durable_new(output/'budget-claim-reference.json',{'claim':bind(claimPath)})
        seq+=1;h.journal(output/'events',seq,{'phase':'prepared','completedInputs':0,'attemptedInputs':0})
        import torch
        import cv2
        import numpy as np
        from ultralytics import YOLO
        torch.set_num_threads(4);torch.manual_seed(0)
        model=YOLO(str(checked(p['inputs']['frozenWeight'])))
        for s in p['sources']:
            for v in s['variants']:
                attempted+=1;ev={'inputIndex':attempted,'identity':s['identity'],'variant':v['name'],'input':v['image']}
                seq+=1;h.journal(output/'events',seq,{'phase':'input_started','completedInputs':completed,'attemptedInputs':attempted,**ev})
                im=cv2.imdecode(np.frombuffer(checked(v['image']).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                if im is None or list(im.shape[:2][::-1])!=s['imageSize']:raise ValueError('native input dimensions')
                r=model.predict(source=im,imgsz=512,conf=.25,iou=.7,device='cpu',retina_masks=True,rect=False,
                    max_det=300,verbose=False,save=False,stream=False)[0]
                boxes=r.boxes.xyxy.cpu().numpy().astype(np.float32);conf=r.boxes.conf.cpu().numpy().astype(np.float32);classes=r.boxes.cls.cpu().numpy().astype(np.float32)
                if r.masks is None:
                    if len(boxes):raise ValueError('boxes without segmentation masks')
                    masks=np.zeros((0,*im.shape[:2]),bool)
                else:masks=r.masks.data.cpu().numpy()>.5
                if masks.shape!=(len(boxes),*im.shape[:2]):raise ValueError('native mask dimensions')
                prediction=h.save_prediction(output/'predictions'/f'{attempted:03d}-{v["name"]}.npz',boxes,conf,classes,masks)
                completed+=1;seq+=1;h.journal(output/'events',seq,{'phase':'input_complete','completedInputs':completed,'attemptedInputs':attempted,'prediction':prediction,**ev})
            print(json.dumps({'confirmedInputs':completed,'plannedInputs':n,'fileName':s['identity']['fileName']}),flush=True)
        seq+=1;h.journal(output/'events',seq,{'phase':'complete','completedInputs':completed,'attemptedInputs':attempted})
        report=reconstruct(ref,output);h.durable_new(output/'model-probe-report.json',report)
        h.durable_new(output/'terminal.json',{'phase':'complete','completedInputs':completed,'attemptedInputs':attempted,
            'wallSeconds':time.monotonic()-start,'report':bind(output/'model-probe-report.json')})
        print(json.dumps({'report':bind(output/'model-probe-report.json'),'counts':report['counts'],'diagnosticPattern':report['diagnosticPattern']}),flush=True)
    except BaseException as err:
        if claimed:
            failure={'phase':'aborted','completedInputs':completed,'attemptedInputs':attempted,'exceptionType':type(err).__name__,
                'message':str(err),'execution':ref,'resumingAllowed':False}
            h.durable_new(output/'exception-terminal.json' if output.is_dir() else Path(str(output)+'-exception-terminal.json'),failure)
        raise
    finally:g.remove_ultralytics_label_caches(Path(e['datasetRoot']))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execution',type=Path);ap.add_argument('--preflight',type=Path)
    ap.add_argument('--output',type=Path);ap.add_argument('--verify-report',type=Path)
    a=ap.parse_args()
    if a.verify_report:
        old=json.loads(a.verify_report.read_bytes())
        new=preflight(old['execution']) if old['decision'] in ('input_contrast_reachable','unreachable') else reconstruct(old['execution'],a.verify_report.parent)
        if new!=old:raise ValueError('reconstruction_mismatch: saved report')
        print(json.dumps({'ok':True,'decision':'saved_report_replay_identical','additionalModelCalls':0}));return
    if a.preflight:
        if not a.output:ap.error('--output required')
        result=preflight(bind(a.preflight));e=read(bind(a.preflight));h=module(e['inputs']['predictionHelper'],'preflight_writer')
        h.durable_new(a.output,result);print(json.dumps({'report':bind(a.output),'ok':result['ok'],'reachability':result['reachability']}));return
    if not a.execution:ap.error('--execution or --preflight required')
    run(a.execution)
if __name__=='__main__':main()
