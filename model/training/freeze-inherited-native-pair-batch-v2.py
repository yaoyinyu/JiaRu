"""完整冻结实看证据的有界批处理；只继承图片，显式人工图对理由，拒绝同源自动晋升。"""
import argparse, copy, hashlib, importlib.util, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def bind(p):
    p = Path(p).resolve()
    assert p.is_file(), str(p)
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

def read(ref):
    p = Path(ref['path'])
    assert bind(p) == ref, 'reconstruction_mismatch: binding'
    return json.loads(p.read_bytes())

def identity(x):
    return (x['split'], x['fileName'], x['imageSha256'])

def pair(x):
    return tuple(x['pairIdentity'])

def select(priority, n):
    assert type(n) is int and 1 <= n <= 12
    return sorted([x for x in priority['allPendingRecordsPreserved'] if x['classification'] == 'currentCandidateRelated'], key=lambda x: x['originalQueueOrdinal'])[:n]

def project_pending(original, priority, old_disposition, remaining, inventory):
    before = {pair(x): x for x in priority['allPendingRecordsPreserved']}
    assert len(before) == len(priority['allPendingRecordsPreserved']) and set(before) == set(map(tuple, old_disposition['pendingPairIdentities']))
    ci = {identity(x['identity']): x for x in inventory}
    assert len(ci) == len(inventory)
    seen = set()
    projected = []
    for ordinal, row in enumerate(original['pairs'], 1):
        key = pair(row)
        assert key not in seen
        seen.add(key)
        for o in row['observations']:
            assert tuple(sorted([o['target']['imageSha256'], o['reference']['image']['sha256']])) == key and o['target']['sourceImage']['sha256'] == o['target']['imageSha256']
        if key in before:
            prior = before[key]
            assert prior['originalQueueOrdinal'] == ordinal and len(prior['observations']) == len(row['observations'])
            for left, right in zip(prior['observations'], row['observations']):
                assert left['target'] == right['target'] and left['reference'] == right['reference'] and (left['candidateOwnerIdentities'] == [x for x in right['target']['ownerCurrentIdentities'] if identity(x) in ci])
        if key in remaining:
            projected.append(before[key])
    assert remaining <= seen and len(projected) == len(remaining)
    return projected

def validate_manual(batch, manual):
    assert len(batch) == len(manual) and len({x['queueOrdinal'] for x in manual}) == len(manual)
    for row, x in zip(batch, manual):
        assert row['originalQueueOrdinal'] == x['queueOrdinal'] and row['pairIdentity'] == x['pairIdentity'] and (x['decision'] == 'visually_distinct') and x['reason'].strip() and (x['priorPairConclusionNotInherited'] is True), 'same-source/uncertain requires its dedicated workflow; no terminal promotion here'
        assert len(row['observations']) == 1 and row['observations'][0]['reference'] == x['referenceBindingExpected'] and (row['observations'][0]['reference']['trainingAllowed'] is False)
        assert row['observations'][0]['target']['imageSha256'] != row['observations'][0]['reference']['image']['sha256'], 'same source requires isolation workflow'

def module(n, p):
    sp = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(sp)
    sys.modules[n] = m
    sp.loader.exec_module(m)
    return m

