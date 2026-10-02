"""版本化局部背景替换及匹配移位控制；原像素视觉批准不能代替模型消融。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import hashlib
import importlib.util

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(ref):
    p=Path(ref['path']).resolve()
    if not p.is_file() or sha(p)!=ref['sha256']:raise ValueError('reconstruction_mismatch: '+str(p))
    return p
def read(ref):return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref,name):
    p=checked(ref);sys.path.insert(0,str(p.parent))
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def replace_background(arr,target,donor):
    """只在目标框内复制邻近背景，以外围边界拟合线性色差；不平滑源图。"""
    import numpy as np
    x1,y1,x2,y2=target;bx1,by1,bx2,by2=donor
    h,w=arr.shape[:2]
    if not(0<x1<x2<w and 0<y1<y2<h and 0<=bx1<bx2<=w and 0<=by1<by2<=h):raise ValueError('patch outside source')
    if (x2-x1,y2-y1)!=(bx2-bx1,by2-by1):raise ValueError('background patch size mismatch')
    if min(x2,bx2)>max(x1,bx1) and min(y2,by2)>max(y1,by1):raise ValueError('background patch overlaps target')
    patch=arr[by1:by2,bx1:bx2].astype(np.float64)
    ph,pw=patch.shape[:2];xx,yy=np.meshgrid(np.linspace(-1,1,pw),np.linspace(-1,1,ph))
    design=np.stack([np.ones_like(xx),xx,yy],axis=-1)
    indices=[(0,x) for x in range(pw)]+[(ph-1,x) for x in range(pw)]+[(y,0) for y in range(1,ph-1)]+[(y,pw-1) for y in range(1,ph-1)]
    exterior=np.concatenate([arr[y1-1,x1:x2],arr[y2,x1:x2],arr[y1+1:y2-1,x1-1],arr[y1+1:y2-1,x2]],axis=0).astype(np.float64)
    matrix=np.array([design[y,x] for y,x in indices]);sample=np.array([patch[y,x] for y,x in indices])
    coefficients=np.linalg.lstsq(matrix,exterior-sample,rcond=None)[0]
    replacement=np.clip(np.rint(patch+design@coefficients),0,255).astype(np.uint8)
    result=arr.copy();result[y1:y2,x1:x2]=replacement
    return result

def relocate(base,original,donor,destination):
    x1,y1,x2,y2=donor;mx1,my1,mx2,my2=destination
    if (x2-x1,y2-y1)!=(mx2-mx1,my2-my1):raise ValueError('relocation size mismatch')
    h,w=base.shape[:2]
    if not (0<=x1<x2<=w and 0<=y1<y2<=h and 0<=mx1<mx2<=w and 0<=my1<my2<=h):raise ValueError('relocation outside source')
    result=base.copy();result[my1:my2,mx1:mx2]=original[y1:y2,x1:x2];return result

def visual_summary(records,decisions):
    if not records or [r['ordinal'] for r in records]!=[r['ordinal'] for r in decisions] or len({r['ordinal'] for r in records})!=len(records):raise ValueError('reconstruction_mismatch: full cohort')
    accepted=[];failed=[]
    for r,d in zip(records,decisions,strict=True):
        for k in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails'):
            if r[k]!=d[k]:raise ValueError('reconstruction_mismatch: source identity')
        if d['viewedPages']!=r['reviewPages'] or d['trainingUse']!='prohibited':raise ValueError('reconstruction_mismatch: review coverage or role')
        if d['decision']=='local_controls_visual_pass':
            if d['failedVariants']:raise ValueError('failed variant cannot pass')
            accepted.append(r['ordinal'])
        elif d['decision']=='rework':
            if not d['failedVariants'] or not d['reason'] or any(k not in r['variants'] for k in d['failedVariants']):raise ValueError('invalid rework')
            failed.append({'ordinal':r['ordinal'],'failedVariants':d['failedVariants'],'reason':d['reason']})
        else:raise ValueError('unknown decision')
    return {'acceptedOrdinals':accepted,'blocked':failed,'ceiling':{'maxInterpretableSourceFraction':len(accepted)/len(records),'requiredFraction':1.0,'fractionOfRequiredCoverage':len(accepted)/len(records),'missingSources':len(failed)}}

def build(execution_ref,output,verify=False):
    execution=read(execution_ref);inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity mismatch')
    guard=module(inputs['readOnlyGuard'],'matched_marker_guard');guard.install_read_only_ultralytics_image_check()
    from PIL import Image
    import numpy as np
    import cv2
    try:
        scope=read(inputs['repairScope']);old=read(scope['inputs']['variantPack']);old_verdict=read(scope['inputs']['usability'])
        helper=module(old['inputs']['runnerSource'],'old_marker_builder')
        if helper.build(old['execution'],checked(scope['inputs']['variantPack']).parent,verify=True)!=old:raise ValueError('reconstruction_mismatch: original variant pack')
        baseline=read(scope['inputs']['manualMaskDisposition'])
        truth={d['ordinal']:d for d in baseline['sourceDispositions']}
        if [r['ordinal'] for r in old['records']]!=[s['ordinal'] for s in scope['sources']]:raise ValueError('full source order changed')
        if old_verdict['decision']!='unreachable_current_local_controls_repair_required':raise ValueError('wrong historical baseline')
        repair_ordinals=[s['ordinal'] for s in scope['repairTargets']]
        if not repair_ordinals or len(set(repair_ordinals))!=len(repair_ordinals) or not set(repair_ordinals).issubset({r['ordinal'] for r in old['records']}):raise ValueError('invalid repair set')
        if not verify:output.mkdir(parents=True,exist_ok=False)
        records=[];generated=0;slots=0
        for s,r in zip(scope['sources'],old['records'],strict=True):
            for k in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails'):
                if s[k]!=r[k] or s[k]!=truth[s['ordinal']][k]:raise ValueError('reviewed truth drift')
            if s['trainingUse']!='prohibited' or s['currentSplit']!='train':raise ValueError('unexpected source role')
            checked(s['sourceLabel']);doc=read(s['annotation'])
            if len(doc['annotations'])!=s['completeVisibleNails']:raise ValueError('nail denominator mismatch')
            with Image.open(checked(s['sourceImage'])) as opened:im=opened.convert('RGB')
            arr=np.asarray(im);nails=helper.raster(doc,im.size)
            protected=cv2.dilate(nails.astype(np.uint8),np.ones((21,21),np.uint8))>0
            helper.validate_boxes(r,*im.size,protected)
            badge,blank,destination=[r[k] for k in ('badgeBox','blankControlBox','relocationBox')]
            refs=dict(r['variants']);images={}
            for name,ref in refs.items():
                with Image.open(checked(ref)) as opened:images[name]=opened.convert('RGB')
            removal_mode='reuse_identically_bound_prior_local_controls'
            if s['ordinal'] in repair_ordinals:
                removed=replace_background(arr,badge,blank)
                blank_removed=replace_background(arr,blank,destination)
                moved=relocate(removed,arr,badge,destination)
                for name,pixels in [('remove',removed),('blank_remove_control',blank_removed),('move_marker',moved)]:
                    images[name]=Image.fromarray(pixels);refs[name]=helper.png(output,f"source-{s['ordinal']:03d}-{name}-repaired",images[name],verify);generated+=1
                removal_mode='donor_patch_with_exterior_fitted_affine_color_plane_v1'
            removed=np.asarray(images['remove'])
            blank_moved=relocate(removed,arr,blank,destination)
            images['blank_move_control']=Image.fromarray(blank_moved)
            refs['blank_move_control']=helper.png(output,f"source-{s['ordinal']:03d}-blank-move-control",images['blank_move_control'],verify);generated+=1
            metrics={};local_names=['remove','blank_remove_control','occlude','blank_occlude_control','move_marker','blank_move_control']
            for name in local_names:
                changed=np.any(np.asarray(images[name])!=arr,axis=-1)
                nc=int((changed&nails).sum());pc=int((changed&protected).sum())
                if nc or pc:raise ValueError('local control changes protected pixels')
                metrics[name]={'changedPixels':int(changed.sum()),'nailPixelsChanged':nc,'protectedPixelsChanged':pc}
            marker_moved=np.asarray(images['move_marker']);delta=np.any(marker_moved!=blank_moved,axis=-1)
            x1,y1,x2,y2=destination;allowed=np.zeros(delta.shape,bool);allowed[y1:y2,x1:x2]=True
            if (delta&~allowed).any() or not delta.any():raise ValueError('matched relocation pair fidelity failed')
            names=['original','remove','blank_remove_control','occlude','blank_occlude_control','move_marker','blank_move_control']
            pages=[]
            for offset in (0,4):
                entries=[(name,images[name].crop(r['cornerBox'])) for name in names[offset:offset+4]]
                pages.append(helper.panel(output,f"source-{s['ordinal']:03d}-matched-controls-{offset}",entries,verify));slots+=len(entries)
            records.append({**s,'imageSize':r['imageSize'],**{k:r[k] for k in ('badgeBox','blankControlBox','relocationBox','cornerBox')},
                            'variants':refs,'localPixelEvidence':metrics,'reviewPages':pages,'removalMode':removal_mode,
                            'matchedRelocation':{'sameRemovalBase':True,'sameDestination':destination,'samePatchSize':True,'pairDifferenceOutsideDestinationPixels':0,'pairDifferentPixels':int(delta.sum()),
                                                 'markerDonor':badge,'blankDonor':blank,'contextLimitation':'Original blank and marker patches may differ in local background texture; matched-input probe remains diagnostic, not definitive causal proof.'},
                            'cropEvidenceUnchanged':r['variantPixelEvidence']['crop12_native'],'cropDiagnosticEligible':r['cropDiagnosticEligible'],
                            'trainingUse':'prohibited'})
        if len(records)!=scope['counts']['sourceImages'] or sum(r['completeVisibleNails'] for r in records)!=scope['counts']['completeVisibleNails']:raise ValueError('scope denominator mismatch')
        return {'schemaVersion':1,'ok':True,'decision':'matched_marker_controls_pending_visual_review','execution':execution_ref,'inputs':inputs,
                'records':records,'counts':{**scope['counts'],'variantsPerSource':9,'boundVariantImages':len(records)*9,'newVariantImages':generated,'nativeReviewPages':len(records)*2,'nativePanelSlots':slots},
                'modelCalls':0,'optimizerSteps':0,'formalTrainingApprovedImages':0,'trainingAllowed':False,'full30PilotAllowed':False,'modelAblationAllowed':False}
    finally:guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))

def audit(execution_ref):
    execution=read(execution_ref);inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve():raise ValueError('audit runner identity mismatch')
    report=read(inputs['variantPack']);visual=read(inputs['visualDecisions'])
    if visual['inputs']['variantPack']!=inputs['variantPack']:raise ValueError('visual pack binding mismatch')
    if build(report['execution'],checked(inputs['variantPack']).parent,verify=True)!=report:raise ValueError('reconstruction_mismatch: matched variant report')
    result=visual_summary(report['records'],visual['records'])
    for d in (report,visual):
        if any(d[k] for k in ('modelCalls','optimizerSteps','formalTrainingApprovedImages','trainingAllowed','full30PilotAllowed')):raise ValueError('unexpected use or promotion')
    return {'schemaVersion':1,'ok':True,'decision':'unreachable_matched_controls_repair_required' if result['blocked'] else 'matched_input_coverage_reachable_preregister_diagnostic_model_probe',
            'execution':execution_ref,'inputs':inputs,**result,'counts':{**report['counts'],'visuallyApprovedSources':len(result['acceptedOrdinals'])},
            'limitations':['Background_patch_texture_is_a_residual_confound','No_model_shortcut_or_whole_source_group_verdict','Parent_independence_and_remaining_full_split_pending'],
            'diagnosticProbePrerequisitesMet':not result['blocked'],'modelAblationAllowed':False,'modelCalls':0,'optimizerSteps':0,
            'formalTrainingApprovedImages':0,'trainingAllowed':False,'full30PilotAllowed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    if args.verify_report:
        doc=json.loads(args.verify_report.read_text(encoding='utf-8'))
        actual=audit(doc['execution']) if 'diagnosticProbePrerequisitesMet' in doc else build(doc['execution'],args.verify_report.parent,True)
        if actual!=doc:raise ValueError('reconstruction_mismatch: report')
        print(json.dumps({'ok':True,'decision':'matched_controls_replay_identical'}));return
    if not args.execution or not args.output:p.error('--execution and --output required')
    doc=audit(bind(args.execution)) if args.audit else build(bind(args.execution),args.output)
    output=args.output if args.audit else args.output/'matched-controls-report.json'
    with output.open('x',encoding='utf-8') as f:f.write(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:doc[k] for k in ('ok','decision','counts')}))
if __name__=='__main__':main()
