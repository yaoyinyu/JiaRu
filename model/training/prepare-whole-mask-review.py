"""完整原图标注审核页准备及像素重放；不批准真值或训练。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('whole_layout', HERE / 'native-source-page-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
bind, read, checked = layout.bind, layout.read, layout.checked


def identity(row):
    value = row['identity']
    return (value['split'], value['fileName'], value['imageSha256'])


def render(raw, annotations):
    painted = raw.copy()
    draw = ImageDraw.Draw(painted)
    points = []
    for annotation in annotations:
        polygon = annotation['polygon']
        xy = [(float(p['x']), float(p['y'])) if isinstance(p, dict)
              else (float(p[0]), float(p[1])) for p in polygon]
        points.append(xy)
        draw.polygon(xy, fill=(0, 255, 100))
    result = Image.blend(raw, painted, 0.12)
    draw = ImageDraw.Draw(result)
    for xy in points:
        draw.line(xy + xy[:1], fill=(0, 255, 100), width=1)
    return result, points


def build(plan_ref, verify=None):
    plan = read(plan_ref)
    checked(plan['inputs']['renderer'])
    assert plan['inputs']['renderer'] == bind(__file__)
    group = read(plan['inputs']['groupPlan'])
    quality = read(plan['inputs']['qualityEligibility'])
    policy = read(plan['inputs']['resourcePolicy'])
    guard = read(plan['inputs']['guardReport'])
    assert policy['wholeImageOnly'] and policy['fullOriginalSizeAndRgbPixelsRequired']
    rows = group['currentEligibleSources']
    membership = group['entireFrozenGroupMembershipPreserved']
    assert membership and all(r['sourceGroup'] == group['selectedSourceGroup'] for r in rows)
    assert len({identity(r) for r in rows}) == len(rows)
    assert all(r['identity']['split'] == 'val' for r in rows), 'current plan is internal-val only'
    by_key = {identity(r): r for r in quality['currentQualityEligibleInventory']}
    assert all(by_key.get(identity(r)) == r for r in rows), 'reconstruction_mismatch: cohort'
    actual = {}
    for ref in quality['qualityReviewBindings']:
        record = read(ref)
        actual[identity(record)] = (ref, record)
    output = Path(plan['outputDirectory'])
    if not verify:
        assert not output.exists(), 'immutable output already exists'
        output.mkdir(parents=True)
    records = []
    with layout.guarded_pixels(guard):
        for ordinal, row in enumerate(rows, 1):
            actual_ref, raw_view = actual[identity(row)]
            assert raw_view['actuallyViewed'] and not raw_view['toolScalingNotice']
            assert raw_view['coordinateOriginsChecked'] and raw_view['nativePixelCoverageComplete']
            assert raw_view['wholeImageOnly'] and len(raw_view['reviewPages']) == 1
            assert raw_view['annotation'] == row['annotation']
            for ref in raw_view['actualPageBindings']:
                read(ref)
            raw = layout.load_rgb(row['sourceImage'])
            w, h = raw.size
            rgb_sha = hashlib.sha256(raw.tobytes()).hexdigest()
            assert raw_view['originalSize'] == [w, h]
            assert raw_view['originalRgbSha256'] == rgb_sha
            page = raw_view['reviewPages'][0]
            checked(page['page'])
            assert page['page']['sha256'] == row['identity']['imageSha256']
            assert page['sourceBox'] == [0, 0, w, h] and page['pageOrigin'] == [0, 0]
            assert page['size'] == [w, h] and not page['resampling']
            annotation = read(row['annotation'])
            assert annotation['image']['fileName'] == row['identity']['fileName']
            assert [annotation['image']['width'], annotation['image']['height']] == [w, h]
            assert len(annotation['annotations']) == row['maskCount']
            overlay, xy = render(raw, annotation['annotations'])
            polygons = [Polygon(p) for p in xy]
            assert all(p.is_valid and p.area > 0 for p in polygons), 'invalid polygon'
            assert all(0 <= x < w and 0 <= y < h for points in xy for x, y in points)
            overlap = sum(polygons[i].intersection(polygons[j]).area
                          for i in range(len(polygons)) for j in range(i))
            assert overlap == 0, 'overlapping polygons'
            target = output / f'whole-mask-{ordinal:03}.webp'
            if not verify:
                overlay.save(target, format='WEBP', lossless=True, quality=100, method=2, exact=True)
            rendered = layout.load_rgb(bind(target))
            assert rendered.size == raw.size and rendered.tobytes() == overlay.tobytes(), 'lossless RGB mismatch'
            file_bytes = target.stat().st_size
            assert file_bytes <= policy['singleImageFileAndPayloadLimitBytes']
            records.append({**row, 'ordinal': ordinal, 'originalSize': [w, h],
                            'originalRgbSha256': rgb_sha, 'inheritedWholeRawReview': actual_ref,
                            'overlay': bind(target), 'overlayRgbSha256': hashlib.sha256(overlay.tobytes()).hexdigest(),
                            'fileBytes': file_bytes, 'nativeLayout': 'whole', 'sourceBox': [0, 0, w, h],
                            'pageOrigin': [0, 0], 'resampling': False, 'losslessRgbVerified': True,
                            'polygonBoundsBySourceIndex': [list(p.bounds) for p in polygons],
                            'geometryValid': True, 'pairwiseIntersectionArea': overlap,
                            'purpose': 'complete_whole_nail_mask_visual_review',
                            'newImageReason': '原图已实审；新增完整轮廓覆盖页核对当前标注，旧源质量裁决不能批准mask。',
                            'actuallyViewed': False, 'trainingAllowed': False})
    total = sum(r['fileBytes'] for r in records)
    assert total <= policy['batchImageFileAndPayloadLimitBytes']
    assert total <= policy['turnImageFileAndPayloadLimitBytes']
    result = {'schemaVersion': 1, 'ok': True, 'plan': plan_ref,
              'sourceGroup': group['selectedSourceGroup'], 'wholeGroupMembershipPreserved': membership,
              'records': records, 'sources': len(rows), 'nails': sum(r['maskCount'] for r in rows),
              'inheritedWholeRawViews': len(rows), 'newImageFiles': len(rows), 'fileBytes': total,
              'base64EstimatedBytes': sum(4 * ((r['fileBytes'] + 2) // 3) for r in records),
              'actualModelImageInputs': 0, 'actualNetworkBytes': None, 'actuallyViewed': False,
              'geometryDoesNotApproveMasks': True, 'trainingAllowed': False, 'productHold': True}
    if verify:
        assert result == verify, 'reconstruction_mismatch: report'
    else:
        with (output / 'report.json').open('xb') as file:
            file.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            file.flush()
            os.fsync(file.fileno())
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
        assert args.plan is not None
        result = build(bind(args.plan))
    print(json.dumps({'ok': True, 'sources': result['sources'], 'nails': result['nails'],
                      'fileBytes': result['fileBytes'], 'actualModelImageInputs': 0,
                      'trainingAllowed': False}, ensure_ascii=False))
