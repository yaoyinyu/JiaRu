"""按现行角色及完整真值构建隔离开发训练副本；不授予正式发布资格。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
from pathlib import Path


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(ref):
    path = Path(ref['path']).resolve()
    if bind(path) != ref:
        raise ValueError(f'reconstruction_mismatch: {path}')
    return path


def read(ref):
    return json.loads(checked(ref).read_bytes())


def new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(raw(value)); stream.flush(); os.fsync(stream.fileno())


def load(path, name):
    path = Path(path); sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def key(identity):
    return identity['split'], identity['fileName'], identity['imageSha256']


def unresolved_groups(disposition):
    queue = read(disposition['inputs']['queue'])
    pairs = {tuple(row['pairIdentity']): row for row in queue['pairs']}
    if len(pairs) != len(queue['pairs']):
        raise ValueError('duplicate pair identities')
    pending = {tuple(pair) for pair in disposition['pendingPairIdentities']}
    pending.update(tuple(row['pairIdentity']) for row in disposition.get('currentUncertainPairDecisions', []) if row.get('decision') == 'uncertain')
    groups = set()
    for pair in pending:
        for observation in pairs[pair]['observations']:
            groups.update(observation['target']['sourceGroups'])
    return groups


def polygons(ref, width, height, identity):
    from shapely.geometry import Polygon
    path = checked(ref)
    result = []
    if path.suffix == '.txt':
        for row in path.read_text(encoding='utf-8').splitlines():
            fields = row.split()
            if not fields: continue
            if fields[0] != '0' or len(fields) < 7 or len(fields) % 2 != 1:
                raise ValueError('invalid normalized polygon label')
            values = list(map(float, fields[1:]))
            result.append([(values[i] * width, values[i + 1] * height) for i in range(0, len(values), 2)])
    else:
        value = read(ref); image = value.get('image', {})
        if image.get('fileName', identity['fileName']) != identity['fileName'] or image.get('sha256', identity['imageSha256']) != identity['imageSha256']:
            raise ValueError('annotation image identity')
        if image.get('width', width) != width or image.get('height', height) != height:
            raise ValueError('annotation image size')
        for item in value['annotations']:
            if item.get('label', 'nail_texture') != 'nail_texture':
                raise ValueError('annotation class')
            result.append([(float(p['x']), float(p['y'])) if isinstance(p, dict) else tuple(map(float, p)) for p in item['polygon']])
    for points in result:
        if not all(math.isfinite(x) and math.isfinite(y) and 0 <= x <= width and 0 <= y <= height for x, y in points):
            raise ValueError('invalid polygon coordinates')
    shapes = [Polygon(points) for points in result]
    if not shapes or any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError('invalid polygon geometry')
    if any(a.intersection(b).area > 0 for i, a in enumerate(shapes) for b in shapes[i + 1:]):
        raise ValueError('polygon overlap')
    return result


def validate(plan):
    if plan['purpose'] != 'stage_a_normal_development_training' or plan['markerPolicy'] != 'retain_original_defer_ablation_to_pre_release':
        raise ValueError('development scope')
    quality = read(plan['inputs']['quality']); roles = read(plan['inputs']['roles'])
    if not quality['ok'] or len(roles['records']) != 286:
        raise ValueError('authority report')
    blocked = unresolved_groups(read(plan['inputs']['pairDisposition']))
    index = {key(row['identity']): row for row in roles['records']}
    vals = {key(row['identity']): row for row in roles['currentInternalValTruthRecords']}
    if len(index) != len(roles['records']) or len(vals) != len(roles['currentInternalValTruthRecords']):
        raise ValueError('role identity collision')
    expected = [row for row in quality['currentQualityEligibleInventory'] if row['sourceGroup'] not in blocked]
    if plan['records'] != expected:
        raise ValueError('reconstruction_mismatch: source selection must be metadata-only exact cohort')
    lineage = read(plan['inputs']['lineage'])
    parents = {key(row['identity']): row for row in lineage['records']}
    reference = read(plan['inputs']['referenceInventory'])
    # 重放权威历史角色账和补充保护角色，未知近重复组仍禁止入本训练副本。
    helper = load(checked(reference['inputs']['rolesHelper']), 'development_role_helper')
    role_sets, _ = helper.role_sets(read(reference['inputs']['roleSourceSupply']))
    old_plan = read(reference['inputs']['frozenReadinessPlan'])
    replacement = read(old_plan['inputs']['releaseTestRoleReplacement'])
    replacement_rows = replacement['items'] + replacement['withdrawnTrainItems']
    role_sets['releaseTestReplacement'] = {'hashes': {r['imageSha256'] for r in replacement_rows}, 'sourceGroups': {r['sourceGroup'] for r in replacement['withdrawnTrainGroups']} | {r['sourceGroup'] for r in replacement_rows}}
    registry = read(old_plan['inputs']['protectedHardNegativeRegistry'])
    negatives = []
    for entry in registry['entries']:
        # 登记行包含独立role字段；文件绑定仍严格匹配绝对路径与SHA。
        manifest = read({'path': entry['path'], 'sha256': entry['sha256']})
        if entry['role'] not in ('training', 'test', 'holdout') or not manifest['ok'] or manifest['status'] != 'PASS':
            raise ValueError('protected registry role/status')
        negatives.extend(manifest['items'])
    role_sets['protectedHardNegativeRegistry'] = {'hashes': {r['imageSha256'] for r in negatives}, 'sourceGroups': {r['sourceGroup'] for r in negatives}}
    val_rows = [row for row in roles['records'] if row['identity']['split'] == 'val']
    role_sets['currentInternalVal'] = {'hashes': {r['identity']['imageSha256'] for r in val_rows}, 'sourceGroups': {r['sourceGroup'] for r in val_rows}}
    readiness = load(Path(__file__).with_name('audit-full-split-data-readiness.py'), 'development_readiness_helper')
    selected = []
    for row in expected:
        ident = row['identity']; current = index[key(ident)]
        if row['sourceGroup'] != current['sourceGroup'] or row['knownRoleConflicts'] or current['protectedTrainConflicts']:
            raise ValueError('protected current role conflict')
        lineage_row = parents.get(key(ident)); ancestor = list(current['parents'])
        if lineage_row:
            if lineage_row['protectedRoleConflicts'] or not lineage_row['lineageMetadataAndPixelsVerified']:
                raise ValueError('protected parent conflict')
            ancestor.append(lineage_row['parent']); checked(lineage_row['parent']['sourceImage'])
        hits = readiness.protected_hits(ident['imageSha256'], row['sourceGroup'], ancestor, role_sets)
        if ident['split'] == 'train' and (current['upstreamDevelopmentSplit'] != 'train' or any(hit['role'] != 'developmentTrain' for hit in hits)):
            raise ValueError('protected identity/parent/group cannot return to train')
        checked(row['sourceImage']); checked(row['annotation'])
        truth = current['currentTruth'] if ident['split'] == 'train' else vals[key(ident)]
        if row['annotation'] != truth['annotation']:
            raise ValueError('current complete truth identity drift')
        if ident['split'] == 'train':
            if truth['geometry']['maskCount'] != row['maskCount'] or not truth['geometry']['polygonValid'] or not truth['geometry']['pairwiseZeroOverlap']:
                raise ValueError('current truth geometry')
            for evidence in truth['reviewEvidence']: checked(evidence)
            size = truth['imageSize']
        else:
            checked(truth['maskClosure'])
            size = read(plan['inputs']['readiness'])['records']
            size = next(r['size'] for r in size if key(r['identity']) == key(ident))
        ps = polygons(row['annotation'], *size, ident)
        if len(ps) != row['maskCount']:
            raise ValueError('truth count changed')
        selected.append({**row, 'size': size, 'polygons': ps, 'parentRoleMatches': hits})
    train = [r for r in selected if r['identity']['split'] == 'train']
    val = [r for r in selected if r['identity']['split'] == 'val']
    if not train or not val or {r['sourceGroup'] for r in train} & {r['sourceGroup'] for r in val}:
        raise ValueError('nonempty disjoint current splits required')
    if {r['identity']['imageSha256'] for r in train} & {r['identity']['imageSha256'] for r in val}:
        raise ValueError('split byte identity overlap')
    counts = {s: {'sources': len([r for r in selected if r['identity']['split'] == s]), 'nails': sum(r['maskCount'] for r in selected if r['identity']['split'] == s)} for s in ('train', 'val')}
    if counts != plan['counts']:
        raise ValueError('denominator contract')
    if max(r['maskCount'] for r in train) > plan['reachability']['candidateBudget'] or plan['reachability']['upperBoundRatio'] != 1:
        raise ValueError('stage A optimistic count ceiling unreachable')
    return selected


def inventory(root):
    return [bind(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'materialization.json' and p.suffix != '.cache']


def verify(report_path):
    report = json.loads(Path(report_path).read_bytes()); plan = read(report['plan'])
    selected = validate(plan); root = Path(report['root'])
    if report['files'] != inventory(root): raise ValueError('dataset file tree drift')
    for row in selected:
        split = row['identity']['split']; name = row['identity']['fileName']
        if bind(root / 'images' / split / name)['sha256'] != row['sourceImage']['sha256']:
            raise ValueError('original image bytes changed')
    return {'ok': True, 'counts': plan['counts'], 'files': len(report['files']), 'formalReleaseAllowed': False}


def materialize(plan_path, root):
    plan = json.loads(plan_path.read_bytes()); selected = validate(plan)
    root.mkdir(parents=True, exist_ok=False)
    guard = load(checked(plan['inputs']['readOnlyGuard']), 'development_image_guard')
    guard.install_read_only_ultralytics_image_check()
    from PIL import Image
    try:
        for row in selected:
            with Image.open(checked(row['sourceImage'])) as image:
                image.load()
                if list(image.size) != row['size']: raise ValueError('image size drift')
            split = row['identity']['split']; name = row['identity']['fileName']
            image_path = root / 'images' / split / name
            label_path = root / 'labels' / split / (Path(name).stem + '.txt')
            image_path.parent.mkdir(parents=True, exist_ok=True); label_path.parent.mkdir(parents=True, exist_ok=True)
            if image_path.exists() or label_path.exists(): raise ValueError('dataset stem collision')
            shutil.copyfile(checked(row['sourceImage']), image_path)
            w, h = row['size']
            text = ''.join('0 ' + ' '.join(format(v, '.17g') for x, y in points for v in (x / w, y / h)) + '\n' for points in row['polygons'])
            # 原浮点polygon存储域的可逆序列化门；无容差放宽。
            decoded = [list(map(float, line.split()[1:])) for line in text.splitlines()]
            if any(abs(d[2*i] * w - x) > 1e-10 or abs(d[2*i+1] * h - y) > 1e-10 for points, d in zip(row['polygons'], decoded) for i, (x, y) in enumerate(points)):
                raise ValueError('normalized annotation reconstruction mismatch')
            with label_path.open('xb') as stream: stream.write(text.encode())
        yaml = f'path: {json.dumps(str(root), ensure_ascii=False)}\ntrain: images/train\nval: images/val\nnames:\n  0: nail_texture\n'
        with (root / 'dataset.yaml').open('xb') as stream: stream.write(yaml.encode('utf-8'))
        new(root / 'materialization.json', {'schemaVersion': 1, 'ok': True, 'purpose': plan['purpose'], 'plan': bind(plan_path), 'root': str(root), 'counts': plan['counts'], 'files': inventory(root), 'originalImageBytesPreserved': True, 'markerAblationDeferred': True, 'formalSourceIndependenceProven': False, 'formalReleaseAllowed': False})
    finally:
        guard.remove_ultralytics_label_caches(root)
        for path in plan['cacheCleanupRoots']: guard.remove_ultralytics_label_caches(Path(path))
    return verify(root / 'materialization.json')


def main():
    p = argparse.ArgumentParser(); p.add_argument('--plan', type=Path); p.add_argument('--output', type=Path); p.add_argument('--verify-report', type=Path); args = p.parse_args()
    result = verify(args.verify_report) if args.verify_report else materialize(args.plan.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
