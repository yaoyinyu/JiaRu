"""同完整候选/原像素真值的零推理开发对照；相对统计不替代绝对质量门。"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
def load(path,name):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=load(HERE/'reviewed-role-development-data.py','development_compare_data')
c=load(HERE/'train-reviewed-stage-b-augmentation-control.py','development_compare_control')
old_stats=load(HERE/'analyze-reviewed-internal-val-outcomes.py','development_compare_statistics')
fixed_stats=load(HERE/'analyze-reviewed-internal-val-outcomes-v2.py','development_compare_endpoint_statistics')

def wilson(k,n):
    z=1.959963984540054;p=k/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (0. if k==0 else center-half,1. if k==n else center+half)

def compare(baseline_ref,control_ref):
    baseline_audit=d.read(baseline_ref);control_audit=d.read(control_ref)
    c.require(baseline_audit['ok'] and control_audit['ok'],'both full audited executions')
    baseline=d.read(baseline_audit['training']);control=d.read(control_audit['training']);plan=d.read(control['inputs']['plan'])
    c.require(plan['inputs']['baselineReplay']==baseline_ref and control_audit['baselineReplay']==baseline_ref,'exact baseline reference')
    p,data,rows,net,band,metric,guard,cleanup=c.resources(Path(control['inputs']['plan']['path']))
    try:
        sizes={d.key(s['identity']):s['size'] for s in data['sourceRecords']};views={k:[] for k in ('coarse','baseline','control','control_presence_bypass')};records=[]
        c.require(len(baseline['predictions'])==len(control['predictions'])==len(rows),'full predictions count')
        for row,old_ref,new_ref,old_metric,new_metric in zip(rows,baseline['predictions'],control['predictions'],baseline_audit['perCandidate'],control_audit['perCandidate'],strict=True):
            with np.load(d.checked(old_ref),allow_pickle=False) as a:old_mask=a['logits'].copy();old_presence=a['presenceLogit'].copy()
            with np.load(d.checked(new_ref),allow_pickle=False) as a:new_mask=a['logits'].copy();new_presence=a['presenceLogit'].copy()
            for a,b in ((old_mask,old_presence),(new_mask,new_presence)):
                c.require(a.dtype==b.dtype==np.float32 and a.shape==(row['nativeSize'][1],row['nativeSize'][0]) and b.shape==() and np.isfinite(a).all() and np.isfinite(b).all(),'all RAW heads original finite float32')
            values={}
            for name in ('nativeCoarse','nativeTarget'):
                with Image.open(d.checked(row['paths'][name])) as image:image.load();values[name]=np.asarray(image).copy()>0
            truth=values['nativeTarget'];size=sizes[d.key(row['candidateIdentity']['identity'])]
            coarse=np.where(values['nativeCoarse'],np.float32(1),np.float32(-1))
            cases={'coarse':(coarse,np.array(0.,np.float32)),'baseline':(old_mask,old_presence),'control':(new_mask,new_presence),'control_presence_bypass':(new_mask,np.array(0.,np.float32))}
            record={'candidateIdentity':row['candidateIdentity'],'sourceGroup':row['sourceGroup'],'target':row['target'],'positive':row['presenceTarget'],'views':{}}
            for name,(mask,presence) in cases.items():
                result=c.candidate_metric(row,mask,presence,truth,size,net,metric);record['views'][name]=result;views[name].append(result)
            c.require(record['views']['baseline']==old_metric and record['views']['control']==new_metric,'full original per-candidate audit isomorphism')
            records.append(record)
        summaries={name:c.summarize(values)[0] for name,values in views.items()}
        c.require(summaries['baseline']==baseline['metrics']==baseline_audit['metrics'] and summaries['control']==control['metrics']==control_audit['metrics'],'summary fidelity')
        c.require(c.summarize(views['control'])[1]==control_audit['trainQualityGatePassed'],'unchanged absolute quality')
        positives=[r for r in records if r['positive']];n=len(positives);required=math.ceil(plan['quality']['jointPositiveRate']*n)
        migrations=[{'identity':r['candidateIdentity']['identity'],'truthIndex':r['target']['truthIndex'],'candidateIdentity':r['candidateIdentity'],
            'baselineJoint':r['views']['baseline']['jointPass'],'controlJoint':r['views']['control']['jointPass'],
            'controlBypassJoint':r['views']['control_presence_bypass']['jointPass'],
            'baselinePresenceAccepted':r['views']['baseline']['presenceAccepted'],'controlPresenceAccepted':r['views']['control']['presenceAccepted']} for r in positives]
        c.require(len({(d.key(r['identity']),r['truthIndex']) for r in migrations})==n==plan['counts']['train']['truthNails'],'all stable truth instances')
        relative=fixed_stats.statistics(summaries['baseline']['jointPassCount'],summaries['control']['jointPassCount'],n,old_stats.minimum_distinguishable,wilson)
        groups={}
        for row in records:groups.setdefault(row['sourceGroup'],[]).append(row)
        group_summaries=[{'sourceGroup':name,'candidateInputs':len(items),'positiveInputs':sum(x['positive'] for x in items),
            'baselineJoint':sum(x['positive'] and x['views']['baseline']['jointPass'] for x in items),
            'controlJoint':sum(x['positive'] and x['views']['control']['jointPass'] for x in items)} for name,items in groups.items()]
        return {'schemaVersion':1,'ok':True,'decision':'all_same_truth_raw_views_reconstructed_absolute_control_quality_separate',
            'inputs':{'baselineAudit':baseline_ref,'controlAudit':control_ref},
            'sources':{'comparator':d.bind(Path(__file__)),'controlTrainer':d.bind(HERE/'train-reviewed-stage-b-augmentation-control.py'),
                'relativeStatistics':d.bind(HERE/'analyze-reviewed-internal-val-outcomes.py'),'endpointStatistics':d.bind(HERE/'analyze-reviewed-internal-val-outcomes-v2.py')},
            'records':records,'truthMigrations':migrations,'sourceGroupSummaries':group_summaries,'summaries':summaries,'relativeJointDiagnostic':relative,
            'zeroInferenceCeilings':{'fullTruthDenominator':n,'requiredJointPositiveCount':required,
                'fixedControlMaskPresenceOnlyMaximumJoint':summaries['control_presence_bypass']['jointPassCount'],
                'fixedControlMaskPresenceOnlyUpperBoundToRequiredRatio':summaries['control_presence_bypass']['jointPassCount']/required,
                'fixedControlMaskPresenceOnlyUnreachable':summaries['control_presence_bypass']['jointPassCount']<required,
                'perfectChangedMaskRepresentationUpperBound':n,'representationNotLearnabilityOrFormalQuality':True},
            'controlTrainQualityGatePassed':control_audit['trainQualityGatePassed'],
            'restoredJointTruthCount':sum(not x['baselineJoint'] and x['controlJoint'] for x in migrations),
            'newJointFailureTruthCount':sum(x['baselineJoint'] and not x['controlJoint'] for x in migrations),
            'baselineFailureNotRewritten':True,'causalGeneralizationOrFormalQualityProven':False,'relativeBranchGateRegistered':False,
            'newModelCalls':0,'optimizerSteps':0,'newChatImageInputs':0,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for root in cleanup:guard.remove_ultralytics_label_caches(Path(root))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline-audit',type=Path);p.add_argument('--control-audit',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    if a.verify_report:
        old=d.read(d.bind(a.verify_report));result=compare(old['inputs']['baselineAudit'],old['inputs']['controlAudit']);c.require(a.verify_report.read_bytes()==d.raw(result),'full comparison report bytes')
    else:result=compare(d.bind(a.baseline_audit),d.bind(a.control_audit));d.new(a.output.resolve(),result)
    print(json.dumps({'ok':True,'summaries':result['summaries'],'controlTrainQualityGatePassed':result['controlTrainQualityGatePassed'],'zeroInferenceCeilings':result['zeroInferenceCeilings'],'newModelCalls':0},ensure_ascii=False))
