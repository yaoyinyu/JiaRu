"""从浏览器实际bitpack直接重算完整原图逐甲质量；不调用模型。"""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('saved_canvas_protocol', HERE/'audit-native-canvas-roundtrip.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
d, require = c.d, c.require


def verify(root):
    gate = json.loads((root/'report.json').read_bytes())
    require(gate['ok'] and gate['originalPixelDifferences'] == 0 and gate['browserSavedOutputCases'] == 222,
            'entire actual browser roundtrip gate')
    execution = json.loads((root/'execution.json').read_bytes())
    for ref in execution['sources'].values():
        c.checked(ref)
    scope = d.read(execution['design']); data = d.read(scope['materialization'])
    materializer = c.module(HERE/'materialize-reviewed-stage-b-train-inputs.py', 'canvas_quality_materializer')
    e, plan, sources, _, cleanup = materializer.resources(data['execution'])
    guard = d.load(d.checked(plan['inputs']['readOnlyGuard']), 'canvas_direct_quality_guard')
    guard.install_read_only_ultralytics_image_check()
    try:
        reader = c.module(d.checked(e['sources']['truthReader']), 'canvas_direct_truth_reader')
        metric = c.module(d.checked(plan['inputs']['roiHelper']), 'canvas_direct_metric')
        normal = c.module(HERE/'train-reviewed-stage-b-normal-development.py', 'canvas_direct_summary')
        truth_map = {d.key(s['identity']): reader.truths(s) for s in sources}
        training = d.read(execution['training'])
        results = {}; failures = {}
        for backend_index, backend in enumerate(['cpu', 'wasm', 'webgpu']):
            rows = []
            for case, frozen in zip(scope['cases'], training['perCandidate'], strict=True):
                ordinal = case['ordinal']; sequence = 3 + 74*backend_index + ordinal
                event = json.loads((root/'events'/f'{sequence:03d}-done.json').read_bytes())
                require(event['key'] == f'{backend}-{ordinal}', 'actual backend/ordinal binding')
                path = root/'browser'/f'{sequence:03d}.bits'
                raw = path.read_bytes()
                pixels = c.unpack(raw, case['sourceSize'])
                require(c.digest(raw) == event['packedSha256'] and
                        c.digest(pixels.astype(np.uint8).tobytes()) == event['pixelSha256'], 'actual full canvas capture hashes')
                truth = truth_map[d.key(case['candidateIdentity']['identity'])]
                truth = truth[case['target']['truthIndex']-1] if case['positive'] else np.zeros_like(pixels)
                presence = np.fromfile(c.checked(case['actual'][backend]['presence']), dtype='<f4')
                require(presence.size == 1 and np.isfinite(presence).all(), 'finite actual presence')
                q = c.quality(case, pixels, float(presence[0]), truth, metric)
                require(q == frozen, 'actual browser original-source per-nail quality equals frozen strict quality')
                rows.append(q)
            summary, passed = normal.summarize(rows)
            require(summary == training['metrics'] and passed == training['trainQualityGatePassed'], 'full browser metric denominator')
            results[backend] = {'metrics': summary, 'perCandidate': rows, 'trainQualityGatePassed': passed}
            failures[backend] = [r['candidateIdentity'] for r in rows if r['positive'] and not r['jointPass']]
        require(failures['cpu'] == failures['wasm'] == failures['webgpu'] and len(failures['cpu']) == 2,
                'two historical positive quality failures preserved by identity')
        return {'ok': True, 'roundtripReport': d.bind(root/'report.json'), 'training': execution['training'],
                'source': d.bind(__file__), 'actualBrowserCases': 222, 'backends': results,
                'unchangedJointFailures': failures['cpu'], 'newModelCalls': 0,
                'internalValInputs': 0, 'protectedInputs': 0, 'formalReleaseAllowed': False, 'productHold': True}
    finally:
        for path in cleanup:
            guard.remove_ultralytics_label_caches(Path(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        result = verify(Path(old['roundtripReport']['path']).parent)
        require(d.raw(result) == args.verify_report.read_bytes(), 'entire direct browser quality report')
    else:
        result = verify(args.root.resolve()); d.new(args.output.resolve(), result)
    print(json.dumps({'ok': True, 'actualBrowserCases': 222, 'metrics': result['backends']['cpu']['metrics'],
                      'unchangedJointFailures': len(result['unchangedJointFailures']), 'newModelCalls': 0}), flush=True)
