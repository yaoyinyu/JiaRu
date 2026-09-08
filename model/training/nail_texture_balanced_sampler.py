"""来源组均衡回放采样器（循环011唯一变量：sourceGroupBalancedReplaySampling）。

只改变train每个epoch的来源组抽样分布：每个来源组每epoch贡献几乎相等的样本数
（largest-remainder配额，总和恰等于train图片数），组内按epoch轮转保证全部图片
跨epoch覆盖，组间按确定性种子轮转交错，防止单一批次被同一来源组占满。
评估折DataLoader（shuffle=False）与分布式路径完全不走本采样器；数据文件树、
样本身份、角色隔离、损失与其余训练/评估参数一律不变。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SAMPLER_SEED = 20260908
SAMPLER_MODE = "equal-quota-largest-remainder-round-robin-interleave"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_group_map(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schemaVersion") != SCHEMA_VERSION
        or not isinstance(value.get("images"), list)
        or not value["images"]
    ):
        raise ValueError(f"source group map is invalid: {path}")
    return value


def build_group_map_from_materialization(report_path: Path, output_path: Path) -> dict[str, Any]:
    """从开发数据集物化报告提取train分图的 stem->sourceGroup 身份映射。"""

    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = report.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError(f"materialization report has no records: {report_path}")
    rows = []
    seen_stems: set[str] = set()
    for record in sorted(
        (row for row in records if isinstance(row, dict) and row.get("developmentSplit") == "train"),
        key=lambda row: str(row["fileName"]),
    ):
        file_name = str(record["fileName"])
        stem = Path(file_name).stem
        group = record.get("sourceGroup")
        if not stem or not isinstance(group, str) or not group:
            raise ValueError(f"train record is missing identity fields: {file_name}")
        if stem in seen_stems:
            raise ValueError(f"duplicate train image stem: {stem}")
        seen_stems.add(stem)
        rows.append(
            {
                "fileName": file_name,
                "stem": stem,
                "sourceGroup": group,
                "role": record.get("role"),
            }
        )
    if not rows:
        raise ValueError("materialization report has no train-split records")
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "mode": SAMPLER_MODE,
        "seed": SAMPLER_SEED,
        "source": {
            "materializationReportPath": str(report_path.resolve()),
            "materializationReportSha256": sha256_file(report_path),
        },
        "counts": {"trainImages": len(rows), "sourceGroups": len({row["sourceGroup"] for row in rows})},
        "images": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def compute_group_quotas(group_sizes: dict[str, int], total: int) -> dict[str, int]:
    """每来源组几乎相等的epoch配额；总和恰为total，每组至少1。"""

    groups = sorted(group_sizes)
    if not groups:
        raise ValueError("no source groups to balance")
    if total < len(groups):
        raise ValueError(f"total={total} is smaller than the number of groups={len(groups)}")
    for name, size in group_sizes.items():
        if size <= 0:
            raise ValueError(f"source group has no images: {name}")
    base, remainder = divmod(total, len(groups))
    quotas = {name: base for name in groups}
    for name in groups[:remainder]:
        quotas[name] += 1
    if sum(quotas.values()) != total or min(quotas.values()) < 1:
        raise ValueError("group quota allocation is inconsistent")
    return quotas


def build_balanced_epoch_order(
    group_to_indices: dict[str, list[int]],
    quotas: dict[str, int],
    epoch: int,
    seed: int,
) -> list[int]:
    """构造第epoch个epoch的均衡索引顺序（确定性、可重放、组间交错）。"""

    rng = random.Random(seed * 1000003 + epoch)
    group_order = sorted(group_to_indices)
    rng.shuffle(group_order)
    pending: dict[str, list[int]] = {}
    for name in group_order:
        items = sorted(group_to_indices[name])
        quota = quotas[name]
        start = (epoch * quota) % len(items)
        pending[name] = [items[(start + offset) % len(items)] for offset in range(quota)]
    order: list[int] = []
    while pending:
        for name in list(pending):
            order.append(pending[name].pop(0))
            if not pending[name]:
                del pending[name]
        rng.shuffle(group_order)
    if len(order) != sum(quotas.values()):
        raise ValueError("balanced epoch order length mismatch")
    return order


def make_balanced_batch_sampler_class(torch_module: Any):
    """构造批次级均衡采样器类；隔离torch依赖以便无torch环境下测试纯逻辑。

    每次迭代恰好产出一个均衡块（len(dataset)个索引）按batch_size切分的批次序列，
    因此trainer每个epoch（len(loader)个batch）精确消费一个来源组均衡块，
    组配额逐epoch严格成立，不会出现跨块漂移。
    """

    class SourceGroupBalancedBatchSampler(torch_module.utils.data.Sampler):
        def __init__(self, group_to_indices: dict[str, list[int]], batch_size: int, drop_last: bool, seed: int):
            sizes = {name: len(items) for name, items in group_to_indices.items()}
            self.total = sum(sizes.values())
            self.quotas = compute_group_quotas(sizes, self.total)
            self.group_to_indices = group_to_indices
            self.batch_size = int(batch_size)
            self.drop_last = bool(drop_last)
            self.seed = seed
            self.epochs_yielded = 0
            if self.batch_size <= 0:
                raise ValueError("batch size must be positive")

        def __len__(self) -> int:
            if self.drop_last:
                return self.total // self.batch_size
            return -(-self.total // self.batch_size)

        def __iter__(self):
            epoch = 0
            while True:
                order = build_balanced_epoch_order(
                    self.group_to_indices, self.quotas, epoch, self.seed
                )
                for start in range(0, len(order), self.batch_size):
                    chunk = order[start : start + self.batch_size]
                    if self.drop_last and len(chunk) < self.batch_size:
                        break
                    yield [int(index) for index in chunk]
                epoch += 1
                self.epochs_yielded = epoch

    return SourceGroupBalancedBatchSampler


def install_source_group_balanced_dataloader(group_map_path: Path) -> dict[str, Any]:
    """补丁ultralytics的build_dataloader：仅train（shuffle=True、单进程）路径生效。"""

    group_map = load_group_map(group_map_path)
    stem_to_group = {row["stem"]: row["sourceGroup"] for row in group_map["images"]}

    import torch
    import ultralytics.data.build as build_module
    import ultralytics.data as data_package

    original = build_module.build_dataloader
    balanced_class = make_balanced_batch_sampler_class(torch)

    def patched_build_dataloader(dataset, batch, workers, shuffle=True, rank=-1, drop_last=False, pin_memory=True):
        if not shuffle or rank != -1:
            # 评估折、导出与非分布式以外路径保持原实现，逐字节不变。
            return original(dataset, batch, workers, shuffle=shuffle, rank=rank, drop_last=drop_last, pin_memory=pin_memory)
        if getattr(dataset, "rect", False):
            # rect模式会在调用方退化为shuffle=False；此处兜底拒绝以防静默不均衡。
            raise ValueError("source-group balanced sampler does not support rect datasets")
        loader = original(
            dataset,
            batch,
            workers,
            shuffle=False,
            rank=rank,
            drop_last=drop_last,
            pin_memory=pin_memory,
        )
        stems = [Path(str(file)).stem for file in dataset.im_files]
        missing = sorted({stem for stem in stems if stem not in stem_to_group})
        if missing:
            raise ValueError(f"train images missing from the source group map: {missing[:5]}")
        group_to_indices: dict[str, list[int]] = {}
        for index, stem in enumerate(stems):
            group_to_indices.setdefault(stem_to_group[stem], []).append(index)
        repeat_sampler = loader.batch_sampler
        repeat_sampler.sampler = balanced_class(
            group_to_indices, batch_size=int(batch), drop_last=bool(drop_last), seed=SAMPLER_SEED
        )
        loader.reset()
        return loader

    patched_modules = []
    build_module.build_dataloader = patched_build_dataloader
    patched_modules.append("ultralytics.data.build")
    if getattr(data_package, "build_dataloader", None) is original:
        data_package.build_dataloader = patched_build_dataloader
        patched_modules.append("ultralytics.data")
    for module_name, module in list(sys.modules.items()):
        if (
            module_name.startswith("ultralytics")
            and module is not None
            and getattr(module, "build_dataloader", None) is original
        ):
            module.build_dataloader = patched_build_dataloader
            patched_modules.append(module_name)

    sizes = Counter(row["sourceGroup"] for row in group_map["images"])
    quotas = compute_group_quotas(dict(sizes), sum(sizes.values()))
    return {
        "enabled": True,
        "mode": SAMPLER_MODE,
        "seed": SAMPLER_SEED,
        "groupMap": str(group_map_path.resolve()),
        "groupMapSha256": sha256_file(group_map_path),
        "trainImages": sum(sizes.values()),
        "sourceGroups": len(sizes),
        "quotaMin": min(quotas.values()),
        "quotaMax": max(quotas.values()),
        "epochSamples": sum(quotas.values()),
        "validationLoaderChanged": False,
        "patchedModules": sorted(set(patched_modules)),
    }


def self_check(group_map_path: Path, epochs: int) -> dict[str, Any]:
    """无torch的纯逻辑不变量自检，供专项测试与预注册前校验使用。"""

    group_map = load_group_map(group_map_path)
    stems = [row["stem"] for row in group_map["images"]]
    if len(stems) != len(set(stems)):
        raise ValueError("group map contains duplicate stems")
    stem_to_index = {stem: index for index, stem in enumerate(stems)}
    group_to_indices: dict[str, list[int]] = {}
    for row in group_map["images"]:
        group_to_indices.setdefault(row["sourceGroup"], []).append(stem_to_index[row["stem"]])
    sizes = {name: len(items) for name, items in group_to_indices.items()}
    quotas = compute_group_quotas(sizes, len(stems))
    coverage = Counter()
    epoch_orders = []
    for epoch in range(epochs):
        order = build_balanced_epoch_order(group_to_indices, quotas, epoch, SAMPLER_SEED)
        epoch_orders.append(order)
        if len(order) != len(stems):
            raise ValueError("epoch order length mismatch")
        counts = Counter()
        for index in order:
            counts[stems[index]] += 1
            coverage[index] += 1
        for name, quota in quotas.items():
            if sum(counts[stems[index]] for index in group_to_indices[name]) != quota:
                raise ValueError(f"group quota violated in epoch {epoch}: {name}")
    missing_images = [stems[index] for index in range(len(stems)) if coverage[index] == 0]
    if missing_images:
        raise ValueError(f"images never sampled across {epochs} epochs: {missing_images[:5]}")
    determinism = build_balanced_epoch_order(group_to_indices, quotas, 0, SAMPLER_SEED) == epoch_orders[0]
    epoch_variation = any(
        build_balanced_epoch_order(group_to_indices, quotas, epoch, SAMPLER_SEED)
        != build_balanced_epoch_order(group_to_indices, quotas, epoch + 1, SAMPLER_SEED)
        for epoch in range(epochs - 1)
    )
    return {
        "ok": True,
        "trainImages": len(stems),
        "sourceGroups": len(sizes),
        "quotaMin": min(quotas.values()),
        "quotaMax": max(quotas.values()),
        "epochsChecked": epochs,
        "coverageComplete": not missing_images,
        "deterministic": determinism,
        "epochOrderVaries": epoch_variation,
    }


def loader_self_check(group_map_path: Path) -> dict[str, Any]:
    """用桩数据集验证补丁后的真实DataLoader行为：train均衡、val逐字节顺序不变。"""

    group_map = load_group_map(group_map_path)
    stems = [row["stem"] for row in group_map["images"]]
    stem_to_group = {row["stem"]: row["sourceGroup"] for row in group_map["images"]}

    import torch
    from torch.utils.data import Dataset

    import ultralytics.data.build as build_module

    class StubDataset(Dataset):
        def __init__(self) -> None:
            self.im_files = [f"stub://{stem}.jpg" for stem in stems]
            self.rect = False

        def __len__(self) -> int:
            return len(stems)

        def __getitem__(self, index):
            return int(index)

    dataset = StubDataset()
    evidence = install_source_group_balanced_dataloader(group_map_path)
    batch = 4
    expected_batches = -(-len(stems) // batch)

    train_loader = build_module.build_dataloader(dataset, batch=batch, workers=0, shuffle=True, rank=-1)
    train_indices: list[int] = []
    for _ in range(expected_batches):
        for value in next(iter(train_loader)).tolist():
            train_indices.append(int(value))
    if len(train_indices) != len(stems):
        raise ValueError("balanced train loader did not yield exactly one epoch of samples")
    train_counts = Counter(stem_to_group[stems[index]] for index in train_indices)
    sizes = dict(Counter(stem_to_group[stem] for stem in stems))
    quotas = compute_group_quotas(sizes, len(stems))
    if {name: train_counts[name] for name in quotas} != quotas:
        raise ValueError("balanced train loader group counts differ from precomputed quotas")
    second_epoch: list[int] = []
    for _ in range(expected_batches):
        for value in next(iter(train_loader)).tolist():
            second_epoch.append(int(value))
    val_loader = build_module.build_dataloader(dataset, batch=batch, workers=0, shuffle=False, rank=-1)
    val_indices: list[int] = []
    for _ in range(expected_batches):
        for value in next(iter(val_loader)).tolist():
            val_indices.append(int(value))
    if val_indices != list(range(len(stems))):
        raise ValueError("validation loader order changed; eval-fold invariance is broken")
    return {
        "ok": True,
        "trainSamplesPerEpoch": len(train_indices),
        "expectedBatchesPerEpoch": expected_batches,
        "trainLoaderLength": len(train_loader),
        "trainGroupCountsMatchQuotas": True,
        "secondEpochDiffers": second_epoch != train_indices,
        "validationOrderSequential": True,
        "samplerEvidence": {key: evidence[key] for key in ("mode", "seed", "sourceGroups", "epochSamples")},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Source-group balanced replay sampler utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    group_map_parser = subparsers.add_parser("build-group-map", help="Extract the train-split stem->sourceGroup map")
    group_map_parser.add_argument("--materialization-report", required=True)
    group_map_parser.add_argument("--output", required=True)
    check_parser = subparsers.add_parser("self-check", help="Verify sampler invariants without torch")
    check_parser.add_argument("--group-map", required=True)
    check_parser.add_argument("--epochs", type=int, default=8)
    loader_parser = subparsers.add_parser("loader-self-check", help="Verify patched DataLoader behaviour with a stub dataset")
    loader_parser.add_argument("--group-map", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "build-group-map":
        payload = build_group_map_from_materialization(
            Path(args.materialization_report).resolve(), Path(args.output).resolve()
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(Path(args.output).resolve()),
                    "sha256": sha256_file(Path(args.output).resolve()),
                    "counts": payload["counts"],
                },
                ensure_ascii=False,
            )
        )
        return
    if args.command == "self-check":
        print(json.dumps(self_check(Path(args.group_map).resolve(), args.epochs), ensure_ascii=False))
        return
    if args.command == "loader-self-check":
        print(json.dumps(loader_self_check(Path(args.group_map).resolve()), ensure_ascii=False))
        return
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
