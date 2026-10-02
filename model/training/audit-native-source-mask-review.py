"""重放原像素审核页和人工处置绑定；不把重放当视觉审核或训练批准。"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def checked(ref):
    path = Path(ref['path']).resolve()
    if not path.is_file() or sha(path) != ref['sha256']:
        raise ValueError('binding_mismatch: ' + str(path))
    return path


def read(ref):
    return json.loads(checked(ref).read_text(encoding='utf-8'))


def unique(rows, key):
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError('duplicate_identity: ' + str(row[key]))
        result[row[key]] = row
    return result


def tiles(width, height, step_x, step_y):
    return [[x, y, min(x + step_x, width), min(y + step_y, height)]
            for y in range(0, height, step_y) for x in range(0, width, step_x)]


def validate_decision(record, decision):
    for left, right in [('sourceFileName', 'fileName'), ('sourceGroup', 'sourceGroup'),
                        ('sourceImage', 'sourceImage'), ('sourceLabel', 'sourceLabel'),
                        ('historicalNails', 'historicalMaskCount')]:
        if record[left] != decision[right]:
            raise ValueError('reconstruction_mismatch: source identity')
    if decision['reviewedHistoricalNailIndices'] != list(range(1, record['historicalNails'] + 1)):
        raise ValueError('reconstruction_mismatch: nail denominator')
    expected = [t['image'] for t in record['rawTiles'] + record['nailPanels']]
    if decision['viewedArtifacts'] != expected:
        raise ValueError('reconstruction_mismatch: visual evidence coverage')
    if decision['retainedApprovedOldMaskIndices'] or decision['trainingUse'] != 'prohibited':
        raise ValueError('unexpected automatic mask promotion')
    if not decision['reason'] or not decision['markerDecision']:
        raise ValueError('missing visual disposition')
    quality = decision['sourceQualityDecision']
    if quality == 'complete_visible_nails_traceable':
        if decision['maskDecision'] != 'label_rework' or decision['fullyTraceableNails'] != record['historicalNails']:
            raise ValueError('inconsistent source/repair denominator')
    elif quality == 'exclude_incomplete_nail_boundary':
        if decision['maskDecision'] != 'source_quality_excluded' or not 0 <= decision['fullyTraceableNails'] < record['historicalNails']:
            raise ValueError('inconsistent source exclusion')
    else:
        raise ValueError('unsupported visual disposition')
    defects = decision['defectiveOldNails']
    if not defects or len(set(defects)) != len(defects) or any(i not in decision['reviewedHistoricalNailIndices'] for i in defects):
        raise ValueError('invalid defect indices')


def apply_dispositions(baseline, decisions):
    rows = copy.deepcopy(baseline['records'])
    index = unique([r for r in rows if r['split'] == 'train'], 'ordinal')
    unique(decisions, 'ordinal')
    for decision in decisions:
        row = index[decision['ordinal']]
        if row['currentSourceDisposition'] != 'pending_original_resolution_complete_source_and_mask_review':
            raise ValueError('cannot silently replace existing disposition')
        for key in ('fileName', 'sourceGroup', 'sourceImage', 'sourceLabel'):
            if row[key] != decision[key]:
                raise ValueError('reconstruction_mismatch: baseline identity')
        if row['historicalMaskCount'] != decision['historicalMaskCount']:
            raise ValueError('reconstruction_mismatch: historical denominator')
        row['currentSourceDisposition'] = decision['maskDecision']
        row['latestOriginalPixelReview'] = decision
        row['markerStatus'] = decision['markerDecision'] + '_ablation_pending'
        row['formalTrainingApproved'] = False
        row['trainingUse'] = 'prohibited'
    return rows


def audit(execution_ref):
    execution = read(execution_ref)
    inputs = execution['inputs']
    if checked(inputs['runnerSource']) != Path(__file__).resolve():
        raise ValueError('runner identity mismatch')
    guard_path = checked(inputs['readOnlyGuard'])
    sys.path.insert(0, str(guard_path.parent))
    spec = importlib.util.spec_from_file_location('native_review_guard', guard_path)
    guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
    guard.install_read_only_ultralytics_image_check()
    try:
        from PIL import Image
        import numpy as np
        from shapely.geometry import Polygon
        pack = read(inputs['nativeReviewPack']); visual = read(inputs['visualDecisions'])
        for key in ('modelCalls', 'optimizerSteps', 'formalTrainingApprovedImages'):
            if pack[key] != 0 or visual[key] != 0:
                raise ValueError('review scope must remain zero-model and unapproved')
        if visual['full30PilotAllowed']:
            raise ValueError('unexpected training authorization')
        if visual['inputs']['nativeReviewPack'] != inputs['nativeReviewPack']:
            raise ValueError('visual pack identity mismatch')
        built_execution = read(pack['inputs']['execution'])
        checked(built_execution['inputs']['runnerSource']); checked(built_execution['inputs']['readOnlyGuard'])
        scope = read(pack['inputs']['scope']); baseline = read(scope['inputs']['fullSplitReadiness'])
        plan = read(scope['inputs']['existingShardBuilderPlan']); checked(plan['builderSource'])
        shard = read(pack['inputs']['historicalShard'])
        frozen = unique(scope['sources'], 'ordinal'); originals = unique(shard['sourceImages'], 'ordinal')
        decisions = unique(visual['sourceDispositions'], 'ordinal')
        if [r['ordinal'] for r in pack['records']] != list(frozen) or list(decisions) != list(frozen):
            raise ValueError('reconstruction_mismatch: source coverage/order')
        limit = pack['maxPageSide']
        if limit != built_execution['maxPageSide'] or not pack['noResampling']:
            raise ValueError('native page size contract mismatch')
        counts = {'sourceImages': len(pack['records']), 'historicalNails': sum(r['historicalNails'] for r in pack['records']),
                  'sourceGroups': len({r['sourceGroup'] for r in pack['records']}),
                  'sourceTiles': sum(len(r['rawTiles']) for r in pack['records']),
                  'nailPanels': sum(len(r['nailPanels']) for r in pack['records'])}
        if counts != pack['counts'] or {k: counts[k] for k in scope['counts']} != scope['counts']:
            raise ValueError('reconstruction_mismatch: frozen counts')
        pixel_checks = 0; geometry_checks = 0
        for r in pack['records']:
            f = frozen[r['ordinal']]; old = originals[r['ordinal']]
            if (r['sourceImage'] != f['sourceImage'] or r['sourceLabel'] != f['sourceLabel'] or
                    [n['roiId'] for n in old['nails']] != f['historicalRoiIds'] or r['historicalNails'] != len(old['nails'])):
                raise ValueError('reconstruction_mismatch: frozen source/nails')
            validate_decision(r, decisions[r['ordinal']])
            for ref in decisions[r['ordinal']]['viewedArtifacts']: checked(ref)
            with Image.open(checked(r['sourceImage'])) as im: source = im.convert('RGB')
            if list(source.size) != r['imageSize'] or [t['box'] for t in r['rawTiles']] != tiles(*source.size, limit, limit):
                raise ValueError('reconstruction_mismatch: full source tile coverage')
            for t in r['rawTiles']:
                with Image.open(checked(t['image'])) as im:
                    if im.mode != 'RGB' or im.size != source.crop(t['box']).size or im.tobytes() != source.crop(t['box']).tobytes():
                        raise ValueError('raw source pixels changed')
                pixel_checks += 1
            expected_panels = []
            for nail in old['nails']:
                crop = source.crop(nail['cropBox'])
                with Image.open(checked(nail['nativeOverlay'])) as im: overlay = im.convert('RGB')
                if overlay.size != crop.size: raise ValueError('overlay size changed')
                boxes = tiles(*crop.size, (limit - 12) // 2, limit - 26)
                expected_panels.extend((nail['truthIndex'], nail['roiId'], nail['cropBox'], b) for b in boxes)
                panels = [p for p in r['nailPanels'] if p['truthIndex'] == nail['truthIndex']]
                if [p['cropTileBox'] for p in panels] != boxes: raise ValueError('nail tile coverage changed')
                for p in panels:
                    box = p['cropTileBox']; w, h = box[2] - box[0], box[3] - box[1]
                    with Image.open(checked(p['image'])) as im:
                        if im.mode != 'RGB' or im.size != (2 * w + 12, h + 26) or max(im.size) > limit:
                            raise ValueError('native pair page geometry changed')
                        if im.crop((0, 26, w, h + 26)).tobytes() != crop.crop(box).tobytes():
                            raise ValueError('pair raw pixels changed')
                        if im.crop((w + 12, 26, 2 * w + 12, h + 26)).tobytes() != overlay.crop(box).tobytes():
                            raise ValueError('pair overlay pixels changed')
                    pixel_checks += 2
            if [(p['truthIndex'], p['roiId'], p['cropBox'], p['cropTileBox']) for p in r['nailPanels']] != expected_panels:
                raise ValueError('reconstruction_mismatch: nail panel identity/order')
            shapes = []
            for line in checked(r['sourceLabel']).read_text(encoding='utf-8').splitlines():
                parts = line.split()
                if parts: shapes.append(Polygon(np.asarray([float(v) for v in parts[1:]]).reshape(-1, 2) * np.asarray(source.size)))
            invalid = [i + 1 for i, p in enumerate(shapes) if not p.is_valid or p.area <= 0]
            overlaps = [{'left': i + 1, 'right': j + 1, 'area': shapes[i].intersection(shapes[j]).area}
                        for i in range(len(shapes)) for j in range(i + 1, len(shapes))
                        if shapes[i].is_valid and shapes[j].is_valid and shapes[i].intersection(shapes[j]).area > 0]
            if len(shapes) != r['historicalNails'] or invalid != r['invalidPolygons'] or overlaps != r['overlapPairs']:
                raise ValueError('geometry reconstruction mismatch')
            geometry_checks += len(shapes)
        # Exact filename lookup preserves historical canonical identities; no new truth manifest is approved.
        original_scope = read(baseline['inputs']['frozenScope'])
        canonical = read(original_scope['inputs']['canonicalTruthIndex'])
        truth_index = unique(canonical['canonicalTruths'], 'fileName')
        updated = apply_dispositions(baseline, visual['sourceDispositions'])
        repair = [{**d, 'canonicalHistoricalTruth': truth_index.get(d['fileName']),
                   'repairMode': 'versioned_original_pixel_complete_polygons_all_nails_then_visual_review',
                   'newTruthApproved': False} for d in visual['sourceDispositions'] if d['maskDecision'] == 'label_rework']
        return {'schemaVersion': 1, 'ok': True, 'decision': 'visual_dispositions_bound_pixel_fidelity_verified_training_prohibited',
                'execution': execution_ref, 'inputs': inputs, 'baselineFullSplit': scope['inputs']['fullSplitReadiness'],
                'canonicalTruthIndex': original_scope['inputs']['canonicalTruthIndex'],
                'sourceDispositions': visual['sourceDispositions'], 'repairSources': repair,
                'currentFullSplitRecords': updated,
                'counts': {**pack['counts'], 'sourceQualityExcluded': len(decisions) - len(repair),
                           'sourceQualityPassedMaskRework': len(repair), 'repairNails': sum(d['historicalMaskCount'] for d in repair),
                           'rawAndOverlayPixelChecks': pixel_checks, 'geometryNails': geometry_checks,
                           'trainDispositions': dict(sorted(Counter(r['currentSourceDisposition'] for r in updated if r['split'] == 'train').items()))},
                'fidelity': {'allSourceTilesAndNailPanelsExact': True, 'historicalDenominatorsUnchanged': True},
                'visualReviewReplayMeaning': 'Replays manually recorded evidence bindings and pixels, not the original visual judgment.',
                'modelCalls': 0, 'optimizerSteps': 0, 'trainingAllowed': False,
                'full30PilotAllowed': False, 'formalTrainingApprovedImages': 0}
    finally:
        guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        report = json.loads(args.verify_report.read_text(encoding='utf-8'))
        if audit(report['execution']) != report: raise ValueError('report reconstruction mismatch')
        print(json.dumps({'ok': True, 'decision': 'report_replay_identical'}, ensure_ascii=False))
    else:
        if not args.execution or not args.output: parser.error('--execution and --output required')
        if args.output.exists(): raise FileExistsError(args.output)
        result = audit(bind(args.execution))
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: result[k] for k in ('ok', 'decision', 'counts')}, ensure_ascii=False))


if __name__ == '__main__': main()
