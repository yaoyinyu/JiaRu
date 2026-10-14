"""全train固定特征的一次独立L1线性头拟合；不恢复旧优化器或诊断见证。"""
import argparse
import importlib.util
import json
import os
import traceback
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import linprog
import torch

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


capture = load(HERE/'capture-reviewed-presence-features.py', 'convex_fit_capture')
certificate = load(HERE/'certify-reviewed-presence-separability.py', 'convex_fit_certificate')
c, d, require = capture.c, capture.d, capture.require
FIT = {
    'objective': 'minimize_L1_of_128_coefficients_and_bias_with_auxiliary_abs_variables',
    'solver': 'scipy.optimize.linprog_highs',
    'solverOptions': {'primal_feasibility_tolerance': 1e-9, 'dual_feasibility_tolerance': 1e-9, 'maxiter': 100000},
    'solverSignedMargin': 2, 'fixedPostSolveMultiplier': 2,
    'requiredExactScaledSignedMargin': 2,
    'rounding': 'one_numpy_float32_round_of_entire_fitted_head',
    'presenceAcceptanceLogit': 0., 'maskAcceptanceLogit': 0.,
    'diagnosticWitnessMayInitializeOrBeLoadedAsHead': False,
    'oneSolveNoRetryNoThresholdSearch': True,
}
BUDGET = {'maximumAttempts': 1, 'fitSolves': 1, 'cachedFeatureCudaHeadInputs': 74,
          'nativeFullModelForwardInputs': 74, 'maskOptimizerSteps': 0,
          'autogradEvaluations': 0, 'internalValInputs': 0, 'protectedInputs': 0,
          'newChatImageInputs': 0, 'restartAllowed': False}
HEAD_KEYS = {'presence.weight', 'presence.bias'}


def domain(features, positive):
    flags = np.asarray(positive)
    require(features.dtype == np.float32 and features.ndim == 2 and len(features) > 1 and
            np.isfinite(features).all() and flags.dtype == bool and flags.shape == (len(features),)
            and flags.any() and (~flags).any(), 'full finite two-class feature domain')
    return flags


def fit_head(features, positive):
    flags = domain(features, positive)
    augmented = np.column_stack((features.astype(np.float64), np.ones(len(features))))
    count = augmented.shape[1]; identity = np.eye(count)
    # theta自由，t非负；完整两类同权约束，绝对值辅助变量不遗漏bias。
    constraints = np.vstack((np.column_stack((-np.where(flags, 1., -1.)[:, None]*augmented, np.zeros_like(augmented))),
                             np.column_stack((identity, -identity)), np.column_stack((-identity, -identity))))
    result = linprog(np.r_[np.zeros(count), np.ones(count)], A_ub=constraints,
                     b_ub=np.r_[np.full(len(features), -2.), np.zeros(2*count)],
                     bounds=[(None, None)]*count+[(0., None)]*count,
                     method='highs', options=FIT['solverOptions'])
    require(result.success and result.status == 0, 'one fresh L1 fit must succeed; no retry')
    raw = np.asarray(result.x[:count], np.float64)
    scaled = raw*FIT['fixedPostSolveMultiplier']
    rounded = scaled.astype(np.float32)
    margins = certificate.exact_margins(features, flags, scaled)
    require(np.isfinite(rounded).all() and all(x >= FIT['requiredExactScaledSignedMargin'] for x in margins),
            'exact scaled fit margins without tolerance')
    record = {'solverStatus': int(result.status), 'solverSuccess': bool(result.success),
              'solverMessage': str(result.message), 'solverIterations': int(result.nit),
              'solverObjective': float(result.fun), 'solverL1Approximate': float(np.abs(raw).sum()),
              'rawSolverCoefficientsBinary64': raw.tolist(), 'scaledCoefficientsBinary64': scaled.tolist(),
              'float32Head': rounded.tolist(), 'float32HeadSha256': capture.sha(rounded),
              'exactSignedMargins': [str(x) for x in margins], 'minimumExactSignedMargin': str(min(margins)),
              'scaledHeadClaimedExactL1Optimum': False, 'fitSolves': 1}
    verify_fit(features, flags, record)
    return record, rounded


