"""逐变体分母与预注册说明保真审核；不读取像素或运行模型。"""
import argparse
import hashlib
import json
from pathlib import Path
import re

def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}

def denominators(plan):
    variants={};marked={'sourceImages':0,'truthNails':0};all_sources={'sourceImages':len(plan['sources']),'truthNails':sum(s['completeVisibleNails'] for s in plan['sources'])}
    for s in plan['sources']:
        names=[v['name'] for v in s['variants']]
        if len(set(names))!=len(names) or not names or names[0]!='original':raise ValueError('variant cohort identity mismatch')
        if len(names)>1:
            marked['sourceImages']+=1;marked['truthNails']+=s['completeVisibleNails']
        for n in names:
            d=variants.setdefault(n,{'sourceImages':0,'truthNails':0});d['sourceImages']+=1;d['truthNails']+=s['completeVisibleNails']
    return {'originalAll':all_sources,'originalMarked':marked,'byVariant':variants}

def audit(plan,report=None):
    expected=denominators(plan);errors=[];verified=False
    if 'comparisonDenominators' in plan:
        verified=True
        if plan['comparisonDenominators']!=expected:errors.append({'kind':'machine_comparison_denominator_mismatch','expected':expected,'actual':plan['comparisonDenominators']})
    for text in plan.get('preregisteredInterpretation',[]):
        found=re.search(r'原图全(\d+)/(\d+)和配对原图(\d+)/(\d+)分母',text)
        if found:
            verified=True;a,b,c,d=map(int,found.groups());declared={'originalAll':{'sourceImages':a,'truthNails':b},'originalMarked':{'sourceImages':c,'truthNails':d}}
            truth={k:expected[k] for k in declared}
            if declared!=truth:errors.append({'kind':'preregistered_text_denominator_mismatch','text':text,'declared':declared,'expected':truth})
            for sources,nails in re.findall(r'其他变体(\d+)/(\d+)',text):
                non_original=[v for k,v in expected['byVariant'].items() if k!='original']
                if any(v!={'sourceImages':int(sources),'truthNails':int(nails)} for v in non_original):errors.append({'kind':'preregistered_other_variant_text_mismatch','text':text,'expected':non_original})
    if not verified:errors.append({'kind':'comparison_denominator_contract_missing'})
    if report is not None:
        for name,expected_count in expected['byVariant'].items():
            actual={k:report['aggregateByVariant'][name][k] for k in ('sourceImages','truthNails')}
            if actual!=expected_count:errors.append({'kind':'report_variant_denominator_mismatch','variant':name,'expected':expected_count,'actual':actual})
        actual={k:report['markedSourceOriginalAggregate'][k] for k in ('sourceImages','truthNails')}
        if actual!=expected['originalMarked']:errors.append({'kind':'report_marked_original_mismatch','expected':expected['originalMarked'],'actual':actual})
    return {'schemaVersion':1,'ok':not errors,'decision':'denominator_contract_consistent' if not errors else 'reconstruction_mismatch',
            'expectedDenominators':expected,'errors':errors,'interpretationConclusionsAllowed':not errors,
            'trainingAllowed':False,'formalTrainingApprovedImages':0,'modelCalls':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--probe-report',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    if a.verify_report:
        old=json.loads(a.verify_report.read_bytes());refs=old['inputs']
        for r in refs.values():
            if bind(r['path'])!=r:raise ValueError('reconstruction_mismatch: input hash')
        plan=json.loads(Path(refs['plan']['path']).read_bytes());probe=json.loads(Path(refs['probeReport']['path']).read_bytes()) if 'probeReport' in refs else None
        result={**audit(plan,probe),'inputs':refs}
        if result!=old:raise ValueError('reconstruction_mismatch: report')
    else:
        if not a.plan or not a.output:p.error('--plan and --output required')
        refs={'runnerSource':bind(__file__),'plan':bind(a.plan)};probe=None
        if a.probe_report:refs['probeReport']=bind(a.probe_report);probe=json.loads(a.probe_report.read_bytes())
        result={**audit(json.loads(a.plan.read_bytes()),probe),'inputs':refs}
        with a.output.open('xb') as f:f.write((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'report':bind(a.verify_report or a.output),'decision':result['decision'],'errors':result['errors']},ensure_ascii=False))
if __name__=='__main__':main()
