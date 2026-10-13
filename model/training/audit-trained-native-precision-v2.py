"""同权重全候选精度复验；持久化两头输出，独立重放数值与容量门。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('precision_v2_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
compare = d.load(HERE / 'verify-native-multiscale-browser-v2.py', 'precision_v2_compare')


def buffer(ref, count):
    path = d.checked({k: ref[k] for k in ('path', 'sha256')})
    if path.stat().st_size != count * 4:
        raise ValueError('float32 buffer byte cardinality')
    value = np.fromfile(path, np.float32)
    if not np.isfinite(value).all():
        raise ValueError('nonfinite reference or captured head')
    return value


def resources(plan_path):
    plan = d.read(d.bind(plan_path))
    if plan['purpose'] != 'same_weights_full68_strict_fp32_capacity_and_precision' or any(plan[k] for k in ('optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed')):
        raise ValueError('zero optimization train-only precision scope')
    if plan['cpuTorchInputsAllowed'] != 68 or plan['strictCudaInputsAllowed'] != 68 or plan['requiredMaximumNumericDifference'] != 1e-4 or plan['requiredDecodedPixelDifferences'] != 0:
        raise ValueError('full68 numeric/pixel contract')
    for ref in plan['inputs'].values():
        d.checked(ref)
    old = d.read(plan['inputs']['cpuFailure'])
    diagnostic = d.read(plan['inputs']['oldDiagnostic'])
    scope = d.read(old['inputs']['scope'])
    for ref in scope['inputs'].values():
        d.checked(ref)
    capacity = d.read(scope['inputs']['capacity'])
    headplan = d.read(capacity['inputs']['plan'])
    features = d.read(headplan['inputs']['featureReport'])
    prior_scope = d.read(features['inputs']['scope'])
    prior_plan = d.read(prior_scope['inputs']['priorPlan'])
    trainer = d.load(d.checked(prior_plan['inputs']['trainer']), 'precision_v2_trainer')
    _, _, rows, net, metric, guard, native = trainer.resources(d.checked(prior_scope['inputs']['priorPlan']))
    try:
        identities = scope['candidateIdentities']
        for records in (rows, old['records'], diagnostic['records'], capacity['perCandidate'], scope['savedOutputs']):
            if [r['candidateIdentity'] for r in records] != identities:
                raise ValueError('all68 identity reconstruction_mismatch')
        if len(rows) != 68 or sum(r['presenceTarget'] for r in rows) != 66 or old['ok']:
            raise ValueError('frozen denominator/failure')
        # 全清单守卫先于任何新前向；同时复验冻结存档与旧CPU判决。
        for row, oldrow, saved in zip(rows, old['records'], scope['savedOutputs'], strict=True):
            h, w = oldrow['h'], oldrow['w']
            if row['ordinal'] != oldrow['ordinal'] or row['nativeSize'] != [w, h]:
                raise ValueError('native dimensions/ordinal')
            for name, count in (('input', 4*h*w), ('mask', h*w), ('presence', 1), ('cpu-mask', h*w), ('cpu-presence', 1)):
                buffer(oldrow['paths'][name], count)
            with np.load(d.checked(saved['output']), allow_pickle=False) as archive:
                if not np.array_equal(archive['logits'].reshape(-1), buffer(oldrow['paths']['mask'], h*w)) or not np.array_equal(archive['presenceLogit'].reshape(1), buffer(oldrow['paths']['presence'], 1)):
                    raise ValueError('frozen Torch output binding')
            stats = compare.compare_outputs(buffer(oldrow['paths']['mask'], h*w), buffer(oldrow['paths']['presence'], 1), buffer(oldrow['paths']['cpu-mask'], h*w), buffer(oldrow['paths']['cpu-presence'], 1), h, w)
            if stats != oldrow['cpuOrt']:
                raise ValueError('original CPU parity reconstruction_mismatch')
        return plan, old, diagnostic, scope, capacity, rows, net, metric, guard, native
    except BaseException:
        for path in native['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(path))
        raise


def reconstruct(plan_path, captures):
    plan, old, diagnostic, scope, capacity, rows, net, metric, guard, native = resources(plan_path)
    records = []
    try:
        if len(captures) != 68 or [c['candidateIdentity'] for c in captures] != scope['candidateIdentities']:
            raise ValueError('complete captured identities')
        for row, oldrow, captured in zip(rows, old['records'], captures, strict=True):
            h, w = oldrow['h'], oldrow['w']
            a = {name: buffer(oldrow['paths'][name], count) for name, count in (('mask', h*w), ('presence', 1), ('cpu-mask', h*w), ('cpu-presence', 1))}
            c = {name: buffer(captured['paths'][name], h*w if name.endswith('mask') else 1) for name in ('cpu-mask', 'cpu-presence', 'strict-mask', 'strict-presence')}
            from PIL import Image
            with Image.open(d.checked(row['paths']['nativeTarget'])) as image:
                image.load()
                truth = np.asarray(image).copy() >= 128
            if truth.shape != (h, w) or int(truth.sum()) != row['nativeTargetPixels'] or bool(truth.any()) != row['presenceTarget']:
                raise ValueError('native truth denominator')
            prediction = net.decode(c['strict-mask'].reshape(h, w), float(c['strict-presence'][0]))
            if row['presenceTarget']:
                boundary = metric.boundary_stats(truth, prediction, 2)
                iou = int((truth & prediction).sum()) / max(1, int((truth | prediction).sum()))
                quality = {'positive': True, 'presenceAccepted': bool(c['strict-presence'][0] >= 0), 'iou': iou, **boundary, 'jointPass': iou >= .75 and boundary['boundaryIoU'] >= .75 and boundary['boundaryF1'] >= .9}
            else:
                quality = {'positive': False, 'outputPixels': int(prediction.sum()), 'rejected': not prediction.any()}
            records.append({'candidateIdentity':row['candidateIdentity'], 'ordinal':row['ordinal'], 'h':h, 'w':w,
                'cpuTorchVsOrt': compare.compare_outputs(c['cpu-mask'], c['cpu-presence'], a['cpu-mask'], a['cpu-presence'], h, w),
                'strictCudaVsOrt': compare.compare_outputs(c['strict-mask'], c['strict-presence'], a['cpu-mask'], a['cpu-presence'], h, w),
                'oldCudaVsStrictCuda': compare.compare_outputs(a['mask'], a['presence'], c['strict-mask'], c['strict-presence'], h, w),
                'strictFp32Quality': quality})
        summary = {}
        for label in ('cpuTorchVsOrt', 'strictCudaVsOrt', 'oldCudaVsStrictCuda'):
            summary[label] = {'maxAbs':max(r[label]['maxAbsoluteDifference'] for r in records), 'numericFailed':sum(not r[label]['numericGatePassed'] for r in records), 'pixelDifferences':sum(r[label]['decodedMaskPixelDifference'] for r in records), 'presenceFailed':sum(not r[label]['presenceDecisionMatched'] for r in records)}
        # v1无可重放CPU/严格CUDA存档；新捕获必须复算其全部逐实例诊断。
        comparable = [{k:r[k] for k in ('candidateIdentity','ordinal','h','w','cpuTorchVsOrt','strictCudaVsOrt','oldCudaVsStrictCuda')} for r in records]
        if comparable != diagnostic['records'] or summary != diagnostic['summary']:
            raise ValueError('old precision diagnostic reconstruction_mismatch')
        positives = [r['strictFp32Quality'] for r in records if r['strictFp32Quality']['positive']]
        negatives = [r['strictFp32Quality'] for r in records if not r['strictFp32Quality']['positive']]
        quality = {'positiveCount':len(positives), 'rejectCount':len(negatives), 'positivePresenceAccepted':sum(r['presenceAccepted'] for r in positives),
            'meanIou':float(np.mean([r['iou'] for r in positives])), 'meanBoundaryIou':float(np.mean([r['boundaryIoU'] for r in positives])), 'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in positives])),
            'jointPassCount':sum(r['jointPass'] for r in positives), 'rejectedCount':sum(r['rejected'] for r in negatives), 'rejectOutputPixels':sum(r['outputPixels'] for r in negatives)}
        quality_ok = quality['jointPassCount'] >= 53 and quality['meanIou'] >= .85 and quality['meanBoundaryF1'] >= .9 and quality['positivePresenceAccepted'] == 66 and quality['rejectedCount'] == 2 and quality['rejectOutputPixels'] == 0
        migration = [{'candidateIdentity':new['candidateIdentity'], 'oldJointPass':previous.get('jointPass'), 'newJointPass':new['strictFp32Quality'].get('jointPass')} for previous,new in zip(capacity['perCandidate'],records,strict=True) if previous.get('jointPass') != new['strictFp32Quality'].get('jointPass')]
        return {'schemaVersion':2, 'ok':True, 'decision':'precision_failure_replayed_strict_fp32_capacity_independently_measured',
            'inputs':{'plan':d.bind(plan_path),'auditor':d.bind(__file__)}, 'captures':captures, 'records':records, 'summary':summary,
            'strictFp32CapacityPassed':quality_ok, 'strictFp32Metrics':quality, 'jointPassMigration':migration,
            'inferencePolicy':{'cudnnAllowTf32':False,'matmulAllowTf32':False}, 'sameWeights':scope['inputs']['trainedWeights'],
            'oldCapacityAndFailurePreserved':True, 'oldDiagnosticReconstructed':True, 'oldCpuParityPassed':False, 'browserAdmitted':False,
            'newCpuTorchInputs':68, 'newStrictCudaInputs':68, 'newOrtInputs':0, 'optimizerSteps':0, 'valModelInputs':0, 'protectedModelInputs':0,
            'releaseIdentityRegistered':False, 'formalReleaseAllowed':False,'productHold':True}
    finally:
        for path in native['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(path))


def capture(plan_path, root):
    if root.exists():
        raise ValueError('new output already exists; use read-only replay')
    plan, old, _, scope, _, _, net, _, guard, native = resources(plan_path)
    original = (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32)
    captures = []
    try:
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.set_num_threads(4)
        state = torch.load(d.checked(scope['inputs']['trainedWeights']), map_location='cpu', weights_only=True)
        models = []
        for device in ('cpu','cuda'):
            model = net.NativeConditionalMaskRefiner().to(device).eval()
            model.requires_grad_(False)
            model.load_state_dict(state, strict=True)
            models.append(model)
        root.mkdir(parents=True, exist_ok=False)
        for row in old['records']:
            h, w = row['h'], row['w']
            x = torch.from_numpy(buffer(row['paths']['input'], 4*h*w).reshape(1,4,h,w))
            paths = {}
            for label, model, device in zip(('cpu','strict'), models, ('cpu','cuda'), strict=True):
                with torch.inference_mode():
                    mask, presence = model(x.to(device))
                if tuple(mask.shape) != (1,1,h,w) or tuple(presence.shape) != (1,1):
                    raise ValueError('actual output shape')
                for name, tensor in (('mask',mask),('presence',presence)):
                    value = tensor.cpu().numpy()
                    if value.dtype != np.float32 or not np.isfinite(value).all():
                        raise ValueError('actual output float32 finite')
                    path = root / f'{row["ordinal"]:03d}-{label}-{name}.bin'
                    with path.open('xb') as stream:
                        stream.write(value.tobytes());stream.flush();os.fsync(stream.fileno())
                    paths[f'{label}-{name}'] = d.bind(path)
            captures.append({'candidateIdentity':row['candidateIdentity'],'ordinal':row['ordinal'],'paths':paths})
        for model in models:
            if any(not torch.equal(value.cpu(),state[name]) for name,value in model.state_dict().items()):
                raise ValueError('weights modified')
    except BaseException as error:
        if root.exists():
            d.new(root/'failure.json',{'ok':False,'type':type(error).__name__,'message':str(error),'completedCandidates':len(captures),'optimizerSteps':0})
        raise
    finally:
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = original
        for path in native['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(path))
    result = reconstruct(plan_path,captures)
    d.new(root/'report.json',result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify-report',type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = d.read(d.bind(args.verify_report))
        d.checked(old['inputs']['auditor'])
        result = reconstruct(d.checked(old['inputs']['plan']),old['captures'])
        if result != old:
            raise ValueError('precision v2 report reconstruction_mismatch')
    else:
        result = capture(args.plan.resolve(),args.output.resolve())
    print(json.dumps({k:result[k] for k in ('ok','summary','strictFp32CapacityPassed','strictFp32Metrics','jointPassMigration','optimizerSteps')}))
