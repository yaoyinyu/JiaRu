#!/usr/bin/env python3
"""训练cycle016第三轮紧凑U-Net单变量pilot。"""

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
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_base() -> Any:
    path = Path(__file__).resolve().with_name("train-development-cycle-016-roi-segformer-pilot.py")
    spec = importlib.util.spec_from_file_location("cycle016_unet_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载cycle016基础训练模块")
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


class ConvBlock(nn.Module):
    def __init__(self, input_channels: int, output_channels: int) -> None:
        super().__init__()
        groups = min(8, output_channels)
        self.block = nn.Sequential(
            nn.Conv2d(input_channels, output_channels, 3, padding=1, bias=False),
            nn.GroupNorm(groups, output_channels),
            nn.GELU(),
            nn.Conv2d(output_channels, output_channels, 3, padding=1, bias=False),
            nn.GroupNorm(groups, output_channels),
            nn.GELU(),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.block(value)


class CompactUNet(nn.Module):
    def __init__(self, channels: tuple[int, int, int, int] = (24, 48, 96, 192)) -> None:
        super().__init__()
        c1, c2, c3, c4 = channels
        self.channels = channels
        self.enc1 = ConvBlock(3, c1)
        self.enc2 = ConvBlock(c1, c2)
        self.enc3 = ConvBlock(c2, c3)
        self.bottleneck = ConvBlock(c3, c4)
        self.pool = nn.MaxPool2d(2)
        self.dec3 = ConvBlock(c4 + c3, c3)
        self.dec2 = ConvBlock(c3 + c2, c2)
        self.dec1 = ConvBlock(c2 + c1, c1)
        self.output = nn.Conv2d(c1, 1, 1)

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(pixel_values)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        bottleneck = self.bottleneck(self.pool(e3))
        d3 = F.interpolate(bottleneck, size=e3.shape[-2:], mode="bilinear", align_corners=False)
        d3 = self.dec3(torch.cat((d3, e3), dim=1))
        d2 = F.interpolate(d3, size=e2.shape[-2:], mode="bilinear", align_corners=False)
        d2 = self.dec2(torch.cat((d2, e2), dim=1))
        d1 = F.interpolate(d2, size=e1.shape[-2:], mode="bilinear", align_corners=False)
        d1 = self.dec1(torch.cat((d1, e1), dim=1))
        return self.output(d1)


@torch.inference_mode()
def validate(model: CompactUNet, loader: DataLoader, device: torch.device, base: Any) -> dict[str, float]:
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
            loss, _ = base.segmentation_loss(logits, truth)
        losses.append(float(loss))
        predictions = (torch.sigmoid(logits) >= 0.5).cpu().numpy()[:, 0]
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


def train(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output}")
    output.mkdir(parents=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for label, key, hash_key in (
        ("冻结复评", "frozenPilotsEvaluationReport", "frozenPilotsEvaluationReportSha256"),
        ("阈值上限", "thresholdCeilingReport", "thresholdCeilingReportSha256"),
    ):
        path = Path(plan["prerequisites"][key])
        if sha256_file(path) != plan["prerequisites"][hash_key]:
            raise ValueError(f"{label}报告哈希不一致")
    dataset = plan["dataset"]
    report_path = Path(dataset["materializationReport"])
    review_path = Path(dataset["finalReview"])
    if sha256_file(report_path) != dataset["materializationReportSha256"] or sha256_file(review_path) != dataset["finalReviewSha256"]:
        raise ValueError("ROI v2证据哈希不一致")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["datasetFilesSha256"] != dataset["datasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    if json.loads(review_path.read_text(encoding="utf-8"))["decision"] != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2全量视觉审核未通过")
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
    base = load_base()
    train_dataset = base.RoiDataset(dataset_root, train_records, training=True, seed=seed)
    val_dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=seed)
    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(train_dataset, batch_size=int(config["batchSize"]), shuffle=True, generator=generator, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=int(config["batchSize"]), shuffle=False, num_workers=0, pin_memory=True)
    model = CompactUNet().to(device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config["learningRate"]), weight_decay=float(config["weightDecay"]))
    epochs = int(config["epochs"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=float(config["learningRate"]) * 0.05)
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
        for images, truth, _ in train_loader:
            images = images.to(device, non_blocking=True)
            truth = truth.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type="cuda"):
                logits = model(pixel_values=images)
                loss, _ = base.segmentation_loss(logits, truth)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            train_losses.append(float(loss.detach()))
        validation = validate(model, val_loader, device, base)
        scheduler.step()
        row = {
            "epoch": epoch,
            "trainLoss": round(float(np.mean(train_losses)), 8),
            "learningRate": optimizer.param_groups[0]["lr"],
            "elapsedSeconds": round(time.perf_counter() - epoch_started, 3),
            "validation": validation,
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if validation["jointScore"] > best_score + 1e-6:
            best_score = validation["jointScore"]
            best_epoch = epoch
            stale = 0
            torch.save({"model": model.state_dict(), "channels": model.channels, "epoch": epoch, "validation": validation}, weights_path)
        else:
            stale += 1
        if stale >= int(config["earlyStoppingPatience"]):
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
        "decision": "roi_unet_internal_pilot_pass" if passed else "roi_unet_internal_pilot_fail",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "datasetMaterializationReport": {"path": str(report_path), "sha256": sha256_file(report_path)},
            "finalReview": {"path": str(review_path), "sha256": sha256_file(review_path)},
            "bestWeights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "environment": {"torch": torch.__version__, "device": torch.cuda.get_device_name(0)},
        "architecture": {"name": "CompactUNet", "channels": list(model.channels), "parameterCount": parameter_count, "outputStride": 1, "singleChangedVariable": plan["singleChangedVariable"]},
        "counts": {"instances": len(train_records) + len(val_records), "trainInstances": len(train_records), "valInstances": len(val_records), "trainSourceGroups": report["counts"]["trainSourceGroups"], "valSourceGroups": report["counts"]["valSourceGroups"]},
        "best": best,
        "pilotGate": gate,
        "history": history,
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
    return {"ok": True, "decision": "verified_roi_unet_pilot", "pilotDecision": report["decision"], "best": report["best"]}


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
