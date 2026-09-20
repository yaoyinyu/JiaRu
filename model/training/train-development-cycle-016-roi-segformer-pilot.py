#!/usr/bin/env python3
"""训练 cycle016 随机初始化的逐甲 ROI SegFormer pilot。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageEnhance
from torch.utils.data import DataLoader, Dataset
from transformers import SegformerConfig, SegformerForSemanticSegmentation


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def build_model(seed: int) -> SegformerForSemanticSegmentation:
    torch.manual_seed(seed)
    config = SegformerConfig(
        num_channels=3,
        num_labels=1,
        depths=[2, 2, 2, 2],
        hidden_sizes=[32, 64, 160, 256],
        decoder_hidden_size=256,
        num_attention_heads=[1, 2, 5, 8],
        sr_ratios=[8, 4, 2, 1],
        patch_sizes=[7, 3, 3, 3],
        strides=[4, 2, 2, 2],
        mlp_ratios=[4, 4, 4, 4],
        semantic_loss_ignore_index=255,
    )
    return SegformerForSemanticSegmentation(config)


class RoiDataset(Dataset[tuple[torch.Tensor, torch.Tensor, str]]):
    def __init__(self, root: Path, records: list[dict[str, Any]], *, training: bool, seed: int) -> None:
        self.root = root
        self.records = records
        self.training = training
        self.seed = seed
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, str]:
        row = self.records[index]
        with Image.open(self.root / row["image"]) as source:
            image = source.convert("RGB")
        with Image.open(self.root / row["mask"]) as source:
            mask = source.convert("L")
        if self.training:
            digest = hashlib.sha256(f"{self.seed}:{self.epoch}:{row['id']}".encode("utf-8")).digest()
            rng = random.Random(int.from_bytes(digest[:8], "big"))
            if rng.random() < 0.5:
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                mask = mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if rng.random() < 0.5:
                image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                mask = mask.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            rotation = rng.randrange(4)
            if rotation:
                image = image.rotate(90 * rotation)
                mask = mask.rotate(90 * rotation)
            image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.9, 1.1))
            image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.9, 1.1))
            image = ImageEnhance.Color(image).enhance(rng.uniform(0.9, 1.1))
        image_array = np.asarray(image, dtype=np.float32) / 255.0
        mask_array = (np.asarray(mask, dtype=np.uint8) >= 128).astype(np.float32)
        image_tensor = torch.from_numpy(image_array).permute(2, 0, 1)
        mean = torch.tensor([0.485, 0.456, 0.406])[:, None, None]
        std = torch.tensor([0.229, 0.224, 0.225])[:, None, None]
        image_tensor = (image_tensor - mean) / std
        return image_tensor, torch.from_numpy(mask_array)[None, :, :], str(row["id"])


def segmentation_loss(logits: torch.Tensor, truth: torch.Tensor) -> tuple[torch.Tensor, dict[str, float]]:
    logits = F.interpolate(logits, size=truth.shape[-2:], mode="bilinear", align_corners=False)
    bce = F.binary_cross_entropy_with_logits(logits, truth)
    probability = torch.sigmoid(logits)
    intersection = (probability * truth).sum(dim=(1, 2, 3))
    dice = 1 - ((2 * intersection + 1) / (probability.sum(dim=(1, 2, 3)) + truth.sum(dim=(1, 2, 3)) + 1)).mean()
    sobel_x = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=probability.dtype, device=probability.device).reshape(1, 1, 3, 3)
    sobel_y = sobel_x.transpose(2, 3)
    probability_edges = torch.sqrt(F.conv2d(probability, sobel_x, padding=1).square() + F.conv2d(probability, sobel_y, padding=1).square() + 1e-6)
    truth_edges = torch.sqrt(F.conv2d(truth, sobel_x, padding=1).square() + F.conv2d(truth, sobel_y, padding=1).square() + 1e-6)
    boundary = F.l1_loss(probability_edges, truth_edges)
    total = bce + dice + 0.2 * boundary
    return total, {"bce": float(bce.detach()), "dice": float(dice.detach()), "boundary": float(boundary.detach())}


def boundary_metrics(truth: np.ndarray, prediction: np.ndarray, tolerance: int = 2) -> tuple[float, float]:
    kernel = np.ones((3, 3), dtype=np.uint8)
    truth_u8 = truth.astype(np.uint8)
    prediction_u8 = prediction.astype(np.uint8)
    truth_boundary = truth_u8 - cv2.erode(truth_u8, kernel, iterations=1)
    prediction_boundary = prediction_u8 - cv2.erode(prediction_u8, kernel, iterations=1)
    dilation = np.ones((2 * tolerance + 1, 2 * tolerance + 1), dtype=np.uint8)
    truth_near = cv2.dilate(truth_boundary, dilation, iterations=1).astype(bool)
    prediction_near = cv2.dilate(prediction_boundary, dilation, iterations=1).astype(bool)
    truth_boundary = truth_boundary.astype(bool)
    prediction_boundary = prediction_boundary.astype(bool)
    precision = np.logical_and(prediction_boundary, truth_near).sum() / max(1, prediction_boundary.sum())
    recall = np.logical_and(truth_boundary, prediction_near).sum() / max(1, truth_boundary.sum())
    f1 = float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    truth_band = np.logical_and(truth, truth_near)
    prediction_band = np.logical_and(prediction, prediction_near)
    union = np.logical_or(truth_band, prediction_band).sum()
    boundary_iou = float(np.logical_and(truth_band, prediction_band).sum() / union) if union else 1.0
    return boundary_iou, f1


@torch.inference_mode()
def validate(model: SegformerForSemanticSegmentation, loader: DataLoader, device: torch.device) -> dict[str, float]:
    model.eval()
    losses: list[float] = []
    ious: list[float] = []
    boundary_ious: list[float] = []
    boundary_f1s: list[float] = []
    for images, truth, _ in loader:
        images = images.to(device, non_blocking=True)
        truth = truth.to(device, non_blocking=True)
        with torch.amp.autocast(device_type="cuda", enabled=device.type == "cuda"):
            logits = model(pixel_values=images).logits
            loss, _ = segmentation_loss(logits, truth)
            logits = F.interpolate(logits, size=truth.shape[-2:], mode="bilinear", align_corners=False)
        losses.append(float(loss))
        predictions = (torch.sigmoid(logits) >= 0.5).cpu().numpy()[:, 0]
        truths = truth.cpu().numpy()[:, 0] >= 0.5
        for prediction, target in zip(predictions, truths, strict=True):
            union = np.logical_or(prediction, target).sum()
            ious.append(float(np.logical_and(prediction, target).sum() / union) if union else 1.0)
            boundary_iou, boundary_f1 = boundary_metrics(target, prediction)
            boundary_ious.append(boundary_iou)
            boundary_f1s.append(boundary_f1)
    joint = sum(iou >= 0.75 and boundary_iou >= 0.75 and boundary_f1 >= 0.9 for iou, boundary_iou, boundary_f1 in zip(ious, boundary_ious, boundary_f1s))
    return {
        "loss": round(float(np.mean(losses)), 8),
        "meanIou": round(float(np.mean(ious)), 8),
        "meanBoundaryIou": round(float(np.mean(boundary_ious)), 8),
        "meanBoundaryF1": round(float(np.mean(boundary_f1s)), 8),
        "jointInstancePassRate": round(joint / len(ious), 8),
        "jointScore": round((float(np.mean(ious)) + float(np.mean(boundary_f1s))) / 2, 8),
    }


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name in ("plan", "datasetMaterializationReport", "bestWeights"):
        binding = report["inputs"][name]
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入或权重哈希不一致：{name}")
    return {"ok": True, "decision": "verified", "best": report["best"], "pilotGate": report["pilotGate"]}


def train(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output}")
    output.mkdir(parents=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset_report_path = Path(plan["dataset"]["materializationReport"])
    if sha256_file(dataset_report_path) != plan["dataset"]["materializationReportSha256"]:
        raise ValueError("ROI物化报告哈希与预注册计划不一致")
    dataset_report = json.loads(dataset_report_path.read_text(encoding="utf-8"))
    if dataset_report["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("ROI数据集聚合哈希与预注册计划不一致")
    dataset_root = Path(dataset_report["outputDir"])
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
    train_dataset = RoiDataset(dataset_root, train_records, training=True, seed=seed)
    val_dataset = RoiDataset(dataset_root, val_records, training=False, seed=seed)
    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(train_dataset, batch_size=int(config["batchSize"]), shuffle=True, generator=generator, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=int(config["batchSize"]), shuffle=False, num_workers=0, pin_memory=True)
    model = build_model(seed).to(device)
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
                logits = model(pixel_values=images).logits
                loss, _ = segmentation_loss(logits, truth)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            train_losses.append(float(loss.detach()))
        validation = validate(model, val_loader, device)
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
            torch.save({"model": model.state_dict(), "config": model.config.to_dict(), "epoch": epoch, "validation": validation}, weights_path)
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
    report = {
        "schemaVersion": 1,
        "ok": passed,
        "decision": "roi_segmenter_internal_pilot_pass" if passed else "roi_segmenter_internal_pilot_fail",
        "scope": {"formalCandidate": False, "releaseEligible": False, "testOrHoldoutRead": False},
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "datasetMaterializationReport": {"path": str(dataset_report_path), "sha256": sha256_file(dataset_report_path)},
            "bestWeights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "environment": {"torch": torch.__version__, "transformers": __import__("transformers").__version__, "device": torch.cuda.get_device_name(0)},
        "architecture": plan["architecture"],
        "counts": dataset_report["counts"],
        "best": best,
        "pilotGate": gate,
        "history": history,
        "elapsedSeconds": round(time.perf_counter() - started, 3),
        "errors": [],
    }
    write_atomic(output / "train-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.plan or not args.output_dir:
        raise ValueError("训练模式需要--plan与--output-dir")
    report = train(Path(args.plan).resolve(), Path(args.output_dir).resolve())
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "best": report["best"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