def verify_fit(features, positive, saved):
    flags = domain(features, positive); count = features.shape[1]+1
    raw = np.asarray(saved['rawSolverCoefficientsBinary64'], np.float64)
    scaled = np.asarray(saved['scaledCoefficientsBinary64'], np.float64)
    head = np.asarray(saved['float32Head'], np.float32)
    require(raw.shape == scaled.shape == head.shape == (count,) and np.isfinite(raw).all()
            and np.isfinite(scaled).all() and np.isfinite(head).all(), 'fitted coefficient domain')
    require(np.array_equal(scaled, raw*FIT['fixedPostSolveMultiplier']) and
            head.tobytes() == scaled.astype(np.float32).tobytes() and capture.sha(head) == saved['float32HeadSha256'],
            'fixed multiplier and single full float32 round')
    margins = certificate.exact_margins(features, flags, scaled)
    require(all(x >= FIT['requiredExactScaledSignedMargin'] for x in margins) and
            saved['exactSignedMargins'] == [str(x) for x in margins] and
            saved['minimumExactSignedMargin'] == str(min(margins)), 'full exact fit margin certificate')
    require(saved['solverSuccess'] and saved['solverStatus'] == 0 and saved['fitSolves'] == 1
            and not saved['scaledHeadClaimedExactL1Optimum'] and
            saved['solverL1Approximate'] == float(np.abs(raw).sum()) and
            np.isclose(saved['solverObjective'], saved['solverL1Approximate'], rtol=1e-8, atol=1e-8), 'solver accounting')
    return head


def updated_state(original, head):
    require(head.dtype == np.float32 and head.shape == (129,) and np.isfinite(head).all(), 'actual 128 coefficient plus bias head')
    state = {name: value.detach().cpu().clone() for name, value in original.items()}
    require(HEAD_KEYS <= state.keys() and state['presence.weight'].shape == (1, 128) and
            state['presence.bias'].shape == (1,), 'fixed architecture head keys')
    state['presence.weight'] = torch.from_numpy(head[:-1].copy()).reshape(1, 128)
    state['presence.bias'] = torch.from_numpy(head[-1:].copy())
    verify_state(original, state, head)
    return state


def verify_state(original, state, head):
    require(state.keys() == original.keys(), 'no state key change')
    for name, value in state.items():
        ref = original[name]
        require(value.dtype == ref.dtype and value.shape == ref.shape and torch.isfinite(value).all().item(), 'state finite dtype/shape')
        if name not in HEAD_KEYS:
            require(value.cpu().contiguous().numpy().tobytes() == ref.cpu().contiguous().numpy().tobytes(), 'all nonpresence tensor bytes unchanged')
    require(state['presence.weight'].cpu().numpy().tobytes() == head[:-1].tobytes() and
            state['presence.bias'].cpu().numpy().tobytes() == head[-1:].tobytes(), 'state is independently fitted float32 head')


def presence_gate(value, positive):
    require(value.dtype == np.float32 and value.shape == () and np.isfinite(value), 'finite scalar float32 presence')
    return bool(value >= 0) == bool(positive)


def mask_exact(actual, reference, size):
    require(actual.dtype == reference.dtype == np.float32 and actual.shape == reference.shape == (size[1], size[0])
            and np.isfinite(actual).all() and np.isfinite(reference).all() and actual.tobytes() == reference.tobytes(),
            'all full native RAW mask bytes unchanged')


