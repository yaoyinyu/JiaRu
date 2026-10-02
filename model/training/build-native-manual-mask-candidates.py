"""绑定人工全甲面轮廓并生成无重采样审核页；不修改旧标签或批准训练。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def bind(path): return {'path': str(Path(path).resolve()), 'sha256': sha(path)}
def checked(ref):
    path = Path(ref['path']).resolve()
    if not path.is_file() or sha(path) != ref['sha256']: raise ValueError('binding_mismatch: ' + str(path))
    return path
def read(ref): return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref, name):
    path = checked(ref); sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def validate_drawing(source, drawing):
    for key in ('ordinal', 'fileName', 'sourceGroup', 'sourceImage', 'sourceLabel'):
        if source[key] != drawing[key]: raise ValueError('source reconstruction mismatch')
    if drawing['trainingUse'] != 'prohibited': raise ValueError('unexpected truth promotion')
    if [n['truthIndex'] for n in drawing['nails']] != list(range(1, source['fullyTraceableNails'] + 1)):
        raise ValueError('complete nail denominator changed')
    for n in drawing['nails']:
        if n['status'] != 'candidate_only_pending_visual_review' or n['annotationMethod'] != 'codex-original-pixel-manual-complete-outline':
            raise ValueError('unapproved polygon retention')


def build(execution_ref, output, verify=False):
    execution = read(execution_ref); inputs = execution['inputs']
    if checked(inputs['runnerSource']) != Path(__file__).resolve(): raise ValueError('runner changed')
    guard = module(inputs['readOnlyGuard'], 'manual_native_guard')
    guard.install_read_only_ultralytics_image_check()
    from PIL import Image, ImageDraw
    try:
        helper = module(inputs['manualPolygonValidator'], 'manual_polygon_validator')
        scope = read(inputs['scope']); canonical = read(scope['inputs']['canonicalTruthIndex'])
        truths = {r['fileName']: r for r in canonical['canonicalTruths']}
        if len(truths) != len(canonical['canonicalTruths']): raise ValueError('duplicate canonical file identity')
        pack = read(inputs['oldNativeReviewPack'])
        old_sources = {r['ordinal']: r for r in pack['records']}
        drawings = [read(ref) for ref in inputs['manualDrawings']]
        if [d['ordinal'] for d in drawings] != [s['ordinal'] for s in scope['sources']]:
            raise ValueError('frozen full repair source order/coverage mismatch')
        if not verify and output.exists(): raise FileExistsError(output)
        prepared = []
        for source, drawing, drawing_ref in zip(scope['sources'], drawings, inputs['manualDrawings'], strict=True):
            validate_drawing(source, drawing)
            if source['canonicalHistoricalTruth'] != truths.get(source['fileName']): raise ValueError('canonical identity changed')
            checked(source['sourceLabel'])
            with Image.open(checked(source['sourceImage'])) as im: image = im.convert('RGB')
            annotations = []
            old = old_sources[source['ordinal']]
            old_boxes = {p['truthIndex']: p['cropBox'] for p in old['nailPanels']}
            for n in drawing['nails']:
                if n['cropBox'] != old_boxes[n['truthIndex']]: raise ValueError('drawing frame mismatch')
                polygon = helper.normalize_points(n['polygon'], *image.size)
                annotations.append({'id': f"n{n['truthIndex']}", 'label': 'nail_texture', 'polygon': polygon,
                                    'attributes': {'annotationMethod': n['annotationMethod'], 'occluded': False,
                                                   'repairDisposition': 'new-version-complete-manual-outline-pending-review'}})
            shapes = helper.validate_polygons(annotations)
            prepared.append((source, drawing_ref, image, annotations, shapes, old))
        # No output is created until every source and every polygon passes the bound geometry contract.
        if not verify: output.mkdir(parents=True)
        records = []; pixel_checks = 0
        for source, drawing_ref, image, annotations, shapes, old in prepared:
            ordinal = source['ordinal']
            document = {'version': 'nail-texture-dataset/v1', 'decision': 'candidate_only_not_training_or_test_truth',
                        'trainingUse': 'prohibited', 'annotationTruthStatus': 'manual-repair-candidate-not-final-truth',
                        'image': {'fileName': source['fileName'], 'sourceGroup': source['sourceGroup'],
                                  'width': image.width, 'height': image.height}, 'annotations': annotations}
            annotation_path = output / f'source-{ordinal:03d}-annotations.json'
            encoded = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
            if verify:
                if annotation_path.read_text(encoding='utf-8') != encoded: raise ValueError('manual annotation reconstruction mismatch')
            else: annotation_path.write_text(encoded, encoding='utf-8')
            pages = []
            for i, (annotation, shape) in enumerate(zip(annotations, shapes, strict=True), start=1):
                x1, y1, x2, y2 = shape.bounds
                bounds = [max(0, int(x1) - 24), max(0, int(y1) - 24), min(image.width, int(x2) + 25), min(image.height, int(y2) + 25)]
                crop = image.crop(bounds)
                layer = Image.new('RGBA', crop.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(layer)
                points = [(p['x'] - bounds[0], p['y'] - bounds[1]) for p in annotation['polygon']]
                draw.polygon(points, fill=(0, 220, 90, 35))
                draw.line(points + points[:1], fill=(255, 25, 20, 255), width=1)
                overlay = Image.alpha_composite(crop.convert('RGBA'), layer).convert('RGB')
                for y in range(0, crop.height, 874):
                    for x in range(0, crop.width, 444):
                        box = [x, y, min(x + 444, crop.width), min(y + 874, crop.height)]
                        raw_part, overlay_part = crop.crop(box), overlay.crop(box)
                        page = Image.new('RGB', (2 * raw_part.width + 12, raw_part.height + 26), 'white')
                        page.paste(raw_part, (0, 26)); page.paste(overlay_part, (raw_part.width + 12, 26))
                        ImageDraw.Draw(page).text((0, 4), f'source {ordinal} nail {i} raw | NEW complete manual outline', fill='black')
                        path = output / f'source-{ordinal:03d}-nail-{i:02d}-pair-{x}-{y}.png'
                        if verify:
                            with Image.open(path) as existing:
                                if existing.mode != 'RGB' or existing.size != page.size or existing.tobytes() != page.tobytes():
                                    raise ValueError('native candidate page pixel reconstruction mismatch')
                        else: page.save(path)
                        pages.append({'truthIndex': i, 'cropBox': bounds, 'cropTileBox': box, 'image': bind(path),
                                      'noResampling': True, 'rawPixelExact': True, 'overlayPixelExact': True})
                        pixel_checks += 2
            records.append({'ordinal': ordinal, 'fileName': source['fileName'], 'sourceGroup': source['sourceGroup'],
                            'sourceImage': source['sourceImage'], 'sourceLabel': source['sourceLabel'], 'drawing': drawing_ref,
                            'annotation': bind(annotation_path), 'completeVisibleNails': len(annotations), 'validPolygons': len(shapes),
                            'pairwiseOverlapCount': 0, 'nativeSourceTiles': old['rawTiles'], 'nailPanels': pages,
                            'visualDecision': 'pending_original_pixel_review', 'trainingUse': 'prohibited'})
        return {'schemaVersion': 1, 'ok': True, 'decision': 'manual_candidates_geometry_valid_pending_original_pixel_review',
                'execution': execution_ref, 'inputs': inputs, 'canonicalTruthIndex': scope['inputs']['canonicalTruthIndex'],
                'records': records, 'counts': {'sourceImages': len(records), 'completeVisibleNails': sum(r['completeVisibleNails'] for r in records),
                                             'sourceGroups': len({r['sourceGroup'] for r in records}),
                                             'nativePanels': sum(len(r['nailPanels']) for r in records), 'rawAndOverlayPixelChecks': pixel_checks},
                'modelCalls': 0, 'optimizerSteps': 0, 'formalTrainingApprovedImages': 0, 'trainingAllowed': False, 'full30PilotAllowed': False}
    finally:
        guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path); parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        report = json.loads(args.verify_report.read_text(encoding='utf-8'))
        if build(report['execution'], args.verify_report.parent, verify=True) != report: raise ValueError('candidate report reconstruction mismatch')
        print(json.dumps({'ok': True, 'decision': 'native_manual_candidates_replay_identical'}))
    else:
        if not args.execution or not args.output: parser.error('--execution and --output required')
        report = build(bind(args.execution), args.output)
        (args.output / 'candidate-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('ok', 'decision', 'counts')}))


if __name__ == '__main__': main()
