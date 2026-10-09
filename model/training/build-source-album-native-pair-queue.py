"""为采集相册增量生成完整原像素待裁队列，保留双向观察及原角色。"""
import argparse,hashlib,json,os
from pathlib import Path
def bind(p):
    p=Path(p).resolve();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def read(ref):
    if bind(ref['path'])!=ref:raise ValueError('reconstruction_mismatch: '+ref['path'])
    return json.loads(Path(ref['path']).read_bytes())
def build(report_path,acquisition_path,output):
    report_ref=bind(report_path);report=read(report_ref);acquisition_ref=bind(acquisition_path);acquisition=read(acquisition_ref)
    if not report['ok'] or report['executionStatus']!='complete':raise ValueError('recall not terminal complete')
    if len(report['results'])!=report['counts']['newTargets'] or [r['ordinal'] for r in report['results']]!=list(range(1,len(report['results'])+1)):
        raise ValueError('complete target denominator or order drift')
    groups={g['sourceGroup']:g for g in acquisition['groups']};pairs={};low=[];nohit=[];observation_count=0;targets=[]
    for result in report['results']:
        query=read(result['report']);raw=query['target'];group=groups[raw['sourceGroup']]
        if query['ordinal']!=result['ordinal'] or len(query['recalledPairs'])!=result['recalledPairs']:
            raise ValueError('query binding/observation count drift')
        if raw['imageSha256']!=raw['sourceImage']['sha256']:raise ValueError('target image identity drift')
        target={'imageSha256':raw['imageSha256'],'sourceImage':raw['sourceImage'],'sourceGroups':[raw['sourceGroup']],
                'kinds':['acquisition_album_related_asset'],'ownerCurrentIdentities':[r['identity'] for r in group['currentCandidates']],
                'acquisitionTargetPreserved':raw,'trainingAllowed':False,'independenceApproved':False}
        targets.append(target)
        if query['lowFeatureQuery']:low.append(target)
        if not query['recalledPairs']:nohit.append(target)
        for hit in query['recalledPairs']:
            pair_id=tuple(sorted([raw['imageSha256'],hit['reference']['image']['sha256']]))
            if pair_id[0]==pair_id[1]:raise ValueError('self reference presented as foreign overlap')
            pairs.setdefault(pair_id,[]).append({'target':target,'reference':hit['reference'],'queryReport':result['report'],'result':hit['result']});observation_count+=1
    if observation_count!=report['counts']['recalledPairs']:raise ValueError('recall observation denominator drift')
    if len({t['imageSha256'] for t in targets})!=len(targets):raise ValueError('duplicate target byte identity')
    # 角色风险决定待裁顺序，全部观察与图对保留；不使用模型质量或mask结果。
    protected={'consumedPositiveTest','releaseTestReplacement'}
    def priority(item):
        roles={role for o in item[1] for role in o['reference']['roles']}
        return (not bool(roles&protected),item[0])
    rows=[{'pairIdentity':list(key),'observations':observations,'nativeDecision':'pending','trainingAllowed':False} for key,observations in sorted(pairs.items(),key=priority)]
    doc={'schemaVersion':1,'inputs':{'recallReport':report_ref,'acquisitionInventory':acquisition_ref,'writer':bind(Path(__file__))},
         'counts':{'newTargets':len(targets),'recalledObservations':observation_count,'uniqueUnorderedPairs':len(rows),'targetsWithNoHits':len(nohit),'lowFeatureTargets':len(low),'nativeReviewedPairs':0},
         'pairs':rows,'noHitTargets':nohit,'lowFeatureTargets':low,'targets':targets,
         'nativeReviewPolicy':'all unique pairs require full original pixel review; prioritize consumed/release source roles, never filter rest',
         'sourceParentIndependenceQualified':False,'trainingAllowed':False}
    with output.open('xb') as f:f.write((json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode());f.flush();os.fsync(f.fileno())
    print(json.dumps({'queue':bind(output),'counts':doc['counts']},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--acquisition',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.report,a.acquisition,a.output)