def resources(ref):
    e = d.read(ref)
    for bound in [*e['inputs'].values(), *e['sources'].values()]: d.checked(bound)
    require(e['purpose'] == 'fresh_full_train_fixed_feature_convex_presence_only_fit_and_native_acceptance', 'purpose')
    require(d.checked(e['sources']['runner']) == Path(__file__).resolve() and e['fit'] == FIT and e['budget'] == BUDGET, 'new fit and budget')
    require(d.checked(e['sources']['captureRunner']) == Path(capture.__file__).resolve() and
            d.checked(e['sources']['certificateRunner']) == Path(certificate.__file__).resolve() and
            d.checked(e['sources']['controlTrainer']) == Path(c.__file__).resolve(), 'frozen imported implementations')
    require(e['solverEnvironment'] == {'scipy': scipy.__version__, 'numpy': np.__version__}, 'frozen solver runtime')
    scope = d.read(e['inputs']['scope']); training = d.read(e['inputs']['failedControlTraining'])
    require(scope['inputs']['capture'] == e['inputs']['capture'] and scope['inputs']['exactCertificate'] == e['inputs']['exactCertificate']
            and scope['inputs']['fixedControlWeights'] == e['inputs']['fixedControlWeights'] == training['inputs']['weights']
            and scope['inputs']['failedControlTraining'] == e['inputs']['failedControlTraining'], 'fixed original and scope')
    require(scope['quality'] == e['quality'] == c.base.QUALITY and e['precision'] == c.base.PRECISION and
            not e['formalReleaseAllowed'] and e['productHold'], 'unchanged absolute quality and release HOLD')
    recipe = scope['fitContract']
    require(recipe['objective'] == FIT['objective'] and recipe['solver'] == FIT['solver'] and
            recipe['solverOptions'] == FIT['solverOptions'] and recipe['rounding'] == FIT['rounding'] and
            recipe['fitSolves'] == recipe['attempts'] == 1 and not recipe['diagnosticWitnessMayInitializeOrBeLoadedAsHead'] and
            not recipe['subsetsOrThresholdSearchAllowed'] and not recipe['optimizerResumeAllowed'], 'unchanged scoped fit recipe')
    require(scope['requiredNewBudgetsBeforeExecution'] == {k: value for k, value in BUDGET.items() if k != 'maximumAttempts'} and
            scope['zeroInferenceReachability']['fixedControlMaskPresenceOnlyMaximumJoint'] == 69 and
            scope['zeroInferenceReachability']['requiredJointPositiveCount'] == 57 and
            not scope['zeroInferenceReachability']['fixedControlMaskPresenceOnlyUnreachable'], 'full budget and prior reachability')
    proof = capture.verify(Path(d.checked(e['inputs']['capture'])))
    old = d.read(e['inputs']['exactCertificate'])
    rebuilt = certificate.analyze(old['execution'], Path(old['captureReplay']['capture']['path']), old['certificate'])
    require(d.raw(rebuilt) == d.checked(e['inputs']['exactCertificate']).read_bytes() and
            old['certificate']['exactFeasible'] and old['captureReplay'] == proof, 'full prior exact eligibility, no solve')
    captured = d.read(e['inputs']['capture']); values = []
    for record in captured['records']:
        with np.load(d.checked(record['capture']), allow_pickle=False) as archive: values.append(archive['features'][0].copy())
    features = np.stack(values); flags = np.asarray([r['positive'] for r in captured['records']], bool)
    require(features.shape == (74, 128) and int(flags.sum()) == 71 and int((~flags).sum()) == 3 and
            capture.sha(features) == proof['featureMatrixSha256'], 'full stored float32 matrix')
    plan, data, rows, net, band, metric, guard, cleanup = c.resources(Path(training['inputs']['plan']['path']))
    require([r['candidateIdentity'] for r in rows] == e['candidateIdentities'] == scope['candidateIdentities'] and
            plan['counts'] == e['counts'] == scope['counts'] and captured['execution'] == scope['inputs']['captureExecution'], 'all source identities and counts')
    return e, training, data, rows, net, metric, guard, cleanup, features, flags


