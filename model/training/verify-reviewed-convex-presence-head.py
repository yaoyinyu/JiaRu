"""不重解LP、不调用模型，完整重放新presence拟合、权重、RAW质量及预算。"""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('convex_presence_fit_reader', HERE/'fit-reviewed-convex-presence-head.py')
fit = importlib.util.module_from_spec(spec); spec.loader.exec_module(fit)
d, c, require = fit.d, fit.c, fit.require


def ledger_replay(ledger, report, identities, root):
    counters = {'fitSolvesStarted': 0, 'fitSolvesConfirmed': 0, 'cachedInputsStarted': 0,
                'cachedInputsConfirmed': 0, 'nativeInputsStarted': 0, 'nativeInputsConfirmed': 0}
    require(len(identities) == len(report['cached']) == len(report['native']) == 74 and len(ledger) == 300,
            'entire single-fit 74 cached/74 native ledger')
    expected = [('claimed', None, None), ('fit_started', 'fitSolvesStarted', 1), ('fit_confirmed', 'fitSolvesConfirmed', 1)]
    for kind in ('cached', 'native'):
        for i in range(1, 75):
            expected.extend([(kind+'_started', kind+'InputsStarted', i), (kind+'_confirmed', kind+'InputsConfirmed', i)])
    expected.append(('closed', None, None))
    for sequence, (event, (phase, counter, index)) in enumerate(zip(ledger, expected, strict=True), 1):
        if counter: counters[counter] = index
        require(event['sequence'] == sequence and event['phase'] == phase and
                all(event[k] == v for k, v in counters.items()), 'immutable ordered exact event counters')
        if phase == 'fit_confirmed': require(event['fit'] == report['fit'], 'fit event reference')
        if phase.startswith(('cached_', 'native_')):
            require(event['candidateIdentity'] == identities[index-1], 'each input stable identity')
            if phase == 'cached_confirmed': require(event['record'] == report['cached'][index-1], 'cached confirmed output')
            if phase == 'native_confirmed': require(event['output'] == report['native'][index-1], 'native confirmed output')
    require(counters == report['counters'] and ledger[-1] == json.loads((root/'terminal.json').read_bytes()) and
            json.loads((root/'attempt.json').read_bytes()) == {'execution': report['execution'], 'attemptConsumed': True, 'restartAllowed': False},
            'closed terminal and exclusive attempt binding')
    return counters


def verify(path):
    saved = d.read(d.bind(path))
    e, training, data, rows, net, metric, guard, cleanup, features, flags = fit.resources(saved['execution'])
    try:
        require(d.checked(e['sources']['verifier']) == Path(__file__).resolve(), 'frozen independent reader')
        require(saved['ok'] and saved['allNonPresenceWeightsUnchanged'] and saved['all74RawMasksUnchanged'], 'actual complete run')
        head = fit.verify_fit(features, flags, d.read(saved['fit']))
        original = torch.load(d.checked(e['inputs']['fixedControlWeights']), map_location='cpu', weights_only=True)
        state = torch.load(d.checked(saved['weights']), map_location='cpu', weights_only=True)
        fit.verify_state(original, state, head)
        ledger = [json.loads(p.read_bytes()) for p in sorted((path.parent/'events').glob('*.json'))]
        counts = ledger_replay(ledger, saved, e['candidateIdentities'], path.parent)
        environment = d.read(saved['environment'])
        require(not environment['cudaMatmulAllowTf32'] and not environment['cudnnAllowTf32'] and
                not environment['autocastEnabled'] and environment['float32MatmulPrecision'] == 'highest', 'actual strict FP32')
        samples = c.base.load_samples(rows)
        sizes = {d.key(r['identity']): r['size'] for r in data['sourceRecords']}
        quality = []; comparisons = []
        for row, sample, cached_ref, native_ref, old in zip(rows, samples, saved['cached'], saved['native'], training['predictions'], strict=True):
            cached = d.read(cached_ref); p = np.array(cached['presenceLogit'], np.float32)
            require(cached['candidateIdentity'] == row['candidateIdentity'] and cached['positive'] == row['presenceTarget'] and
                    cached['presenceSha256'] == fit.capture.sha(p) and cached['signPassed'] is True and
                    fit.presence_gate(p, row['presenceTarget']), 'all cached actual CUDA signs')
            with np.load(d.checked(native_ref), allow_pickle=False) as archive:
                a = archive['logits'].copy(); b = archive['presenceLogit'].copy()
            with np.load(d.checked(old), allow_pickle=False) as archive: fit.mask_exact(a, archive['logits'], row['nativeSize'])
            require(fit.presence_gate(b, row['presenceTarget']), 'all actual native signs')
            comparisons.append({'candidateIdentity': row['candidateIdentity'], 'cachedPresence': float(p),
                                'nativePresence': float(b), 'sameFloat32Bytes': p.tobytes() == b.tobytes(),
                                'absoluteDifferenceDiagnostic': abs(float(p)-float(b))})
            quality.append(c.candidate_metric(row, a, b, sample[2] > 0, sizes[d.key(row['candidateIdentity']['identity'])], net, metric))
        metrics, passed = c.summarize(quality)
        require(quality == saved['perCandidate'] and metrics == saved['metrics'] and passed == saved['trainQualityGatePassed'] and
                saved['decision'] == ('development_train_quality_passed' if passed else 'development_train_quality_failed'), 'full original source quality reconstruction')
        require(all(saved[k] == 0 for k in ('autogradEvaluations', 'maskOptimizerSteps', 'internalValInputs', 'protectedInputs', 'newChatImageInputs'))
                and not saved['formalReleaseAllowed'] and saved['productHold'], 'roles, restart and formal HOLD')
        return {'schemaVersion': 1, 'ok': True, 'training': d.bind(path), 'execution': saved['execution'],
                'weights': saved['weights'], 'trainQualityGatePassed': passed, 'metrics': metrics,
                'perCandidate': quality, 'cachedAndNativePresence': comparisons, 'eventCount': len(ledger), 'counters': counts,
                'all74RawMaskBytesUnchanged': True, 'allNonPresenceTensorBytesUnchanged': True,
                'exactScaledFitMarginsReplayed': True, 'singleFloat32RoundReplayed': True,
                'newModelCalls': 0, 'newFitSolves': 0, 'formalReleaseAllowed': False, 'productHold': True}
    finally:
        for root in cleanup: guard.remove_ultralytics_label_caches(Path(root))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--training', type=Path); parser.add_argument('--output', type=Path); parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = d.read(d.bind(args.verify_report)); result = verify(Path(saved['training']['path']))
        require(d.raw(result) == args.verify_report.read_bytes(), 'complete independent audit report bytes')
    else:
        result = verify(args.training.resolve()); d.new(args.output.resolve(), result)
    print(json.dumps({'ok': result['ok'], 'trainQualityGatePassed': result['trainQualityGatePassed'], 'metrics': result['metrics'], 'newModelCalls': 0, 'newFitSolves': 0}))
