"""终态全45质量保真、逐实例迁移与保存执行统计；零模型调用。"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path
import numpy as np


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def build(plan_path):
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    t=module('native_outcome_trainer',plan['inputs']['capacityVerifier']['path'])
    a=t.a
    for value in plan['inputs'].values():
        a.checked(value)
    if plan['modelCalls']!=0 or plan['optimizerSteps']!=0 or plan['diagnostic']!='all45 saved native outputs and immutable progress only':
        raise ValueError('zero-model diagnostic scope')
    path=a.checked(plan['inputs']['capacityReport'])
    report=a.read(path)
    replay=t.verify(path)
    frozen=a.read(a.checked(report['inputs']['plan']))
    _,parent,records=t.validate(frozen)
    h,data=t.s.native_data(parent,records)
    with np.load(a.checked(report['finalDeltas']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=frozen['candidateIds']:
            raise ValueError('reconstruction_mismatch: candidates')
        deltas=[saved[f'delta_{i:03d}'].copy() for i in range(45)]
    rows,summary=t.metrics(data,deltas,h)
    if rows!=report['perCandidate'] or summary!=report['metrics'] or report['gates']!=parent['qualityGatesUnchanged']:
        raise ValueError('reconstruction_mismatch: full45 masks/metrics/gates')
    previous=a.read(a.checked(plan['inputs']['previousCapacityReport']))
    if [row['id'] for row in previous['perCandidate']]!=[row['id'] for row in rows]:
        raise ValueError('reconstruction_mismatch: previous candidate identity')
    prior={row['id']:row for row in previous['perCandidate']}
    transitions={key:[] for key in ('newFailure','recovered','persistentFailure','persistentPass')}
    details=[]
    oracle=[]
    for item,delta,row in zip(data,deltas,rows,strict=True):
        prediction=h.apply_native_delta(item['base'],delta,item['band'])>=.5
        truth=item['target']>=.5
        wrong=prediction!=truth
        details.append({'id':row['id'],'positive':row['positive'],'jointPass':row.get('jointPass'),
                        'wrongPixelsInsideBand':int((wrong&item['band']).sum()),'wrongPixelsOutsideBand':int((wrong&~item['band']).sum())})
        if row['positive']:
            old,new=prior[row['id']]['jointPass'],row['jointPass']
            kind=('persistentPass' if new else 'newFailure') if old else ('recovered' if new else 'persistentFailure')
            transitions[kind].append(row['id'])
        base=np.clip(item['base'].astype(np.float64),1e-6,1-1e-6)
        baseline=np.log(base)-np.log1p(-base)
        oracle.append((np.where(truth,3.,-3.)-baseline).astype(np.float32))
    _,witness=t.metrics(data,oracle,h)
    if witness['jointPassCount']!=34 or witness['emptyOutputPixels']!=0:
        raise ValueError('reconstruction_mismatch: frozen ideal band witness')
    events=[a.read(p)['value'] for p in sorted((path.parent/'progress-events').glob('*.json'))]
    attempts=[row for row in events if row['optimizerStepInFlight']]
    if [row['attemptedNextStep'] for row in attempts]!=list(range(1,385)):
        raise ValueError('step event fidelity')
    norms=np.array([row['gradientNorm'] for row in attempts],np.float64)
    if not np.isfinite(norms).all():
        raise ValueError('nonfinite recorded norm')
    positive=[row for row in rows if row['positive']]
    count=summary['jointPassCount']
    need=28-count
    z=1.959963984540054
    proportion=count/34
    denominator=1+z*z/34
    center=(proportion+z*z/68)/denominator
    half=z*math.sqrt(proportion*(1-proportion)/34+z*z/(4*34*34))/denominator
    return {'schemaVersion':1,'ok':True,'decision':'full45_quality_fail_outcomes_reconstructed_no_model_calls',
            'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'qualityDecision':report['decision'],'metrics':summary,
            'failureCounts':{'joint':sum(not row['jointPass'] for row in positive),
                'iou':sum(row['iou']<.75 for row in positive),'boundaryIou':sum(row['boundaryIou']<.75 for row in positive),
                'boundaryF1':sum(row['boundaryF1']<.9 for row in positive)},
            'perCandidate':details,'instanceTransitionsDiagnosticOnly':transitions,'journal':replay['journal'],
            'wrongPixels':{'insideBand':sum(row['wrongPixelsInsideBand'] for row in details),'outsideBand':sum(row['wrongPixelsOutsideBand'] for row in details)},
            'executionStatistics':{'recordedStepNormCount':384,'preClipNormMaximum':float(norms.max()),
                'preClipNormMedian':float(np.median(norms)),'clippedStepCount':int((norms>1).sum()),
                'lastEpochNorms':norms[-6:].tolist(),'firstEpochTrainingLoss':report['history'][0]['meanTrainingLoss'],
                'lastEpochTrainingLoss':report['history'][-1]['meanTrainingLoss']},
            'jointWilson95':[center-half,center+half],'relativeClaim':False,
            'idealBandWitness':witness,'reachability':{'idealEditableMaskCountCeiling':34,'witnessJointCount':34,'requiredCount':28,
                'currentCount':count,'additionalGainNeeded':need,'witnessGain':34-count,'witnessGainToNeedRatio':(34-count)/need},
            'modelCalls':0,'optimizerSteps':0,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
            'scope':'Absolute capacity gate unchanged. Error transitions and training loss/norms do not prove significance, gradient conflict, cause or new recipe quality; ideal mask witness is not learned capacity.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify-report',type=Path)
    args=parser.parse_args()
    saved=json.loads(args.verify_report.read_text(encoding='utf-8')) if args.verify_report else None
    plan_path=args.plan if args.plan else Path(saved['inputs']['plan']['path'])
    guard=module('native_outcome_guard',Path(__file__).with_name('train-yolo-seg.py'))
    guard.install_read_only_ultralytics_image_check()
    try:
        report=build(plan_path)
        if saved is not None and report!=saved:
            raise ValueError('reconstruction_mismatch: outcomes report')
        if saved is None:
            with args.output.open('x',encoding='utf-8',newline='\n') as stream:
                stream.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({key:report[key] for key in ('ok','failureCounts','wrongPixels','executionStatistics','instanceTransitionsDiagnosticOnly','reachability')},ensure_ascii=False),flush=True)
    finally:
        plan=json.loads(plan_path.read_text(encoding='utf-8'))
        parent=json.loads(Path(plan['inputs']['parentPlan']['path']).read_text(encoding='utf-8'))
        for directory in parent['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':
    main()
