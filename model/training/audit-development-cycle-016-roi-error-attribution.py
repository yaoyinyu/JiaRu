#!/usr/bin/env python3
"""生成 cycle016 ROI pilot 内部验证折的逐实例边界误差归因证据。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from transformers import SegformerConfig, SegformerForSemanticSegmentation


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_guards() -> tuple[Any, Any]:
    training_script = Path(__file__).resolve().with_name("train-yolo-seg.py")
    spec = importlib.util.spec_from_file_location("nail_texture_train_yolo_seg", training_script)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载训练器只读图片守卫")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.install_read_only_ultralytics_image_check, module.remove_ultralytics_label_caches


def boundary_metrics(truth: np.ndarray, prediction: np.ndarray, tolerance: int) -> tuple[float, float, float]:
    kernel = np.ones((3, 3), dtype=np.uint8)
    truth_u8 = truth.astype(np.uint8)
    prediction_u8 = prediction.astype(np.uint8)
    truth_boundary = (truth_u8 - cv2.erode(truth_u8, kernel, iterations=1)).astype(bool)
    prediction_boundary = (prediction_u8 - cv2.erode(prediction_u8, kernel, iterations=1)).astype(bool)
    dilation = np.ones((2 * tolerance + 1, 2 * tolerance + 1), dtype=np.uint8)
    truth_near = cv2.dilate(truth_boundary.astype(np.uint8), dilation, iterations=1).astype(bool)
    prediction_near = cv2.dilate(prediction_boundary.astype(np.uint8), dilation, iterations=1).astype(bool)
    precision = np.logical_and(prediction_boundary, truth_near).sum() / max(1, prediction_boundary.sum())
    recall = np.logical_and(truth_boundary, prediction_near).sum() / max(1, truth_boundary.sum())
    f1 = float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    truth_band = np.logical_and(truth, truth_near)
    prediction_band = np.logical_and(prediction, prediction_near)
    union = np.logical_or(truth_band, prediction_band).sum()
    boundary_iou = float(np.logical_and(truth_band, prediction_band).sum() / union) if union else 1.0
    distance_to_truth = cv2.distanceTransform((~truth_boundary).astype(np.uint8), cv2.DIST_L2, 3)
    distance_to_prediction = cv2.distanceTransform((~prediction_boundary).astype(np.uint8), cv2.DIST_L2, 3)
    mean_distance = 0.5 * (
        float(distance_to_truth[prediction_boundary].mean()) if prediction_boundary.any() else 384.0
    ) + 0.5 * (float(distance_to_prediction[truth_boundary].mean()) if truth_boundary.any() else 384.0)
    return boundary_iou, f1, mean_distance


def mask_iou(truth: np.ndarray, prediction: np.ndarray) -> float:
    union = np.logical_or(truth, prediction).sum()
    return float(np.logical_and(truth, prediction).sum() / union) if union else 1.0


def image_tensor(image: np.ndarray) -> torch.Tensor:
    value = torch.from_numpy(image.astype(np.float32) / 255.0).permute(2, 0, 1)
    mean = torch.tensor([0.485, 0.456, 0.406])[:, None, None]
    std = torch.tensor([0.229, 0.224, 0.225])[:, None, None]
    return (value - mean) / std


def feature_values(image: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    ys, xs = np.where(truth)
    width = int(xs.max() - xs.min() + 1)
    height = int(ys.max() - ys.min() + 1)
    area = int(truth.sum())
    contours, _ = cv2.findContours(truth.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    ring = np.logical_and(cv2.dilate(truth.astype(np.uint8), np.ones((31, 31), np.uint8), iterations=1).astype(bool), ~truth)
    foreground = image[truth].astype(np.float32)
    background = image[ring].astype(np.float32)
    contrast = float(np.linalg.norm(foreground.mean(axis=0) - background.mean(axis=0)) / (255 * np.sqrt(3))) if len(background) else 0.0
    return {
        "areaFraction": float(area / truth.size),
        "aspectRatio": float(max(width, height) / max(1, min(width, height))),
        "boundaryComplexity": float(perimeter / max(1.0, np.sqrt(area))),
        "foregroundRingRgbContrast": contrast,
    }


def grouped(records: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    values = np.asarray([row["features"][feature] for row in records], dtype=np.float64)
    first, second = np.quantile(values, [1 / 3, 2 / 3])
    bins = (("low", -np.inf, first), ("middle", first, second), ("high", second, np.inf))
    output: dict[str, Any] = {"cutpoints": [float(first), float(second)], "bins": {}}
    for name, lower, upper in bins:
        selected = [row for row in records if row["features"][feature] > lower and row["features"][feature] <= upper]
        output["bins"][name] = {
            "count": len(selected),
            "meanIou": round(float(np.mean([row["iou"] for row in selected])), 8),
            "meanBoundaryF1": round(float(np.mean([row["boundaryF1"] for row in selected])), 8),
            "meanBoundaryDistancePixels": round(float(np.mean([row["meanBoundaryDistancePixels"] for row in selected])), 8),
        }
    return output


def make_montage(records: list[dict[str, Any]], dataset_root: Path, output: Path, title: str) -> None:
    tile_width, tile_height = 384, 424
    columns = 4
    rows = (len(records) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * tile_width, rows * tile_height), "white")
    draw = ImageDraw.Draw(canvas)
    for index, row in enumerate(records):
        image = np.asarray(Image.open(dataset_root / row["image"]).convert("RGB"))
        truth = np.asarray(Image.open(dataset_root / row["mask"]).convert("L")) >= 128
        prediction = np.asarray(Image.open(output.parent / row["prediction"]).convert("L")) >= 128
        overlay = image.astype(np.float32)
        overlay[truth] = 0.55 * overlay[truth] + 0.45 * np.asarray([0, 255, 0], dtype=np.float32)
        overlay[prediction] = 0.55 * overlay[prediction] + 0.45 * np.asarray([255, 0, 255], dtype=np.float32)
        tile = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8))
        x = (index % columns) * tile_width
        y = (index // columns) * tile_height
        canvas.paste(tile, (x, y))
        draw.text((x + 4, y + 386), f"{row['id'][:34]}", fill="black")
        draw.text((x + 4, y + 402), f"IoU {row['iou']:.3f} BF1 {row['boundaryF1']:.3f}", fill="black")
    canvas.save(output, format="PNG", optimize=True)


def run(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset_report_path = Path(plan["inputs"]["datasetReport"])
    train_report_path = Path(plan["inputs"]["trainReport"])
    if sha256_file(dataset_report_path) != plan["inputs"]["datasetReportSha256"]:
        raise ValueError("数据集报告哈希不匹配")
    if sha256_file(train_report_path) != plan["inputs"]["trainReportSha256"]:
        raise ValueError("训练报告哈希不匹配")
    dataset_report = json.loads(dataset_report_path.read_text(encoding="utf-8"))
    if dataset_report["datasetFilesSha256"] != plan["inputs"]["datasetFilesSha256"]:
        raise ValueError("数据集文件树哈希不匹配")
    train_report = json.loads(train_report_path.read_text(encoding="utf-8"))
    dataset_root = Path(dataset_report["outputDir"])
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    records = [row for row in manifest["records"] if row["split"] == "val"]
    if len(records) != int(plan["fixedContract"]["instances"]):
        raise ValueError("验证实例数与预注册合同不一致")
    checkpoint_path = Path(train_report["inputs"]["bestWeights"]["path"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = SegformerForSemanticSegmentation(SegformerConfig.from_dict(checkpoint["config"]))
    model.load_state_dict(checkpoint["model"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    (temporary / "predictions").mkdir()
    audit_records: list[dict[str, Any]] = []
    try:
        for offset in range(0, len(records), 12):
            batch = records[offset : offset + 12]
            images = [np.asarray(Image.open(dataset_root / row["image"]).convert("RGB")) for row in batch]
            truths = [np.asarray(Image.open(dataset_root / row["mask"]).convert("L")) >= 128 for row in batch]
            tensor = torch.stack([image_tensor(image) for image in images]).to(device)
            with torch.inference_mode(), torch.amp.autocast(device_type="cuda", enabled=device.type == "cuda"):
                logits = model(pixel_values=tensor).logits
                logits = F.interpolate(logits, size=(384, 384), mode="bilinear", align_corners=False)
                predictions = (torch.sigmoid(logits) >= 0.5).cpu().numpy()[:, 0]
            for row, image, truth, prediction in zip(batch, images, truths, predictions, strict=True):
                boundary_iou, boundary_f1, distance = boundary_metrics(truth, prediction, 2)
                small_truth = cv2.resize(truth.astype(np.uint8), (96, 96), interpolation=cv2.INTER_NEAREST)
                ceiling = cv2.resize(small_truth.astype(np.float32), (384, 384), interpolation=cv2.INTER_LINEAR) >= 0.5
                ceiling_iou, ceiling_f1, _ = boundary_metrics(truth, ceiling, 2)
                prediction_path = temporary / "predictions" / f"{row['id']}.png"
                Image.fromarray(prediction.astype(np.uint8) * 255).save(prediction_path, format="PNG", optimize=True)
                audit_records.append(
                    {
                        "id": row["id"],
                        "sourceGroup": row["sourceGroup"],
                        "image": row["image"],
                        "mask": row["mask"],
                        "prediction": prediction_path.relative_to(temporary).as_posix(),
                        "predictionSha256": sha256_file(prediction_path),
                        "iou": round(mask_iou(truth, prediction), 8),
                        "boundaryIou": round(boundary_iou, 8),
                        "boundaryF1": round(boundary_f1, 8),
                        "meanBoundaryDistancePixels": round(distance, 8),
                        "strideCeilingIou": round(mask_iou(truth, ceiling), 8),
                        "strideCeilingBoundaryIou": round(ceiling_iou, 8),
                        "strideCeilingBoundaryF1": round(ceiling_f1, 8),
                        "features": feature_values(image, truth),
                    }
                )
        worst = sorted(audit_records, key=lambda row: (row["boundaryF1"], row["iou"]))[:24]
        best = sorted(audit_records, key=lambda row: (row["boundaryF1"], row["iou"]), reverse=True)[:12]
        make_montage(worst, dataset_root, temporary / "worst-24.png", "worst")
        make_montage(best, dataset_root, temporary / "best-12.png", "best")
        ious = [row["iou"] for row in audit_records]
        boundary_f1s = [row["boundaryF1"] for row in audit_records]
        ceiling_f1s = [row["strideCeilingBoundaryF1"] for row in audit_records]
        summary = {
            "instances": len(audit_records),
            "meanIou": round(float(np.mean(ious)), 8),
            "meanBoundaryF1": round(float(np.mean(boundary_f1s)), 8),
            "meanBoundaryDistancePixels": round(float(np.mean([row["meanBoundaryDistancePixels"] for row in audit_records])), 8),
            "meanStrideCeilingIou": round(float(np.mean([row["strideCeilingIou"] for row in audit_records])), 8),
            "meanStrideCeilingBoundaryF1": round(float(np.mean(ceiling_f1s)), 8),
            "strideCeilingBoundaryF1AtLeast090Rate": round(sum(value >= 0.9 for value in ceiling_f1s) / len(ceiling_f1s), 8),
        }
        stratification = {feature: grouped(audit_records, feature) for feature in ("areaFraction", "aspectRatio", "foregroundRingRgbContrast", "boundaryComplexity")}
        decision = "learning_or_supervision_bottleneck_not_stride4_ceiling" if summary["meanStrideCeilingBoundaryF1"] >= 0.9 else "stride4_ceiling_requires_architecture_change"
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": decision,
            "scope": {"formalCandidate": False, "releaseEligible": False, "testOrHoldoutRead": False},
            "inputs": {
                "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
                "datasetReport": {"path": str(dataset_report_path), "sha256": sha256_file(dataset_report_path)},
                "trainReport": {"path": str(train_report_path), "sha256": sha256_file(train_report_path)},
                "weights": {"path": str(checkpoint_path), "sha256": sha256_file(checkpoint_path)},
            },
            "summary": summary,
            "stratification": stratification,
            "montages": {"worst24": "worst-24.png", "best12": "best-12.png"},
            "records": audit_records,
            "errors": [],
        }
        (temporary / "audit-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
        return report
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify(path: Path) -> dict[str, Any]:
    report_path = path / "audit-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"绑定哈希不一致：{name}")
    for row in report["records"]:
        if sha256_file(path / row["prediction"]) != row["predictionSha256"]:
            raise ValueError(f"预测证据哈希不一致：{row['id']}")
    return {"ok": True, "decision": "verified", "summary": report["summary"], "reportSha256": sha256_file(report_path)}


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
        raise ValueError("执行模式需要--plan与--output-dir")
    plan_path = Path(args.plan).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset_report = json.loads(Path(plan["inputs"]["datasetReport"]).read_text(encoding="utf-8"))
    dataset_root = Path(dataset_report["outputDir"])
    install_guard, remove_caches = load_guards()
    install_guard()
    remove_caches(dataset_root)
    try:
        report = run(plan_path, Path(args.output_dir).resolve())
    finally:
        remove_caches(dataset_root)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "summary": report["summary"], "stratification": report["stratification"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
