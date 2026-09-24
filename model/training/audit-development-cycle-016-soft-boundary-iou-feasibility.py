#!/usr/bin/env python3
"""严格Boundary IoU可微目标的train-only、零优化可达性审计。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(file_name: str, name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    result = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        result[order[start:end]] = (start + end - 1) / 2
        start = end
    return result


def spearman(left: list[float], right: list[float]) -> float:
    ranked_left = average_ranks(np.asarray(left, dtype=np.float64))
    ranked_right = average_ranks(np.asarray(right, dtype=np.float64))
    if np.std(ranked_left) == 0 or np.std(ranked_right) == 0:
        raise ValueError("相关性输入没有可判别变化")
    return float(np.corrcoef(ranked_left, ranked_right)[0, 1])


def hard_inner_band(mask: np.ndarray) -> np.ndarray:
    value = mask.astype(np.uint8)
    edge = value - cv2.erode(value, np.ones((3, 3), dtype=np.uint8), iterations=1)
    near = cv2.dilate(edge, np.ones((5, 5), dtype=np.uint8), iterations=1)
    return np.logical_and(value != 0, near != 0)


def compute(plan_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for label, binding in plan["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"预注册输入哈希漂移：{label}")
    previous = json.loads(Path(plan["inputs"]["previousMicrofitReport"]["path"]).read_text(encoding="utf-8"))
    if previous["decision"] != "bidirectional_highres_train_only_microfit_fail_no_full_pilot" or previous["completedOptimizerSteps"] != 256:
        raise ValueError("前序微型失败报告身份不符")
    if previous["inputs"]["finalWeights"]["sha256"] != plan["inputs"]["previousWeights"]["sha256"]:
        raise ValueError("前序失败权重绑定不符")
    if previous["dataset"]["selectedTrainIds"] != plan["dataset"]["selectedTrainIds"]:
        raise ValueError("微型名单不得修改")
    materialization_path = Path(plan["inputs"]["materializationReport"]["path"])
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    if materialization["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("ROI v2文件树身份漂移")
    root = Path(materialization["outputDir"])
    guards = load_module("train-yolo-seg.py", "cycle016_soft_iou_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_soft_iou_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(root)
    atexit.register(cleanup)
    if not materializer.verify(materialization_path)["ok"]:
        raise ValueError("训练数据文件树重放失败")
    all_records = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["records"]
    by_id = {row["id"]: row for row in all_records if row["split"] == "train"}
    identities = plan["dataset"]["selectedTrainIds"]
    if len(identities) != 32 or any(identity not in by_id for identity in identities):
        raise ValueError("32例train-only名单无效")
    records = [by_id[identity] for identity in identities]
    if len({row["sourceGroup"] for row in records}) != 32:
        raise ValueError("32例来源组不互异")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_soft_iou_base")
    previous_loss = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_soft_iou_old_loss")
    new_loss = load_module("development-cycle-016-soft-boundary-iou.py", "cycle016_soft_iou_new_loss")
    architecture = load_module("audit-development-cycle-016-bidirectional-highres-feasibility.py", "cycle016_soft_iou_architecture")
    dataset = base.RoiDataset(root, records, training=False, seed=int(plan["training"]["seed"]))
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0, pin_memory=True)
    model = architecture.load_model(plan).cuda().eval()
    checkpoint = torch.load(plan["inputs"]["previousWeights"]["path"], map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"], strict=True)
    strict_scores: list[float] = []
    new_scores: list[float] = []
    old_scores: list[float] = []
    per_instance: list[dict[str, Any]] = []
    exact_band_mismatches = 0
    oracle_max_loss = 0.0
    frozen_rows = {row["id"]: row for row in previous["perInstance"]}
    with torch.inference_mode():
        for images, truth, batch_ids in loader:
            for truth_one in truth:
                hard = truth_one[0].numpy() >= 0.5
                torch_band = new_loss.inner_boundary_band(truth_one[None], near_kernel=5)[0, 0].numpy() >= 0.5
                exact_band_mismatches += int(np.count_nonzero(torch_band != hard_inner_band(hard)))
            oracle_logits = torch.where(truth >= 0.5, 16.0, -16.0)
            oracle_scores = new_loss.soft_boundary_iou_per_instance(torch.sigmoid(oracle_logits), truth, plan["loss"])
            oracle_max_loss = max(oracle_max_loss, float((1.0 - oracle_scores).max()))
            with torch.amp.autocast(device_type="cuda"):
                logits = model(images.cuda(non_blocking=True))
            probability = torch.sigmoid(logits.float())
            soft_iou = new_loss.soft_boundary_iou_per_instance(probability, truth.cuda(), plan["loss"]).cpu().numpy()
            soft_f1 = previous_loss.soft_boundary_f1_per_instance(probability, truth.cuda(), plan["loss"]).cpu().numpy()
            hard_predictions = (probability >= 0.5).cpu().numpy()[:, 0]
            truths = truth.numpy()[:, 0] >= 0.5
            for identity, target, prediction, score_iou, score_f1 in zip(batch_ids, truths, hard_predictions, soft_iou, soft_f1, strict=True):
                strict_iou, _ = base.boundary_metrics(target, prediction, 2)
                frozen = frozen_rows[identity]
                if abs(strict_iou - frozen["boundaryIou"]) > 1e-6:
                    raise ValueError(f"reconstruction_mismatch: {identity}严格Boundary IoU不等于冻结微型报告")
                strict_scores.append(strict_iou)
                new_scores.append(float(score_iou))
                old_scores.append(float(score_f1))
                per_instance.append({"id": identity, "strictBoundaryIou": strict_iou,
                                     "softBoundaryIou": float(score_iou), "softBoundaryF1": float(score_f1)})
    if [row["id"] for row in per_instance] != identities:
        raise ValueError("reconstruction_mismatch: 32例顺序改变")
    new_correlation = spearman(strict_scores, new_scores)
    old_correlation = spearman(strict_scores, old_scores)
    del model
    torch.cuda.empty_cache()

    # 全模型梯度使用相同结构的新随机头和真实train ROI；无优化器步、无val读取。
    gradient_model = architecture.load_model(plan).cuda().train()
    gradient_model.backbone.gradient_checkpointing_enable()
    first_images, first_truth, _ = next(iter(loader))
    torch.cuda.reset_peak_memory_stats()
    with torch.amp.autocast(device_type="cuda"):
        gradient_logits = gradient_model(first_images.cuda())
    total, components = new_loss.soft_boundary_iou_loss(gradient_logits, first_truth.cuda(), plan["loss"])
    total.backward()
    expected_unused = {"backbone.embeddings.mask_token"}
    gradients = {name: parameter.grad for name, parameter in gradient_model.named_parameters() if parameter.requires_grad}
    missing = [name for name, gradient in gradients.items() if name not in expected_unused and
               (gradient is None or not torch.isfinite(gradient).all())]
    if any(gradients.get(name) is not None for name in expected_unused):
        raise ValueError("mask_token参与非遮蔽前向梯度")
    groups = {"backbone": "backbone.", "spatial": "spatial", "fusion": "top", "down": "down", "boundary": "boundary_tower", "output": "output"}
    nonzero_groups = {label: any(name.startswith(prefix) and grad is not None and torch.count_nonzero(grad).item() > 0
                                 for name, grad in gradients.items()) for label, prefix in groups.items()}
    peak = int(torch.cuda.max_memory_allocated())
    removed_after = guards.remove_ultralytics_label_caches(root)
    integrity = materializer.verify(materialization_path)
    atexit.unregister(cleanup)
    if not integrity["ok"] or integrity["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("训练数据文件树训练后重放失败")
    gates = plan["gates"]
    passed = (exact_band_mismatches == 0 and oracle_max_loss <= float(gates["maximumOracleLoss"]) and
              new_correlation >= float(gates["minimumStrictMetricSpearman"]) and
              new_correlation + float(gates["maximumCorrelationRegression"]) >= old_correlation and
              not missing and all(nonzero_groups.values()) and peak <= int(gates["maximumCudaPeakAllocatedBytesBatch2"]))
    return {"schemaVersion": 1, "ok": passed,
            "decision": "soft_boundary_iou_feasible_for_train_only_microfit" if passed else "soft_boundary_iou_signal_gate_fail_no_training",
            "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
            "scope": plan["scope"], "dataset": {"selectedTrainIds": identities, "sourceGroups": 32, "valInstancesRead": 0,
                                         "datasetFilesSha256After": integrity["datasetFilesSha256"],
                                         "removedCachesBefore": removed_before, "removedCachesAfter": removed_after},
            "loss": plan["loss"], "gates": gates,
            "signal": {"exactTargetBandMismatchedPixels": exact_band_mismatches, "oracleMaximumLoss": oracle_max_loss,
                       "strictMetricSpearmanNew": new_correlation, "strictMetricSpearmanOld": old_correlation,
                       "perInstance": per_instance},
            "gradient": {"usedFiniteParameterTensors": len(gradients) - len(expected_unused),
                         "missingOrNonfinite": missing, "nonzeroGroups": nonzero_groups,
                         "totalLoss": float(total.detach()), "components": components},
            "cuda": {"peakAllocatedBytesBatch2": peak}, "optimizerSteps": 0, "errors": []}


def verify(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    replay = compute(Path(report["inputs"]["plan"]["path"]))
    for label in ("ok", "decision", "dataset", "loss", "gates"):
        if replay[label] != report[label]:
            raise ValueError(f"审计重放不一致：{label}")
    for label in ("exactTargetBandMismatchedPixels", "oracleMaximumLoss", "strictMetricSpearmanNew", "strictMetricSpearmanOld"):
        if abs(replay["signal"][label] - report["signal"][label]) > 1e-5:
            raise ValueError(f"信号重放不一致：{label}")
    if replay["gradient"]["missingOrNonfinite"] != report["gradient"]["missingOrNonfinite"] or replay["gradient"]["nonzeroGroups"] != report["gradient"]["nonzeroGroups"]:
        raise ValueError("梯度重放不一致")
    return {"ok": True, "decision": "verified_soft_boundary_iou_feasibility",
            "feasibilityDecision": report["decision"], "signal": {key: report["signal"][key] for key in ("exactTargetBandMismatchedPixels", "oracleMaximumLoss", "strictMetricSpearmanNew", "strictMetricSpearmanOld")}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        result = compute(args.plan)
        write_new(args.output, result)
    print(json.dumps(result if args.verify_report else {key: result[key] for key in ("ok", "decision", "signal", "gradient", "cuda", "optimizerSteps")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
