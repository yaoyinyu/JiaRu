"""只读冻结原像素输出：保持候选分母，定位边界误差及像素BCE监督分布。"""
from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('saved_boundary_data', HERE/'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

def boundary_error_distribution(truth, prediction, logits):
    if truth.dtype != bool or prediction.dtype != bool or logits.dtype != np.float32 or truth.shape != prediction.shape or truth.shape != logits.shape or not np.isfinite(logits).all():
        raise ValueError('native storage reconstruction_mismatch')
    edge = truth & ~cv2.erode(truth.astype(np.uint8), np.ones((3,3),np.uint8)).astype(bool)
    error = truth ^ prediction
    probability = 1/(1+np.exp(-logits.astype(np.float64)))
    derivative = np.abs(probability-truth)
    bce = np.logaddexp(0, logits.astype(np.float64))-logits*truth
    cumulative = {}
    for radius in (2,4,8):
        strip = cv2.dilate(edge.astype(np.uint8),np.ones((2*radius+1,2*radius+1),np.uint8)).astype(bool)
        cumulative[str(radius)] = {
            'stripPixels':int(strip.sum()), 'roiFraction':float(strip.mean()),
            'errorPixels':int((error & strip).sum()), 'outsideErrorPixels':int((error & ~strip).sum()),
            'falseNegativePixels':int((truth & ~prediction & strip).sum()),
            'falsePositivePixels':int((prediction & ~truth & strip).sum()),
            'stripBceMean':float(bce[strip].mean()) if strip.any() else 0.,
            'stripAbsoluteBceDerivative':float(derivative[strip].sum()),
            'outsideAbsoluteBceDerivative':float(derivative[~strip].sum()),
        }
    return {'roiPixels':truth.size,'truthPixels':int(truth.sum()),'errorPixels':int(error.sum()),
            'globalBceMean':float(bce.mean()),'cumulativeOriginalPixelStrips':cumulative}

def analyze(plan_path):
    plan=d.read(d.bind(plan_path))
    if plan['contract'] != {'radiiOriginalPixels':[2,4,8],'additionalModelCalls':0,'optimizerSteps':0,'trainCandidateCount':68,'positiveCount':66,'rejectCount':2,'toleranceOriginalPixels':2}:
        raise ValueError('frozen diagnostic contract')
    for ref in plan['inputs'].values():d.checked(ref)
    report=d.read(plan['inputs']['capacity']); capacity_plan=d.read(report['inputs']['plan']); data=d.read(capacity_plan['inputs']['materialization']); input_plan=d.read(data['plan'])
    rows=[r for r in data['records'] if r['split']=='train']
    if [r['candidateIdentity'] for r in rows] != capacity_plan['candidateIdentities'] or len(rows)!=68 or sum(r['presenceTarget'] for r in rows)!=66:
        raise ValueError('candidate reconstruction_mismatch')
    net=d.load(d.checked(capacity_plan['inputs']['modelSource']),'saved_boundary_model')
    roi=d.load(d.checked(input_plan['inputs']['roiHelper']),'saved_boundary_metric')
    # 守卫必须先于解码；读取只限绑定训练候选，不读内部val/受保护图片。
    guard=d.load(d.checked(input_plan['inputs']['readOnlyGuard']),'saved_boundary_guard');guard.install_read_only_ultralytics_image_check()
    metrics=[]; outputs=[]
    try:
        for row in rows:
            with Image.open(d.checked(row['paths']['nativeTarget'])) as im:im.load();truth=np.asarray(im).copy()>=128
            pred_ref=plan['predictions'][str(row['ordinal'])]
            with np.load(d.checked(pred_ref),allow_pickle=False) as z:
                logits=z['logits'].copy();presence=float(z['presenceLogit'])
                if set(z.files)!={'logits','presenceLogit'} or z['presenceLogit'].dtype != np.float32:raise ValueError('prediction storage')
            prediction=net.decode(logits,presence)
            if row['presenceTarget']:
                b=roi.boundary_stats(truth,prediction,2); iou=int((truth & prediction).sum())/max(1,int((truth | prediction).sum()))
                metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':True,'iou':iou,**b,'jointPass':iou>=.75 and b['boundaryIoU']>=.75 and b['boundaryF1']>=.9})
                outputs.append({'candidateIdentity':row['candidateIdentity'],**boundary_error_distribution(truth,prediction,logits)})
            else:metrics.append({'candidateIdentity':row['candidateIdentity'],'positive':False,'outputPixels':int(prediction.sum()),'rejected':not prediction.any()})
        if metrics != report['perCandidate']:raise ValueError('reconstruction_mismatch: saved authoritative metrics')
        positive=[r for r in metrics if r['positive']]
        if len(outputs)!=66:raise ValueError('positive denominator')
        strips={}
        for radius in ('2','4','8'):
            values=[r['cumulativeOriginalPixelStrips'][radius] for r in outputs]
            errors=sum(v['errorPixels'] for v in values);total=sum(r['errorPixels'] for r in outputs)
            strips[radius]={'errorPixels':errors,'errorFraction':errors/max(1,total),
                'roiFractionMedian':float(np.median([v['roiFraction'] for v in values])),
                'normalizationAmplificationMedian':float(np.median([1/max(v['roiFraction'],1e-30) for v in values])),
                'derivativeSum':sum(v['stripAbsoluteBceDerivative'] for v in values),
                'outsideDerivativeSum':sum(v['outsideAbsoluteBceDerivative'] for v in values)}
        return {'schemaVersion':1,'ok':True,'decision':'full68_saved_metric_reconstruction_boundary_distribution_diagnostic',
            'plan':d.bind(plan_path),'records':outputs,'all68MetricsReconstructed':True,'positiveCount':66,'rejectCount':2,
            'summary':{'errorPixels':sum(r['errorPixels'] for r in outputs),'strips':strips,
                'iou075Pass':sum(r['iou']>=.75 for r in positive),'boundaryIou075Pass':sum(r['boundaryIoU']>=.75 for r in positive),
                'boundaryF109Pass':sum(r['boundaryF1']>=.9 for r in positive),'jointPass':sum(r['jointPass'] for r in positive)},
            'interpretation':'监督分布诊断；不证明梯度冲突因果，不改变输出阈值、质量门、完整目标或数据角色',
            'additionalModelCalls':0,'optimizerSteps':0,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for root in d.read(input_plan['inputs']['trainingContract'])['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path);parser.add_argument('--verify-report',type=Path);args=parser.parse_args()
    result=analyze(args.plan.resolve())
    if args.verify_report and result!=d.read(d.bind(args.verify_report)):raise ValueError('diagnostic replay mismatch')
    if args.output:d.new(args.output.resolve(),result)
    print(json.dumps({'ok':True,'summary':result['summary']}))
