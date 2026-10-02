"""全45保存输出硬保真后原像素误差取证；原图和边缘面板不改真值。"""
from __future__ import annotations
import argparse
import importlib.util
import io
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


t=module('residual_pixel_trainer',Path(__file__).with_name('train-native-fixed-lr-microfit.py'));a=t.a
stats=module('residual_pixel_statistics',Path(__file__).with_name('native-residual-pixel-statistics.py'))


def png_bytes(image):
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


def edge(mask):
    padded=np.pad(mask.astype(np.uint8),1)
    return (padded-cv2.erode(padded,np.ones((3,3),np.uint8)))[1:-1,1:-1].astype(bool)


def panel(item,probability):
    rgb=item['rgb'];truth=item['target']>=.5;predicted=probability>=.5
    reference=rgb.copy();reference[edge(truth)]=[0,255,0]
    prediction=rgb.copy();prediction[edge(predicted)]=[0,255,255]
    errors=rgb.copy();errors[predicted&~truth]=[255,0,0];errors[~predicted&truth]=[0,80,255]
    height,width=truth.shape;canvas=Image.new('RGB',(width*4,height+28),'white');draw=ImageDraw.Draw(canvas)
    for index,(pixels,label) in enumerate(zip((rgb,reference,prediction,errors),('NATIVE RGB','REFERENCE EDGE green','PREDICTION EDGE cyan','ERROR FP red / FN blue'),strict=True)):
        canvas.paste(Image.fromarray(pixels),(index*width,28));draw.text((index*width+4,6),label,fill='black')
    return canvas


def build(plan_path,output,verify=False):
    plan=a.read(plan_path)
    for v in plan['inputs'].values():a.checked(v)
    if plan['inputs']['runnerSource']!=a.bind(Path(__file__)) or plan['inputs']['statisticsSource']!=a.bind(Path(stats.__file__)):
        raise ValueError('runner/statistics source binding')
    if plan['modelCalls'] or plan['optimizerSteps'] or plan['trainingAllowed']:raise ValueError('zero model/optimization only')
    scope=a.read(a.checked(plan['inputs']['scope']))
    for v in scope['inputs'].values():a.checked(v)
    if plan['inputs']['capacityReport']!=scope['inputs']['capacityReport']:raise ValueError('scope identity')
    report_path=a.checked(scope['inputs']['capacityReport']);capacity=a.read(report_path)
    replay=t.verify(report_path)
    frozen=a.read(a.checked(capacity['inputs']['plan']));_,parent,records=t.validate(frozen)
    h,data=t.s.native_data(parent,records)
    with np.load(a.checked(capacity['finalDeltas']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=scope['candidateIds']:raise ValueError('reconstruction_mismatch: saved candidateIds')
        deltas=[saved[f'delta_{i:03d}'].copy() for i in range(45)]
    accepted,summary=t.metrics(data,deltas,h)
    if accepted!=capacity['perCandidate'] or summary!=capacity['metrics'] or frozen['gates']!=scope['qualityGatesUnchanged']:
        raise ValueError('reconstruction_mismatch: accepted masks/all45 metrics/gates')
    failed=[row['id'] for row in accepted if row['positive'] and not row['jointPass']]
    if failed!=scope['failedIds']:raise ValueError('reconstruction_mismatch: failed identities')
    if not verify:
        if output.exists():raise FileExistsError('analysis output already exists')
        output.mkdir(parents=True)
    results=[];parents={};artifacts=[]
    def artifact(path,content):
        if verify:
            if not path.is_file() or path.read_bytes()!=content:raise ValueError('reconstruction_mismatch: panel/original pixels')
        else:
            with path.open('xb') as stream:stream.write(content)
        return a.bind(path)
    for item,delta,quality in zip(data,deltas,accepted,strict=True):
        probability=h.apply_native_delta(item['base'],delta,item['band'])
        pixel=stats.summarize(item['base'],probability,item['target']>=.5,item['band'])
        result={'id':quality['id'],'positive':quality['positive'],'jointPass':quality.get('jointPass'),'pixel':pixel}
        if quality['id'] in failed:
            row=item['row'];source=a.checked(row['sourceImage'])
            with Image.open(source) as im:
                full=im.convert('RGB');crop=np.asarray(full.crop(tuple(row['cropBox'])))
                if not np.array_equal(crop,item['rgb']):raise ValueError('reconstruction_mismatch: original native RGB crop')
                key=row['sourceImage']['sha256']
                if key not in parents:
                    parents[key]={'source':row['sourceImage'],'sourceGroup':row['sourceGroup'],
                                  'originalPng':artifact(output/f'source-{row["ordinal"]:03d}-original.png',png_bytes(full))}
            result['visual']={'source':row['sourceImage'],'sourceGroup':row['sourceGroup'],'truth':row['candidateTruth'],
                              'nativeRgb':row['paths']['nativeRgb'],'nativeTarget':row['paths']['nativeTarget'],
                              'cropBox':row['cropBox'],'truthIndex':row['truthIndex'],
                              'panel':artifact(output/f'{quality["id"]}-panel.png',png_bytes(panel(item,probability)))}
            artifacts.append(result['visual'])
        results.append(result)
    keys=results[0]['pixel'].keys();aggregate={key:sum(row['pixel'][key] for row in results) for key in keys}
    old=a.read(a.checked(scope['inputs']['outcomesReport']))
    if aggregate['falsePositiveInsideBand']+aggregate['falseNegativeInsideBand']!=old['wrongPixels']['insideBand'] or aggregate['falsePositiveOutsideBand']+aggregate['falseNegativeOutsideBand']!=old['wrongPixels']['outsideBand']:
        raise ValueError('reconstruction_mismatch: frozen error count')
    return {'schemaVersion':1,'ok':True,'decision':'all45_saved_metrics_and_native_pixel_error_reconstruction_pass_visual_review_pending',
            'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'metrics':summary,'qualityDecisionUnchanged':capacity['decision'],
            'perCandidate':results,'aggregate':aggregate,'failedIds':failed,'visualArtifacts':artifacts,'originalImages':list(parents.values()),
            'journal':replay['journal'],'learningRateRecording':replay['learningRateRecording'],
            'diagnosticConfidenceBins':{'highConfidenceFalsePositive':'>=0.9','highConfidenceFalseNegative':'<=0.1','deploymentThreshold':0.5,'calibration':False},
            'modelCalls':0,'optimizerSteps':0,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
            'visualReviewPerformed':False,'scope':'Counts are native raster diagnosis, actual quality reproduced in original2px domain. Rendering/replay is not original-image visual approval or causal/generalization evidence; no role/truth/threshold changes.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--verify-report',type=Path);args=parser.parse_args()
    saved=a.read(args.verify_report) if args.verify_report else None
    plan_path=Path(saved['inputs']['plan']['path']) if saved else args.plan.resolve()
    output=args.verify_report.parent if saved else args.output.resolve()
    guard=module('residual_pixels_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    try:
        report=build(plan_path,output,verify=saved is not None)
        if saved is not None:
            if report!=saved:raise ValueError('reconstruction_mismatch: all45 residual report')
        else:a.write_new(output/'residual-report.json',report)
        print(json.dumps({'ok':True,'decision':report['decision'],'aggregate':report['aggregate'],'report':a.bind(output/'residual-report.json')},ensure_ascii=False),flush=True)
    finally:
        plan=a.read(plan_path);scope=a.read(plan['inputs']['scope']['path']);capacity=a.read(scope['inputs']['capacityPlan']['path']);parent=a.read(capacity['inputs']['parentPlan']['path'])
        for directory in parent['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':main()
