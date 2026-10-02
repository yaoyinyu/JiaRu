"""重放标记对照并计算零推理覆盖上限；不以局部可用冒充训练或捷径通过。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(ref):
    p=Path(ref['path']).resolve()
    if not p.is_file() or sha(p)!=ref['sha256']:raise ValueError('reconstruction_mismatch: binding '+str(p))
    return p
def read(ref):return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref,name):
    p=checked(ref);sys.path.insert(0,str(p.parent))
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def summarize(records,decisions,required_count):
    if required_count<=0:raise ValueError('reconstruction_mismatch: empty cohort')
    if len(records)!=required_count or [r['ordinal'] for r in records]!=[d['ordinal'] for d in decisions]:
        raise ValueError('reconstruction_mismatch: full cohort denominator')
    if len({r['ordinal'] for r in records})!=required_count:raise ValueError('reconstruction_mismatch: duplicate source')
    accepted=[];blocked=[];crop_safe=[];crop_unsafe=[]
    for r,d in zip(records,decisions,strict=True):
        for key in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails'):
            if r[key]!=d[key]:raise ValueError('reconstruction_mismatch: review identity')
        if d['trainingUse']!='prohibited' or d['viewedPages']!=r['reviewPages']:
            raise ValueError('reconstruction_mismatch: view evidence or role')
        if d['localControlsDecision']=='diagnostic_candidate':
            if d['failedVariants']:raise ValueError('failed local control cannot pass')
            accepted.append(r['ordinal'])
        elif d['localControlsDecision']=='rework':
            if not d['failedVariants'] or not d['reason']:raise ValueError('rework needs specific failed variant')
            if any(name not in r['variants'] for name in d['failedVariants']):raise ValueError('unknown failed variant')
            blocked.append({'ordinal':r['ordinal'],'failedVariants':d['failedVariants'],'reason':d['reason']})
        else:raise ValueError('unknown local-control visual disposition')
        p=r['variantPixelEvidence']['crop12_native']
        eligible=p['nailPixelsLost']==0 and p['protectedPixelsLost']==0
        if eligible!=r['cropDiagnosticEligible']:raise ValueError('reconstruction_mismatch: crop protection gate')
        expected='pixel_preserving_crop_candidate_context_confounding' if eligible else 'reject_protected_pixel_loss'
        if d['cropDecision']!=expected:raise ValueError('reconstruction_mismatch: crop visual decision')
        if eligible:crop_safe.append(r['ordinal'])
        else:crop_unsafe.append({'ordinal':r['ordinal'],'nailPixelsLost':p['nailPixelsLost'],'protectedPixelsLost':p['protectedPixelsLost']})
    return {'acceptedOrdinals':accepted,'blocked':blocked,'cropSafeOrdinals':crop_safe,'cropUnsafe':crop_unsafe,
            'ceiling':{'maxInterpretableLocalSourceFraction':len(accepted)/required_count,
                       'requiredFraction':1.0,'fractionOfRequiredCoverage':len(accepted)/required_count,
                       'missingSources':required_count-len(accepted)}}

def audit(execution_ref):
    execution=read(execution_ref);inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity mismatch')
    guard=module(inputs['readOnlyGuard'],'marker_audit_guard');guard.install_read_only_ultralytics_image_check()
    from PIL import Image,ImageDraw
    try:
        pack=read(inputs['variantPack']);visual=read(inputs['visualDecisions']);blur=read(inputs['blurReview'])
        source_visual=read(visual['inputs']['fullSourceAndMaskReview'])
        scope=read(pack['inputs']['scope'])
        for doc in (pack,visual):
            if any(doc[k] for k in ('modelCalls','optimizerSteps','formalTrainingApprovedImages','trainingAllowed','full30PilotAllowed')):
                raise ValueError('unexpected model use or training promotion')
        if visual['inputs']['variantPack']!=inputs['variantPack'] or visual['inputs']['blurReview']!=inputs['blurReview']:
            raise ValueError('visual pack binding mismatch')
        if blur['inputs']['variantPack']!=inputs['variantPack']:raise ValueError('blur pack binding mismatch')
        builder=module(pack['inputs']['runnerSource'],'marker_builder')
        if builder.build(pack['execution'],checked(inputs['variantPack']).parent,verify=True)!=pack:raise ValueError('variant replay mismatch')
        if [r['ordinal'] for r in pack['records']]!=[s['ordinal'] for s in scope['sources']]:raise ValueError('frozen source order changed')
        result=summarize(pack['records'],visual['records'],scope['counts']['sourceImages'])
        old={r['ordinal']:r for r in source_visual['sourceDispositions']};blur_pages={p['ordinal']:p for p in blur['pages']}
        pixel_slots=0
        for r,d in zip(pack['records'],visual['records'],strict=True):
            for key in ('fileName','sourceImage','annotation','completeVisibleNails'):
                if old[r['ordinal']][key]!=r[key]:raise ValueError('original full source/mask review provenance changed')
            if old[r['ordinal']]['decision']!='mask_visual_pass_pending_role_and_marker_gates':raise ValueError('original mask review not approved')
            for ref in d['viewedPages']+[d['viewedBlurPage']]:checked(ref)
            if d['viewedBlurPage']!=blur_pages[r['ordinal']]['page']:raise ValueError('blur review page mismatch')
            corner=r['cornerBox'];names=['original','remove','blank_remove_control','occlude','blank_occlude_control','move_marker','blur_corner']
            for offset,ref in zip((0,4),r['reviewPages'],strict=True):
                entries=[]
                for key in names[offset:offset+4]:
                    with Image.open(checked(r['variants'][key])) as im:entries.append((key,im.convert('RGB').crop(corner)))
                if builder.panel(checked(ref).parent,Path(ref['path']).stem,entries,True)!=ref:raise ValueError('corner panel replay mismatch')
                pixel_slots+=len(entries)
            bp=blur_pages[r['ordinal']];entries=[]
            for key in ('original','blur_corner'):
                with Image.open(checked(r['variants'][key])) as im:entries.append((key,im.convert('RGB').crop(bp['box'])))
            if builder.panel(checked(bp['page']).parent,Path(bp['page']['path']).stem,entries,True)!=bp['page']:raise ValueError('whole blur region replay mismatch')
            pixel_slots+=2
        return {'schemaVersion':1,'ok':True,'decision':'unreachable_current_local_controls_repair_required' if result['blocked'] else 'local_control_visual_coverage_reachable_model_probe_pending',
                'execution':execution_ref,'inputs':inputs,'scope':pack['inputs']['scope'],**result,
                'counts':{**pack['counts'],'variantsPerSource':8,'variantImages':len(pack['records'])*8,
                          'reviewedChangedRegionPages':len(pack['records'])*3,'reconstructedNativePanelSlots':pixel_slots,
                          'localDiagnosticCandidates':len(result['acceptedOrdinals']),'localReworkImages':len(result['blocked']),
                          'cropProtectedSafeImages':len(result['cropSafeOrdinals']),
                          'newTrainingApprovedImages':0},
                'localPixelProtection':{'nailPixelsChanged':0,'protectedPixelsChanged':0},
                'limitations':['crop_and_large_blur_change_background_context_not_causal_shortcut_proof',
                               'matched_blank_relocation_control_missing','full_source_review_reused_same_bound_original_identity',
                               'whole_source_group_marker_gate_and_source_parent_independence_pending'],
                'modelAblationAllowed':False,'modelAblationComplete':False,'modelCalls':0,'optimizerSteps':0,
                'formalTrainingApprovedImages':0,'trainingAllowed':False,'full30PilotAllowed':False}
    finally:guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))

def main():
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    if args.verify_report:
        report=json.loads(args.verify_report.read_text(encoding='utf-8'))
        if audit(report['execution'])!=report:raise ValueError('usability report reconstruction mismatch')
        print(json.dumps({'ok':True,'decision':'marker_usability_replay_identical'}))
    else:
        if not args.execution or not args.output:p.error('--execution and --output required')
        report=audit(bind(args.execution))
        with args.output.open('x',encoding='utf-8') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('ok','decision','counts','ceiling','cropUnsafe')}))
if __name__=='__main__':main()
