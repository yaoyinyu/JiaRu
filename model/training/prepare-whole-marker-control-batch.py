"""整图匹配控制批次保真准备；网络测量与视觉批准独立记账。"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import time
from pathlib import Path
HERE = Path(__file__).resolve().parent
def bind(p):
    p = Path(p).resolve()
    assert p.is_file()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
def read(ref):
    assert bind(ref['path']) == ref, 'reconstruction_mismatch: binding'
    return json.loads(Path(ref['path']).read_bytes())
def key(value):
    identity = value['identity']
    return identity['split'], identity['fileName'], identity['imageSha256']
def preflight(plan_ref):
    plan = read(plan_ref)
    assert plan['inputs']['runner'] == bind(__file__)
    batch_plan = read(plan['inputs']['batchPlan'])
    refs = batch_plan['inputs']
    pack, policy, group, mask, roles = [read(ref) for ref in
                                     [refs['controls'], refs['policy'], refs['groupPlan'], refs['maskReview'], plan['inputs']['roles']]]
    selected = batch_plan['batches'][plan['batchOrdinal'] - 1]
    assert selected['batchOrdinal'] == plan['batchOrdinal']
    assert pack['wholeGroupMembershipPreserved'] == group['entireFrozenGroupMembershipPreserved']
    sources = group['currentEligibleSources']
    assert len(sources) == len(pack['records']) == 8 and sum(r['maskCount'] for r in sources) == 40
    assert len(roles['records']) == 286
    role_map = {key(r): r for r in roles['records']}
    truths = {key(r): r for r in roles['currentInternalValTruthRecords']}
    assert len(role_map) == len(roles['records'])
    for source, variant_row, reviewed in zip(sources, pack['records'], mask['records'], strict=True):
        role, truth = role_map[key(source)], truths[key(source)]
        assert source['identity'] == variant_row['identity'] == reviewed['identity']
        assert role['sourceGroup'] == source['sourceGroup'] == truth['sourceGroup']
        assert role['sourceImage'] == source['sourceImage']
        assert truth['annotation'] == source['annotation'] == reviewed['annotation']
        assert truth['maskCount'] == source['maskCount'] == 5
        assert not truth['trainingAllowed'] and not truth['formalIndependentValAllowed']
        assert role['trainingUse'] == 'prohibited' and not role['formalTrainingApproved']
        assert reviewed['decision']['decision'] == 'complete_mask_visual_pass'
        assert bind(source['sourceImage']['path']) == source['sourceImage']
        assert bind(source['annotation']['path']) == source['annotation']
    full_pages = [p for b in batch_plan['batches'] for p in b['pages']]
    expected_pages = []
    for r in pack['records']:
        for name, ref in r['variants'].items():
            m = r['variantPixelEvidence'][name]
            expected_pages.append((key(r), name, ref, m['fileBytes'], r['originalSize']))
    assert [(key(p), p['variant'], p['page'], p['fileBytes'], p['originalSize']) for p in full_pages] == expected_pages
    assert len(full_pages) == 48
    for page in full_pages:
        assert bind(page['page']['path']) == page['page']
        assert Path(page['page']['path']).stat().st_size == page['fileBytes']
        assert page['wholeImageOnly'] and page['sourceBox'] == [0, 0, *page['originalSize']] and page['pageOrigin'] == [0, 0]
        assert page['fileBytes'] <= policy['singleImageFileAndPayloadLimitBytes']
    assert sum(p['fileBytes'] for p in selected['pages']) == selected['fileBytes']
    assert selected['fileBytes'] <= policy['batchImageFileAndPayloadLimitBytes']
    assert selected['fileBytes'] <= policy['turnImageFileAndPayloadLimitBytes']
    assert all(len(g) <= policy['maximumImagesPerModelResponse'] for g in selected['imageResponseGroups'])
    # 全清单角色和字节通过之后才进入受守卫保护的像素重放。
    spec = importlib.util.spec_from_file_location('whole_controls_batch', HERE / 'build-whole-marker-control-review.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert helper.build(pack['plan'], verify=pack) == pack
    return {'schemaVersion': 1, 'ok': True, 'decision': 'whole_control_batch_prepared_pending_actual_view',
            'plan': plan_ref, 'inputs': refs, 'roleIndex': plan['inputs']['roles'],
            'batchOrdinal': selected['batchOrdinal'], 'pages': selected['pages'],
            'imageResponseGroups': selected['imageResponseGroups'], 'fileBytes': selected['fileBytes'],
            'base64EstimatedBytes': sum(4 * ((p['fileBytes'] + 2) // 3) for p in selected['pages']),
            'newPages': len(selected['pages']), 'necessaryRelookPages': 0, 'inheritedRawSources': 8,
            'inheritedMaskNails': 40, 'entire48PageManifestValidated': True,
            'fullGroupMembershipPreserved': pack['wholeGroupMembershipPreserved'],
            'actualModelImageInputs': 0, 'actuallyViewedPages': 0, 'actualNetworkBytes': None,
            'trainingAllowed': False, 'productHold': True}

def sample_resource(plan_ref, preparation_ref):
    plan, prep = read(plan_ref), read(preparation_ref)
    policy = read(prep['inputs']['policy'])
    now = int(time.time())
    records, queried, error = [], [], None
    try:
        db = Path(plan['requestLogDatabase'])
        with sqlite3.connect('file:' + db.as_posix() + '?mode=ro', uri=True) as connection:
            queried = connection.execute("SELECT id,ts,thread_id,feedback_log_body FROM logs WHERE ts>=? AND ts<=? AND target='codex_http_client::request' ORDER BY ts DESC,id DESC LIMIT 200", (now - 300, now)).fetchall()
        for oid, ts, tid, body in queried:
            match = re.search(r'pre_compression_bytes=(\d+) post_compression_bytes=(\d+)', body or '')
            if match and (tid == plan['threadId'] or 'thread_id=' + plan['threadId'] in (body or '')):
                records.append({'logId': oid, 'ts': ts, 'threadId': plan['threadId'],
                                'bodySha256': hashlib.sha256((body or '').encode()).hexdigest(),
                                'preCompressionBytes': int(match[1]), 'postCompressionBytes': int(match[2])})
    except Exception as exc: error = {'type': type(exc).__name__, 'message': str(exc)}
    maximum = max((r['postCompressionBytes'] for r in records), default=None)
    known = bool(records) and error is None
    passed = (maximum < policy['preparedRequestHardStopBytes']) if known else None
    allowed = passed is True or (not known and policy['allowBoundedWholeImagesWhenRequestTelemetryUnavailable'])
    return {'schemaVersion': 1, 'ok': passed is True, 'inputs': {'preparation': preparation_ref, 'plan': plan_ref},
            'sampleTimeBoundary': [now - 300, now], 'threadId': plan['threadId'], 'originalRowsQueried': len(queried),
            'requestRecords': records, 'collectionError': error, 'maximumRecentCompressedBytes': maximum,
            'measuredRequestGatePassed': passed, 'boundedWholeImageSendingAuthorized': allowed,
            'maximumPlannedImageFileBytes': prep['fileBytes'], 'actualNetworkBytes': None,
            'imageFileBytesNotWireMeasurement': True, 'nano275GbCauseUnresolved': True, 'trainingAllowed': False}

def frozen(p, doc):
    with Path(p).open('xb') as file:
        file.write((json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode())
        file.flush()
        os.fsync(file.fileno())

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resource-output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        report = read(bind(args.verify_report))
        assert preflight(report['plan']) == report, 'reconstruction_mismatch: preparation'
        print(json.dumps({'ok': True, 'replayedSources': 8, 'newModelImageInputs': 0}))
    else:
        assert args.plan and args.output and args.resource_output
        assert not args.output.exists() and not args.resource_output.exists()
        plan_ref = bind(args.plan)
        result = preflight(plan_ref)
        frozen(args.output, result)
        window = sample_resource(plan_ref, bind(args.output))
        frozen(args.resource_output, window)
        print(json.dumps({'ok': True, 'preparation': bind(args.output), 'pages': result['newPages'],
                          'fileBytes': result['fileBytes'], 'maxCompressedBytes': window['maximumRecentCompressedBytes'],
                          'measuredRequestGatePassed': window['measuredRequestGatePassed'],
                          'sendingAuthorized': window['boundedWholeImageSendingAuthorized']}, ensure_ascii=False))
        assert window['boundedWholeImageSendingAuthorized'], 'request_hard_stop_no_image_sending'
