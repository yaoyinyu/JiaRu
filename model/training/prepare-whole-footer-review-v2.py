"""完整单图外附定位底条；保留原尺寸、原点和全部RGB，不批准质量。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('whole_footer_layout', HERE / 'native-source-page-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
bind, read, checked = layout.bind, layout.read, layout.checked

def build(plan_ref, verify=None):
    plan = read(plan_ref)
    assert plan['inputs']['runner'] == bind(__file__)
    group = read(plan['inputs']['groupPlan'])
    guard = read(plan['inputs']['guardReport'])
    policy = read(plan['inputs']['policy'])
    all_rows = group['currentEligibleSources']
    ordinals = plan['selectedSourceOrdinals']
    assert len(set(ordinals)) == len(ordinals) and ordinals == sorted(ordinals)
    assert all(1 <= n <= len(all_rows) for n in ordinals)
    assert plan['outsideSourceFooterRows'] == 128
    for row in all_rows:
        checked(row['sourceImage'])
        checked(row['annotation'])
    out = Path(plan['outputDirectory'])
    if not verify:
        assert not out.exists()
        out.mkdir(parents=True)
    records = []
    with layout.guarded_pixels(guard):
        for ordinal in ordinals:
            row = all_rows[ordinal - 1]
            raw = layout.load_rgb(row['sourceImage'])
            w, h = raw.size
            page = Image.new('RGB', (w, h + 128), (32, 32, 32))
            page.paste(raw, (0, 0))
            draw = ImageDraw.Draw(page)
            draw.rectangle((0, h, 119, h + 127), fill=(255, 0, 255))
            draw.rectangle((w - 120, h, w - 1, h + 127), fill=(0, 255, 255))
            draw.text((140, h + 24), f'END OF COMPLETE SOURCE: {w} x {h}; source {ordinal}', fill=(255, 255, 255))
            draw.text((140, h + 48), 'Original RGB at (0, 0). No resize, crop, tile or montage.', fill=(255, 255, 255))
            path = out / f'whole-source-{ordinal:03}.png'
            if not verify: page.save(path, format='PNG', optimize=True)
            saved = layout.load_rgb(bind(path))
            assert saved.size == page.size and saved.tobytes() == page.tobytes()
            assert saved.crop((0, 0, w, h)).tobytes() == raw.tobytes()
            size = path.stat().st_size
            assert size <= policy['singleImageFileAndPayloadLimitBytes']
            records.append({**row, 'sourceOrdinal': ordinal, 'page': bind(path),
                            'originalSize': [w, h], 'pageSize': [w, h + 128], 'sourceBox': [0, 0, w, h],
                            'pageOrigin': [0, 0], 'fullSourcePixels': w * h,
                            'originalRgbSha256': hashlib.sha256(raw.tobytes()).hexdigest(),
                            'pageRgbSha256': hashlib.sha256(page.tobytes()).hexdigest(),
                            'fileBytes': size, 'outsideSourceFooterRows': 128, 'resampling': False,
                            'newCropTileMontageOrRearrangement': False,
                            'actuallyViewed': False, 'trainingAllowed': False})
    total = sum(r['fileBytes'] for r in records)
    assert total <= policy['batchImageFileAndPayloadLimitBytes']
    turn_limit = policy.get('turnImageFileAndPayloadLimitBytes')
    assert turn_limit is None or total <= turn_limit
    result = {'schemaVersion': 1, 'ok': True, 'plan': plan_ref, 'sourceGroup': group['selectedSourceGroup'],
              'records': records, 'wholeGroupMembershipPreserved': group['entireFrozenGroupMembershipPreserved'],
              'counts': {'newWholePageFiles': len(records), 'fileBytes': total, 'actuallyViewedPages': 0,
                         'actualModelImageInputs': 0},
              'newPagePurpose': plan['purpose'], 'qualityApproval': False, 'trainingAllowed': False,
              'actualNetworkBytes': None, 'productHold': True}
    if verify:
        assert result == verify, 'reconstruction_mismatch: whole footer report'
    else:
        with (out / 'report.json').open('xb') as f:
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
    print(json.dumps({'ok': True, 'counts': result['counts'], 'trainingAllowed': False}))