def build(plan_ref, verify):
    plan = read(plan_ref)
    refs = plan['inputs']
    docs = {k: read(r) for k, r in refs.items()}
    pr = docs['priority']
    d = docs['disposition']
    s = docs['scope']
    q = docs['preparation']
    reg = docs['registry']
    l = docs['ledger']
    a = docs['audit']
    batch = select(pr, plan['maximumPairs'])
    assert len(batch) == plan['maximumPairs'] and [x['originalQueueOrdinal'] for x in batch] == plan['selectedOriginalQueueOrdinals']
    validate_manual(batch, plan['manualDecisions'])
    assert l['currentCandidateCounts'] == s['prospectiveCandidateCounts'] == a['counts'] and (not any(a['gates'].values())) and (not l['trainingAllowed'])
    by = {x['imageSha256']: x for x in reg['images']}
    assert len(by) == len(reg['images'])
    sources = {}
    for row in batch:
        o = row['observations'][0]
        for src in [o['target']['sourceImage'], o['reference']['image']]:
            assert src['sha256'] in by, 'missing complete actual view; do not skip original-order record'
            sources[src['sha256']] = src
    names = plan['outputs']
    assert len(names) == len(set(names.values()))
    paths = {k: ROOT / 'model/reviews' / v for k, v in names.items()}
    if not verify:
        assert all((not p.exists() for p in paths.values())), 'exclusive outputs already exist'
    original = read(d['inputs']['queue'])
    done_before_pixels = {pair(x) for x in plan['manualDecisions']}
    assert len(done_before_pixels) == len(batch) and done_before_pixels <= set(map(tuple, d['pendingPairIdentities']))
    remaining_before_pixels = set(map(tuple, d['pendingPairIdentities'])) - done_before_pixels
    projected_before_pixels = project_pending(original, pr, d, remaining_before_pixels, l['sourceParentQualificationInventory'])
    review_root = (ROOT / 'model/reviews').resolve()
    assert all((path.resolve().is_relative_to(review_root) for path in paths.values())), 'output path escapes review root'
    layout = module('inherited_batch_layout', ROOT / 'model/training/native-source-page-layout.py')
    reuse = module('inherited_batch_reuse', ROOT / 'model/training/native-source-view-reuse.py')
    images = []
    with layout.guarded_pixels(docs['guardPlanReport']):
        for sha, src in sources.items():
            im = by[sha]
            av = read(im['actualView'])
            prior = read(av['inputs']['reviewReport'])
            old = next((x for x in prior['images'] if x['image']['sha256'] == sha))
            reuse.validate_record(im['actualView'], old)
            layout.check_pixels(old)
            raw = layout.load_rgb(src)
            assert list(raw.size) == im['originalSize'] and hashlib.sha256(raw.tobytes()).hexdigest() == im['originalRgbSha256']
            images.append({'source': src, 'originalSize': im['originalSize'], 'originalRgbSha256': im['originalRgbSha256'], 'actualView': im['actualView'], 'canonicalPages': im['pages'], 'completeOriginalPixelCoverageReplayed': True, 'newActualView': False})
    decisions = []
    for row, x in zip(batch, plan['manualDecisions']):
        o = row['observations'][0]
        decisions.append({'queueOrdinal': row['originalQueueOrdinal'], 'pairIdentity': row['pairIdentity'], 'observationPreserved': {'target': o['target'], 'reference': o['reference']}, 'decision': 'visually_distinct', 'relationshipType': 'visually_distinct', 'reason': x['reason'], 'priorReferencePairConclusionNotInherited': True, 'targetActualView': by[o['target']['imageSha256']]['actualView'], 'referenceActualView': by[o['reference']['image']['sha256']]['actualView'], 'trainingAllowed': False})
    review = {'schemaVersion': 1, 'ok': True, 'meaning': 'explicit_new_pair_decisions_from_complete_images_not_source_independence_or_training_permission', 'inputs': dict(refs, plan=plan_ref, runner=bind(Path(__file__))), 'selectedOriginalQueueOrdinals': plan['selectedOriginalQueueOrdinals'], 'decisions': decisions, 'inheritedImages': images, 'inheritedUniqueImages': len(images), 'inheritedCanonicalPages': sum((len(x['canonicalPages']) for x in images)), 'pairEndpointReuseUses': 2 * len(batch), 'newActualViews': 0, 'modelImageInputs': 0, 'newUniqueStockImages': 0, 'newUniqueStockPages': 0, 'requestRecoveryVerified': False, 'actualWireBytesNotMeasured': True, 'trainingAllowed': False, 'productHold': True}

    def write(k, x):
        path = paths[k]
        b = (json.dumps(x, ensure_ascii=False, indent=2) + '\n').encode()
        if verify:
            assert path.read_bytes() == b, 'reconstruction_mismatch: ' + k
        else:
            with path.open('xb') as f:
                f.write(b)
                f.flush()
                os.fsync(f.fileno())
        return bind(path)
    rr = write('review', review)
    n = len(decisions)
    old_count = len(d['newActuallyReviewedDecisions'])
    nd = copy.deepcopy(d)
    nd['inputs'].update({'priorDisposition': refs['disposition'], 'currentInheritedReview': rr})
    nd['newActuallyReviewedDecisions'] += decisions
    done = {pair(x) for x in decisions}
    nd['pendingPairIdentities'] = [x for x in d['pendingPairIdentities'] if tuple(x) not in done]
    nd['counts'].update({'newActuallyReviewedPairs': len(nd['newActuallyReviewedDecisions']), 'pendingPairs': len(nd['pendingPairIdentities'])})
    nd['combinedReviewedPairs'] = d['combinedReviewedPairs'] + n
    assert nd['newActuallyReviewedDecisions'][:old_count] == d['newActuallyReviewedDecisions'] and nd['inheritedDecisions'] == d['inheritedDecisions'] and (nd['currentUncertainPairDecisions'] == d['currentUncertainPairDecisions']) and (nd['combinedReviewedPairs'] + len(nd['pendingPairIdentities']) == d['combinedUniquePairs'])
    dr = write('disposition', nd)
    ns = copy.deepcopy(s)
    ns['inputs'].update({'priorInheritedBatchScope': refs['scope'], 'currentInheritedReview': rr, 'currentDisposition': dr})
    ns['currentAlbumDelta234Governance'].update({'evidence': dr, 'newActuallyReviewedPairs': len(nd['newActuallyReviewedDecisions']), 'combinedReviewedPairs': nd['combinedReviewedPairs'], 'pendingPairs': len(nd['pendingPairIdentities'])})
    ns['currentInheritedNativePairBatch'] = {'evidence': rr, 'newActualViews': 0, 'imageInputs': 0, 'inheritedUniqueImages': len(images), 'inheritedCanonicalPages': review['inheritedCanonicalPages'], 'endpointUses': 2 * n}
    sr = write('scopeIntermediate', ns)
    original = read(d['inputs']['queue'])
    remaining = set(map(tuple, nd['pendingPairIdentities']))
    projected = projected_before_pixels
    counts = {k: sum((x['classification'] == k for x in projected)) for k in ['currentCandidateRelated', 'isolatedGroupRelated', 'otherPreserved']}
    nextrow = min([x for x in projected if x['classification'] == 'currentCandidateRelated'], key=lambda x: x['originalQueueOrdinal'])
    np = copy.deepcopy(pr)
    np['inputs'].update({'priorPriority': refs['priority'], 'scope': sr, 'disposition': dr, 'runner': bind(Path(__file__))})
    np['originalCounts'].update({'reviewed': nd['combinedReviewedPairs'], 'pending': len(remaining)})
    np['pendingPartitionCounts'] = counts
    np['allPendingRecordsPreserved'] = projected
    np['selectedNextPair'] = nextrow
    assert np['deferredOriginalSevenUncertain'] == nd['currentUncertainPairDecisions']
    prref = write('priority', np)
    fs = copy.deepcopy(ns)
    fs['inputs'].update({'priorScopeIntermediate': sr, 'currentCandidateSourcePriority': prref})
    fs['currentCandidateSourcePairPriority'] = {'evidence': prref, 'selectedNextPair': nextrow, 'pendingPartitionCounts': counts, 'allPendingPreserved': True, 'originalSevenUncertainDeferredNotClosed': True}
    fr = write('scope', fs)
    nq = copy.deepcopy(q)
    nq['inputs'].update({'priorPreparation': refs['preparation'], 'currentScope': fr, 'currentCandidateSourcePriority': prref})
    nq['historicalInheritedBatchMilestonePreserved'] = q['nextExecutableMilestone']
    nq['nextExecutableMilestone']['selectedNextPair'] = nextrow
    nq['nextExecutableMilestone']['priorityEvidence'] = prref
    assert nq['records'] == q['records'] and nq['counts'] == q['counts']
    qr = write('preparation', nq)
    for k in ['groups', 'prospectiveCandidateCounts', 'currentCounts', 'currentSourceParentQualificationIsolation', 'currentTrainingAdmissionEvidence', 'currentI016LocalPixelDiagnostic', 'currentPositiveOnlyRegistration', 'currentAlbumSupplementalProtectedReuse']:
        assert fs[k] == s[k]
    print(json.dumps({'ok': True, 'review': rr, 'disposition': dr, 'scope': fr, 'priority': prref, 'preparation': qr, 'reviewed': nd['combinedReviewedPairs'], 'pending': len(remaining), 'pendingPartition': counts, 'nextQueue': nextrow['originalQueueOrdinal'], 'nextTarget': nextrow['observations'][0]['target']['imageSha256'], 'nextReference': nextrow['observations'][0]['reference']['image']['sha256'], 'imageInputs': 0, 'inheritedUniqueImages': len(images), 'inheritedCanonicalPages': review['inheritedCanonicalPages']}))
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--verify-report', action='store_true')
    a = p.parse_args()
    build(bind(a.plan), a.verify_report)
