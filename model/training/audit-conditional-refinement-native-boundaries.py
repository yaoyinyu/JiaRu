"""固定全45终态输出的原像素边界审计；不调用模型、不改变旧质量判决。"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw


def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


core=module('native_boundaries_original',Path(__file__).with_name('train-conditional-nail-refinement-microfit.py'))
a=core.a


def edge(mask):return mask.astype(np.uint8)-cv2.erode(mask.astype(np.uint8),np.ones((3,3),np.uint8))


def stats(target,prediction,source_size=None,crop_box=None):
    if source_size is not None:
        width,height=source_size;x0,y0,x1,y1=crop_box
        full_target=np.zeros((height,width),bool);full_prediction=np.zeros_like(full_target)
        full_target[y0:y1,x0:x1]=target;full_prediction[y0:y1,x0:x1]=prediction
        target,prediction=full_target,full_prediction
    bi,bf=core.metric_tool.boundary_metrics(target,prediction,2)
    intersection=int((target&prediction).sum());union=int((target|prediction).sum())
    iou=intersection/max(1,union)
    return {'iou':float(iou),'boundaryIou':bi,'boundaryF1':bf,'jointPass':iou>=.75 and bi>=.75 and bf>=.9}


def panel(rgb,target,prediction,path,identity):
    """原像素ROI和焦点3倍最近邻；焦点不改变任何指标分母。"""
    te=edge(target).astype(bool);pe=edge(prediction).astype(bool)
    ys,xs=np.where(target|prediction)
    h,w=target.shape
    box=[max(0,int(xs.min())-12),max(0,int(ys.min())-12),min(w,int(xs.max())+13),min(h,int(ys.max())+13)]
    x0,y0,x1,y1=box
    source=rgb[y0:y1,x0:x1].copy();gt=source.copy();pred=source.copy();both=source.copy()
    gt[te[y0:y1,x0:x1]]=[0,255,0];pred[pe[y0:y1,x0:x1]]=[255,0,255]
    both[te[y0:y1,x0:x1]]=[0,255,0];both[pe[y0:y1,x0:x1]]=[255,0,255]
    both[(te&pe)[y0:y1,x0:x1]]=[255,255,0]
    pictures=[Image.fromarray(v).resize(((x1-x0)*3,(y1-y0)*3),Image.Resampling.NEAREST) for v in [source,gt,pred,both]]
    pw,ph=pictures[0].size
    canvas=Image.new('RGB',(pw*4,ph+48),'#181818');draw=ImageDraw.Draw(canvas)
    for i,(pic,label) in enumerate(zip(pictures,['SOURCE','GT GREEN','PRED MAGENTA','BOTH: SHARED YELLOW'])):
        canvas.paste(pic,(i*pw,48));draw.text((i*pw+5,25),label,fill='white')
    draw.text((5,5),identity+' / native pixels, focus 3x nearest',fill='white');canvas.save(path)
    return box


def build(plan_path,output,render):
    plan=a.read(plan_path)
    for b in plan['inputs'].values():a.checked(b)
    if plan['diagnostic']!={'boundaryOriginalPixels':2,'fixedThreshold':.5,'alternativeInverseDomain':'logit_bilinear_threshold_zero','oracleEditableBoundaryRadiusOriginalPixels':4,'renderScale':3}:raise ValueError('pre-registered diagnostic contract')
    report_path=Path(plan['inputs']['capacityReport']['path']);report=a.read(report_path)
    frozen=a.read(a.checked(report['inputs']['plan']))
    verifier=module('native_journal_verifier',a.checked(frozen['inputs']['trainerSource']))
    verifier.t.validate=verifier.validate
    verifier.verify(report_path)
    records,_=verifier.validate(frozen)
    attribution=a.read(plan['inputs']['errorAttribution']['path'])
    if [r['id'] for r in records]!=plan['candidateIds'] or [r['id'] for r in attribution['perCandidate']]!=plan['candidateIds']:raise ValueError('reconstruction_mismatch: all45 identities')
    with np.load(a.checked(report['finalLogits']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=plan['candidateIds']:raise ValueError('reconstruction_mismatch: logits order')
        logits=saved['logits'].copy()
    if not np.isfinite(logits).all() or logits.shape!=(45,384,384):raise ValueError('all45 finite logits')
    rows=[];artifacts=[];positive=[];source_sizes={}
    for original,values,accepted in zip(records,logits,report['perCandidate'],strict=True):
        with Image.open(a.checked(original['paths']['nativeTarget'])) as im:target=np.asarray(im).copy()>=128
        with Image.open(a.checked(original['paths']['target'])) as im:truth384=np.asarray(im).copy()>=128
        probability=(1/(1+np.exp(-np.clip(values,-80,80)))).astype(np.float32)
        native_probability=np.asarray(Image.fromarray(probability).resize(tuple(original['nativeSize']),Image.Resampling.BILINEAR))
        pred=native_probability>=.5
        native_logit=np.asarray(Image.fromarray(values.astype(np.float32)).resize(tuple(original['nativeSize']),Image.Resampling.BILINEAR))
        logit_pred=native_logit>=0
        row={'id':original['id'],'ordinal':original['ordinal'],'truthIndex':original['truthIndex'],'sourceGroup':original['sourceGroup'],
             'positive':bool(original['presenceTarget']),'nativeSize':original['nativeSize'],'pixelsFalsePositive':int((pred&~target).sum()),
             'pixelsFalseNegative':int((target&~pred).sum()),'pixelsAlternativeFalsePositive':int((logit_pred&~target).sum()),
             'pixelsAlternativeFalseNegative':int((target&~logit_pred).sum())}
        if original['presenceTarget']:
            source_path=a.checked(original['sourceImage'])
            if source_path not in source_sizes:
                with Image.open(source_path) as source:source_sizes[source_path]=source.size
            native_stats=lambda truth,guess:stats(truth,guess,source_sizes[source_path],original['cropBox'])
            current=native_stats(target,pred)
            # ROI四周有冻结完整裁片余量；再次按完整源图权威结果同构。
            if any(current[k]!=accepted[k] for k in current):raise ValueError('reconstruction_mismatch: original-scale accepted mask')
            back=np.asarray(Image.fromarray(truth384.astype(np.float32)).resize(tuple(original['nativeSize']),Image.Resampling.BILINEAR))>=.5
            oracle=native_stats(target,back)
            if oracle!=original['nativeRoundtripReference']:raise ValueError('reconstruction_mismatch: frozen supervision roundtrip')
            pred_edge=edge(pred);truth_edge=edge(target)
            near=cv2.dilate(pred_edge,np.ones((9,9),np.uint8)).astype(bool)
            repaired=pred.copy();repaired[near]=target[near]
            distance_to_truth=cv2.distanceTransform((1-truth_edge).astype(np.uint8),cv2.DIST_C,3)
            distance_to_prediction=cv2.distanceTransform((1-pred_edge).astype(np.uint8),cv2.DIST_C,3)
            pd=distance_to_truth[pred_edge.astype(bool)];td=distance_to_prediction[truth_edge.astype(bool)]
            row.update(current=current,direct384=stats(truth384,probability>=.5),roundtripOracle=oracle,
                alternateLogitInverse=native_stats(target,logit_pred),fourPixelTruthRepairWitness=native_stats(target,repaired),
                boundaryDistanceChebyshev={'predictionToTruthMedian':float(np.median(pd)),'predictionToTruthP95':float(np.percentile(pd,95)),
                    'truthToPredictionMedian':float(np.median(td)),'truthToPredictionP95':float(np.percentile(td,95))},
                errorPixelsOutsideFourPixelEditableBand=int(((target^pred)&~near).sum()))
            positive.append(row)
            if render:
                with Image.open(a.checked(original['paths']['nativeRgb'])) as im:rgb=np.asarray(im.convert('RGB')).copy()
                path=output/f"{original['id']}-native-focus.png";focus=panel(rgb,target,pred,path,original['id'])
                artifacts.append({'id':original['id'],'focusBoxInNativeRoi':focus,'file':a.bind(path)})
        else:
            if int(pred.sum())!=accepted['predictedPixels']:raise ValueError('reconstruction_mismatch: all11 empty outputs')
            row.update(currentRejected=not pred.any(),alternativeRejected=not logit_pred.any())
        rows.append(row)
    summary={}
    for key in ['current','direct384','roundtripOracle','alternateLogitInverse','fourPixelTruthRepairWitness']:
        summary[key]={'jointPassCount':sum(r[key]['jointPass'] for r in positive),'meanBoundaryIou':float(np.mean([r[key]['boundaryIou'] for r in positive])),
            'meanBoundaryF1':float(np.mean([r[key]['boundaryF1'] for r in positive])),'meanIou':float(np.mean([r[key]['iou'] for r in positive]))}
    required=int(np.ceil(34*frozen['gates']['minimumJointInstancePassRate']));needed=required-summary['current']['jointPassCount']
    witness_gain=summary['fourPixelTruthRepairWitness']['jointPassCount']-summary['current']['jointPassCount']
    negatives=[r for r in rows if not r['positive']]
    summary.update(positiveCount=len(positive),emptyCount=len(negatives),requiredJointPassCount=required,requiredAdditionalPasses=needed,
        fourPixelRepairWitnessAdditionalPasses=witness_gain,witnessGainToRequiredGainRatio=witness_gain/needed,
        currentAllEmptyRejected=all(r['currentRejected'] for r in negatives),alternateAllEmptyRejected=all(r['alternativeRejected'] for r in negatives),
        errorPixelsFalsePositive=sum(r['pixelsFalsePositive'] for r in positive),errorPixelsFalseNegative=sum(r['pixelsFalseNegative'] for r in positive))
    return {'schemaVersion':1,'ok':True,'decision':'native_boundary_diagnostics_reconstructed_no_new_model_calls',
        'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'summary':summary,'perCandidate':rows,'visualPanels':artifacts,
        'modelCalls':0,'optimizerSteps':0,'oldQualityDecision':report['decision'],'full30PilotAllowed':False,'formalTrainingApprovedImages':0,
        'scope':'All45 frozen outputs, original 2px gates; direct384 uses 2 input pixels for debugging only. Alternative interpolation is one preregistered train-only diagnostic, not threshold calibration or changed runtime. GT band replacement is an existence witness, not learned performance or a mathematical upper bound. Human review remains required.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    guard=module('native_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    plan_path=args.plan.resolve() if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path']);plan=a.read(plan_path)
    try:
        if args.verify_report:
            saved=a.read(args.verify_report);output=args.verify_report.parent
            report=build(plan_path,output,False)
            for item in saved['visualPanels']:a.checked(item['file'])
            report['visualPanels']=saved['visualPanels']
            if report!=saved:raise ValueError('reconstruction_mismatch: native diagnostics')
        else:
            output=args.output.resolve()
            if output.exists():raise FileExistsError('immutable diagnostics output exists')
            output.mkdir(parents=True);report=build(plan_path,output,True);a.write_new(output/'report.json',report)
        print(json.dumps({'ok':True,'decision':report['decision'],'summary':report['summary'],'report':a.bind(output/'report.json')},ensure_ascii=False))
    finally:
        for root in plan['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))


if __name__=='__main__':main()
