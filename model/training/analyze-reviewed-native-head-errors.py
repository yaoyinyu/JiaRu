"""从完整冻结双头RAW分解后端误差；重建不一致时拒绝结论，不调用模型。"""
import argparse
import importlib.util
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('native_head_reader', HERE/'audit-reviewed-native-deployment.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m); d = m.d


def analyze(report_ref):
    report = d.read(report_ref); prep = d.read(report['inputs']['preparation']); e = d.read(prep['execution'])
    scope = d.read(e['scope']); cases = scope['cases']; n = len(cases); kind = report['kind']
    comparator = d.load(d.checked(e['sources']['comparator']), 'native_head_comparator')
    expected = [(b, i) for b in ('cpu', 'wasm', 'webgpu') for i in range(1, n+1)]
    if not report['ok'] or n != len(scope['candidateIdentities']) or [c['candidateIdentity'] for c in cases] != scope['candidateIdentities']:
        raise ValueError('reconstruction_mismatch: full stable identities')
    if [(r['backend'], r['ordinal']) for r in report['records']] != expected:
        raise ValueError('reconstruction_mismatch: full per-backend denominator')
    rows = []; references = []
    for backend in ('cpu', 'wasm', 'webgpu'):
        captures = report['captures'][backend]
        if len(captures) != n: raise ValueError('reconstruction_mismatch: complete captures')
        for case, cap in zip(cases, captures, strict=True):
            ordinal = case['ordinal']
            if cap['candidateIdentity'] != case['candidateIdentity'] or cap['ordinal'] != ordinal or cap['backend'] != backend:
                raise ValueError('reconstruction_mismatch: stable capture binding')
            stats = m.compare(case, kind, cap['outputs'], comparator)
            record = report['records'][len(rows)]
            if record['candidateIdentity'] != case['candidateIdentity'] or record['parity'] != stats or record['gatePassed'] != m.passed(stats):
                raise ValueError('reconstruction_mismatch: exact original parity')
            heads = {}
            for head in ('mask', 'presence'):
                ref = case['references'][kind][head]; actual = cap['outputs'][head]
                a = m.tensor(ref); b = m.tensor(actual); diff = a-b
                error = float(np.abs(diff).max())
                index = int(np.abs(diff).reshape(-1).argmax())
                heads[head] = {'maxAbs': error, 'numericPassed': error <= scope['quality']['maximumBothHeadDifference'],
                    'signedReferenceMinusActualAtMaximum': float(diff.reshape(-1)[index]), 'flatIndexAtMaximum': index,
                    'referenceAtMaximum': float(a.reshape(-1)[index]), 'actualAtMaximum': float(b.reshape(-1)[index])}
                references.extend([ref, actual])
            if max(v['maxAbs'] for v in heads.values()) != stats['maxAbsoluteDifference']:
                raise ValueError('reconstruction_mismatch: head attribution')
            rows.append({'backend': backend, 'ordinal': ordinal, 'candidateIdentity': case['candidateIdentity'], 'heads': heads, 'parity': stats})
    summary = {backend: {head: {'candidateCount': n,
        'maxAbs': max(r['heads'][head]['maxAbs'] for r in rows if r['backend'] == backend),
        'failedOrdinals': [r['ordinal'] for r in rows if r['backend'] == backend and not r['heads'][head]['numericPassed']]}
        for head in ('mask', 'presence')} for backend in ('cpu', 'wasm', 'webgpu')}
    return {'schemaVersion': 1, 'ok': True, 'decision': 'full_frozen_raw_head_errors_reconstructed',
        'inputs': {'report': report_ref, 'scope': e['scope'], 'reader': d.bind(__file__), 'comparator': e['sources']['comparator']},
        'records': rows, 'summary': summary, 'rawReferences': references,
        'newModelCalls': 0, 'oldFailurePreserved': True, 'rootCauseProven': False,
        'formalReleaseAllowed': False, 'productHold': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--report', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path)
    a = p.parse_args()
    if a.verify_report:
        saved = d.read(d.bind(a.verify_report)); result = analyze(saved['inputs']['report'])
        if saved != result: raise ValueError('reconstruction_mismatch: full head report')
    else:
        result = analyze(d.bind(a.report)); d.new(a.output, result)
    print(__import__('json').dumps({'ok': result['ok'], 'summary': result['summary'], 'newModelCalls': 0}))
