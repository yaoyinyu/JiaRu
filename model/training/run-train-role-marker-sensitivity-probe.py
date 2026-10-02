"""单次train角色标记敏感性探针；保存原像素预测，重放不加载模型。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time

NAMES=['original','remove','blank_remove_control','occlude','blank_occlude_control','move_marker','blank_move_control']
PAIRS=[('original','remove'),('original','blank_remove_control'),('original','occlude'),('original','blank_occlude_control'),('move_marker','blank_move_control')]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(ref):
    p=Path(ref['path']).resolve()
    if not p.is_file() or sha(p)!=ref['sha256']:raise ValueError('reconstruction_mismatch: '+str(p))
    return p
def read(ref):return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref,name):
    p=checked(ref);sys.path.insert(0,str(p.parent))
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def environment():
    return {'python':platform.python_version(),'executable':str(Path(sys.executable).resolve()),'platform':platform.platform(),
            'packages':{k:importlib.metadata.version(k) for k in ('torch','ultralytics','numpy','scipy','Pillow','opencv-python')}}
def durable_new(path,value):
    with Path(path).open('xb') as f:
        f.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'));f.flush();os.fsync(f.fileno())
def journal(folder,sequence,value):
    durable_new(folder/f'{sequence:06d}.json',{'sequence':sequence,'value':value})

def validate_scope(plan,pack):
    if plan['contract']['variantOrder']!=NAMES or not plan['contract']['oneInferencePerVariant']:raise ValueError('variant contract drift')
    if [r['ordinal'] for r in plan['sources']]!=[r['ordinal'] for r in pack['records']]:raise ValueError('full source order drift')
    if len({r['ordinal'] for r in plan['sources']})!=len(plan['sources']):raise ValueError('duplicate source')
    if len(plan['sources'])!=plan['counts']['sourceImages'] or sum(r['completeVisibleNails'] for r in plan['sources'])!=plan['counts']['completeVisibleNails']:raise ValueError('truth denominator drift')
    if plan['counts']['plannedInferenceInputs']!=len(plan['sources'])*len(NAMES):raise ValueError('input budget drift')
    for r,p in zip(plan['sources'],pack['records'],strict=True):
        for k in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails','currentSplit','upstreamDevelopmentSplit','parents','trainingUse'):
            if r[k]!=p[k]:raise ValueError('source identity or lineage drift')
        if r['currentSplit']!='train' or r['trainingUse']!='prohibited':raise ValueError('only prohibited train-role diagnostic sources allowed')
        if list(r['variants'])!=NAMES or any(r['variants'][k]!=p['variants'][k] for k in NAMES):raise ValueError('variant identity drift')

def save_prediction(path,boxes,confidence,classes,masks):
    import numpy as np
    if masks.dtype!=np.bool_ or masks.ndim!=3:raise ValueError('native binary mask contract')
    n,h,w=masks.shape
    if boxes.shape!=(n,4) or confidence.shape!=(n,) or classes.shape!=(n,) or not all(np.isfinite(v).all() for v in (boxes,confidence,classes)):raise ValueError('prediction cardinality or finite values')
    if n and (classes!=0).any():raise ValueError('unexpected non-nail class')
    bits=np.packbits(masks.reshape(-1),bitorder='little')
    with Path(path).open('xb') as f:
        np.savez_compressed(f,boxes=boxes.astype(np.float32),confidence=confidence.astype(np.float32),classes=classes.astype(np.float32),
                            maskShape=np.array([n,h,w],np.int64),masksPacked=bits)
        f.flush();os.fsync(f.fileno())
    return bind(path)

def load_prediction(ref,size):
    import numpy as np
    with np.load(checked(ref),allow_pickle=False) as z:
        if set(z.files)!={'boxes','confidence','classes','maskShape','masksPacked'}:raise ValueError('prediction storage keys')
        shape=z['maskShape'];boxes=z['boxes'];conf=z['confidence'];classes=z['classes'];bits=z['masksPacked']
        if shape.dtype!=np.int64 or shape.shape!=(3,) or (shape<0).any():raise ValueError('invalid mask shape')
        n,h,w=map(int,shape)
        if [w,h]!=size or boxes.shape!=(n,4) or conf.shape!=(n,) or classes.shape!=(n,):raise ValueError('native prediction dimensions mismatch')
        if any(v.dtype!=np.float32 for v in (boxes,conf,classes)) or bits.dtype!=np.uint8 or bits.ndim!=1:raise ValueError('prediction storage dtype')
        if bits.size!=(n*h*w+7)//8 or any(not np.isfinite(v).all() for v in (boxes,conf,classes)):raise ValueError('invalid prediction bytes')
        unpack=np.unpackbits(bits,bitorder='little')
        if unpack[n*h*w:].any():raise ValueError('nonzero packed padding')
        masks=unpack[:n*h*w].reshape((n,h,w)).astype(bool)
        if n and (classes!=0).any():raise ValueError('unexpected class')
        return boxes,conf,classes,masks

def truth_masks(source,size):
    from PIL import Image,ImageDraw
    import numpy as np
    doc=read(source['annotation'])
    if len(doc['annotations'])!=source['completeVisibleNails']:raise ValueError('complete nail denominator drift')
    masks=[]
    for a in doc['annotations']:
        im=Image.new('L',tuple(size));ImageDraw.Draw(im).polygon([(p['x'],p['y']) for p in a['polygon']],fill=255);masks.append(np.asarray(im)>0)
    return np.stack(masks)

def match_masks(predictions,truths,threshold=.75):
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    if predictions.shape[1:]!=truths.shape[1:]:raise ValueError('truth/prediction pixel domain mismatch')
    ious=np.zeros((len(truths),len(predictions)),np.float64)
    tp=[int(m.sum()) for m in truths];pp=[int(m.sum()) for m in predictions]
    for i,t in enumerate(truths):
        for j,p in enumerate(predictions):
            intersection=int((t&p).sum());union=tp[i]+pp[j]-intersection
            ious[i,j]=intersection/union if union else 0.
    rows,cols=linear_sum_assignment(-ious) if ious.size else ([],[])
    assignment=[{'truthIndex':int(i)+1,'predictionIndex':int(j)+1,'iou':float(ious[i,j])} for i,j in zip(rows,cols,strict=True)]
    matched=[m for m in assignment if m['iou']>=threshold]
    return {'iouMatrix':ious.tolist(),'assignment':assignment,'matches':matched,
            'missedTruthIndices':[i+1 for i in range(len(truths)) if i+1 not in {m['truthIndex'] for m in matched}],
            'unmatchedPredictionIndices':[j+1 for j in range(len(predictions)) if j+1 not in {m['predictionIndex'] for m in matched}],
            'truthMaskPixels':tp,'predictionMaskPixels':pp}

def comparison(a,b,ma,mb):
    import numpy as np
    ua=np.any(ma,axis=0);ub=np.any(mb,axis=0);union=int((ua|ub).sum())
    am=set(a['missedTruthIndices']);bm=set(b['missedTruthIndices'])
    return {'candidateCountDelta':len(mb)-len(ma),'matchedNailDelta':len(b['matches'])-len(a['matches']),
            'newMissedTruthIndices':sorted(bm-am),'recoveredTruthIndices':sorted(am-bm),'persistentMissedTruthIndices':sorted(am&bm),
            'unionSymmetricDifferencePixels':int((ua^ub).sum()),'unionIoU':int((ua&ub).sum())/union if union else 1.}

def reconstruct(execution_ref,output):
    execution=read(execution_ref);inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity drift')
    guard=module(inputs['readOnlyGuard'],'probe_replay_guard');guard.install_read_only_ultralytics_image_check()
    try:
        plan=read(inputs['plan']);pack=read(plan['inputs']['variantPack']);validate_scope(plan,pack)
        checked(plan['inputs']['frozenWeight']);read(inputs['environment'])
        scope_by={r['ordinal']:r for r in pack['records']}
        claim=read(bind(output/'budget-claim-reference.json'));checked(claim['claim'])
        if read(claim['claim'])['execution']!=execution_ref:raise ValueError('budget identity mismatch')
        events=[]
        for seq,p in enumerate(sorted((output/'events').glob('*.json')),1):
            doc=json.loads(p.read_text(encoding='utf-8'))
            if doc['sequence']!=seq or p.name!=f'{seq:06d}.json':raise ValueError('event sequence gap')
            events.append(doc['value'])
        expected=len(plan['sources'])*len(NAMES)
        if len(events)!=expected*2+2 or events[0]['phase']!='prepared' or events[-1]['phase']!='complete':raise ValueError('incomplete or ambiguous inference budget')
        if events[0]['completedInputs']!=0 or events[0]['attemptedInputs']!=0:raise ValueError('nonzero initial progress')
        if events[-1]['completedInputs']!=expected or events[-1]['attemptedInputs']!=expected:raise ValueError('input accounting mismatch')
        records=[];index=0;aggregates={k:{'matchedNails':0,'missedNails':0,'missedImages':0,'candidateCount':0,'unmatchedPredictions':0} for k in NAMES}
        for s in plan['sources']:
            p=scope_by[s['ordinal']];truths=truth_masks(s,p['imageSize']);rows={};masks={}
            for name in NAMES:
                index+=1;started=events[index*2-1];done=events[index*2]
                if started['phase']!='input_started' or done['phase']!='input_complete':raise ValueError('per-input event order')
                for d in (started,done):
                    if d['inputIndex']!=index or d['ordinal']!=s['ordinal'] or d['variant']!=name or d['input']!=s['variants'][name]:raise ValueError('input identity or order drift')
                    if d['attemptedInputs']!=index:raise ValueError('attempted-input sequence drift')
                expected_path=output/'predictions'/f'{index:03d}-source-{s["ordinal"]:03d}-{name}.npz'
                if checked(done['prediction'])!=expected_path.resolve():raise ValueError('prediction slot identity drift')
                if started['completedInputs']!=index-1 or done['completedInputs']!=index:raise ValueError('confirmation sequence drift')
                checked(s['variants'][name]);boxes,conf,classes,mask=load_prediction(done['prediction'],p['imageSize']);masks[name]=mask
                row=match_masks(mask,truths,execution['controls']['truthIoUThreshold']);rows[name]={'prediction':done['prediction'],'boxesXyxy':boxes.tolist(),'confidence':conf.tolist(),'classes':classes.tolist(),'instanceCount':len(mask),**row}
                a=aggregates[name];a['matchedNails']+=len(row['matches']);a['missedNails']+=len(row['missedTruthIndices']);a['missedImages']+=bool(row['missedTruthIndices']);a['candidateCount']+=len(mask);a['unmatchedPredictions']+=len(row['unmatchedPredictionIndices'])
            comparisons={f'{a}__{b}':comparison(rows[a],rows[b],masks[a],masks[b]) for a,b in PAIRS}
            records.append({**{k:s[k] for k in ('ordinal','fileName','sourceGroup','sourceImage','annotation','completeVisibleNails','currentSplit','upstreamDevelopmentSplit','parents','trainingUse')},
                            'imageSize':p['imageSize'],'predictions':rows,'comparisons':comparisons})
        return {'schemaVersion':1,'ok':True,'decision':'train_role_marker_sensitivity_diagnostic_only','execution':execution_ref,'inputs':inputs,'contract':plan['contract'],
                'records':records,'counts':{**plan['counts'],'confirmedInferenceInputs':expected,'progressEvents':len(events)},'aggregateByVariant':aggregates,
                'comparisonSummary':{f'{a}__{b}':{'sourcesWithCandidateCountChange':sum(r['comparisons'][f'{a}__{b}']['candidateCountDelta']!=0 for r in records),
                                               'sourcesWithTruthMatchMigration':sum(bool(r['comparisons'][f'{a}__{b}']['newMissedTruthIndices'] or r['comparisons'][f'{a}__{b}']['recoveredTruthIndices']) for r in records),
                                               'sourcesWithAnyUnionMaskDifference':sum(r['comparisons'][f'{a}__{b}']['unionSymmetricDifferencePixels']!=0 for r in records)} for a,b in PAIRS},
                'modelCalls':expected,'optimizerSteps':0,'formalTrainingApprovedImages':0,'trainingAllowed':False,'full30PilotAllowed':False,
                'independentShortcutExclusionProven':False,'dualPathStageBQualityEvaluated':False,'wholeSourceGroupsApproved':False,
                'limitations':['Train-only existing Stage A developer weight','Background texture and global context remain confounds','No effect does not prove shortcut absence or formal quality']}
    finally:guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))

def run(execution_path):
    execution_ref=bind(execution_path);execution=read(execution_ref);inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve():raise ValueError('runner identity drift')
    if environment()!=read(inputs['environment']):raise ValueError('frozen environment mismatch')
    guard=module(inputs['readOnlyGuard'],'probe_guard');guard.install_read_only_ultralytics_image_check()
    output=Path(execution['outputRoot']);completed=attempted=sequence=0;t0=time.monotonic();claimed=False
    try:
        plan=read(inputs['plan']);usability=read(plan['inputs']['usability']);pack=read(plan['inputs']['variantPack']);validate_scope(plan,pack)
        if not usability['diagnosticProbePrerequisitesMet'] or usability['ceiling']['missingSources']:raise ValueError('diagnostic input gate not met')
        matcher=module(pack['inputs']['runnerSource'],'matched_input_verifier')
        if matcher.audit(usability['execution'])!=usability:raise ValueError('reconstruction_mismatch: usability')
        for s in plan['sources']:
            checked(s['sourceImage']);checked(s['annotation'])
            for ref in s['variants'].values():checked(ref)
        weight=checked(plan['inputs']['frozenWeight'])
        contract=plan['contract'];controls=execution['controls']
        if [contract[k] for k in ('imgsz','conf','iou','device','retinaMasks')]!=[512,.25,.7,'cpu',True] or controls['truthIoUThreshold']!=.75:raise ValueError('fixed probe contract drift')
        claim_path=checked(inputs['plan']).parent/f"marker-probe-budget-{inputs['plan']['sha256']}.json"
        if output.exists():raise FileExistsError(output)
        durable_new(claim_path,{'execution':execution_ref,'scope':inputs['plan'],'plannedInputs':plan['counts']['plannedInferenceInputs'],'resumingAllowed':False})
        claimed=True;output.mkdir();(output/'events').mkdir();(output/'predictions').mkdir()
        durable_new(output/'budget-claim-reference.json',{'claim':bind(claim_path)})
        sequence+=1;journal(output/'events',sequence,{'phase':'prepared','completedInputs':0,'attemptedInputs':0})
        import torch
        import cv2
        import numpy as np
        from ultralytics import YOLO
        torch.set_num_threads(controls['cpuThreads']);torch.manual_seed(controls['seed'])
        model=YOLO(str(weight));sizes={r['ordinal']:r['imageSize'] for r in pack['records']}
        for s in plan['sources']:
            for name in NAMES:
                attempted+=1;input_ref=s['variants'][name]
                event={'inputIndex':attempted,'ordinal':s['ordinal'],'variant':name,'input':input_ref}
                sequence+=1;journal(output/'events',sequence,{'phase':'input_started','completedInputs':completed,'attemptedInputs':attempted,**event})
                image=cv2.imdecode(np.frombuffer(checked(input_ref).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                if image is None or list(image.shape[:2][::-1])!=sizes[s['ordinal']]:raise ValueError('input pixel mapping mismatch')
                result=model.predict(source=image,imgsz=contract['imgsz'],conf=contract['conf'],iou=contract['iou'],device='cpu',retina_masks=True,
                                     max_det=controls['maxDet'],verbose=False,save=False,stream=False)[0]
                boxes=result.boxes.xyxy.cpu().numpy().astype(np.float32);confidence=result.boxes.conf.cpu().numpy().astype(np.float32);classes=result.boxes.cls.cpu().numpy().astype(np.float32)
                if result.masks is None:
                    if len(boxes):raise ValueError('boxes without segmentation masks are execution failure')
                    masks=np.zeros((0,*image.shape[:2]),bool)
                else:masks=result.masks.data.cpu().numpy()>.5
                if masks.shape!=(len(boxes),*image.shape[:2]):raise ValueError('retina mask native dimensions mismatch')
                prediction=save_prediction(output/'predictions'/f'{attempted:03d}-source-{s["ordinal"]:03d}-{name}.npz',boxes,confidence,classes,masks)
                completed+=1;sequence+=1
                journal(output/'events',sequence,{'phase':'input_complete','completedInputs':completed,'attemptedInputs':attempted,'prediction':prediction,**event})
                if completed%7==0:print(json.dumps({'confirmedInputs':completed,'plannedInputs':plan['counts']['plannedInferenceInputs'],'lastOrdinal':s['ordinal']}),flush=True)
        sequence+=1;journal(output/'events',sequence,{'phase':'complete','completedInputs':completed,'attemptedInputs':attempted})
        report=reconstruct(execution_ref,output);durable_new(output/'model-probe-report.json',report)
        durable_new(output/'terminal.json',{'phase':'complete','completedInputs':completed,'attemptedInputs':attempted,'wallSeconds':time.monotonic()-t0,'report':bind(output/'model-probe-report.json')})
        print(json.dumps({k:report[k] for k in ('ok','decision','counts','aggregateByVariant','comparisonSummary')}),flush=True)
    except BaseException as error:
        if claimed:
            failure={'phase':'aborted','completedInputs':completed,'attemptedInputs':attempted,'exceptionType':type(error).__name__,'message':str(error),'execution':execution_ref,'resumingAllowed':False}
            failure_path=output/'exception-terminal.json' if output.is_dir() else Path(str(output)+'-exception-terminal.json')
            durable_new(failure_path,failure)
        raise
    finally:guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))

def main():
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    if args.verify_report:
        old=json.loads(args.verify_report.read_text(encoding='utf-8'))
        if reconstruct(old['execution'],args.verify_report.parent)!=old:raise ValueError('reconstruction_mismatch: stored predictions')
        print(json.dumps({'ok':True,'decision':'saved_prediction_replay_identical','additionalModelCalls':0}));return
    if not args.execution:p.error('--execution required')
    run(args.execution)
if __name__=='__main__':main()
