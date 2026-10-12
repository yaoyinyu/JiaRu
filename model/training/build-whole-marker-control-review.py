"""生成完整图片的标记匹配控制候选；几何与保真不批准视觉语义。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import cv2
HERE = Path(__file__).resolve().parent
def module(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
layout = module(HERE / 'native-source-page-layout.py', 'marker_whole_layout')
bind, read, checked = layout.bind, layout.read, layout.checked
NAMES = ['remove', 'blank_remove_control', 'occlude', 'blank_occlude_control', 'move_marker', 'blank_move_control']

def replace_background(arr, target, donor):
    """复制等尺寸背景；边缘窗口也保留完整范围，不平滑或扩大改动区。"""
    h, w = arr.shape[:2]
    x1, y1, x2, y2 = target
    bx1, by1, bx2, by2 = donor
    assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h
    assert 0 <= bx1 < bx2 <= w and 0 <= by1 < by2 <= h
    assert (x2 - x1, y2 - y1) == (bx2 - bx1, by2 - by1)
    assert max(0, min(x2, bx2) - max(x1, bx1)) * max(0, min(y2, by2) - max(y1, by1)) == 0
    result = arr.copy()
    result[y1:y2, x1:x2] = arr[by1:by2, bx1:bx2]
    return result

def build(plan_ref, verify=None):
    plan = read(plan_ref)
    assert plan['inputs']['runner'] == bind(__file__)
    helper = module(checked(plan['inputs']['matchedControlHelper']), 'whole_matched_helper')
    mask_review = read(plan['inputs']['maskReview'])
    group = read(plan['inputs']['groupPlan'])
    guard = read(plan['inputs']['guardReport'])
    assert mask_review['ok'] and mask_review['counts']['maskPassedSources'] == len(group['currentEligibleSources'])
    assert mask_review['wholeGroupMembershipPreserved'] == group['entireFrozenGroupMembershipPreserved']
    assert plan['controlNames'] == NAMES and len(plan['records']) == len(group['currentEligibleSources'])
    out = Path(plan['outputDirectory'])
    if not verify:
        assert not out.exists()
        out.mkdir(parents=True)
    result_rows = []
    with layout.guarded_pixels(guard):
        for item, source, reviewed in zip(plan['records'], group['currentEligibleSources'], mask_review['records'], strict=True):
            assert item['identity'] == source['identity'] == reviewed['identity']
            assert source['annotation'] == reviewed['annotation'] and source['sourceImage'] == reviewed['sourceImage']
            assert reviewed['decision']['decision'] == 'complete_mask_visual_pass'
            raw = layout.load_rgb(source['sourceImage'])
            w, h = raw.size
            doc = read(source['annotation'])
            truth = Image.new('L', raw.size)
            draw = ImageDraw.Draw(truth)
            for annotation in doc['annotations']:
                points = [(p['x'], p['y']) if isinstance(p, dict) else tuple(p) for p in annotation['polygon']]
                draw.polygon(points, fill=255)
            protected = cv2.dilate(np.asarray(truth), np.ones((21, 21), np.uint8)) > 0
            marker, blank, destination = [item[k] for k in ('markerEnvelopeCandidate', 'blankControlBox', 'relocationBox')]
            boxes = [marker, blank, destination]
            assert item['markerEnvelopeApproved'] is False
            assert len({(b[2] - b[0], b[3] - b[1]) for b in boxes}) == 1
            for x1, y1, x2, y2 in boxes:
                assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h
                assert not protected[y1:y2, x1:x2].any(), 'control box intersects protected nails'
            for i, a in enumerate(boxes):
                for b in boxes[:i]:
                    assert max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1])) == 0
            arr = np.asarray(raw)
            removed = replace_background(arr, marker, blank)
            blank_removed = replace_background(arr, blank, destination)
            moved = helper.relocate(removed, arr, marker, destination)
            blank_moved = helper.relocate(removed, arr, blank, destination)
            occluded, blank_occluded = arr.copy(), arr.copy()
            for pixels, box in [(occluded, marker), (blank_occluded, blank)]:
                x1, y1, x2, y2 = box
                pixels[y1:y2, x1:x2] = (127, 127, 127)
            variants = dict(zip(NAMES, [removed, blank_removed, occluded, blank_occluded, moved, blank_moved], strict=True))
            delta = np.any(moved != blank_moved, axis=2)
            allowed = np.zeros((h, w), dtype=bool)
            x1, y1, x2, y2 = destination
            allowed[y1:y2, x1:x2] = True
            assert not (delta & ~allowed).any()
            refs, metrics = {}, {}
            for name, pixels in variants.items():
                changed = np.any(pixels != arr, axis=2)
                assert not (changed & protected).any(), 'protected pixel changed'
                target = out / f'source-{item["ordinal"]:03}-{name}.webp'
                image = Image.fromarray(pixels)
                if not verify:
                    image.save(target, format='WEBP', lossless=True, quality=100, method=2, exact=True)
                saved = layout.load_rgb(bind(target))
                assert saved.size == raw.size and saved.tobytes() == image.tobytes(), 'lossless whole-image mismatch'
                refs[name] = bind(target)
                metrics[name] = {'originalSize': [w, h], 'wholeImageOnly': True, 'resampling': False,
                                 'rgbSha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                                 'changedPixels': int(changed.sum()), 'protectedPixelsChanged': 0,
                                 'nailPixelsChanged': 0, 'fileBytes': target.stat().st_size,
                                 'actuallyViewed': False}
            result_rows.append({**source, **item, 'variants': refs, 'variantPixelEvidence': metrics,
                                'originalSize': [w, h], 'sourceRgbSha256': hashlib.sha256(raw.tobytes()).hexdigest(),
                                'matchedRelocation': {'sameRemovalBase': True, 'sameDestination': destination,
                                                      'samePatchSize': True, 'pairDifferenceOutsideDestinationPixels': 0,
                                                      'pairDifferentPixels': int(delta.sum())},
                                'backgroundPatchResidualConfound': True, 'trainingAllowed': False})
    total = sum(m['fileBytes'] for r in result_rows for m in r['variantPixelEvidence'].values())
    return_value = {'schemaVersion': 1, 'ok': True, 'decision': 'whole_marker_control_candidates_pending_visual_review',
                    'plan': plan_ref, 'records': result_rows, 'wholeGroupMembershipPreserved': mask_review['wholeGroupMembershipPreserved'],
                    'counts': {'sources': len(result_rows), 'nails': sum(r['maskCount'] for r in result_rows),
                               'variantsPerSource': len(NAMES), 'newWholeImageFiles': len(result_rows) * len(NAMES),
                               'fileBytes': total, 'actuallyViewedPages': 0, 'modelImageInputs': 0},
                    'markerExtentsNotApprovedByGeometry': True, 'wholeGroupMarkerQualification': False,
                    'batchesMustRespectResourcePolicyBeforeSending': True,
                    'projectModelCalls': 0, 'optimizerSteps': 0, 'trainingAllowed': False, 'productHold': True}
    if verify:
        assert return_value == verify, 'reconstruction_mismatch: controls'
    else:
        with (out / 'report.json').open('xb') as file:
            file.write((json.dumps(return_value, ensure_ascii=False, indent=2) + '\n').encode())
            file.flush()
            os.fsync(file.fileno())
    return return_value

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
