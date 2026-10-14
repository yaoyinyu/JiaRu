"""独立重放原质量/事件，并逐输入核对identity像素及基线完整RNG轨迹。"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
def module(path,name):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','control_verify_data')
c=module(HERE/'train-reviewed-stage-b-augmentation-control.py','control_verify_training')
base=module(HERE/'verify-reviewed-stage-b-normal-training.py','control_verify_base')
require=c.require

def validate_control_trace(ledger,baseline_ledger,plan,rows):
    events=[e for e in ledger if e['phase']=='training_input_started']
    old=[e for e in baseline_ledger if e['phase']=='training_input_started']
    require(len(events)==len(old)==plan['budget']['augmentedTrainingInputs'],'full training trace')
    pixel_map={json.dumps(r['candidateIdentity'],sort_keys=True):r['nativePixelSha256'] for r in rows}
    require(len(pixel_map)==len(rows)==len(plan['candidateIdentities']),'unique stable native identity')
    rng=np.random.default_rng(plan['control']['rngSeed']);index=0
    for epoch in range(plan['budget']['epochs']):
        for ordinal in rng.permutation(len(rows)).tolist():
            draw=c.choice(rng);row=rows[ordinal];actual=events[index];previous=old[index];index+=1
            require(actual['epoch']==previous['epoch']==epoch+1 and actual['candidateIdentity']==previous['candidateIdentity']==row['candidateIdentity'],'exact baseline epoch candidate order')
            require(actual['augmentation']==previous['augmentation']==draw,'all baseline RNG choices exactly consumed')
            require(actual['augmentationApplied']==c.IDENTITY and actual['sampledAugmentationNotApplied'] is True,'identity applied')
            require(actual['appliedNativePixelSha256']==pixel_map[json.dumps(row['candidateIdentity'],sort_keys=True)],'actual applied RGB/coarse/target exact native bytes')
    return {'trainingInputs':index,'allEpochOrdersAndSampledChoicesExactlyBaseline':True,'allAppliedNativeRgbCoarseTargetBytesUnchanged':True,'onlyWholeInputAugmentationChanged':True}

def verify_preflight(path):
    report=d.read(d.bind(path));plan=d.read(report['plan']);old=d.read(plan['inputs']['baselineReplay']);training=d.read(old['training'])
    initial=d.read(training['inputs']['preflight']);result=base.verify_preflight(path)
    require(report['initialTensorSha256']==initial['initialTensorSha256'],'exact baseline fresh initialization')
    return {'ok':True,'controlPreflight':result,'baselineInitialTensorHashesExactlySame':True,'newModelCalls':0,'optimizerSteps':0,'formalReleaseAllowed':False,'productHold':True}

def verify(path):
    report=d.read(d.bind(path));plan=d.read(report['inputs']['plan']);result=base.verify(path)
    p,data,rows,net,band,metric,guard,cleanup=c.resources(Path(report['inputs']['plan']['path']))
    try:
        old_audit=d.read(plan['inputs']['baselineReplay']);old=d.read(old_audit['training']);old_root=Path(old_audit['training']['path']).parent
        old_ledger,old_bindings=base.events(old_root);require(base.event_digest(old_bindings)==old_audit['eventFilesSha256'],'baseline all immutable events unchanged')
        ledger,bindings=base.events(path.parent);trace=validate_control_trace(ledger,old_ledger,plan,rows)
        pre=verify_preflight(Path(report['inputs']['preflight']['path']))
        require(not old['trainQualityGatePassed'],'baseline failure kept')
        return {'schemaVersion':1,'ok':True,'decision':'full_no_augmentation_control_reconstructed_absolute_quality_separate',
            'training':d.bind(path),'verifier':d.bind(Path(__file__)),'baseAudit':result,'controlPreflight':pre,'controlTrace':trace,
            'baselineReplay':plan['inputs']['baselineReplay'],'metrics':result['metrics'],'perCandidate':result['perCandidate'],
            'trainQualityGatePassed':result['trainQualityGatePassed'],'counts':result['counts'],
            'oldNormalModelStillFailed':True,'oldGradientReconstructionStillFailed':True,'newModelCalls':0,'optimizerSteps':0,
            'newChatImageInputs':0,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for root in cleanup:guard.remove_ultralytics_label_caches(Path(root))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preflight',type=Path);p.add_argument('--report',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    if a.verify_report:
        saved=d.read(d.bind(a.verify_report));result=verify(Path(saved['training']['path']));require(a.verify_report.read_bytes()==d.raw(result),'complete control audit bytes')
    else:
        result=verify_preflight(a.preflight.resolve()) if a.preflight else verify(a.report.resolve());d.new(a.output.resolve(),result)
    print(json.dumps({'ok':True,'trainQualityGatePassed':result.get('trainQualityGatePassed'),'counts':result.get('counts'),'metrics':result.get('metrics')},ensure_ascii=False))
