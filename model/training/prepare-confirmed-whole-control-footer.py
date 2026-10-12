"""为已逐源确认标记的完整控制附源外定位条，支持严格像素重放。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('confirmed_control_layout', HERE / 'native-source-page-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
bind, read, checked = layout.bind, layout.read, layout.checked
def key(r):
    i = r['identity']
    return i['split'], i['fileName'], i['imageSha256']
def build(plan_ref, verify=None):
    plan = read(plan_ref)
    assert plan['inputs']['runner'] == bind(__file__)
    pack, locations, policy, roles = [read(plan['inputs'][k]) for k in ['controls', 'locations', 'policy', 'roles']]
    selected = plan['selectedSourceOrdinals']
    assert selected and selected == sorted(set(selected))
    assert pack['wholeGroupMembershipPreserved'] == locations['wholeGroupMembershipPreserved']
    assert set(selected).issubset(locations['confirmedSourceOrdinals'])
    role_map = {key(r): r for r in roles['records']}
    truths = {key(r): r for r in roles['currentInternalValTruthRecords']}
    assert len(role_map) == len(roles['records']) == plan['expectedRoleRecords']
    # 完整全组校验先于像素解码，不按已定位子集改变分母。
    for source, observed in zip(pack['records'], locations['records'], strict=True):
        role, truth = role_map[key(source)], truths[key(source)]
        assert source['identity'] == observed['identity']
        assert role['sourceImage'] == source['sourceImage']
        assert truth['annotation'] == source['annotation'] and truth['maskCount'] == source['maskCount']
        assert role['trainingUse'] == 'prohibited' and not role['formalTrainingApproved']
        assert not truth['trainingAllowed'] and not truth['formalIndependentValAllowed']
        checked(source['sourceImage'])
        checked(source['annotation'])
        for ref in source['variants'].values(): checked(ref)
    output = Path(plan['outputDirectory'])
    if not verify:
        assert not output.exists()
        output.mkdir(parents=True)
    guard = read(read(pack['plan'])['inputs']['guardReport'])
    records = []
    with layout.guarded_pixels(guard):
        for ordinal in selected:
            source, observed = pack['records'][ordinal - 1], locations['records'][ordinal - 1]
            assert observed['markerEnvelopeApproved'] and observed['markerPresentVisuallyConfirmed']
            assert observed['markerEnvelopeCandidate'] == source['markerEnvelopeCandidate']
            for name, ref in source['variants'].items():
                raw = layout.load_rgb(ref)
                w, h = raw.size
                assert hashlib.sha256(raw.tobytes()).hexdigest() == source['variantPixelEvidence'][name]['rgbSha256']
                page = Image.new('RGB', (w, h + 128), (32, 32, 32))
                page.paste(raw, (0, 0))
                draw = ImageDraw.Draw(page)
                draw.rectangle((0, h, 119, h + 127), fill=(255, 0, 255))
                draw.rectangle((w - 120, h, w - 1, h + 127), fill=(0, 255, 255))
                draw.text((140, h + 24), f'END OF COMPLETE SOURCE: {w} x {h}; source {ordinal}; {name}', fill=(255, 255, 255))
                draw.text((140, h + 48), 'Original control RGB at (0, 0). No resize, crop, tile or montage.', fill=(255, 255, 255))
                path = output / f'source-{ordinal:03}-{name}.png'
                if not verify: page.save(path, format='PNG', optimize=True)
                saved = layout.load_rgb(bind(path))
                assert saved.size == page.size and saved.tobytes() == page.tobytes()
                assert saved.crop((0, 0, w, h)).tobytes() == raw.tobytes()
                count = path.stat().st_size
                assert count <= policy['singleImageFileAndPayloadLimitBytes']
                records.append({'identity': source['identity'], 'sourceGroup': source['sourceGroup'],
                                'annotation': source['annotation'], 'maskCount': source['maskCount'],
                                'sourceOrdinal': ordinal, 'variant': name, 'originalControl': ref,
                                'page': bind(path), 'originalSize': [w, h], 'pageSize': [w, h + 128],
                                'sourceBox': [0, 0, w, h], 'pageOrigin': [0, 0],
                                'originalControlRgbSha256': hashlib.sha256(raw.tobytes()).hexdigest(),
                                'fileBytes': count, 'resampling': False, 'actuallyViewed': False, 'trainingAllowed': False})
    groups = [{'sourceOrdinal': ordinal, 'pages': [r for r in records if r['sourceOrdinal'] == ordinal],
               'fileBytes': sum(r['fileBytes'] for r in records if r['sourceOrdinal'] == ordinal)} for ordinal in selected]
    assert all(g['fileBytes'] <= policy['batchImageFileAndPayloadLimitBytes'] and
               len(g['pages']) <= policy['maximumImagesPerModelResponse'] for g in groups)
    result = {'schemaVersion': 1, 'ok': True, 'plan': plan_ref, 'records': records, 'groups': groups,
              'wholeGroupMembershipPreserved': pack['wholeGroupMembershipPreserved'],
              'counts': {'preparedSources': len(selected), 'preparedFullControlPages': len(records),
                         'fileBytes': sum(r['fileBytes'] for r in records), 'actuallyViewedPages': 0},
              'selectedByNativeLocationNotModelOutputs': True, 'wholeGroupMarkerQualified': False,
              'trainingAllowed': False, 'actualNetworkBytes': None, 'productHold': True}
    if verify: assert result == verify, 'reconstruction_mismatch: confirmed control footers'
    else:
        with (output / 'report.json').open('xb') as f:
            f.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
            f.flush()
            os.fsync(f.fileno())
    return result
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        report = read(bind(args.verify_report))
        result = build(report['plan'], report)
    else:
        assert args.plan
        result = build(bind(args.plan))
    print(json.dumps({'ok': True, 'counts': result['counts'],
                      'groupBytes': [{'sourceOrdinal': g['sourceOrdinal'], 'bytes': g['fileBytes']} for g in result['groups']]}, ensure_ascii=False))
