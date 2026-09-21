#!/usr/bin/env python3
"""训练cycle016第六轮DINOv2有符号距离场边界监督pilot。"""

from __future__ import annotations

import argparse
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
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel


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
    weight_path = Path(prerequisite["pretrainedWeight"])
    if sha256_file(weight_path) != prerequisite["pretrainedWeightSha256"]:
        raise ValueError("DINOv2预训练权重哈希不一致")
    backbone = AutoModel.from_pretrained(
        prerequisite["huggingFaceModelId"],
        revision=prerequisite["huggingFaceRevision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    if plan["training"]["gradientCheckpointing"]:
        backbone.gradient_checkpointing_enable()
    return architecture.Dinov2HighResBoundarySegmenter(backbone)


class SignedDistanceDataset(Dataset[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, str]]):
    """复用第五轮完全相同的图像/掩码增强，并由增强后的mask确定性生成距离场。"""

    def __init__(self, inner: Any, distance_config: dict[str, Any], loss_module: Any) -> None:
        self.inner = inner
        self.distance_config = distance_config
        self.loss_module = loss_module

    def set_epoch(self, epoch: int) -> None:
        self.inner.set_epoch(epoch)

    def __len__(self) -> int:
        return len(self.inner)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, str]:
        image, truth, identity = self.inner[index]
        mask = truth.numpy()[0] >= 0.5
        pixels, target = self.loss_module.distance_targets(mask, self.distance_config)
        return image, truth, torch.from_numpy(pixels)[None], torch.from_numpy(target)[None], identity


