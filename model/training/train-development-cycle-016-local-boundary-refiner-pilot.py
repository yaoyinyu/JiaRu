#!/usr/bin/env python3
"""训练cycle016第九轮冻结粗模型的局部边界残差修正器pilot。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
import math
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


def load_module(file_name: str, module_name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_model(plan: dict[str, Any], architecture: Any) -> torch.nn.Module:
    prerequisite = plan["prerequisites"]
    feasibility_plan_path = Path(prerequisite["staticFeasibilityPlan"])
    feasibility_plan = json.loads(feasibility_plan_path.read_text(encoding="utf-8"))
    return architecture.load_model(feasibility_plan)


@torch.inference_mode()
def validate(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    base: Any,
    loss_module: Any,
    loss_config: dict[str, Any],
    threshold: float,
) -> dict[str, float]:
    model.eval()
    losses: list[float] = []
    ious: list[float] = []
    boundary_ious: list[float] = []
    boundary_f1s: list[float] = []
    for images, truth, _ in loader:
        images = images.to(device, non_blocking=True)
        truth = truth.to(device, non_blocking=True)
        with torch.amp.autocast(device_type="cuda", enabled=device.type == "cuda"):
            logits = model(pixel_values=images)
        loss, _ = loss_module.soft_boundary_f1_loss(logits, truth, loss_config)
        losses.append(float(loss))
        predictions = (torch.sigmoid(logits) >= threshold).cpu().numpy()[:, 0]
        truths = truth.cpu().numpy()[:, 0] >= 0.5
        for prediction, target in zip(predictions, truths, strict=True):
            union = np.logical_or(prediction, target).sum()
            ious.append(float(np.logical_and(prediction, target).sum() / union) if union else 1.0)
            boundary_iou, boundary_f1 = base.boundary_metrics(target, prediction, 2)
            boundary_ious.append(boundary_iou)
            boundary_f1s.append(boundary_f1)
    joint = sum(
        iou >= 0.75 and boundary_iou >= 0.75 and boundary_f1 >= 0.9
        for iou, boundary_iou, boundary_f1 in zip(ious, boundary_ious, boundary_f1s, strict=True)
    )
    return {
        "loss": round(float(np.mean(losses)), 8),
        "meanIou": round(float(np.mean(ious)), 8),
        "meanBoundaryIou": round(float(np.mean(boundary_ious)), 8),
        "meanBoundaryF1": round(float(np.mean(boundary_f1s)), 8),
        "jointInstancePassRate": round(joint / len(ious), 8),
        "jointScore": round((float(np.mean(ious)) + float(np.mean(boundary_f1s))) / 2, 8),
    }


def validate_inputs(plan: dict[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    prerequisite = plan["prerequisites"]
    for label, path_key, hash_key in (
        ("第七轮训练报告", "seventhPilotReport", "seventhPilotReportSha256"),
        ("第七轮冻结权重", "seventhWeights", "seventhWeightsSha256"),
        ("32像素带可达性报告", "bandReachabilityReport", "bandReachabilityReportSha256"),
        ("静态可行性计划", "staticFeasibilityPlan", "staticFeasibilityPlanSha256"),
        ("静态可行性报告", "staticFeasibilityReport", "staticFeasibilityReportSha256"),
        ("浏览器运行报告", "browserRuntimeReport", "browserRuntimeReportSha256"),
    ):
        if sha256_file(Path(prerequisite[path_key])) != prerequisite[hash_key]:
            raise ValueError(f"{label}哈希不一致")
    browser = json.loads(Path(prerequisite["browserRuntimeReport"]).read_text(encoding="utf-8"))
    if browser.get("decision") != "local_boundary_refiner_browser_feasible_for_ninth_pilot" or not browser.get("ok"):
        raise ValueError("浏览器可行性门未通过")
    seventh = json.loads(Path(prerequisite["seventhPilotReport"]).read_text(encoding="utf-8"))
    if seventh.get("decision") != "roi_dinov2_soft_boundary_f1_internal_pilot_fail" or seventh.get("completedEpochs") != 30:
        raise ValueError("第七轮完整失败报告不一致")
    reachability = json.loads(Path(prerequisite["bandReachabilityReport"]).read_text(encoding="utf-8"))
    if reachability.get("decision") != "local_boundary_refiner_band_reachable" or not reachability.get("ok"):
        raise ValueError("32像素带可达性门未通过")
    feasibility = json.loads(Path(prerequisite["staticFeasibilityReport"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "local_boundary_refiner_static_feasible_pending_browser_runtime" or not feasibility.get("ok"):
        raise ValueError("局部边界修正器静态门未通过")
    dataset = plan["dataset"]
    report_path = Path(dataset["materializationReport"])
    review_path = Path(dataset["finalReview"])
    if sha256_file(report_path) != dataset["materializationReportSha256"] or sha256_file(review_path) != dataset["finalReviewSha256"]:
        raise ValueError("ROI v2证据哈希不一致")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["datasetFilesSha256"] != dataset["datasetFilesSha256"]:
        raise ValueError("ROI v2聚合哈希不一致")
    if json.loads(review_path.read_text(encoding="utf-8"))["decision"] != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2全量视觉审核未通过")
    return report, report_path, review_path


def train(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output}")
    output.mkdir(parents=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    report, report_path, review_path = validate_inputs(plan)
    dataset_root = Path(report["outputDir"])
    guards = load_module("train-yolo-seg.py", "cycle016_local_refiner_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_local_refiner_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_caches_before = guards.remove_ultralytics_label_caches(dataset_root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(dataset_root)
    atexit.register(cleanup)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    train_records = [row for row in manifest["records"] if row["split"] == "train"]
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    config = plan["training"]
    seed = int(config["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.set_float32_matmul_precision("high")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("该pilot预注册为本机GPU训练，CUDA不可用")

    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_dino_base")
    architecture = load_module("audit-development-cycle-016-local-boundary-refiner-feasibility.py", "cycle016_local_refiner_architecture")
    loss_module = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_soft_boundary_loss")
    loss_config = plan["loss"]
    train_dataset = base.RoiDataset(dataset_root, train_records, training=True, seed=seed)
    val_dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=seed)
    generator = torch.Generator().manual_seed(seed)
    batch_size = int(config["physicalBatchSize"])
    accumulation = int(config["gradientAccumulationSteps"])
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, generator=generator, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True)
    model = build_model(plan, architecture).to(device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    trainable_parameter_count = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    if parameter_count != int(plan["architecture"]["expectedTotalParameters"]) or trainable_parameter_count != int(plan["architecture"]["expectedTrainableRefinerParameters"]):
        raise ValueError(f"冻结/可训练参数量不符合计划：{parameter_count}/{trainable_parameter_count}")
    optimizer = torch.optim.AdamW(model.refiner.parameters(), lr=float(config["refinerLearningRate"]), weight_decay=float(config["weightDecay"]))
    epochs = int(config["epochs"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=float(config["refinerLearningRate"]) * 0.05)
    scaler = torch.amp.GradScaler("cuda")
    weights_path = output / "best.pt"
    history: list[dict[str, Any]] = []
    best_score = -math.inf
    best_epoch = 0
    stale = 0
    started = time.perf_counter()
    for epoch in range(1, epochs + 1):
        epoch_started = time.perf_counter()
        train_dataset.set_epoch(epoch)
        model.train()
        train_losses: list[float] = []
        optimizer.zero_grad(set_to_none=True)
        loader_length = len(train_loader)
        final_group_size = loader_length % accumulation or accumulation
        for batch_index, (images, truth, _) in enumerate(train_loader, start=1):
            images = images.to(device, non_blocking=True)
            truth = truth.to(device, non_blocking=True)
            current_group_size = final_group_size if batch_index > loader_length - final_group_size else accumulation
            with torch.amp.autocast(device_type="cuda"):
                logits = model(pixel_values=images)
            loss, _ = loss_module.soft_boundary_f1_loss(logits, truth, loss_config)
            scaler.scale(loss / current_group_size).backward()
            if batch_index % accumulation == 0 or batch_index == loader_length:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            train_losses.append(float(loss.detach()))
        validation = validate(model, val_loader, device, base, loss_module, loss_config, float(config["scoreThreshold"]))
        scheduler.step()
        row = {
            "epoch": epoch,
            "trainLoss": round(float(np.mean(train_losses)), 8),
            "refinerLearningRate": optimizer.param_groups[0]["lr"],
            "elapsedSeconds": round(time.perf_counter() - epoch_started, 3),
            "peakCudaMemoryBytes": int(torch.cuda.max_memory_allocated()),
            "validation": validation,
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if validation["jointScore"] > best_score + 1e-6:
            best_score = validation["jointScore"]
            best_epoch = epoch
            stale = 0
            torch.save({"model": model.state_dict(), "epoch": epoch, "validation": validation}, weights_path)
        else:
            stale += 1
        if not bool(config.get("fullRunRequired", False)) and stale >= int(config["earlyStoppingPatience"]):
            break
    best = history[best_epoch - 1]
    gate = plan["pilotGate"]
    passed = (
        best["validation"]["meanIou"] >= float(gate["minimumMeanIou"])
        and best["validation"]["meanBoundaryF1"] >= float(gate["minimumMeanBoundaryF1At2Pixels"])
        and best["validation"]["jointInstancePassRate"] >= float(gate["minimumJointInstancePassRate"])
    )
    removed_caches_after = guards.remove_ultralytics_label_caches(dataset_root)
    integrity = materializer.verify(report_path)
    atexit.unregister(cleanup)
    result = {
        "schemaVersion": 1,
        "ok": passed,
        "decision": "roi_dinov2_local_boundary_refiner_internal_pilot_pass" if passed else "roi_dinov2_local_boundary_refiner_internal_pilot_fail",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "datasetMaterializationReport": {"path": str(report_path), "sha256": sha256_file(report_path)},
            "finalReview": {"path": str(review_path), "sha256": sha256_file(review_path)},
            "seventhPilotReport": {"path": plan["prerequisites"]["seventhPilotReport"], "sha256": plan["prerequisites"]["seventhPilotReportSha256"]},
            "seventhWeights": {"path": plan["prerequisites"]["seventhWeights"], "sha256": plan["prerequisites"]["seventhWeightsSha256"]},
            "bandReachabilityReport": {"path": plan["prerequisites"]["bandReachabilityReport"], "sha256": plan["prerequisites"]["bandReachabilityReportSha256"]},
            "staticFeasibilityPlan": {"path": plan["prerequisites"]["staticFeasibilityPlan"], "sha256": plan["prerequisites"]["staticFeasibilityPlanSha256"]},
            "staticFeasibilityReport": {"path": plan["prerequisites"]["staticFeasibilityReport"], "sha256": plan["prerequisites"]["staticFeasibilityReportSha256"]},
            "browserRuntimeReport": {"path": plan["prerequisites"]["browserRuntimeReport"], "sha256": plan["prerequisites"]["browserRuntimeReportSha256"]},
            "bestWeights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "environment": {"torch": torch.__version__, "transformers": __import__("transformers").__version__, "device": torch.cuda.get_device_name(0)},
        "architecture": {"name": "frozen seventh DINOv2 coarse segmenter plus RGB-guided fixed-band dilated residual refiner", "parameterCount": parameter_count, "trainableParameterCount": trainable_parameter_count, "outputStride": 1, "singleChangedVariable": plan["singleChangedVariable"]},
        "training": config,
        "counts": {"instances": len(train_records) + len(val_records), "trainInstances": len(train_records), "valInstances": len(val_records), "trainSourceGroups": report["counts"]["trainSourceGroups"], "valSourceGroups": report["counts"]["valSourceGroups"]},
        "datasetIntegrity": {
            "removedCachesBefore": removed_caches_before,
            "removedCachesAfter": removed_caches_after,
            "datasetFilesSha256After": integrity["datasetFilesSha256"],
            "verified": integrity["ok"],
        },
        "best": best,
        "pilotGate": gate,
        "history": history,
        "completedEpochs": len(history),
        "fullRunSatisfied": len(history) == epochs,
        "elapsedSeconds": round(time.perf_counter() - started, 3),
        "errors": [],
    }
    write_atomic(output / "train-report.json", result)
    return result


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入或权重哈希不一致：{label}")
    if report["training"].get("fullRunRequired") is True and (report.get("completedEpochs") != report["training"]["epochs"] or report.get("fullRunSatisfied") is not True):
        raise ValueError("全30轮合同未满足")
    if not report.get("datasetIntegrity", {}).get("verified"):
        raise ValueError("ROI v2训练后完整性未通过")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_local_refiner_verify_materializer")
    integrity = materializer.verify(Path(report["inputs"]["datasetMaterializationReport"]["path"]))
    if integrity["datasetFilesSha256"] != report["datasetIntegrity"]["datasetFilesSha256After"]:
        raise ValueError("ROI v2文件树重放不一致")
    return {"ok": True, "decision": "verified_roi_dinov2_local_boundary_refiner_pilot", "pilotDecision": report["decision"], "best": report["best"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.output:
            parser.error("训练需要--plan与--output")
        print(json.dumps(train(args.plan, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
