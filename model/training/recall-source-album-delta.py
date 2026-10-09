"""仅扫描此前未查询的来源组相关资产；冻结旧分母并扩充可复用特征缓存。"""
import argparse,hashlib,importlib.util,io,json,sys,time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

R=Path(__file__).resolve().parents[2]
sp=importlib.util.spec_from_file_location('album_recall_base',R/'model/training/recall-source-parent-near-duplicates.py');base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
KEYS=('maxLongSide','maxFeatures','ratio','minimumRatioMatches','minimumInliers','minimumInlierFraction','minimumQueryInlierHullCoverage','ransacThresholdPixels','seed','lowFeatureQueryThreshold')

def validate(plan,old_plan,old_report,old_targets,targets,inventory,cache_plan):
    ids=[x['imageSha256'] for x in targets['targets']];old_ids={x['imageSha256'] for x in old_targets['targets']}
    if not ids or len(ids)!=len(set(ids)) or set(ids)&old_ids:raise ValueError('delta must contain only distinct previously unqueried assets')
    if any(plan['contract'][k]!=old_plan['contract'][k] or plan['contract'][k]!=cache_plan['contract'][k] for k in KEYS[:-1]):raise ValueError('cached algorithm drift')
    if plan['contract']['lowFeatureQueryThreshold']!=old_plan['contract']['lowFeatureQueryThreshold']:raise ValueError('low-feature rule drift')
    if not old_report['ok'] or old_report['counts']['positiveControlsPassed']!=12 or old_report['counts']['targetsCompleted']!=len(old_targets['targets']):raise ValueError('old recall proof not complete')
    if plan['positiveControls']!=old_plan['positiveControls'] or len(plan['positiveControls'])!=12:raise ValueError('positive control identity drift')
    if len(inventory['corpus'])!=plan['counts']['references'] or len(ids)!=plan['counts']['newTargets']:raise ValueError('delta denominator drift')
    ref_ids=[r['image']['sha256'] for r in inventory['corpus']]
    if len(ref_ids)!=len(set(ref_ids)) or any(not r['roles'] or not r['sourceGroups'] or r['trainingAllowed'] for r in inventory['corpus']):raise ValueError('protected reference identity/role drift')
    if plan['trainingAllowed'] or plan['newModelCalls'] or plan['optimizerSteps']:raise ValueError('source scan is not training or model inference')
    return True

