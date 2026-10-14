"""继承双域已存上采样，补齐全候选2×2特征交叉；只作数学诊断。"""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('feature_cross_upstream', HERE / 'analyze-reviewed-upstream-counterfactual.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
m = u.m
t = u.t
d = u.d
source_resources = u.resources
BRANCHES = ['deep_wasm_skip_cuda', 'deep_cuda_skip_wasm']
STAGES = ('concat64', 'firstConv64', *m.STAGES)


def interaction(cc, ww, wc, cw, original_cuda, original_wasm):
    values = [value.astype(np.float64) for value in (cc, ww, wc, cw, original_cuda, original_wasm)]
    if any(value.shape != values[0].shape or not np.isfinite(value).all() for value in values):
        raise ValueError('same native finite four-cell and original output domains')
    c, w, deep, skip, original_c, original_w = values
    total = w - c
    deep_effect = deep - c
    skip_effect = skip - c
    coupling = w - deep - skip + c
    residual = total - (deep_effect + skip_effect + coupling)
    error = float(np.abs(residual).max())
    if error > 1e-12:
        raise ValueError('same-coordinate factorial identity')
    at = tuple(int(i) for i in np.unravel_index(np.abs(original_w - original_c).argmax(), c.shape))
    return {'equationResidualMaxAbs': error, 'coordinateOfOriginalActualMax': list(at),
            'signedAtSameCoordinate': {'originalActualDifference': float((original_w - original_c)[at]),
                                      'mathematicalTotal': float(total[at]), 'deepOnlyEffect': float(deep_effect[at]),
                                      'skipOnlyEffect': float(skip_effect[at]), 'interaction': float(coupling[at])},
            'mathematicalTotalMaxAbs': float(np.abs(total).max()),
            'deepOnlyMaxAbs': float(np.abs(deep_effect).max()), 'skipOnlyMaxAbs': float(np.abs(skip_effect).max()),
            'interactionMaxAbs': float(np.abs(coupling).max()), 'notIndividualOperatorOrSourceCausalityProof': True}


def sources():
    return u.sources() | {Path(__file__).name: d.bind(__file__)}


def validate_contract(p):
    count = len(p['cases'])
    if count <= 0 or p['fullCandidateCount'] != count or p['branches'] != BRANCHES or p['newBranchCandidateCount'] != 2 * count or p['inheritedBranchCandidateCount'] != 2 * count or p['fourCellCandidateCount'] != 4 * count:
        raise ValueError('complete new/inherited/four-cell denominators')
    if [c['ordinal'] for c in p['cases']] != list(range(1, count + 1)) or p['analyticalEvaluationsAllowed'] != ({stage: 2 * count for stage in STAGES} | {'total': 2 * count * len(STAGES)}) or p['singleFinalFloat32Conversions'] != 2 * count or p['inheritedResizeCount'] != 2 * count:
        raise ValueError('no repeated resize or old stage denominator')
    if p['requiredMaxAbs'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0 or p['requiredPresenceDecisionDifferences'] != 0:
        raise ValueError('original final head gates')
    if any(p[key] for key in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed')) or not p['productHold'] or p['formalReleaseAllowed'] or p['fullModelLearnedGatePassed']:
        raise ValueError('zero neural budget and mathematical diagnosis only')


def derive(prior_ref, tail_ref):
    prior = d.read(prior_ref)
    tail = d.read(tail_ref)
    if not prior['ok'] or prior['summary']['wasm_features']['failedOrdinals'] != [40, 41, 74] or prior['summary']['cuda_features']['failedOrdinals'] or prior['fullModelLearnedGatePassed'] or not tail['ok'] or tail['mathReport'] != prior_ref:
        raise ValueError('complete prior two-domain failure and independent replay')
    _, old, parameters, _ = source_resources(d.checked(prior['inputs']['execution']))
    if len(prior['records']) != len(old['cases']):
        raise ValueError('complete inherited input denominator')
    cases = []
    for c, result in zip(old['cases'], prior['records'], strict=True):
        if c['ordinal'] != result['ordinal'] or c['candidateIdentity'] != result['candidateIdentity'] or c['candidateIdentity']['identity']['split'] != 'train':
            raise ValueError('stable train identities in all cells')
        pure = {row['branch']: row for row in result['branches']}
        if set(pure) != {'cuda_features', 'wasm_features'}:
            raise ValueError('exact inherited pure cells')
        branches = {}
        for branch, deep_origin, skip_origin in [('deep_wasm_skip_cuda', 'wasm', 'cuda'), ('deep_cuda_skip_wasm', 'cuda', 'wasm')]:
            resized = pure[deep_origin + '_features']['resize64']
            t.read_tensor(resized)
            skip = c['features']['enc1.5'][skip_origin]
            t.read_tensor(skip)
            branches[branch] = {'inheritedResize64': resized, 'originalSkip': skip, 'presence': c['originalWasmHeads']['presence']}
        cases.append(c | {'branches': branches, 'inheritedPureBranches': pure})
    count = len(cases)
    p = {key: old[key] for key in ('model', 'firstGroupNorm', 'lastGroupNorm', 'gelu', 'maximumOutputPixelsPerChunk', 'coordinatePolicy')}
    p |= {'purpose': 'complete_four_cell_feature_interaction_with_two_new_crosses_math_only',
          'prior': prior_ref, 'priorTail': tail_ref, 'fullCandidateCount': count, 'branches': BRANCHES,
          'newBranchCandidateCount': 2 * count, 'inheritedBranchCandidateCount': 2 * count, 'fourCellCandidateCount': 4 * count,
          'cases': cases, 'analyticalEvaluationsAllowed': {stage: 2 * count for stage in STAGES} | {'total': 2 * count * len(STAGES)},
          'singleFinalFloat32Conversions': 2 * count, 'inheritedResizeCount': 2 * count,
          'expectedRawCount': 2 * count * (len(STAGES) + 1),
          'expectedRawBytes': sum(c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] for c in cases) * 2 * (146 * 8 + 4),
          'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
          'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0,
          'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
          'actualRepairOrWholeModelUnreachableNotProvenByMath': True,
          'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}
    validate_contract(p)
    return p, parameters


def resources(execution):
    e = d.read(d.bind(execution))
    if e['sources'] != sources() or e['runtime'] != m.decoder.runtime_binding():
        raise ValueError('frozen full math sources and runtime')
    p = d.read(e['scope'])
    expected, parameters = derive(p['prior'], p['priorTail'])
    if p != expected:
        raise ValueError('reconstruction_mismatch: full four-cell contract')
    return e, p, parameters, None


def evaluate_case(c, p, parameters, unused_graph, run):
    branches = {}
    upstream = {}
    for branch, inputs in c['branches'].items():
        concat, concat_stats = run(branch, 'concat64', {'inheritedResize64': inputs['inheritedResize64'], 'originalSkip': inputs['originalSkip']},
                                   lambda: u.concat64(t.read_tensor(inputs['inheritedResize64']), t.read_tensor(inputs['originalSkip'])))
        conv, conv_stats = run(branch, 'firstConv64', {'concat64': concat},
                               lambda: m.decoder.conv64(t.read_tensor(concat), parameters['upstreamConvWeight'], p['maximumOutputPixelsPerChunk']))
        branches[branch] = {'firstGnInput': conv, 'presence': inputs['presence']}
        upstream[branch] = {'inheritedResize64': inputs['inheritedResize64'], 'concat64': concat, 'firstConv64': conv,
                             'upstreamStatistics': {'concat64': concat_stats, 'firstConv64': conv_stats}}
    result = m.decoder.evaluate_case(c | {'branches': branches}, p, parameters, run)
    for row in result['branches']:
        row.update(upstream[row['branch']])
    return result


def make_report(execution, root, p, records):
    interaction_records = []
    for c, record in zip(p['cases'], records, strict=True):
        mixed = {b['branch']: b for b in record['branches']}
        pure = c['inheritedPureBranches']
        values = [pure['cuda_features']['mask32'], pure['wasm_features']['mask32'], mixed['deep_wasm_skip_cuda']['mask32'], mixed['deep_cuda_skip_wasm']['mask32'], c['originalCudaHeads']['mask'], c['originalWasmHeads']['mask']]
        interaction_records.append({'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'decomposition': interaction(*(t.read_tensor(ref) for ref in values))})
    files = list((root / 'results').glob('*.bin'))
    size = sum(path.stat().st_size for path in files)
    events = [d.bind(path) for path in sorted((root / 'events').glob('*.json'))]
    if len(files) != p['expectedRawCount'] or size != p['expectedRawBytes'] or len(events) != p['analyticalEvaluationsAllowed']['total']:
        raise ValueError('complete new raw/event denominator separate from inherited resize')
    prior = d.read(p['prior'])
    return {'ok': True, 'decision': 'complete_four_cell_feature_interaction_diagnostic_only',
            'inputs': {'execution': d.bind(execution), 'auditor': d.bind(__file__)}, 'records': records,
            'summary': t.summarize(p, records), 'inheritedPureSummary': prior['summary'], 'fourCellInteraction': interaction_records,
            'startEvents': events, 'analyticalEvaluationsConsumed': p['analyticalEvaluationsAllowed'],
            'singleFinalFloat32Conversions': p['singleFinalFloat32Conversions'], 'inheritedResizeCount': p['inheritedResizeCount'],
            'candidateCount': len(records), 'newBranchCandidateCount': len(records) * 2, 'inheritedBranchCandidateCount': len(records) * 2,
            'fourCellCandidateCount': len(records) * 4, 'actualRawCount': len(files), 'actualRawBytes': size,
            'actualFp32RepairOrWholeModelUnreachableProven': False, 'newModelCalls': 0, 'optimizerSteps': 0,
            'valInputs': 0, 'protectedInputs': 0, 'newChatImageInputs': 0, 'oldFailuresAndConsumedBudgetsPreserved': True,
            'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-report', action='store_true')
    a = parser.parse_args()
    root = a.output.resolve()
    execution = d.checked(d.read(d.bind(root / 'report.json'))['inputs']['execution']) if a.verify_report else a.execution.resolve()
    u.resources = resources
    u.evaluate_case = evaluate_case
    u.make_report = make_report
    u.compute(execution, root, a.verify_report)