def execute(ref, root):
    e, training, data, rows, net, metric, guard, cleanup, features, flags = resources(ref)
    counters = {'fitSolvesStarted': 0, 'fitSolvesConfirmed': 0, 'cachedInputsStarted': 0,
                'cachedInputsConfirmed': 0, 'nativeInputsStarted': 0, 'nativeInputsConfirmed': 0}
    sequence = 0; claimed = False
    def event(phase, **extra):
        nonlocal sequence
        sequence += 1
        value = {'sequence': sequence, 'phase': phase, **counters, **extra}
        d.new(root/'events'/f'{sequence:06d}.json', value)
        return value
    try:
        root.mkdir(parents=True, exist_ok=False)
        for name in ('events', 'cached', 'native'): (root/name).mkdir()
        d.new(root/'attempt.json', {'execution': ref, 'attemptConsumed': True, 'restartAllowed': False}); claimed = True
        event('claimed'); counters['fitSolvesStarted'] = 1; event('fit_started')
        fit, head = fit_head(features, flags); d.new(root/'fit.json', fit)
        counters['fitSolvesConfirmed'] = 1; event('fit_confirmed', fit=d.bind(root/'fit.json'))
        original = torch.load(d.checked(e['inputs']['fixedControlWeights']), map_location='cpu', weights_only=True)
        state = updated_state(original, head)
        with (root/'candidate-weights.pt').open('xb') as stream:
            torch.save(state, stream); stream.flush(); os.fsync(stream.fileno())
        c.base.set_precision(); d.new(root/'environment.json', c.base.environment())
        layer = torch.nn.Linear(128, 1).cuda().float().eval(); layer.requires_grad_(False)
        layer.load_state_dict({'weight': state['presence.weight'], 'bias': state['presence.bias']})
        cached = []
        for i, (row, feature, positive) in enumerate(zip(rows, features, flags, strict=True), 1):
            counters['cachedInputsStarted'] = i; event('cached_started', candidateIdentity=row['candidateIdentity'])
            with torch.inference_mode(): value = layer(torch.from_numpy(feature.copy()).reshape(1, 128).cuda())
            p = np.array(float(value[0, 0]), np.float32)
            record = {'candidateIdentity': row['candidateIdentity'], 'positive': bool(positive),
                      'presenceLogit': float(p), 'presenceSha256': capture.sha(p), 'signPassed': presence_gate(p, positive)}
            d.new(root/'cached'/f'{i:03d}.json', record); cached.append(d.bind(root/'cached'/f'{i:03d}.json'))
            counters['cachedInputsConfirmed'] = i; event('cached_confirmed', record=cached[-1], candidateIdentity=row['candidateIdentity'])
            require(record['signPassed'], 'all74 cached CUDA signs at unchanged zero threshold')
        samples = c.base.load_samples(rows)
        model = net.NativeConditionalMaskRefiner().cuda().float().eval(); model.requires_grad_(False); model.load_state_dict(state, strict=True)
        sizes = {d.key(r['identity']): r['size'] for r in data['sourceRecords']}; native = []; quality = []
        for i, (row, sample, old) in enumerate(zip(rows, samples, training['predictions'], strict=True), 1):
            rgb, coarse, target, positive = sample
            counters['nativeInputsStarted'] = i; event('native_started', candidateIdentity=row['candidateIdentity'])
            with torch.inference_mode(): logits, presence = model(torch.from_numpy(net.pack(rgb, coarse))[None].cuda())
            a = logits[0, 0].float().cpu().numpy().copy(); p = np.array(float(presence[0, 0]), np.float32)
            path = root/'native'/f'{i:03d}.npz'
            with path.open('xb') as stream:
                np.savez_compressed(stream, logits=a, presenceLogit=p); stream.flush(); os.fsync(stream.fileno())
            native.append(d.bind(path)); counters['nativeInputsConfirmed'] = i
            event('native_confirmed', candidateIdentity=row['candidateIdentity'], output=native[-1])
            with np.load(d.checked(old), allow_pickle=False) as archive: mask_exact(a, archive['logits'], row['nativeSize'])
            require(presence_gate(p, positive), 'all native presence signs correct')
            quality.append(c.candidate_metric(row, a, p, target > 0, sizes[d.key(row['candidateIdentity']['identity'])], net, metric))
            if i % 10 == 0: print(json.dumps({'nativeInputsConfirmed': i}), flush=True)
        verify_state(original, model.cpu().state_dict(), head)
        metrics, passed = c.summarize(quality)
        report = {'schemaVersion': 1, 'ok': True, 'decision': 'development_train_quality_passed' if passed else 'development_train_quality_failed',
                  'execution': ref, 'fit': d.bind(root/'fit.json'), 'weights': d.bind(root/'candidate-weights.pt'),
                  'environment': d.bind(root/'environment.json'), 'cached': cached, 'native': native,
                  'perCandidate': quality, 'metrics': metrics, 'trainQualityGatePassed': passed,
                  'allNonPresenceWeightsUnchanged': True, 'all74RawMasksUnchanged': True,
                  'counters': counters.copy(), 'autogradEvaluations': 0, 'maskOptimizerSteps': 0,
                  'internalValInputs': 0, 'protectedInputs': 0, 'newChatImageInputs': 0,
                  'formalReleaseAllowed': False, 'productHold': True}
        d.new(root/'report.json', report); d.new(root/'terminal.json', event('closed'))
        return report
    except BaseException as error:
        if claimed:
            d.new(root/'failure.json', {'error': str(error), 'traceback': traceback.format_exc(), **counters,
                                      'restartAllowed': False, 'conclusionsAllowed': False})
            if not (root/'terminal.json').exists(): d.new(root/'terminal.json', event('failed'))
        raise
    finally:
        for path in cleanup: guard.remove_ultralytics_label_caches(Path(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execution', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = execute(d.bind(args.execution), args.output.resolve())
    print(json.dumps({'ok': result['ok'], 'trainQualityGatePassed': result['trainQualityGatePassed'], 'metrics': result['metrics']}))