@torch.inference_mode()
def validate(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    base: Any,
    loss_module: Any,
    distance_config: dict[str, Any],
    threshold: float,
) -> dict[str, float]:
    model.eval()
    losses: list[float] = []
    ious: list[float] = []
    boundary_ious: list[float] = []
    boundary_f1s: list[float] = []
    for images, truth, distance_pixels, distance_target, _ in loader:
        images = images.to(device, non_blocking=True)
        truth = truth.to(device, non_blocking=True)
        distance_pixels = distance_pixels.to(device, non_blocking=True)
        distance_target = distance_target.to(device, non_blocking=True)
        with torch.amp.autocast(device_type="cuda", enabled=device.type == "cuda"):
            logits = model(pixel_values=images)
            loss, _ = loss_module.signed_distance_loss(logits, truth, distance_pixels, distance_target, distance_config)
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
        ("第五轮训练报告", "fifthPilotReport", "fifthPilotReportSha256"),
        ("第五轮最佳权重", "fifthBestWeights", "fifthBestWeightsSha256"),
        ("静态可行性报告", "staticFeasibilityReport", "staticFeasibilityReportSha256"),
        ("距离场可行性计划", "signedDistanceFeasibilityPlan", "signedDistanceFeasibilityPlanSha256"),
        ("距离场可行性报告", "signedDistanceFeasibilityReport", "signedDistanceFeasibilityReportSha256"),
        ("DINOv2权重", "pretrainedWeight", "pretrainedWeightSha256"),
    ):
        if sha256_file(Path(prerequisite[path_key])) != prerequisite[hash_key]:
            raise ValueError(f"{label}哈希不一致")
    fifth = json.loads(Path(prerequisite["fifthPilotReport"]).read_text(encoding="utf-8"))
    if fifth.get("decision") != "roi_dinov2_highres_decoder_internal_pilot_fail" or fifth.get("completedEpochs") != 30 or fifth.get("best", {}).get("epoch") != 27:
        raise ValueError("第五轮完整30轮冻结对照不一致")
    feasibility = json.loads(Path(prerequisite["signedDistanceFeasibilityReport"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "signed_distance_boundary_supervision_reachable_for_sixth_pilot" or feasibility.get("initialization", {}).get("fifthBestWeightsLoaded") is not False:
        raise ValueError("距离场边界监督可达性门未通过或错误加载第五轮权重")
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
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_dino_highres_architecture")
    loss_module = load_module("audit-development-cycle-016-signed-distance-boundary-feasibility.py", "cycle016_signed_distance_loss")
    distance_config = plan["signedDistanceSupervision"]
    train_dataset = SignedDistanceDataset(base.RoiDataset(dataset_root, train_records, training=True, seed=seed), distance_config, loss_module)
    val_dataset = SignedDistanceDataset(base.RoiDataset(dataset_root, val_records, training=False, seed=seed), distance_config, loss_module)
    generator = torch.Generator().manual_seed(seed)
    batch_size = int(config["physicalBatchSize"])
    accumulation = int(config["gradientAccumulationSteps"])
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, generator=generator, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True)
    model = build_model(plan, architecture).to(device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    decoder_parameters = [parameter for name, parameter in model.named_parameters() if not name.startswith("backbone.")]
    optimizer = torch.optim.AdamW(
        [
            {"params": model.backbone.parameters(), "lr": float(config["backboneLearningRate"])},
            {"params": decoder_parameters, "lr": float(config["decoderLearningRate"])},
        ],
        weight_decay=float(config["weightDecay"]),
    )
    epochs = int(config["epochs"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=float(config["backboneLearningRate"]) * 0.05)
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
        train_components: dict[str, list[float]] = {"bce": [], "dice": [], "signedDistance": []}
        for batch_index, (images, truth, distance_pixels, distance_target, _) in enumerate(train_loader, start=1):
            images = images.to(device, non_blocking=True)
            truth = truth.to(device, non_blocking=True)
            distance_pixels = distance_pixels.to(device, non_blocking=True)
            distance_target = distance_target.to(device, non_blocking=True)
            current_group_size = final_group_size if batch_index > loader_length - final_group_size else accumulation
            with torch.amp.autocast(device_type="cuda"):
                logits = model(pixel_values=images)
                loss, components = loss_module.signed_distance_loss(logits, truth, distance_pixels, distance_target, distance_config)
            scaler.scale(loss / current_group_size).backward()
            if batch_index % accumulation == 0 or batch_index == loader_length:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            train_losses.append(float(loss.detach()))
            for name, value in components.items():
                train_components[name].append(float(value.detach()))
        validation = validate(model, val_loader, device, base, loss_module, distance_config, float(config["scoreThreshold"]))
        scheduler.step()
        row = {
            "epoch": epoch,
            "trainLoss": round(float(np.mean(train_losses)), 8),
            "trainLossComponents": {name: round(float(np.mean(values)), 8) for name, values in train_components.items()},
            "backboneLearningRate": optimizer.param_groups[0]["lr"],
            "decoderLearningRate": optimizer.param_groups[1]["lr"],
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
    result = {
        "schemaVersion": 1,
        "ok": passed,
        "decision": "roi_dinov2_signed_distance_boundary_internal_pilot_pass" if passed else "roi_dinov2_signed_distance_boundary_internal_pilot_fail",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "datasetMaterializationReport": {"path": str(report_path), "sha256": sha256_file(report_path)},
            "finalReview": {"path": str(review_path), "sha256": sha256_file(review_path)},
            "fifthPilotReport": {"path": plan["prerequisites"]["fifthPilotReport"], "sha256": plan["prerequisites"]["fifthPilotReportSha256"]},
            "fifthBestWeightsComparator": {"path": plan["prerequisites"]["fifthBestWeights"], "sha256": plan["prerequisites"]["fifthBestWeightsSha256"]},
            "staticFeasibilityReport": {"path": plan["prerequisites"]["staticFeasibilityReport"], "sha256": plan["prerequisites"]["staticFeasibilityReportSha256"]},
            "signedDistanceFeasibilityPlan": {"path": plan["prerequisites"]["signedDistanceFeasibilityPlan"], "sha256": plan["prerequisites"]["signedDistanceFeasibilityPlanSha256"]},
            "signedDistanceFeasibilityReport": {"path": plan["prerequisites"]["signedDistanceFeasibilityReport"], "sha256": plan["prerequisites"]["signedDistanceFeasibilityReportSha256"]},
            "pretrainedWeight": {"path": plan["prerequisites"]["pretrainedWeight"], "sha256": plan["prerequisites"]["pretrainedWeightSha256"]},
            "bestWeights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "environment": {"torch": torch.__version__, "transformers": __import__("transformers").__version__, "device": torch.cuda.get_device_name(0)},
        "architecture": {"name": "DINOv2-small plus 384/192/96 spatial-skip high-resolution boundary decoder", "parameterCount": parameter_count, "outputStride": 1, "singleChangedVariable": plan["singleChangedVariable"]},
        "initialization": {"seed": seed, "pretrainedWeightSha256": plan["prerequisites"]["pretrainedWeightSha256"], "fifthBestWeightsBoundAsComparator": True, "fifthBestWeightsLoaded": False},
        "signedDistanceSupervision": plan["signedDistanceSupervision"],
        "training": config,
        "counts": {"instances": len(train_records) + len(val_records), "trainInstances": len(train_records), "valInstances": len(val_records), "trainSourceGroups": report["counts"]["trainSourceGroups"], "valSourceGroups": report["counts"]["valSourceGroups"]},
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
    if report.get("initialization", {}).get("fifthBestWeightsLoaded") is not False:
        raise ValueError("第六轮错误加载第五轮最佳权重")
    return {"ok": True, "decision": "verified_roi_dinov2_signed_distance_boundary_pilot", "pilotDecision": report["decision"], "best": report["best"]}


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
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        dataset_report_path = Path(plan["dataset"]["materializationReport"])
        dataset_report = json.loads(dataset_report_path.read_text(encoding="utf-8"))
        dataset_root = Path(dataset_report["outputDir"])
        guards = load_module("train-yolo-seg.py", "cycle016_sdf_training_guard")
        materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_sdf_training_materializer")
        guards.install_read_only_ultralytics_image_check()
        guards.remove_ultralytics_label_caches(dataset_root)
        try:
            result = train(args.plan, args.output)
        finally:
            guards.remove_ultralytics_label_caches(dataset_root)
        integrity = materializer.verify(dataset_report_path)
        if integrity["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
            raise ValueError("第六轮训练后ROI v2数据集完整性重放失败")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
