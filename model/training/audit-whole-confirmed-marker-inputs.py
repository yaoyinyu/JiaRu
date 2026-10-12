"""逐源六完整对照的实看/像素/角色审计；局部输入不批准整组或模型。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('confirmed_input_pixels', HERE / 'native-source-page-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)
bind, read, checked = layout.bind, layout.read, layout.checked
NAMES = ['remove', 'blank_remove_control', 'occlude', 'blank_occlude_control', 'move_marker', 'blank_move_control']
def key(r):
    i = r['identity']
    return i['split'], i['fileName'], i['imageSha256']
def audit(plan_ref):
    plan = read(plan_ref)
    assert plan['runner'] == bind(__file__)
    pack, locations, roles = [read(plan['inputs'][k]) for k in ['originalControls', 'rawLocations', 'roles']]
    assert pack['wholeGroupMembershipPreserved'] == locations['wholeGroupMembershipPreserved']
    source_map = {key(r): r for r in pack['records']}
    location_map = {key(r): r for r in locations['records']}
    roles_map = {key(r): r for r in roles['records']}
    truth_map = {key(r): r for r in roles['currentInternalValTruthRecords']}
    assert len(roles_map) == len(roles['records']) == plan['expectedRoleRecords']
    for source in pack['records']:
        role, truth = roles_map[key(source)], truth_map[key(source)]
        assert role['sourceImage'] == source['sourceImage'] and truth['annotation'] == source['annotation']
        assert source['maskCount'] == truth['maskCount']
        assert role['trainingUse'] == 'prohibited' and not role['formalTrainingApproved']
        assert not truth['trainingAllowed'] and not truth['formalIndependentValAllowed']
        checked(source['sourceImage'])
        checked(source['annotation'])
    preparations = [read(ref) for ref in plan['reviewPreparations']]
    pages = {}
    for prep in preparations:
        for row in prep['records']:
            identity = key(row), row['variant']
            assert identity not in pages
            source = source_map[key(row)]
            assert row['annotation'] == source['annotation'] and row['originalControl'] == source['variants'][row['variant']]
            checked(row['page'])
            pages[identity] = row
    observations, payload = {}, 0
    for actual_ref in plan['actualReviews']:
        actual = read(actual_ref)
        assert actual['actuallyViewed'] and actual['wholeImageOnly'] and actual['coordinateOriginsChecked']
        assert actual['toolScalingNotice'] is False and len(actual['transport']) == len(actual['observations']) <= 6
        for transport, observation in zip(actual['transport'], actual['observations'], strict=True):
            assert transport['sourceOrdinal'] == observation['sourceOrdinal']
            assert transport['variant'] == observation['variant']
            source = pack['records'][observation['sourceOrdinal'] - 1]
            identity = key(source), observation['variant']
            assert identity not in observations and identity in pages
            page = pages[identity]
            assert transport['path'] == page['page']['path'] and transport['detail'] == 'original'
            assert transport['actualEncodedBytes'] == page['fileBytes'] == checked(page['page']).stat().st_size
            assert observation['decision'] == 'local_control_visual_pass' and observation['reason']
            assert location_map[key(source)]['markerEnvelopeApproved'] and location_map[key(source)]['markerPresentVisuallyConfirmed']
            observations[identity] = {'observation': observation, 'actualReview': actual_ref, 'pageRecord': page}
            payload += transport['actualEncodedBytes']
    selected = sorted({s[0] for s in observations})
    for identity in selected:
        assert {name for sid, name in observations if sid == identity} == set(NAMES)
    result_rows = []
    guard = read(read(pack['plan'])['inputs']['guardReport'])
    with layout.guarded_pixels(guard):
        for identity in selected:
            source = source_map[identity]
            rendered = {}
            for name in NAMES:
                row = observations[identity, name]['pageRecord']
                original = layout.load_rgb(row['originalControl'])
                displayed = layout.load_rgb(row['page'])
                assert list(original.size) == row['originalSize']
                assert list(displayed.size) == row['pageSize'] == [original.width, original.height + 128]
                assert row['sourceBox'] == [0, 0, *row['originalSize']] and row['pageOrigin'] == [0, 0] and row['resampling'] is False
                assert displayed.crop(tuple(row['sourceBox'])).tobytes() == original.tobytes()
                assert hashlib.sha256(original.tobytes()).hexdigest() == row['originalControlRgbSha256'] == source['variantPixelEvidence'][name]['rgbSha256']
                assert source['variantPixelEvidence'][name]['nailPixelsChanged'] == source['variantPixelEvidence'][name]['protectedPixelsChanged'] == 0
                rendered[name] = np.asarray(original)
            delta = np.any(rendered['move_marker'] != rendered['blank_move_control'], axis=2)
            allowed = np.zeros(delta.shape, bool)
            x1, y1, x2, y2 = source['relocationBox']
            allowed[y1:y2, x1:x2] = True
            assert not (delta & ~allowed).any() and int(delta.sum()) == source['matchedRelocation']['pairDifferentPixels']
            result_rows.append({**source, 'rawLocation': location_map[identity],
                                'completeControlEvidence': {n: observations[identity, n] for n in NAMES},
                                'localInputVisualControlsComplete': True, 'matchedRelocationOutsideDestinationPixels': 0,
                                'residualBackgroundTextureConfound': True, 'modelAblationQualified': False,
                                'trainingAllowed': False})
    return {'schemaVersion': 1, 'ok': True, 'decision': 'partial_native_input_controls_complete_whole_group_and_model_hold',
            'plan': plan_ref, 'records': result_rows, 'wholeGroupMembershipPreserved': pack['wholeGroupMembershipPreserved'],
            'counts': {'fullGroupSources': len(pack['records']), 'fullGroupNails': sum(r['maskCount'] for r in pack['records']),
                       'completeLocalInputSources': len(result_rows), 'completeLocalInputNails': sum(r['maskCount'] for r in result_rows),
                       'actuallyViewedControlPages': len(observations), 'actualEncodedControlBytes': payload,
                       'wholeGroupInputQualifiedSources': 0, 'modelMarkerQualifiedSources': 0},
            'wholeGroupInputControlsQualified': False, 'wholeGroupMarkerQualification': False,
            'modelProbeAllowed': False, 'projectModelCalls': 0, 'optimizerSteps': 0,
            'trainingAllowed': False, 'productHold': True}
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    args = parser.parse_args()
    if args.verify_report:
        report = read(bind(args.verify_report))
        assert audit(report['plan']) == report
        result = report
    else:
        assert args.plan and args.output
        result = audit(bind(args.plan))
        with args.output.open('xb') as f:
            f.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
            f.flush()
            os.fsync(f.fileno())
    print(json.dumps({'ok': True, 'counts': result['counts'], 'trainingAllowed': False}))
