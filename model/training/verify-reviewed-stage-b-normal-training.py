"""只读重建完整正常训练预算及原图像素质量；不重跑模型或恢复优化。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
import torch

HERE=Path(__file__).resolve().parent
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
d=module(HERE/'reviewed-role-development-data.py','normal_verify_data')
def require(ok,message):
    if not ok:raise ValueError('reconstruction_mismatch: '+message)
def events(root):
    files=sorted((root/'events').glob('*.json'));rows=[json.loads(p.read_bytes()) for p in files]
    require([r['sequence'] for r in rows]==list(range(1,len(rows)+1)),'unique contiguous immutable events')
    require(rows[-1]==json.loads((root/'terminal.json').read_bytes()) and rows[-1]['phase']=='closed','closed terminal binding')
    return rows,[d.bind(p) for p in files]
def event_digest(refs):
    return hashlib.sha256(d.raw(refs)).hexdigest()
def environment(ref):
    value=d.read(ref)
    require(not value['cudaMatmulAllowTf32'] and not value['cudnnAllowTf32'] and not value['autocastEnabled'] and value['float32MatmulPrecision']=='highest','actual strict FP32 environment')
    return value


def verify_preflight(report_path):
    ref=d.bind(report_path);report=d.read(ref);plan=d.read(report['plan'])
    trainer=module(d.checked(plan['sources']['trainer']),'verify_normal_preflight_trainer')
    p,data,rows,net,band,metric,guard,cleanup=trainer.resources(Path(report['plan']['path']))
    try:
        require(report['ok'] and report['optimizerSteps']==0 and report['initialWeightsUnchanged'],'zero-step gate')
        require(report['precision']==plan['precision'],'preflight precision')
        require(report['trainForwardBackwardInputs']==len(rows) and report['valModelInputs']==report['protectedModelInputs']==0,'preflight budget')
        require([r['candidateIdentity'] for r in report['records']]==plan['candidateIdentities'],'all preflight candidates')
        for row,saved in zip(rows,report['records'],strict=True):
            require(saved['positive']==row['presenceTarget'] and saved['nativeSize']==row['nativeSize'] and math.isfinite(saved['loss']) and saved['finiteUsedGradientTensors']>0,'gradient records')
        ledger,bindings=events(report_path.parent)
        started=[r for r in ledger if r['phase']=='preflight_input_started'];confirmed=[r for r in ledger if r['phase']=='preflight_input_confirmed']
        require([r['candidateIdentity'] for r in started]==[r['candidateIdentity'] for r in confirmed]==plan['candidateIdentities'],'preflight started/confirmed denominator')
        require([r['modelInputsStarted'] for r in started]==list(range(1,len(rows)+1)) and all(r['confirmedOptimizerSteps']==0 for r in ledger),'preflight optimizer/event budget')
        require(ledger[-1]['preflightOk'] and len(ledger)==2*len(rows)+2,'preflight full event tree')
        actual_environment=environment(report['environment'])
        # 仅初始化CPU模型，不前向、不读训练图，用于独立核对固定随机种子的初始参数。
        initial=trainer.fresh_model(net,'cpu');require(trainer.tensors_sha(initial)==report['initialTensorSha256'],'fresh initialization tensor hashes')
        return {'report':ref,'ok':True,'eventCount':len(ledger),'eventFilesSha256':event_digest(bindings),
                'trainForwardBackwardInputs':len(rows),'optimizerSteps':0,'strictEnvironment':actual_environment,
                'freshCpuInitializationNoForwardVerified':True}
    finally:
        for path in cleanup:guard.remove_ultralytics_label_caches(Path(path))


def validate_training_ledger(ledger,plan):
    n=len(plan['candidateIdentities']);per_epoch=math.ceil(n/4);epochs=steps=inputs=0;in_flight=False
    by_epoch={};final=[]
    for event in ledger:
        phase=event['phase']
        if phase=='training_input_started':
            require(not in_flight and event['epoch']==epochs+1,'training input epoch/in-flight')
            by_epoch.setdefault(event['epoch'],[]).append(event['candidateIdentity']);inputs+=1
            choice=event['augmentation']
            require(choice['rotation'] in (0,1,2,3) and isinstance(choice['flip'],bool) and .9<=choice['brightness']<=1.1 and .9<=choice['contrast']<=1.1,'augmentation contract')
        elif phase=='optimizer_in_flight':
            require(not in_flight and event['attemptedStep']==steps+1,'optimizer attempt ordering');in_flight=True
        elif phase=='optimizer_confirmed':
            require(in_flight,'unstarted optimizer confirmation');steps+=1;in_flight=False
        elif phase=='epoch_completed':
            epochs+=1;require(steps==epochs*per_epoch and inputs==epochs*n,'full epoch budget')
            require(math.isfinite(event['meanLoss']),'epoch loss finite')
        elif phase=='final_train_input_started':
            require(epochs==plan['budget']['epochs'] and steps==plan['budget']['optimizerSteps'],'final inference before training complete')
            final.append(event['candidateIdentity']);inputs+=1
        elif phase not in ('claimed','closed'):raise ValueError('unknown normal event phase')
        require(event['confirmedOptimizerSteps']==steps and event['completedEpochs']==epochs and event['modelInputsStarted']==inputs and event['optimizerStepInFlight']==in_flight,'exact persisted event state')
    canonical=sorted(json.dumps(ci,sort_keys=True) for ci in plan['candidateIdentities'])
    require(len(by_epoch)==plan['budget']['epochs'],'all epochs')
    require(all(sorted(json.dumps(ci,sort_keys=True) for ci in values)==canonical for values in by_epoch.values()),'whole cohort each epoch')
    require(final==plan['candidateIdentities'] and inputs==plan['budget']['augmentedTrainingInputs']+n,'full final inference order/budget')
    return {'completedEpochs':epochs,'confirmedOptimizerSteps':steps,'augmentedTrainingInputs':inputs-n,'finalTrainInferenceInputs':len(final),'modelInputsStarted':inputs}


def verify(report_path):
    report_ref=d.bind(report_path);report=d.read(report_ref);root=report_path.parent;plan_ref=report['inputs']['plan'];plan=d.read(plan_ref)
    trainer=module(d.checked(plan['sources']['trainer']),'verify_normal_complete_trainer')
    p,data,rows,net,band,metric,guard,cleanup=trainer.resources(Path(plan_ref['path']))
    try:
        require(report['ok'],'execution complete field')
        claim=d.read(d.bind(root/'attempt.json'))
        require(claim['plan']==plan_ref and claim['attemptConsumed'] and not claim['resumeAllowed'],'single consumed attempt')
        pre=d.read(report['inputs']['preflight']);require(pre['plan']==plan_ref,'preflight plan binding')
        preflight=verify_preflight(Path(report['inputs']['preflight']['path']))
        ledger,bindings=events(root);counts=validate_training_ledger(ledger,plan)
        for name,value in counts.items():require(report[name]==value,'report '+name)
        require(report['precision']==plan['precision'],'training precision')
        actual_environment=environment(report['environment'])
        source_sizes={d.key(s['identity']):s['size'] for s in data['sourceRecords']};metrics=[]
        require(len(report['predictions'])==len(rows),'all final RAW files')
        for row,ref in zip(rows,report['predictions'],strict=True):
            path=d.checked(ref);require(path==root/'predictions'/f'{row["ordinal"]:03d}.npz','final raw identity/path')
            with np.load(path,allow_pickle=False) as archive:
                logits=archive['logits'].copy();presence=archive['presenceLogit'].copy()
            require(logits.dtype==presence.dtype==np.float32 and presence.shape==(),'raw float32 head storage')
            with Image.open(d.checked(row['paths']['nativeTarget'])) as im:im.load();truth=np.asarray(im).copy()>0
            require(int(truth.sum())==row['nativeTargetPixels'],'full original target pixels')
            metrics.append(trainer.candidate_metric(row,logits,presence,truth,source_sizes[d.key(row['candidateIdentity']['identity'])],net,metric))
        summary,quality=trainer.summarize(metrics)
        require(metrics==report['perCandidate'] and summary==report['metrics'] and quality==report['trainQualityGatePassed'],'full quality reconstruction')
        require(ledger[-1]['trainQualityGatePassed']==quality,'terminal quality')
        final_weights=torch.load(d.checked(report['inputs']['weights']),map_location='cpu',weights_only=True)
        require(set(final_weights)==set(pre['initialTensorSha256']) and all(v.dtype==torch.float32 and torch.isfinite(v).all() for v in final_weights.values()),'finite fresh final tensors')
        checkpoints=[]
        for epoch in range(10,101,10):
            path=root/f'forensic-epoch-{epoch:03d}.pt';checkpoint=torch.load(path,map_location='cpu',weights_only=False)
            require(checkpoint['completedEpochs']==epoch and checkpoint['confirmedOptimizerSteps']==epoch*math.ceil(len(rows)/4),'forensic epoch/step counts')
            require(checkpoint['use']=='forensic_no_resume_authority' and checkpoint['optimizer'] and checkpoint['rng'],'forensic state not restart authority')
            if epoch==100:require(all(torch.equal(value,checkpoint['model'][key]) for key,value in final_weights.items()),'final checkpoint/weights exact')
            checkpoints.append(d.bind(path))
        require(report['valModelInputs']==report['protectedModelInputs']==report['newChatImageInputs']==0 and not report['resumeAllowed'] and not report['formalReleaseAllowed'] and report['productHold'],'role/release semantics')
        return {'schemaVersion':1,'ok':True,'decision':'normal_training_events_and_all_original_pixel_quality_reconstructed',
                'training':report_ref,'verifier':d.bind(Path(__file__)),'plan':plan_ref,'preflight':preflight,
                'counts':counts,'metrics':summary,'perCandidate':metrics,'trainQualityGatePassed':quality,
                'eventCount':len(ledger),'eventFilesSha256':event_digest(bindings),'forensicCheckpoints':checkpoints,
                'strictEnvironment':actual_environment,'fullTruthDenominator':data['fullTruthDenominator'],
                'qualityCoordinateDomain':'full original source canvas, integer crop mapping, 2 original pixels',
                'newModelCalls':0,'optimizerSteps':0,'newChatImageInputs':0,'valModelInputs':0,'protectedModelInputs':0,
                'resumeAllowed':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for path in [*cleanup,root]:guard.remove_ultralytics_label_caches(Path(path))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--verify-report',type=Path)
    args=parser.parse_args()
    if args.verify_report:
        old=d.read(d.bind(args.verify_report));result=verify(Path(old['training']['path']))
        require(args.verify_report.read_bytes()==d.raw(result),'full audit JSON bytes')
    else:
        result=verify(args.report.resolve());d.new(args.output.resolve(),result)
    print(json.dumps({'ok':True,'trainQualityGatePassed':result['trainQualityGatePassed'],'counts':result['counts'],'metrics':result['metrics']},ensure_ascii=False))

if __name__=='__main__':main()
