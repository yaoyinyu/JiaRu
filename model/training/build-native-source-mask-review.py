"""生成无重采样的完整源图分块和逐甲原图/旧mask对照页；不批准真值。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(binding):
    path = Path(binding['path']).resolve()
    if not path.is_file() or sha(path) != binding['sha256']:
        raise ValueError('binding mismatch: ' + str(path))
    return path


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path)}


def load(path):
    path = Path(path)
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def build(execution_path, output):
    execution = json.loads(Path(execution_path).read_text(encoding='utf-8'))
    checked(execution['inputs']['runnerSource'])
    guard = load(checked(execution['inputs']['readOnlyGuard']))
    guard.install_read_only_ultralytics_image_check()
    source_root = Path(execution['datasetRoot'])
    from PIL import Image, ImageDraw
    from shapely.geometry import Polygon
    import numpy as np
    try:
        scope = json.loads(checked(execution['inputs']['scope']).read_text(encoding='utf-8'))
        plan_path = checked(scope['inputs']['existingShardBuilderPlan'])
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        builder = load(checked(plan['builderSource']))
        if output.exists():
            raise FileExistsError(output)
        shard = builder.build(plan_path, output / 'historical-shard')
        frozen = {r['ordinal']: r for r in scope['sources']}
        records = []
        limit = execution['maxPageSide']
        for source in shard['sourceImages']:
            ordinal = source['ordinal']
            expected = frozen[ordinal]
            if expected['sourceImage'] != source['sourceImage'] or expected['historicalRoiIds'] != [n['roiId'] for n in source['nails']]:
                raise ValueError('source reconstruction mismatch')
            with Image.open(checked(source['sourceImage'])) as image:
                original = image.convert('RGB')
            width, height = original.size
            polygons = builder.polygons(checked(source['sourceLabel']))
            shapes = [Polygon(p * np.asarray([width, height])) for p in polygons]
            invalid = [i + 1 for i, p in enumerate(shapes) if not p.is_valid or p.area <= 0]
            overlaps = [{'left': i + 1, 'right': j + 1, 'area': shapes[i].intersection(shapes[j]).area}
                        for i in range(len(shapes)) for j in range(i + 1, len(shapes))
                        if shapes[i].is_valid and shapes[j].is_valid and shapes[i].intersection(shapes[j]).area > 0]
            tiles = []
            for y in range(0, height, limit):
                for x in range(0, width, limit):
                    box = [x, y, min(x + limit, width), min(y + limit, height)]
                    tile = original.crop(box)
                    if tile.tobytes() != original.crop(box).tobytes():
                        raise ValueError('native source tile pixel mismatch')
                    path = output / f'source-{ordinal:03d}-raw-{x}-{y}.png'
                    tile.save(path)
                    tiles.append({'box': box, 'image': bind(path), 'pixelExact': True})
            panels = []
            # Each row keeps raw and overlay pixels side by side at 1:1.
            # Crop tiling handles any oversized nail; no implicit image resize.
            for nail in source['nails']:
                crop = original.crop(nail['cropBox'])
                with Image.open(checked(nail['nativeOverlay'])) as image:
                    overlay = image.convert('RGB')
                if crop.size != overlay.size:
                    raise ValueError('native crop size mismatch')
                for y in range(0, crop.height, limit - 26):
                    for x in range(0, crop.width, (limit - 12) // 2):
                        box = [x, y, min(x + (limit - 12) // 2, crop.width), min(y + limit - 26, crop.height)]
                        raw_part, overlay_part = crop.crop(box), overlay.crop(box)
                        page = Image.new('RGB', (raw_part.width * 2 + 12, raw_part.height + 26), 'white')
                        page.paste(raw_part, (0, 26)); page.paste(overlay_part, (raw_part.width + 12, 26))
                        ImageDraw.Draw(page).text((0, 4), f"source {ordinal} nail {nail['truthIndex']} raw | old polygon", fill='black')
                        if page.crop((0, 26, raw_part.width, raw_part.height + 26)).tobytes() != raw_part.tobytes():
                            raise ValueError('native comparison raw pixels mismatch')
                        path = output / f"source-{ordinal:03d}-nail-{nail['truthIndex']:02d}-pair-{x}-{y}.png"
                        page.save(path)
                        panels.append({'truthIndex': nail['truthIndex'], 'roiId': nail['roiId'], 'cropBox': nail['cropBox'],
                                       'cropTileBox': box, 'image': bind(path), 'pixelExact': True})
            records.append({'ordinal': ordinal, 'sourceFileName': source['sourceFileName'], 'sourceGroup': source['sourceGroup'],
                            'sourceImage': source['sourceImage'], 'sourceLabel': source['sourceLabel'], 'imageSize': [width, height],
                            'historicalNails': len(source['nails']), 'invalidPolygons': invalid, 'overlapPairs': overlaps,
                            'rawTiles': tiles, 'nailPanels': panels, 'reviewDecision': 'pending_original_pixel_review', 'trainingUse': 'prohibited'})
        report = {'schemaVersion': 1, 'ok': True, 'decision': 'native_source_and_mask_review_pack_pending_visual',
                  'inputs': {'execution': bind(execution_path), 'scope': execution['inputs']['scope'],
                             'historicalShard': bind(output / 'historical-shard/shard-report.json')},
                  'counts': {'sourceImages': len(records), 'historicalNails': sum(r['historicalNails'] for r in records),
                             'sourceGroups': len({r['sourceGroup'] for r in records}),
                             'sourceTiles': sum(len(r['rawTiles']) for r in records), 'nailPanels': sum(len(r['nailPanels']) for r in records)},
                  'records': records, 'maxPageSide': limit, 'noResampling': True,
                  'modelCalls': 0, 'optimizerSteps': 0, 'formalTrainingApprovedImages': 0}
        path = output / 'native-review-pack.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    finally:
        guard.remove_ultralytics_label_caches(source_root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.execution, args.output)
    print(json.dumps({k: result[k] for k in ('ok', 'decision', 'counts')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
