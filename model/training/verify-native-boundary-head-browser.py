"""重放全45实际浏览器打包/组合及两后端原输出；未训练接口门。"""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('native_browser_static',Path(__file__).with_name('audit-native-boundary-head-feasibility.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);a=s.a


def build(static_path,capture_path):
    static=a.read(static_path);plan=a.read(a.checked(static['inputs']['plan']));parent,records=s.validate(plan)
    live=a.read(capture_path);folder=static_path.parent
    if not static['ok'] or not live['ok'] or live['staticSha256']!=a.sha(static_path) or live['modelHashes']!={k:v['file']['sha256'] for k,v in static['models'].items()}:raise ValueError('live/static identity or failure')
    if [r['id'] for r in live['nativeResults']]!=parent['candidateIds'] or [r['id'] for r in static['nativeControls']]!=parent['candidateIds']:raise ValueError('all45 denominator')
    outputs=[]
    for recorded,control in zip(live['nativeResults'],static['nativeControls'],strict=True):
        files=control['files'];width,height=control['nativeSize'];pixels=width*height;identity=control['id']
        bindings={k:a.bind(folder/'browser-capture'/f'{identity}-{k}.bin') for k in ['packed','band','probability','mask']}
        packed=np.fromfile(bindings['packed']['path'],np.float32);expected=np.fromfile(a.checked(files['packed']),np.float32)
        band=np.fromfile(bindings['band']['path'],np.uint8);expected_band=np.fromfile(a.checked(files['band']),np.uint8)
        probability=np.fromfile(bindings['probability']['path'],np.float32);expected_p=np.fromfile(a.checked(files['composition-probability']),np.float32)
        mask=np.fromfile(bindings['mask']['path'],np.uint8);expected_mask=np.fromfile(a.checked(files['composition-mask']),np.uint8)
        base=np.fromfile(a.checked(files['base']),np.float32)
        if packed.size!=6*pixels or probability.size!=pixels or band.size!=pixels or mask.size!=pixels or not np.isfinite(packed).all() or not np.isfinite(probability).all():raise ValueError('all raw native captures')
        packed_error=float(np.max(np.abs(packed.astype(np.float64)-expected)));probability_error=float(np.max(np.abs(probability.astype(np.float64)-expected_p)))
        bm=int((band!=expected_band).sum());mm=int((mask!=expected_mask).sum());outside=int((probability.view(np.uint32)[band==0]!=base.view(np.uint32)[band==0]).sum())
        if any(recorded[k]!=v for k,v in [('packedError',packed_error),('probabilityError',probability_error),('bandMismatch',bm),('maskMismatch',mm),('outsideBitMismatch',outside)]):raise ValueError('browser reconstruction_mismatch')
        if not recorded['ok'] or packed_error>plan['limits']['packingAbsoluteError'] or probability_error>plan['limits']['compositionAbsoluteError'] or bm or mm or outside or recorded['initialMaskMismatch'] or recorded['kind']!=control['kind']:raise ValueError('native parity gate')
        outputs.extend(bindings.values())
    expected_cases=[(key,identity) for key in ['zero','control'] for identity in plan['runtimeProbeIds']]
    if [r['backend'] for r in live['backendResults']]!=plan['requiredBackends']:raise ValueError('backend count/order')
    for backend in live['backendResults']:
        if not backend['ok'] or [(r.get('modelKey'),r.get('id')) for r in backend['cases']]!=expected_cases:raise ValueError('all fixed backend cases')
        for row in backend['cases']:
            reference=next(p for p in static['runtimeProbes'] if p['modelKey']==row['modelKey'] and p['id']==row['id'])
            path=folder/'browser-capture'/f"{backend['backend']}-{row['modelKey']}-{row['id']}.bin"
            actual=np.fromfile(path,np.float32);cpu=np.fromfile(a.checked(reference['cpu']),np.float32)
            if actual.size!=cpu.size or not np.isfinite(actual).all() or row['dims']!=reference['dims']:raise ValueError('native backend output')
            delta=float(np.max(np.abs(actual.astype(np.float64)-cpu.astype(np.float64))))
            if row['maxAbsoluteError']!=delta or delta>plan['limits']['browserAbsoluteError'] or not row['ok'] or row['inputNames']!=['native_input'] or row['outputNames']!=['delta']:raise ValueError('native backend CPU mismatch')
            outputs.append(a.bind(path))
    if [live[k] for k in ['validEmptyKind','nonFiniteKind','invalidShapeKind']]!=['rejected','execution-error','execution-error']:raise ValueError('valid-empty/error separation')
    return {'schemaVersion':1,'ok':True,'decision':'native_head_initial_gradient_static_browser_feasible_for_preregistered_capacity',
            'inputs':{'staticReport':a.bind(static_path),'liveBrowser':a.bind(capture_path),'sourceVerifier':a.bind(Path(__file__)),
                      'compiledRuntime':a.bind(folder/'native-runtime.mjs'),'harness':a.bind(folder/'browser.html'),'config':a.bind(folder/'browser-config.json'),
                      'preparerSource':plan['inputs']['browserPreparer'],'serverSource':plan['inputs']['browserServer']},
            'capturedOutputs':outputs,'browser':live,'optimizerSteps':0,'upstreamModelCalls':0,'trainingApprovedImages':0,
            'qualityEvidence':False,'mobileSlaEvidence':False,'productionConnected':False,'full30PilotAllowed':False,
            'scope':'All45 native packing/composition controls and3 fixed native sizes for zero/nonzero untrained heads on both actual browser backends. Prepared native pixels, no original-image extraction pipeline, no learned mask or independent quality claim.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--static-report',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    if args.verify_report:
        saved=a.read(args.verify_report)
        for binding in saved['inputs'].values():a.checked(binding)
        report=build(Path(saved['inputs']['staticReport']['path']),Path(saved['inputs']['liveBrowser']['path']))
        if saved!=report:raise ValueError('browser report reconstruction_mismatch')
        path=args.verify_report
    else:
        report=build(args.static_report.resolve(),args.capture.resolve());a.write_new(args.output,report);path=args.output
    print(json.dumps({'ok':True,'decision':'verified' if args.verify_report else report['decision'],'nativeCount':45,'capturedBinaryCount':len(report['capturedOutputs']),'report':a.bind(path)},ensure_ascii=False))


if __name__=='__main__':main()
