"""冻结终评全候选保真、错像素先验幅度诊断及唯一裁剪变量可达性。"""
from pathlib import Path
import argparse
import json
import math
import importlib.util
import numpy as np


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


t=module('native_error_trainer',Path(__file__).with_name('train-native-boundary-head-microfit.py'));a=t.a


def wilson(successes,total):
    z=1.959963984540054;p=successes/total;denom=1+z*z/total
    center=(p+z*z/(2*total))/denom;half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denom
    return [center-half,center+half]


def build(plan_path):
    plan=a.read(plan_path)
    for binding in plan['inputs'].values():a.checked(binding)
    if plan['diagnostic']!={'highAbsolutePriorLogit':8,'proposedBandPriorLogitCap':2,'idealCorrectiveDeltaMagnitude':3}:raise ValueError('fixed diagnostic no scan')
    path=Path(plan['inputs']['capacityReport']['path']);report=a.read(path);replay=t.verify(path)
    if replay['qualityDecision']!='native_capacity_fail_no_full30':raise ValueError('preserve quality fail')
    frozen=a.read(a.checked(report['inputs']['plan']));_,parent,records=t.validate(frozen);h,data=t.s.native_data(parent,records)
    with np.load(a.checked(report['finalDeltas']),allow_pickle=False) as saved:deltas=[saved[f'delta_{i:03d}'].copy() for i in range(45)]
    rows=[];clipped_ideal=[];fail_ids=[];max_delta=max(float(np.max(np.abs(v))) for v in deltas)
    for item,delta,accepted in zip(data,deltas,report['perCandidate'],strict=True):
        row=item['row'];base=item['base'];band=item['band'];truth=item['target']>=.5
        corrected=h.apply_native_delta(base,delta,band)>=.5;initial=base>=.5
        clipped=np.clip(base.astype(np.float64),1e-6,1-1e-6);prior=np.log(clipped)-np.log1p(-clipped)
        cap_prior=np.clip(prior,-2,2);initial_probability=base.copy()
        initial_probability[band]=(1/(1+np.exp(-cap_prior[band]))).astype(np.float32)
        if not np.array_equal(initial_probability>=.5,initial):raise ValueError('cap2 zero-residual initial mask parity')
        if not np.array_equal(initial_probability[~band].view(np.uint32),base[~band].view(np.uint32)):raise ValueError('cap2 outside bit contract')
        # ±3在带内跨越±2先验，复现理想GT替换；只是解析见证，无模型输出。
        ideal_probability=base.copy();ideal_probability[band]=(1/(1+np.exp(-(cap_prior+np.where(truth,3.,-3.))[band]))).astype(np.float32)
        wanted=initial.copy();wanted[band]=truth[band]
        if not np.array_equal(ideal_probability>=.5,wanted):raise ValueError('cap2 ideal sign witness')
        # 转成原组合所需的无界oracle delta，仅供同一权威metrics重放。
        oracle_delta=np.where(truth,3.,-3.)+cap_prior-prior;clipped_ideal.append(oracle_delta.astype(np.float32))
        residual_wrong=(corrected!=truth)&band;original_wrong=(initial!=truth)&band
        entry={'id':row['id'],'positive':bool(row['presenceTarget']),'cap2ZeroResidualInitialMaskParity':True,'cap2OutsideBitsParity':True,
               'currentJointPass':accepted.get('jointPass'),'currentResidualErrorPixelsInsideBand':int(residual_wrong.sum()),
               'currentResidualErrorsInsideBandWithAbsolutePriorAtLeast8':int((residual_wrong&(np.abs(prior)>=8)).sum()),
               'initialErrorPixelsInsideBand':int(original_wrong.sum()),'initialErrorPixelsOutsideBand':int(((initial!=truth)&~band).sum()),
               'originalPriorLogitMaxAbsoluteInBand':float(np.max(np.abs(prior[band]))) if band.any() else None,
               'trainedDeltaMaxAbsoluteInBand':float(np.max(np.abs(delta[band]))) if band.any() else None}
        if row['presenceTarget'] and not accepted['jointPass']:fail_ids.append(row['id'])
        rows.append(entry)
    _,witness=t.metrics(data,clipped_ideal,h)
    if witness['jointPassCount']!=34 or witness['emptyOutputPixels']!=0:raise ValueError('cap2 ideal witness differs from frozen all34')
    errors=sum(r['currentResidualErrorPixelsInsideBand'] for r in rows)
    high=sum(r['currentResidualErrorsInsideBandWithAbsolutePriorAtLeast8'] for r in rows)
    positives=[r for r in report['perCandidate'] if r['positive']]
    need=28-report['metrics']['jointPassCount'];gain=34-report['metrics']['jointPassCount']
    snapshots=[a.bind(p) for p in sorted(path.parent.glob('forensic-epoch-*.pt'))]
    if len(snapshots)!=8:raise ValueError('eight bound forensic snapshots')
    return {'schemaVersion':1,'ok':True,'decision':'native_quality_fail_reconstructed_prior_cap2_feasibility_next_no_new_model_calls',
            'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'oldQualityDecision':report['decision'],'metrics':report['metrics'],
            'failureCounts':{'joint':len(fail_ids),'iou':sum(r['iou']<.75 for r in positives),'boundaryIou':sum(r['boundaryIou']<.75 for r in positives),'boundaryF1':sum(r['boundaryF1']<.9 for r in positives)},
            'failedIds':fail_ids,'perCandidate':rows,'journal':replay['journal'],'forensicSnapshots':snapshots,
            'priorDiagnostic':{'currentErrorsInsideBand':errors,'highPriorErrorsInsideBand':high,'highPriorFraction':high/max(1,errors),
                               'observedGlobalDeltaAbsoluteMax':max_delta,'meaning':'High prior may burden learning; observed delta range is not an architectural bound or proof of cause.'},
            'cap2IdealWitness':witness,'reachability':{'idealEditableMaskCountCeiling':34,'witnessJointCount':34,'requiredCount':28,
                            'currentCount':16,'additionalGainNeeded':need,'witnessGain':gain,'witnessGainToNeedRatio':gain/need},
            'absoluteJointWilson95':wilson(16,34),'relativeClaim':False,'branchDecisionBasis':'Absolute16/34 <0.80; no significance claim or branch retention from one additional nail',
            'nextUniqueVariable':'Inside fixed4px band only, clip frozen prior logit to[-2,2]; keep6channel input/base/threshold/architecture/quality gates unchanged. Fresh feasibility gates before one independently preregistered capacity attempt.',
            'modelCalls':0,'optimizerSteps':0,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
            'scope':'Same all45 final masks and metrics preserved. Cap2 zero-residual mask parity and ±3 GT existence witness only; no learned cap2 result, no future training approval, no independent validation.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--verify-report',type=Path);args=parser.parse_args()
    path=args.plan if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path']);plan=a.read(path)
    guard=module('native_error_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    parent=a.read(plan['inputs']['parentPlan']['path'])
    try:
        report=build(path)
        if args.verify_report:
            if report!=a.read(args.verify_report):raise ValueError('reconstruction_mismatch: full45 native error/prior report')
        else:a.write_new(args.output,report)
        print(json.dumps({'ok':True,'decision':report['decision'],'failureCounts':report['failureCounts'],'priorDiagnostic':report['priorDiagnostic'],
                          'reachability':report['reachability'],'report':a.bind(args.verify_report or args.output)},ensure_ascii=False))
    finally:
        for folder in parent['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(folder))


if __name__=='__main__':main()
