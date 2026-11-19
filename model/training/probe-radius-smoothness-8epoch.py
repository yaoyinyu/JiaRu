"""半径平滑性正则的短跑探针：只回答「抖动是否真的下降、损失是否发散」。

本脚本**不是**可登记的正式训练（不写 model/reviews、不产权重候选、不碰门），
只为方案 S2 提供方向性信号。装配路径全部复用仓库自身实现，不手工复刻：

    runner.setup(base)                      # 模型/recipe/arrays/codec/helper
    <86 层>.install(model, helper, p)       # capacity + joint geometry + initialWeights
    <86 层>.load_joint_row(...)             # strip + geometry cache 行装配
    joint-geometry-optimizer.build(model,p) # 与正式训练同款双组 AdamW（geometry 1/10 学习率）

唯一被替换的是目标函数：native-radial-smoothness-loss（λ 可调，λ=0 时逐位等价上游
native-side-boundary-loss，即已关闭的第90次配方末端）。

保真门：epochs=0 且 λ=0 时，634 甲的原生半径抖动必须复现 cycle096 的 diffStd≈3.14px
（口径 std(|r[i+1]-r[i]|)，float64）。复现不出即说明装配路径或数据绑定已偏离基线，
脚本直接失败，不进入训练。

用法：
    python probe-radius-smoothness-8epoch.py --epochs 0 --lambda 0 --tag fidelity
    python probe-radius-smoothness-8epoch.py --epochs 8 --lambda 0 --tag control
    python probe-radius-smoothness-8epoch.py --epochs 8 --lambda 0.1 --tag smooth010
"""

import argparse
import json
import random
import sys
import time
import traceback
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
BASE = ROOT / 'model/reviews/cycle016-wevis-real-material-v1/batch037'
BASELINE_PLAN = BASE / 'real-only100-neighborhood90-side634-v1/plan.json'
REPORTS = ROOT / 'model/reports'
# cycle096 在 634 甲上测得的原生半径抖动（std(|Δr|)，float64），作为装配保真参照。
REFERENCE_DIFF_STD = 3.14
REFERENCE_TOLERANCE = 0.25


def load(path, name):
    spec = spec_from_file_location(name, path)
    value = module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def walk(node, attribute):
    """沿 oneoff 脚本的包装链找到真正持有该属性的那一层。

    `parent` 指向被包装的上层脚本，`m` 指向供给 io/OUT 的模板模块，两者都要跟；
    只跟 `m` 会跳过那些仅以 `parent` 身份出现的中间层（如第86次的 joint 层）。
    """
    queue, seen = [node], set()
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        if hasattr(current, attribute):
            return current
        queue.extend(m for m in (getattr(current, 'parent', None), getattr(current, 'm', None)) if m is not None)
    raise SystemExit(f'attribute {attribute} not found along the oneoff chain')


def build_two_groups(model, plan):
    """与 joint-geometry-optimizer.build 同规则的双组 AdamW。

    该 helper 的冻结计数用 79（含 `local.offsets` / `local.prior` 两个 buffer），
    与 `named_parameters()` 的 77 口径不一致；本探针只按参数名分组，冻结侧不参与优化，
    因此按同一前缀规则自行构造，并把实测计数写进报告。
    """
    geometry, neighborhood = [], []
    for name, value in model.named_parameters():
        if name.startswith('previous.base.'):
            assert not value.requires_grad, name
            continue
        assert value.requires_grad, name
        (geometry if name.startswith('previous.') else neighborhood).append((name, value))
    assert (len(geometry), len(neighborhood)) == (24, 40), (len(geometry), len(neighborhood))
    multiplier = plan['geometryLearningRateMultiplier']
    assert 0 < multiplier < 1
    groups = [
        dict(params=[v for _, v in geometry], parameterNames=[n for n, _ in geometry],
             branch='geometry', lr=plan['learningRate'] * multiplier),
        dict(params=[v for _, v in neighborhood], parameterNames=[n for n, _ in neighborhood],
             branch='neighborhood', lr=plan['learningRate']),
    ]
    return torch.optim.AdamW(groups, weight_decay=plan['weightDecay'])


