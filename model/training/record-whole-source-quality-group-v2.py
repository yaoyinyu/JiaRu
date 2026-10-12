"""整图模型输入分组逐源持久化，质量决策与实际载荷分别绑定。"""
import argparse, hashlib, json, os
from pathlib import Path

def bind(p):
    p = Path(p).resolve()
    assert p.is_file()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

def read(ref):
    assert bind(ref['path']) == ref
    return json.loads(Path(ref['path']).read_bytes())

def validate_resource_window(policy, window, preparation_ref, preparation):
    measured = window.get('maximumRecentCompressedBytes')
    if measured is not None:
        if not window['ok'] or measured >= policy['preparedRequestHardStopBytes']:
            raise ValueError('measured request resource gate failed')
        return
    if not policy.get('allowBoundedWholeImagesWhenRequestTelemetryUnavailable'):
        raise ValueError('unknown telemetry route not authorized')
    if window.get('ok') is not False or window.get('measuredRequestGatePassed') is not None:
        raise ValueError('unknown telemetry falsely marked passed')
    if not window.get('boundedWholeImageSendingAuthorized') or window['preparation'] != preparation_ref:
        raise ValueError('bounded whole image preparation binding mismatch')
    if window['boundedImageBatchBytes'] != preparation['imageFileBytesTotal'] or preparation['imageFileBytesTotal'] > policy['batchImageFileAndPayloadLimitBytes']:
        raise ValueError('bounded image batch budget mismatch')

def run(args):
    refs = {k: bind(getattr(args, k)) for k in ['preparation', 'transport', 'decisions']}
    p = read(refs['preparation'])
    transport = read(refs['transport'])
    decisions = read(refs['decisions'])
    plan = read(p['inputs']['plan'])
    policy = read(plan['inputs']['humanPolicy'])
    window = read(transport['requestWindow'])
    assert policy['wholeImageOnly'] and policy['newCropTileOrMontageInputsProhibited']
    validate_resource_window(policy, window, refs['preparation'], p)
    ordinals = plan['modelResponseGroups'][transport['groupOrdinal'] - 1]
    assert len(ordinals) <= policy['maximumImagesPerModelResponse'] and [x['ordinal'] for x in transport['images']] == ordinals == [x['ordinal'] for x in decisions['decisions']]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    def save(name, x):
        out = args.output_dir / name
        data = (json.dumps(x, ensure_ascii=False, indent=2) + '\n').encode()
        if args.verify_report:
            assert out.read_bytes() == data
        else:
            with out.open('xb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        return bind(out)
    outputs = []
    for t, d in zip(transport['images'], decisions['decisions']):
        row = p['records'][t['ordinal'] - 1]
        assert row['ordinal'] == d['ordinal'] == t['ordinal'] and t['sourceSha256'] == row['identity']['imageSha256'] and (bind(row['source']['path']) == row['source']) and (bind(row['annotation']['path']) == row['annotation'])
        assert t['actualEncodedBytes'] == row['fileBytes'] <= policy['singleImageFileAndPayloadLimitBytes'] and t['actuallyDisplayed'] and (not t['toolScalingNotice']) and (t['toolDetail'] == 'original') and (d['decision'] in ['source_quality_candidate', 'source_quality_excluded']) and d['reason']
        pg = row['reviewPages'][0]
        assert len(row['reviewPages']) == 1 and pg['sourceBox'] == [0, 0, *row['originalSize']]
        page = save(f"actual-page-{row['ordinal']:03d}.json", {'schemaVersion': 1, 'ok': True, 'inputs': {'preparation': refs['preparation'], 'transport': refs['transport'], 'requestWindow': transport['requestWindow']}, 'identity': row['identity'], 'pageOrdinal': 1, 'reviewPage': pg, 'actuallyViewed': True, 'toolScalingNotice': False, 'coordinateOriginsChecked': True, 'actualModelImageInputs': 1, 'actualToolEncodedImageBytes': t['actualEncodedBytes'], 'groupOrdinal': transport['groupOrdinal'], 'wholeImageOnly': True, 'trainingAllowed': False})
        quality = {'schemaVersion': 1, 'ok': True, 'inputs': {**refs, 'writer': bind(__file__)}, 'identity': row['identity'], 'sourceGroup': row['sourceGroup'], 'annotation': row['annotation'], 'maskCountPreserved': row['maskCount'], 'currentRoleRecordSha256Preserved': row['currentRoleRecordSha256'], 'priorActualView': row['priorView'], 'actualPageBindings': [page], 'reviewPages': row['reviewPages'], 'wholeSourcePage': {'page': row['source'], 'size': row['originalSize'], 'pageOrigin': [0, 0], 'rawRgbSha256': row['originalRgbSha256'], 'resampling': False}, 'originalSize': row['originalSize'], 'originalRgbSha256': row['originalRgbSha256'], 'actuallyViewed': True, 'toolScalingNotice': False, 'coordinateOriginsChecked': True, 'nativePixelCoverageComplete': True, 'noResamplingOrReencoding': True, 'actualToolEncodedImageBytes': t['actualEncodedBytes'], 'actualModelImageInputs': 1, 'fileBytes': row['fileBytes'], 'wholeImageOnly': True, 'necessaryRelook': row['priorView'] is not None, 'newUniqueStockImages': 0 if row['priorView'] else 1, 'newUniqueStockPages': 0 if row['priorView'] else 1, 'decision': d['decision'], 'nativeSourceQualityReason': d['reason'], 'newMaskApproval': False, 'oldRolesTruthsAndHistoricalDenominatorsPreserved': True, 'trainingUse': 'prohibited', 'trainingAllowed': False, 'productHold': True}
        qr = save(f"source-quality-{row['ordinal']:03d}.json", quality)
        native = None
        if not row['priorView']:
            native = save(f"native-view-{row['ordinal']:03d}.json", {'schemaVersion': 1, 'inputs': {'reviewReport': refs['preparation'], 'writer': bind(__file__), 'entry': qr}, 'image': row['source'], 'originalSize': row['originalSize'], 'pages': row['wholeImage']['pages'], 'decision': {'actuallyViewed': True, 'toolScalingNotice': False, 'coordinateOriginsChecked': True, 'nativeContentSummary': d['reason']}, 'trainingAllowed': False, 'productHold': True})
        outputs.append({'ordinal': row['ordinal'], 'qualityReview': qr, 'newNativeView': native})
    report = save(f"group-{transport['groupOrdinal']:02d}-report.json", {'schemaVersion': 1, 'ok': True, 'inputs': refs, 'outputs': outputs, 'wholeImagesViewed': len(outputs), 'actualEncodedBytes': sum((x['actualEncodedBytes'] for x in transport['images'])), 'trainingAllowed': False, 'productHold': True})
    print(json.dumps({'ok': True, 'report': report, 'sources': len(outputs)}, ensure_ascii=False))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--preparation', type=Path, required=True)
    ap.add_argument('--transport', type=Path, required=True)
    ap.add_argument('--decisions', type=Path, required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    ap.add_argument('--verify-report', action='store_true')
    run(ap.parse_args())
