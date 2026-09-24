#!/usr/bin/env python3
"""双向高分辨率网络只替换soft Boundary IoU损失的固定32例微型门。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

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
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def train(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for name, binding in plan["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{name}")
    static = json.loads(Path(plan["inputs"]["staticReport"]["path"]).read_text(encoding="utf-8"))
    browser = json.loads(Path(plan["inputs"]["browserReport"]["path"]).read_text(encoding="utf-8"))
    if static.get("decision") != "bidirectional_highres_static_feasible_pending_browser_and_microfit" or not static.get("ok"):
        raise ValueError("静态门未过")
    if browser.get("decision") != "bidirectional_highres_browser_feasible_for_train_only_microfit" or not browser.get("ok"):
        raise ValueError("真实浏览器门未过")
    feasibility = json.loads(Path(plan["inputs"]["softBoundaryIouFeasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "soft_boundary_iou_feasible_for_train_only_microfit" or not feasibility.get("ok") or feasibility.get("optimizerSteps") != 0:
        raise ValueError("soft Boundary IoU零训练门未过")
    materialization_path = Path(plan["inputs"]["materializationReport"]["path"])
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    root = Path(materialization["outputDir"])
    if materialization["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("ROI v2文件树身份漂移")
    records = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["records"]
    by_id = {row["id"]: row for row in records if row["split"] == "train"}
    selected_ids = plan["dataset"]["selectedTrainIds"]
    if len(selected_ids) != 32 or len(set(selected_ids)) != 32 or any(identity not in by_id for identity in selected_ids):
        raise ValueError("32例train-only名单无效")
    selected = [by_id[identity] for identity in selected_ids]
    if len({row["sourceGroup"] for row in selected}) != 32:
        raise ValueError("微型样本来源组未隔离")
    guards = load_module("train-yolo-seg.py", "cycle016_bidirectional_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_bidirectional_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(root)
    atexit.register(cleanup)
    if not materializer.verify(materialization_path)["ok"]:
        raise ValueError("训练前数据集重放失败")

    config = plan["training"]
    seed = int(config["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.set_float32_matmul_precision("high")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA不可用")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_bidirectional_base")
    loss_module = load_module("development-cycle-016-soft-boundary-iou.py", "cycle016_soft_boundary_iou_loss")
    auditor = load_module("audit-development-cycle-016-bidirectional-highres-feasibility.py", "cycle016_bidirectional_auditor")
    dataset = base.RoiDataset(root, selected, training=False, seed=seed)
    batch_size = int(config["physicalBatchSize"])
    train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True,
                              generator=torch.Generator().manual_seed(seed), num_workers=0, pin_memory=True)
    eval_loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True)
    model = auditor.load_model(plan).cuda()
    model.backbone.gradient_checkpointing_enable()
    decoder_parameters = [parameter for name, parameter in model.named_parameters() if not name.startswith("backbone.")]
    optimizer = torch.optim.AdamW([
        {"params": model.backbone.parameters(), "lr": float(config["backboneLearningRate"])},
        {"params": decoder_parameters, "lr": float(config["decoderLearningRate"])},
    ], weight_decay=float(config["weightDecay"]))
    scaler = torch.amp.GradScaler("cuda")
    epochs = int(config["microfitEpochs"])
    accumulation = int(config["gradientAccumulationSteps"])
    expected_steps = int(config["microfitOptimizerSteps"])
    if len(train_loader) % accumulation or len(train_loader) // accumulation * epochs != expected_steps:
        raise ValueError("预注册优化步数与样本/批次不一致")
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs,
                                                           eta_min=float(config["backboneLearningRate"]) * 0.05)
    output.mkdir(parents=True)
    started = time.perf_counter()
    optimizer_steps = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        losses: list[float] = []
        for batch_index, (images, truth, _) in enumerate(train_loader, start=1):
            images = images.cuda(non_blocking=True)
            truth = truth.cuda(non_blocking=True)
            with torch.amp.autocast(device_type="cuda"):
                logits = model(images)
            loss, _ = loss_module.soft_boundary_iou_loss(logits, truth, plan["loss"])
            scaler.scale(loss / accumulation).backward()
            if batch_index % accumulation == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                optimizer_steps += 1
            losses.append(float(loss.detach()))
        scheduler.step()
        history.append({"epoch": epoch, "meanTrainLoss": round(float(np.mean(losses)), 8)})
        if epoch % 8 == 0:
            print(json.dumps({"epoch": epoch, "completedOptimizerSteps": optimizer_steps}), flush=True)
    if optimizer_steps != expected_steps:
        raise ValueError("微型过拟合未完成固定步数")

    # 唯一终点判决：不在训练途中查看val，也不按指标选择epoch。
    model.eval()
    ious: list[float] = []
    boundary_ious: list[float] = []
    boundary_f1s: list[float] = []
    per_instance: list[dict[str, Any]] = []
    with torch.inference_mode():
        for images, truth, identities in eval_loader:
            with torch.amp.autocast(device_type="cuda"):
                logits = model(images.cuda(non_blocking=True))
            predictions = (torch.sigmoid(logits) >= float(config["scoreThreshold"])).cpu().numpy()[:, 0]
            truths = truth.numpy()[:, 0] >= 0.5
            for prediction, target, identity in zip(predictions, truths, identities, strict=True):
                union = np.logical_or(prediction, target).sum()
                iou = float(np.logical_and(prediction, target).sum() / union) if union else 1.0
                boundary_iou, boundary_f1 = base.boundary_metrics(target, prediction, 2)
                ious.append(iou)
                boundary_ious.append(boundary_iou)
                boundary_f1s.append(boundary_f1)
                per_instance.append({"id": identity, "iou": iou, "boundaryIou": boundary_iou,
                                     "boundaryF1": boundary_f1,
                                     "jointPass": iou >= 0.75 and boundary_iou >= 0.75 and boundary_f1 >= 0.9})
    metrics = {"meanIou": float(np.mean(ious)), "meanBoundaryIou": float(np.mean(boundary_ious)),
               "meanBoundaryF1": float(np.mean(boundary_f1s)),
               "jointInstancePassRate": sum(row["jointPass"] for row in per_instance) / len(per_instance)}
    passed = (metrics["meanBoundaryF1"] >= float(config["microfitMinimumMeanBoundaryF1"]) and
              metrics["jointInstancePassRate"] >= float(config["microfitMinimumJointInstancePassRate"]))
    weights_path = output / "final.pt"
    torch.save({"model": model.state_dict(), "epoch": epochs, "trainOnlyMicrofit": True}, weights_path)
    removed_after = guards.remove_ultralytics_label_caches(root)
    integrity = materializer.verify(materialization_path)
    atexit.unregister(cleanup)
    if not integrity["ok"] or integrity["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("训练后ROI v2文件树漂移")
    report = {"schemaVersion": 1, "ok": passed,
              "decision": "soft_boundary_iou_train_only_microfit_pass" if passed else "soft_boundary_iou_train_only_microfit_fail_no_full_pilot",
              "scope": plan["scope"], "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"],
                                           "finalWeights": {"path": str(weights_path), "sha256": sha256_file(weights_path)}},
              "dataset": {"selectedTrainIds": selected_ids, "sourceGroups": 32, "valInstancesRead": 0,
                          "datasetFilesSha256After": integrity["datasetFilesSha256"],
                          "removedCachesBefore": removed_before, "removedCachesAfter": removed_after},
              "training": config, "completedEpochs": epochs, "completedOptimizerSteps": optimizer_steps,
              "metrics": metrics, "perInstance": per_instance, "history": history,
              "elapsedSeconds": round(time.perf_counter() - started, 3), "errors": []}
    write_new(output / "microfit-report.json", report)
    return report


def verify(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    for name, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入或权重漂移：{name}")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_bidirectional_verify_materializer")
    integrity = materializer.verify(Path(report["inputs"]["materializationReport"]["path"]))
    if not integrity["ok"] or integrity["datasetFilesSha256"] != report["dataset"]["datasetFilesSha256After"]:
        raise ValueError("ROI v2文件树重放失败")
    rows = report["perInstance"]
    if len(rows) != 32 or [row["id"] for row in rows] != report["dataset"]["selectedTrainIds"]:
        raise ValueError("32例名单/顺序漂移")
    metrics = report["metrics"]
    for key, field in (("meanIou", "iou"), ("meanBoundaryIou", "boundaryIou"), ("meanBoundaryF1", "boundaryF1")):
        if abs(metrics[key] - sum(row[field] for row in rows) / 32) > 1e-8:
            raise ValueError(f"指标重算不一致：{key}")
    if abs(metrics["jointInstancePassRate"] - sum(row["jointPass"] for row in rows) / 32) > 1e-8:
        raise ValueError("联合率重算不一致")
    passed = (metrics["meanBoundaryF1"] >= report["training"]["microfitMinimumMeanBoundaryF1"] and
              metrics["jointInstancePassRate"] >= report["training"]["microfitMinimumJointInstancePassRate"])
    if passed != report["ok"] or report["completedOptimizerSteps"] != report["training"]["microfitOptimizerSteps"]:
        raise ValueError("微型过拟合裁决不一致")
    return {"ok": True, "decision": "verified_soft_boundary_iou_train_only_microfit", "microfitDecision": report["decision"], "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    result = verify(args.verify_report) if args.verify_report else train(args.plan, args.output)
    print(json.dumps(result if args.verify_report else {key: result[key] for key in ("ok", "decision", "metrics", "completedEpochs", "completedOptimizerSteps", "elapsedSeconds")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
