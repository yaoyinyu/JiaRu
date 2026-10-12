"""完整图片发送的字节预算与请求准备元数据；不等同网络收发测量。"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
def bind(p):
    p = Path(p).resolve()
    assert p.is_file()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
def read(ref):
    assert bind(ref['path']) == ref
    return json.loads(Path(ref['path']).read_bytes())
def authorize(policy, maximum, error, batch_bytes, previous_bytes):
    known = maximum is not None and error is None
    measured = (maximum < policy['preparedRequestHardStopBytes']) if known else None
    observed_stop = maximum is not None and maximum >= policy['preparedRequestHardStopBytes']
    turn_limit = policy.get('turnImageFileAndPayloadLimitBytes')
    turn_bounded = turn_limit is None or previous_bytes + batch_bytes <= turn_limit
    bounded = 0 < batch_bytes <= policy['batchImageFileAndPayloadLimitBytes'] and previous_bytes >= 0 and turn_bounded
    allowed = bounded and not observed_stop and (measured is True or (not known and policy['allowBoundedWholeImagesWhenRequestTelemetryUnavailable']))
    return {'ok': measured is True, 'measuredRequestGatePassed': measured,
            'observedRequestHardStop': observed_stop, 'imageBudgetPassed': bounded,
            'boundedWholeImageSendingAuthorized': allowed}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--thread-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest_ref = bind(args.manifest)
    manifest = read(manifest_ref)
    policy = read(manifest['policy'])
    assert policy['wholeImageOnly'] and policy['fullOriginalSizeAndRgbPixelsRequired']
    pages = manifest['pages']
    assert pages
    groups = manifest.get('imageResponseGroups', [pages])
    assert [r for group in groups for r in group] == pages
    assert all(0 < len(group) <= policy['maximumImagesPerModelResponse'] for group in groups)
    assert len({r['page']['sha256'] for r in pages}) == len(pages)
    for row in pages:
        assert bind(row['page']['path']) == row['page']
        assert row['fileBytes'] == Path(row['page']['path']).stat().st_size
        assert 0 < row['fileBytes'] <= policy['singleImageFileAndPayloadLimitBytes']
        assert row['resampling'] is False and row['pageOrigin'] == [0, 0]
        assert row['sourceBox'] == [0, 0, *row['originalSize']]
    batch_bytes = sum(r['fileBytes'] for r in pages)
    assert batch_bytes == manifest['fileBytes']
    now = int(time.time())
    records, rows, error = [], [], None
    try:
        with sqlite3.connect('file:' + args.database.as_posix() + '?mode=ro', uri=True) as c:
            rows = c.execute("SELECT id,ts,thread_id,feedback_log_body FROM logs WHERE ts>=? AND ts<=? AND target='codex_http_client::request' ORDER BY ts DESC,id DESC LIMIT 200", (now - 300, now)).fetchall()
        for oid, ts, tid, body in rows:
            match = re.search(r'pre_compression_bytes=(\d+) post_compression_bytes=(\d+)', body or '')
            if match and (tid == args.thread_id or 'thread_id=' + args.thread_id in (body or '')):
                records.append({'logId': oid, 'ts': ts, 'threadId': args.thread_id,
                                'bodySha256': hashlib.sha256((body or '').encode()).hexdigest(),
                                'preCompressionBytes': int(match[1]), 'postCompressionBytes': int(match[2])})
    except Exception as exc: error = {'type': type(exc).__name__, 'message': str(exc)}
    maximum = max((r['postCompressionBytes'] for r in records), default=None)
    authority = authorize(policy, maximum, error, batch_bytes, manifest['previousTurnImagesActualBytes'])
    result = {'schemaVersion': 1, **authority, 'manifest': manifest_ref, 'policy': manifest['policy'],
              'sampleTimeBoundary': [now - 300, now], 'threadId': args.thread_id,
              'originalRowsQueried': len(rows), 'requestRecords': records, 'collectionError': error,
              'maximumRecentCompressedBytes': maximum, 'plannedImageFileBytes': batch_bytes,
              'plannedTurnImagePayloadBytes': manifest['previousTurnImagesActualBytes'] + batch_bytes,
              'base64EstimatedBytes': sum(4 * ((r['fileBytes'] + 2) // 3) for r in pages),
              'actualNetworkBytes': None, 'nano275GbCauseUnresolved': True, 'trainingAllowed': False}
    with args.output.open('xb') as f:
        f.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'report': bind(args.output), **authority,
                      'maxCompressedBytes': maximum, 'plannedTurnBytes': result['plannedTurnImagePayloadBytes']}, ensure_ascii=False))
    assert authority['boundedWholeImageSendingAuthorized'], 'no_image_sending_resource_stop'