def run(plan_path,out):
    ref=base.bind(plan_path);plan=base.read(ref);refs=plan['inputs']
    old_plan,old_report,old_targets,targets,inventory,cache=[base.read(refs[k]) for k in ['oldPlan','oldRecall','oldTargets','targets','referenceInventory','historicalFeatureManifest']]
    validate(plan,old_plan,old_report,old_targets,targets,inventory,base.read(cache['plan']))
    if refs['baseRunner']!=base.bind(Path(base.__file__)):raise ValueError('frozen matcher source drift')
    controls_old=base.read(old_report['inputs']['controls']);assert controls_old['ok'] and len(controls_old['controls'])==12
    old_dhash={r['image']['sha256']:r['dhash256'] for r in base.read(old_report['inputs']['features'])['records']}
    cache_by={r['image']['sha256']:r for r in cache['items']};c=plan['contract']
    images={r['image']['sha256']:r['image'] for r in inventory['corpus']}
    for row in targets['targets']:images[row['imageSha256']]=row['sourceImage']
    for ctrl in plan['positiveControls']:
        for key in ('sourceImage','referenceImage'):
            if ctrl.get(key):images[ctrl[key]['sha256']]=ctrl[key]
    for r in images.values():base.checked(r)
    guard_path=base.checked(refs['readOnlyGuard']);sys.path.insert(0,str(guard_path.parent));sp=importlib.util.spec_from_file_location('album_guard',guard_path);guard=importlib.util.module_from_spec(sp);sys.modules[sp.name]=guard;sp.loader.exec_module(guard);guard.install_read_only_ultralytics_image_check()
    roots=[Path(base.read(inventory['inputs'][k])['outputDir']) for k in ('cycle012Materialization','cleanDevelopmentEvaluation')]
    out.mkdir(exist_ok=False);(out/'features').mkdir();(out/'events').mkdir();start=time.monotonic();seq=0
    def event(kind,**values):
        nonlocal seq;seq+=1;base.put(out/'events'/f'{seq:06d}.json',{'sequence':seq,'kind':kind,**values})
    try:
        cv2.setNumThreads(1);event('started',plan=ref);features={};hashes={};entries=[];reuse_count=0
        for ordinal,(digest,image_ref) in enumerate(sorted(images.items()),1):
            path=base.checked(image_ref)
            if digest in cache_by:
                item=cache_by[digest]
                with np.load(base.checked(item['feature']),allow_pickle=False) as data:f=(data['points'].copy(),data['descriptors'].copy(),data['size'].copy())
                assert f[0].shape==(item['featureCount'],2) and f[1].shape==(len(f[0]),128) and f[2].tolist()==item['resizedSize']
                feature_ref=item['feature'];reuse_count+=1
            else:
                gray=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE);assert gray is not None
                f=base.sift(gray,c);feature_path=out/'features'/f'{digest}.npz'
                np.savez_compressed(feature_path,points=f[0],descriptors=f[1],size=f[2]);feature_ref=base.bind(feature_path)
            if digest in old_dhash:hashes[digest]=old_dhash[digest]
            else:
                with Image.open(path) as im:im.load();hashes[digest]=base.dhash(im)
            features[digest]=f;entries.append({'image':image_ref,'feature':feature_ref,'featureCount':len(f[0]),'resizedSize':f[2].tolist(),'dhash256':hashes[digest]})
        base.put(out/'feature-manifest.json',{'schemaVersion':1,'plan':ref,'items':entries,'cacheReuseSources':reuse_count,'trainingAllowed':False});event('features_complete',total=len(entries),reused=reuse_count)
        controls=[]
        for number,ctrl in enumerate(plan['positiveControls'],1):
            digest=ctrl['sourceImage']['sha256']
            if ctrl['kind']=='bound_real_child_parent':result=base.recall(features[digest],features[ctrl['referenceImage']['sha256']],hashes[digest],hashes[ctrl['referenceImage']['sha256']],c)
            else:
                with Image.open(base.checked(ctrl['sourceImage'])) as raw:raw.load();im=base.transform(raw,ctrl['transform']).convert('RGB')
                result=base.recall(base.sift(cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2GRAY),c),features[digest],base.dhash(im),hashes[digest],c)
            assert result==controls_old['controls'][number-1]['result'],'reconstruction_mismatch: positive control changed'
            controls.append({'ordinal':number,'control':ctrl,'result':result,'ok':result['recalled']})
        assert all(r['ok'] for r in controls);base.put(out/'controls.json',{'controls':controls,'ok':True,'originalControlResultsPreserved':True})
        results=[]
        for ordinal,target in enumerate(targets['targets'],1):
            digest=target['imageSha256'];hits=[];self_refs=[]
            for reference in inventory['corpus']:
                other=reference['image']['sha256']
                if other==digest:self_refs.append(reference);continue
                result=base.recall(features[digest],features[other],hashes[digest],hashes[other],c)
                if result['recalled']:hits.append({'reference':reference,'result':result})
            row={'ordinal':ordinal,'target':target,'featureCount':len(features[digest][0]),'lowFeatureQuery':len(features[digest][0])<c['lowFeatureQueryThreshold'],
                 'comparisons':len(inventory['corpus'])-len(self_refs),'selfReferenceBindings':self_refs,'recalledPairs':hits,'trainingAllowed':False,'independenceApproved':False}
            path=out/f'query-{ordinal:03d}.json';base.put(path,row);results.append({'ordinal':ordinal,'report':base.bind(path),'recalledPairs':len(hits),'comparisons':row['comparisons'],'lowFeatureQuery':row['lowFeatureQuery']});event('query_complete',ordinal=ordinal,hits=len(hits));print(json.dumps({'query':ordinal,'total':len(targets['targets']),'hits':len(hits)}),flush=True)
        report={'schemaVersion':1,'ok':True,'executionStatus':'complete','decision':'new_album_assets_recall_only_native_pair_adjudication_required',
                'inputs':{'plan':ref,'runner':base.bind(Path(__file__)),'features':base.bind(out/'feature-manifest.json'),'controls':base.bind(out/'controls.json')},
                'counts':{'newTargets':len(results),'references':len(inventory['corpus']),'comparisons':sum(r['comparisons'] for r in results),'recalledPairs':sum(r['recalledPairs'] for r in results),'lowFeatureQueries':sum(r['lowFeatureQuery'] for r in results),'positiveControlReplays':12,'old114QueriesRepeated':0,'cachedFeatureSources':reuse_count,'newFeatureSources':len(entries)-reuse_count},
                'results':results,'trainingAllowed':False,'sourceParentIndependenceQualified':False,'newModelCalls':0,'optimizerSteps':0,'elapsedSeconds':round(time.monotonic()-start,3)}
        event('terminal',counts=report['counts']);base.put(out/'report.json',report);print(json.dumps({'report':base.bind(out/'report.json'),'counts':report['counts']}),flush=True)
    except BaseException as error:
        base.put(out/'failure.json',{'ok':False,'errorType':type(error).__name__,'error':str(error),'lastPersistedSequence':seq,'trainingAllowed':False,'newModelCalls':0,'optimizerSteps':0});raise
    finally:
        for root in roots:guard.remove_ultralytics_label_caches(root)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.plan.resolve(),a.output.resolve())
