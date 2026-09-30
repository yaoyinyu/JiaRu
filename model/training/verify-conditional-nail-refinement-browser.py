"""绑定浏览器真实捕获、CPU参考和零优化接口门；不批准模型发布。"""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('conditional_static',Path(__file__).with_name('audit-conditional-nail-refinement-feasibility.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def build(static_path, capture_path):
    static=a.read(static_path);plan=a.read(a.checked(static['inputs']['plan']))
    a.validate(plan)
    live=a.read(capture_path);folder=static_path.parent
    if not static['ok'] or live['ok'] is not True or live['modelSha256']!=static['model']['sha256'] or live['staticSha256']!=a.sha(static_path):raise ValueError('browser/static identity or failure')
    if static['optimizerSteps']!=0 or static['trainingApprovedImages']!=0:raise ValueError('zero optimization scope')
    rows=live['backendResults'];expected_ids=plan['runtimeProbeIds']
    if [r['backend'] for r in rows]!=plan['requiredBackends']:raise ValueError('both actual browser backends required')
    binaries=[]
    probes={r['id']:r for r in static['runtimeProbes']}
    for row in rows:
        if not row['ok'] or row['inputNames']!=['candidate_input'] or row['outputNames']!=['logits'] or [r['id'] for r in row['probes']]!=expected_ids:raise ValueError('backend interface')
        for probe in row['probes']:
            file=folder/'browser-capture'/f"{row['backend']}-{probe['id']}.bin"
            values=np.fromfile(file,np.float32)
            reference=np.fromfile(a.checked(probes[probe['id']]['files']['cpu']),np.float32)
            if values.size!=384**2 or not np.isfinite(values).all() or probe['dims']!=[1,1,384,384]:raise ValueError('all finite output pixels')
            delta=float(np.max(np.abs(values.astype(np.float64)-reference.astype(np.float64))))
            if delta!=probe['maxAbsoluteError'] or delta>plan['limits']['maximumBrowserCpuAbsoluteError'] or not probe['ok']:raise ValueError('browser CPU raw output mismatch')
            binaries.append(a.bind(file))
    if [r['id'] for r in live['packing']]!=expected_ids or any(not r['ok'] or r['maxAbsoluteError']>plan['limits']['maximumInputPackingAbsoluteError'] for r in live['packing']):raise ValueError('four channel packing')
    controls=static['inverseOracleControls']
    if len(live['inverse'])!=45 or [r['id'] for r in live['inverse']]!=[r['id'] for r in controls]:raise ValueError('all45 inverse denominator')
    for row,oracle in zip(live['inverse'],controls):
        if not row['ok'] or row['mismatchPixels']!=0 or row['actualKind']!=oracle['kind'] or row['expectedKind']!=oracle['kind']:raise ValueError('native pixel parity')
    if [live[k] for k in ['validEmptyKind','nonFiniteKind','invalidShapeKind']]!=['rejected','execution-error','execution-error']:raise ValueError('rejection distinct from failure')
    if len(static['gradient']['perCandidateLogitGradients'])!=45 or not static['gradient']['conditionChannelNonzero'] or static['gradient']['backboneInputChannels']!=[3]:raise ValueError('gradient gate')
    inputs={'staticReport':a.bind(static_path),'liveBrowser':a.bind(capture_path),'sourceVerifier':a.bind(Path(__file__)),
        'compiledRuntime':a.bind(folder/'conditional-runtime.mjs'),'harness':a.bind(folder/'browser.html'),'browserConfig':a.bind(folder/'browser-config.json'),
        'preparerSource':a.bind(Path(plan['inputs']['freezeSource']['path']).parent/'prepare-cycle016-conditional-browser-v2.mjs'),
        'captureServerSource':a.bind(Path(plan['inputs']['freezeSource']['path']).parent/'serve-cycle016-conditional-browser-v2.py')}
    return {'schemaVersion':1,'ok':True,'decision':'conditional_refinement_browser_gradient_static_feasible_for_one_train_only_microfit',
        'inputs':inputs,'model':static['model'],'capturedOutputFiles':binaries,'browser':live,
        'gates':{'fourChannelPacking':True,'nativeInverse45ZeroPixelMismatch':True,'bothBackendFiniteCpuParity':True,'emptyRejectNotFallback':True,'errorNotModelSuccess':True,'zeroOptimizationGradient':True},
        'optimizerSteps':0,'trainingApprovedImages':0,'qualityEvidence':False,'mobileSlaEvidence':False,'productionConnected':False,
        'scope':'New untrained interface feasibility only. 34 positive/11 empty inverse oracle controls are not model predictions. Full split, formal thresholds and release HOLD unchanged.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--static-report',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    if args.verify_report:
        saved=a.read(args.verify_report)
        for binding in saved['inputs'].values():a.checked(binding)
        report=build(Path(saved['inputs']['staticReport']['path']),Path(saved['inputs']['liveBrowser']['path']))
        if report!=saved:raise ValueError('browser reconstruction_mismatch')
    else:
        report=build(args.static_report.resolve(),args.capture.resolve());a.write_new(args.output,report)
    print(json.dumps({'ok':True,'decision':'verified' if args.verify_report else report['decision'],'modelSha256':report['model']['sha256'],'inverseCount':45,'backends':[r['backend'] for r in report['browser']['backendResults']],'report':a.bind(args.verify_report or args.output)},ensure_ascii=False))


if __name__=='__main__':main()
