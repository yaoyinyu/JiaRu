"""从已存预测重建配对干预效应和全来源组覆盖，不再次推理或晋升训练。"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json
from pathlib import Path
import sys
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(ref):
    p=Path(ref['path']).resolve()
    if not p.is_file() or sha(p)!=ref['sha256']:raise ValueError('reconstruction_mismatch: '+str(p))
    return p
def read(ref):return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref,name):
    p=checked(ref);sys.path.insert(0,str(p.parent));s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def summarize(probe,baseline):
    records=probe['records'];source_by={(r['split'],r['ordinal']):r for r in baseline['currentFullSplitRecords']}
    if len(records)!=probe['counts']['sourceImages'] or sum(r['completeVisibleNails'] for r in records)!=probe['counts']['completeVisibleNails']:raise ValueError('probe denominator mismatch')
    if len({r['ordinal'] for r in records})!=len(records):raise ValueError('duplicate probe source')
    for r in records:
        b=source_by.get(('train',r['ordinal']))
        if b is None:raise ValueError('source absent from full split')
        for k in ('fileName','sourceGroup','sourceImage','upstreamDevelopmentSplit','parents','trainingUse'):
            if b[k]!=r[k]:raise ValueError('baseline source/role drift')
    comparisons={}
    for name in records[0]['comparisons']:
        values=[r['comparisons'][name] for r in records]
        comparisons[name]={'totalUnionDifferentPixels':sum(v['unionSymmetricDifferencePixels'] for v in values),
                           'maxUnionDifferentPixels':max(v['unionSymmetricDifferencePixels'] for v in values),
                           'maxUnionChangedFraction':max(1-v['unionIoU'] for v in values),
                           'sourcesWithCandidateCountChange':sum(v['candidateCountDelta']!=0 for v in values),
                           'sourcesWithTruthMatchMigration':sum(bool(v['newMissedTruthIndices'] or v['recoveredTruthIndices']) for v in values)}
    original_failures=[]
    for r in records:
        p=r['predictions']['original'];missed=set(p['missedTruthIndices'])
        for a in p['assignment']:
            if a['truthIndex'] in missed:original_failures.append({'ordinal':r['ordinal'],**a,'interpretation':'Existing matched candidate below fixed IoU0.75; this is not proof of absent Stage A ROI.'})
    groups=[]
    for group in sorted({r['sourceGroup'] for r in records}):
        full=[r for r in baseline['currentFullSplitRecords'] if r['sourceGroup']==group]
        included=[r['ordinal'] for r in records if r['sourceGroup']==group]
        groups.append({'sourceGroup':group,'fullSnapshotSources':len(full),'probeSourceOrdinals':included,
                       'unprobedSourceRecords':[{k:r[k] for k in ('split','ordinal','fileName','sourceImage','currentSourceDisposition','historicalMaskCount')} for r in full if r['split']!='train' or r['ordinal'] not in included],
                       'wholeGroupShortcutExclusionProven':False})
    return {'comparisons':comparisons,'originalLowIoUAssignedCandidates':original_failures,'groupCoverage':groups,
            'diagnosticInterpretation':'No observed candidate-count or IoU0.75 match migration across the preregistered local inputs. Pixel sensitivity exists for marker and blank interventions. Neither establishes shortcut absence or formal quality.'}
def audit(execution_ref):
    execution=read(execution_ref);inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity mismatch')
    probe=read(inputs['probeReport']);baseline=read(inputs['manualMaskDisposition'])
    runner=module(probe['inputs']['runnerSource'],'saved_probe_replay')
    if runner.reconstruct(probe['execution'],checked(inputs['probeReport']).parent)!=probe:raise ValueError('reconstruction_mismatch: saved prediction report')
    result=summarize(probe,baseline)
    return {'schemaVersion':1,'ok':True,'decision':'diagnostic_effects_replayed_no_training_or_group_promotion','execution':execution_ref,'inputs':inputs,
            **result,'counts':probe['counts'],'aggregateByVariant':probe['aggregateByVariant'],
            'recordedProbeModelCalls':probe['modelCalls'],'additionalModelCalls':0,'optimizerSteps':0,
            'formalTrainingApprovedImages':0,'trainingAllowed':False,'full30PilotAllowed':False,'wholeSourceGroupsApproved':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    if args.verify_report:
        old=json.loads(args.verify_report.read_text(encoding='utf-8'))
        if audit(old['execution'])!=old:raise ValueError('effects reconstruction mismatch')
        print(json.dumps({'ok':True,'decision':'effects_replay_identical','additionalModelCalls':0}));return
    if not args.execution or not args.output:p.error('--execution and --output required')
    result=audit(bind(args.execution))
    with args.output.open('x',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('ok','decision','comparisons','originalLowIoUAssignedCandidates','groupCoverage')}))
if __name__=='__main__':main()