def jitter(radius):
    values = radius.astype(np.float64)
    previous = np.concatenate([values[-1:], values[:-1]])
    following = np.concatenate([values[1:], values[:1]])
    first = np.abs(following - values)
    second = np.abs(previous - 2 * values + following)
    return {
        'diffStd': float(np.std(first)),
        'diffMedian': float(np.median(first)),
        'secondDiffStd': float(np.std(second)),
        'secondDiffMedian': float(np.median(second)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, required=True)
    parser.add_argument('--lambda-weight', dest='lam', type=float, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--weights', default=None, help='覆盖 initialWeights，用于测任一臂的终态权重')
    args = parser.parse_args()

    chain = load(ROOT / 'model/training/oneoff/train-neighborhood90-side634-v1.py', 'probe_chain90')
    io = chain.io
    optimizer_helper = load(ROOT / 'model/training/joint-geometry-optimizer.py', 'probe_optimizer')
    smooth = load(ROOT / 'model/training/native-radial-smoothness-loss.py', 'probe_smoothness')
    smooth.configure(args.lam)
    assert Path(smooth.previous.__file__).name == 'native-side-boundary-loss.py'

    out = REPORTS / f'radius-smoothness-probe-{args.tag}-v1'
    if out.exists():
        raise SystemExit(f'refusing to overwrite {out}')

    plan_ref = io.bind(BASELINE_PLAN)
    p = io.read(plan_ref)
    if args.weights:
        p['initialWeights'] = io.bind(Path(args.weights))
    base = io.read(p['baseTraining'])
    runner = io.load(io.checked(p['baseRunner']), 'probe_runner')
    recipe, geometry, trainer, used_guard, util, model, arrays, codec, _, helper, upstream = runner.setup(base)
    holder = walk(chain, 'install')
    holder.install(model, helper, p)
    rows = walk(chain, 'load_joint_row')
    rows.load_joint_row.runner = runner
    rows.load_joint_row.GEOMETRY_RECORDS = io.read(p['geometryCache'])['records']

    model.train()
    params = [v for v in model.parameters() if v.requires_grad]
    assert len(params) == p['trainableTensors'], (len(params), p['trainableTensors'])
    frozen = util.tensor_hashes(model.previous.base)
    assert len(frozen) == p['frozenTensors'], len(frozen)
    loaded = {n: rows.load_joint_row(base, n - 1, arrays, geometry) for n in range(1, 635)}
    cpu_bytes = sum(v.nbytes for a, cache in loaded.values() for v in [*a.values(), *cache.values()])
    assert cpu_bytes <= p['maximumPreloadedCpuBytes'], cpu_bytes

    optimizer = build_two_groups(model, p)
    assert len(optimizer.param_groups) == 2
    torch.manual_seed(p['seed'])
    torch.cuda.manual_seed_all(p['seed'])
    random.seed(p['seed'])
    rng = np.random.default_rng(p['seed'])
    torch.cuda.reset_peak_memory_stats()

    def forward(n, phase, window=None):
        a, cache = loaded[n]
        values, truth, target = recipe.tensors(a)
        mask, presence, radius = helper.forward(
            model, {k: torch.from_numpy(v).cuda() for k, v in cache.items()}, *values)
        if phase != 'training':
            return 0.0, radius
        value = smooth.objective(
            mask, presence, radius, truth, target,
            torch.from_numpy(a['boundaryBand'])[None, None].cuda())
        assert torch.isfinite(value)
        (value / window).backward()
        return float(value.detach()), radius

    @torch.no_grad()
    def measure():
        stats, penalties = [], []
        for n in range(1, 635):
            _, radius = forward(n, 'measure')
            stats.append(jitter(radius.detach().cpu().numpy()[0]))
            penalties.append(float(smooth.radial_smoothness_penalty(radius.detach())))
        assert torch.cuda.max_memory_allocated() <= p['maximumCudaAllocatedBytes']
        return {
            'nails': len(stats),
            'diffStd': float(np.mean([s['diffStd'] for s in stats])),
            'diffMedian': float(np.median([s['diffMedian'] for s in stats])),
            'secondDiffStd': float(np.mean([s['secondDiffStd'] for s in stats])),
            'secondDiffMedian': float(np.median([s['secondDiffMedian'] for s in stats])),
            'meanPenalty': float(np.mean(penalties)),
        }

    started = time.monotonic()
    before = measure()
    common = dict(tag=args.tag, plan=plan_ref, lambdaWeight=args.lam, batch=args.batch,
                  cpuBytes=cpu_bytes, trainableTensors=len(params), frozenTensors=len(frozen),
                  baseLoss=io.bind(Path(smooth.previous.__file__)),
                  setupObjective=io.bind(Path(upstream.__file__)),
                  smoothnessLoss=io.bind(Path(smooth.__file__)), before=before)

    if args.epochs == 0:
        delta = abs(before['diffStd'] - REFERENCE_DIFF_STD)
        # 只有沿用基线权重时才对 cycle096 参照做判定；测其他臂的终态权重时只记录偏差。
        applicable = args.weights is None
        report = dict(ok=(delta <= REFERENCE_TOLERANCE) if applicable else True, mode='fidelity', epochs=0,
                      reference=dict(diffStd=REFERENCE_DIFF_STD, tolerance=REFERENCE_TOLERANCE,
                                     absoluteDelta=delta, applicable=applicable,
                                     source='model/training/audit-development-cycle-096-radius-jitter-reachability.py'),
                      weights=io.bind(Path(args.weights)) if args.weights else None,
                      elapsedSeconds=time.monotonic() - started, **common)
        out.mkdir(parents=True)
        (out / 'report.json').write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode('utf-8'))
        print(json.dumps(report, ensure_ascii=False, indent=1))
        if not report['ok']:
            raise SystemExit('fidelity gate failed: native radius jitter deviates from cycle096 reference')
        return

    curve = []
    try:
        for epoch in range(1, args.epochs + 1):
            optimizer_helper.start_epoch(optimizer, p, epoch)
            lr = [group['lr'] for group in optimizer.param_groups]
            order = rng.permutation(np.arange(1, 635)).tolist()
            total, penalties, steps, first_penalty = 0.0, [], 0, None
            for offset in range(0, 634, args.batch):
                window = order[offset:offset + args.batch]
                optimizer.zero_grad(set_to_none=True)
                for n in window:
                    value, radius = forward(n, 'training', len(window))
                    total += value
                    penalty = float(smooth.radial_smoothness_penalty(radius.detach()))
                    penalties.append(penalty)
                    if first_penalty is None:
                        first_penalty = penalty
                assert all(v.grad is None for v in model.previous.base.parameters())
                assert all(v.grad is not None and torch.isfinite(v.grad).all() for v in params)
                torch.nn.utils.clip_grad_norm_(params, p['gradientClip'], error_if_nonfinite=True)
                optimizer.step()
                torch.cuda.synchronize()
                steps += 1
                assert all(torch.isfinite(v).all() for v in params)
            assert frozen == util.tensor_hashes(model.previous.base)
            entry = dict(epoch=epoch, steps=steps, learningRates=lr, meanLoss=total / 634,
                         meanPenalty=float(np.mean(penalties)))
            curve.append(entry)
            print(f"epoch {epoch}/{args.epochs} steps={steps} lr={lr} "
                  f"loss={entry['meanLoss']:.6f} penalty={entry['meanPenalty']:.6f}", flush=True)
        after = measure()
        report = dict(ok=True, mode='probe', epochs=args.epochs, seed=p['seed'],
                      learningRate=p['learningRate'], curve=curve, after=after,
                      diffStdReduction=before['diffStd'] - after['diffStd'],
                      penaltyReduction=before['meanPenalty'] - after['meanPenalty'],
                      lossFinite=all(np.isfinite(e['meanLoss']) for e in curve),
                      peakCudaBytes=torch.cuda.max_memory_allocated(),
                      elapsedSeconds=time.monotonic() - started, **common)
        out.mkdir(parents=True)
        (out / 'report.json').write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode('utf-8'))
        print(json.dumps({k: v for k, v in report.items() if k != 'curve'}, ensure_ascii=False, indent=1))
    except BaseException:
        out.mkdir(parents=True, exist_ok=True)
        (out / 'exception.json').write_bytes(
            json.dumps(dict(ok=False, tag=args.tag, traceback=traceback.format_exc(), curve=curve),
                       ensure_ascii=False, indent=1).encode('utf-8'))
        raise
    finally:
        used_guard.remove_ultralytics_label_caches(BASE / 'real-only100-stage-a-v1/dataset')


if __name__ == '__main__':
    main()
