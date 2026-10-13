"""从真实WASM/WebGPU RAW与一次性事件重放完整两头和全候选准入门。"""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('trained_browser_audit_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)


def build(root):
    preparation = d.read(d.bind(root / 'preparation.json'))
    server = d.load(d.checked(preparation['server']), 'trained_browser_server_helper')
    d.checked(preparation['html']); d.checked(preparation['config'])
    plan, cases, precision = server.resources(d.checked(preparation['plan']))
    config = d.read(preparation['config'])
    live = d.read(d.bind(root / 'browser-capture/live-browser.json'))
    if config['planSha256'] != preparation['plan']['sha256'] or live['planSha256'] != config['planSha256'] or live['configSha256'] != config['configSha256'] or not live['userAgent'] or not live['origin'].startswith('http://127.0.0.1:') or not live['crossOriginIsolated']:
        raise ValueError('real browser runtime/config binding')
    expected_order = [(kind, backend, c['ordinal']) for kind in ('control', 'learned') for backend in ('wasm', 'webgpu') for c in cases]
    case_map = {c['ordinal']: c for c in cases}
    if len(case_map) != 68 or len(expected_order) != 272: raise ValueError('full68 stable denominator')
    events = []
    for path in (root / 'started-inputs').glob('*.json'):
        value = d.read(d.bind(path))
        ordinal = value['ordinal']
        if ordinal not in case_map or value['candidateIdentity'] != case_map[ordinal]['candidateIdentity'] or path.name != f'{value["kind"]}-{value["backend"]}-{ordinal}.json' or type(value['startedAtUnixNs']) != int:
            raise ValueError('input event stable identity')
        events.append({'event': value, 'file': d.bind(path)})
    events.sort(key=lambda row: row['event']['startedAtUnixNs'])
    event_order = [(r['event']['kind'], r['event']['backend'], r['event']['ordinal']) for r in events]
    if event_order != expected_order[:len(events)] or len(set(event_order)) != len(events): raise ValueError('budget start event prefix')
    started = [(r['kind'], r['backend'], r['ordinal']) for r in live['startedInputs']]
    if started != event_order: raise ValueError('browser vs server input starts')
    order = [(r['kind'], r['backend'], r['ordinal']) for r in live['records']]
    if order != expected_order[:len(order)]: raise ValueError('complete captured input prefix')
    records = []; bindings = []
    for row in live['records']:
        c = case_map[row['ordinal']]; h, w = c['h'], c['w']; kind, backend = row['kind'], row['backend']
        if row['candidateIdentity'] != c['candidateIdentity'] or row['dims'] != [1, 1, h, w] or row['presenceDims'] != [1, 1]: raise ValueError('native candidate identity/heads shape')
        refs = {name: d.bind(root / 'browser-capture' / f'{kind}-{backend}-{c["ordinal"]}-{name}.bin') for name in ('mask', 'presence')}
        stats = precision.compare.compare_outputs(precision.buffer(c['refs'][kind+'-mask'], h*w), precision.buffer(c['refs'][kind+'-presence'], 1),
            precision.buffer(refs['mask'], h*w), precision.buffer(refs['presence'], 1), h, w)
        browser_stats = {'maxAbs': stats['maxAbsoluteDifference'], 'pixels': stats['decodedMaskPixelDifference'], 'presenceMatched': stats['presenceDecisionMatched'],
            'ok': stats['numericGatePassed'] and stats['decodedPixelGatePassed'] and stats['presenceDecisionMatched']}
        if row['parity'] != browser_stats: raise ValueError('browser vs RAW numerical/pixel summary')
        records.append({'kind': kind, 'backend': backend, 'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'parity': stats})
        bindings.extend(refs.values())
    controls = [r for r in records if r['kind']=='control']
    controls_pass = len(controls)==136 and all(r['parity'][key] for r in controls for key in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched'))
    if any(r['kind']=='learned' for r in records) and not controls_pass: raise ValueError('learned inputs without both nonzero control gates')
    summary = {kind: {backend: {'captured': len(rows), 'started': sum(r['event']['kind']==kind and r['event']['backend']==backend for r in events),
        'maxAbs': max((r['parity']['maxAbsoluteDifference'] for r in rows), default=None),
        'numericFailed': sum(not r['parity']['numericGatePassed'] for r in rows), 'pixelDifferences': sum(r['parity']['decodedMaskPixelDifference'] for r in rows),
        'presenceFailed': sum(not r['parity']['presenceDecisionMatched'] for r in rows)}
        for backend in ('wasm', 'webgpu') for rows in [[r for r in records if r['kind']==kind and r['backend']==backend]]} for kind in ('control', 'learned')}
    passed = len(records)==272 and len(events)==272 and not live['errors'] and all(r['parity'][key] for r in records for key in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched'))
    if live['ok'] != passed: raise ValueError('live browser terminal decision mismatch')
    return {'schemaVersion': 1, 'ok': True, 'decision': 'trained_native_wasm_webgpu_full68_pass_internal_val_pending' if passed else 'trained_native_browser_failure_reconstructed',
        'inputs': {'preparation': d.bind(root/'preparation.json'), 'liveBrowser': d.bind(root/'browser-capture/live-browser.json'), 'auditor': d.bind(__file__)},
        'records': records, 'captureBindings': bindings, 'inputStartEvents': events, 'summary': summary,
        'actualBrowserUserAgent': live['userAgent'], 'adapterInfo': live.get('adapterInfo'), 'errors': live['errors'],
        'bothBackendNonzeroControlGatePassed': controls_pass, 'learnedBrowserGatePassed': passed, 'internalValEligibleForNewDiagnosticScope': passed,
        'newBrowserModelInputs': len(events), 'newOptimizerSteps': 0, 'valModelInputs': 0, 'protectedModelInputs': 0,
        'releaseIdentityRegistered': False, 'formalReleaseAllowed': False, 'productHold': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); a = p.parse_args()
    if a.verify_report:
        old = d.read(d.bind(a.verify_report)); d.checked(old['inputs']['auditor'])
        root = Path(old['inputs']['preparation']['path']).parent; result = build(root)
        if result != old: raise ValueError('browser report reconstruction_mismatch')
    else: result = build(a.root.resolve()); d.new(a.output.resolve(), result)
    print(json.dumps({k: result[k] for k in ('ok', 'decision', 'learnedBrowserGatePassed', 'summary', 'errors', 'newBrowserModelInputs')}))
