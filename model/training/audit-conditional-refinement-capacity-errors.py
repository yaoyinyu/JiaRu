"""完整重放固定容量门后按实例/来源组整理错误；零模型调用，不作因果归因。"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path


def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def build(report_path):
    reader=module('capacity_error_reader',Path(__file__).with_name('audit-conditional-nail-refinement-feasibility.py'))
    report=reader.read(report_path);plan=reader.read(reader.checked(report['inputs']['plan']))
    source=reader.checked(plan['inputs']['trainerSource'])
    allowed=['train-conditional-nail-refinement-microfit.py','train-conditional-nail-refinement-bf16-microfit.py','train-conditional-nail-refinement-bf16-journal-microfit.py']
    if source.parent!=Path(__file__).parent.resolve() or source.name not in allowed:raise ValueError('unknown capacity verifier')
    trainer=module('capacity_error_verifier',source)
    if hasattr(trainer,'original_validate'):
        trainer.t.validate=trainer.validate;core=trainer.t
    else:core=trainer
    replay=trainer.verify(report_path)
    if replay['ok'] is not True:raise ValueError('reconstruction_mismatch: capacity report')
    records,_=core.validate(plan)
    if [r['id'] for r in records]!=[r['id'] for r in report['perCandidate']]:raise ValueError('reconstruction_mismatch: all45 rows')
    rows=[];groups={};counts={k:0 for k in ['iouBelowGate','boundaryIouBelowGate','boundaryF1BelowGate','positiveJointFailures','emptyLeakageCandidates']}
    gates=plan['gates']
    for original,result in zip(records,report['perCandidate'],strict=True):
        if bool(original['presenceTarget'])!=result['positive']:raise ValueError('reconstruction_mismatch: positive/empty identity')
        failures=[]
        if result['positive']:
            for metric,threshold,key in [('iou','perPositiveIou','iouBelowGate'),('boundaryIou','perPositiveBoundaryIou','boundaryIouBelowGate'),('boundaryF1','perPositiveBoundaryF1','boundaryF1BelowGate')]:
                if result[metric]<gates[threshold]:failures.append(key);counts[key]+=1
            if bool(failures)==result['jointPass']:raise ValueError('reconstruction_mismatch: frozen per-instance gate')
            if failures:counts['positiveJointFailures']+=1
        elif result['predictedPixels']:
            failures.append('emptyLeakageCandidates');counts['emptyLeakageCandidates']+=1
        row={'id':result['id'],'ordinal':original['ordinal'],'proposalIndex':original['proposalIndex'],'truthIndex':original['truthIndex'],
            'sourceGroup':original['sourceGroup'],'sourceImage':original['sourceImage'],'nativeSize':original['nativeSize'],
            'otherNailPixelsInCrop':original['otherNailPixelsInCrop'],'negativeKind':original['negativeKind'],
            'metricResult':result,'failureCodes':failures}
        rows.append(row)
        group=groups.setdefault(original['sourceGroup'],{'sourceGroup':original['sourceGroup'],'sourceOrdinals':set(),'positiveCount':0,'emptyCount':0,'positiveJointPassCount':0,'emptyRejectedCount':0,'failedCandidateIds':[]})
        group['sourceOrdinals'].add(original['ordinal'])
        if result['positive']:
            group['positiveCount']+=1;group['positiveJointPassCount']+=int(result['jointPass'])
        else:group['emptyCount']+=1;group['emptyRejectedCount']+=int(result['rejected'])
        if failures:group['failedCandidateIds'].append(result['id'])
    for group in groups.values():group['sourceOrdinals']=sorted(group['sourceOrdinals'])
    if len(rows)!=45 or len(groups)!=6 or sum(g['positiveCount'] for g in groups.values())!=34 or sum(g['emptyCount'] for g in groups.values())!=11:raise ValueError('reconstruction_mismatch: full denominator/groups')
    m=report['metrics']
    all_gates={'jointInstancePassRate':m['jointInstancePassRate']>=gates['minimumJointInstancePassRate'],
        'meanBoundaryF1':m['meanBoundaryF1']>=gates['minimumMeanBoundaryF1'],'meanIou':m['meanIou']>=gates['minimumMeanIou'],
        'all11Rejected':m['emptyRejectedCount']==gates['emptyAllRejected'],'zeroEmptyPixels':m['emptyOutputPixels']==gates['emptyTotalOutputPixels']}
    if all(all_gates.values())!=report['ok']:raise ValueError('reconstruction_mismatch: frozen aggregate gate')
    return {'schemaVersion':1,'ok':True,'decision':'all45_capacity_errors_replayed_no_new_inference',
        'inputs':{'capacityReport':reader.bind(report_path),'sourceAuditor':reader.bind(Path(__file__)),'manifest':plan['inputs']['manifest']},
        'capacityDecision':report['decision'],'metrics':m,'allRequiredGates':all_gates,'failureCounts':counts,
        'sourceGroups':list(groups.values()),'perCandidate':rows,'modelCalls':0,'optimizerSteps':0,
        'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
        'scope':'Fixed final outputs and frozen gates only; overlapping failure counts, no metric scan, causal claim, source re-selection, independent quality or formal promotion.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--capacity-report',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    guard=module('capacity_error_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    cleanup_roots=[]
    try:
        if args.verify_report:
            saved=json.loads(args.verify_report.read_text(encoding='utf-8'))
            reader=module('capacity_error_reader_main',Path(__file__).with_name('audit-conditional-nail-refinement-feasibility.py'))
            for b in saved['inputs'].values():reader.checked(b)
            capacity=Path(saved['inputs']['capacityReport']['path'])
            raw=json.loads(capacity.read_text(encoding='utf-8'));cleanup_roots=json.loads(Path(raw['inputs']['plan']['path']).read_text(encoding='utf-8'))['cacheCleanupRoots']
            report=build(capacity)
            if report!=saved:raise ValueError('reconstruction_mismatch: error attribution')
        else:
            capacity=args.capacity_report.resolve()
            raw=json.loads(capacity.read_text(encoding='utf-8'));cleanup_roots=json.loads(Path(raw['inputs']['plan']['path']).read_text(encoding='utf-8'))['cacheCleanupRoots']
            report=build(capacity);args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('xb') as stream:stream.write((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
        print(json.dumps({k:report[k] for k in ['ok','decision','capacityDecision','allRequiredGates','failureCounts']},ensure_ascii=False))
    finally:
        # 仅清理绑定容量计划列出的Ultralytics派生缓存，不修改哈希图片。
        for root in cleanup_roots:guard.remove_ultralytics_label_caches(Path(root))


if __name__=='__main__':main()
