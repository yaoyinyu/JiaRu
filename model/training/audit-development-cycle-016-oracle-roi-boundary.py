#!/usr/bin/env python3
"""执行或重放 cycle016 真值ROI边界可达性审计。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_guards() -> tuple[Any, Any]:
    training_script = Path(__file__).resolve().with_name("train-yolo-seg.py")
    spec = importlib.util.spec_from_file_location("nail_texture_train_yolo_seg", training_script)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载训练器只读图片守卫")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.install_read_only_ultralytics_image_check, module.remove_ultralytics_label_caches


def polygons(label_path: Path) -> list[np.ndarray]:
    values: list[np.ndarray] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.strip().split()
        if not tokens:
            continue
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法YOLO分割标签：{label_path}:{line_number}")
        coordinates = np.asarray([float(token) for token in tokens[1:]], dtype=np.float32).reshape(-1, 2)
        values.append(coordinates)
    return values


def square_crop_box(polygon: np.ndarray, width: int, height: int, scale: float) -> tuple[int, int, int, int]:
    pixels = polygon * np.asarray([width, height], dtype=np.float32)
    minimum = pixels.min(axis=0)
    maximum = pixels.max(axis=0)
    center = (minimum + maximum) / 2
    side = max(float(maximum[0] - minimum[0]), float(maximum[1] - minimum[1])) * scale
    side = max(side, 8.0)
    x1 = int(np.floor(center[0] - side / 2))
    y1 = int(np.floor(center[1] - side / 2))
    x2 = int(np.ceil(center[0] + side / 2))
    y2 = int(np.ceil(center[1] + side / 2))
    shift_x = max(0, -x1) - max(0, x2 - width)
    shift_y = max(0, -y1) - max(0, y2 - height)
    x1 = max(0, x1 + shift_x)
    y1 = max(0, y1 + shift_y)
    x2 = min(width, x2 + shift_x)
    y2 = min(height, y2 + shift_y)
    return x1, y1, x2, y2


def raster_truth(polygon: np.ndarray, box: tuple[int, int, int, int], width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = box
    pixels = polygon * np.asarray([width, height], dtype=np.float32)
    pixels -= np.asarray([x1, y1], dtype=np.float32)
    mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(pixels).astype(np.int32)], 1)
    return mask.astype(bool)


def resize_mask(mask: np.ndarray, size: int) -> np.ndarray:
    return cv2.resize(mask.astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST).astype(bool)


def intersection_over_union(first: np.ndarray, second: np.ndarray) -> float:
    union = np.logical_or(first, second).sum()
    return float(np.logical_and(first, second).sum() / union) if union else 1.0


def boundary_metrics(truth: np.ndarray, prediction: np.ndarray, tolerance: int) -> tuple[float, float]:
    kernel = np.ones((3, 3), dtype=np.uint8)
    truth_u8 = truth.astype(np.uint8)
    prediction_u8 = prediction.astype(np.uint8)
    truth_boundary = truth_u8 - cv2.erode(truth_u8, kernel, iterations=1)
    prediction_boundary = prediction_u8 - cv2.erode(prediction_u8, kernel, iterations=1)
    dilation = np.ones((2 * tolerance + 1, 2 * tolerance + 1), dtype=np.uint8)
    truth_near = cv2.dilate(truth_boundary, dilation, iterations=1).astype(bool)
    prediction_near = cv2.dilate(prediction_boundary, dilation, iterations=1).astype(bool)
    truth_boundary_bool = truth_boundary.astype(bool)
    prediction_boundary_bool = prediction_boundary.astype(bool)
    precision = float(np.logical_and(prediction_boundary_bool, truth_near).sum() / max(1, prediction_boundary_bool.sum()))
    recall = float(np.logical_and(truth_boundary_bool, prediction_near).sum() / max(1, truth_boundary_bool.sum()))
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    truth_band = np.logical_and(truth, truth_near)
    prediction_band = np.logical_and(prediction, prediction_near)
    boundary_iou = intersection_over_union(truth_band, prediction_band)
    return boundary_iou, f1


def percentiles(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=np.float64)
    return {name: round(float(np.percentile(data, quantile)), 8) for name, quantile in (("p05", 5), ("p50", 50), ("p95", 95))}


def summarize(instances: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    ious = [float(row["iou"]) for row in instances]
    boundary_ious = [float(row["boundaryIou"]) for row in instances]
    boundary_f1s = [float(row["boundaryF1"]) for row in instances]
    joint = sum(
        iou >= contract["standardIouCompleteGate"]
        and boundary_iou >= contract["boundaryIouGate"]
        and boundary_f1 >= contract["boundaryF1Gate"]
        for iou, boundary_iou, boundary_f1 in zip(ious, boundary_ious, boundary_f1s)
    )
    return {
        "truthInstances": len(instances),
        "roiWithPredictions": sum(int(row["predictionCount"] > 0) for row in instances),
        "standardIou": {"mean": round(float(np.mean(ious)), 8), **percentiles(ious)},
        "boundaryIou": {"mean": round(float(np.mean(boundary_ious)), 8), **percentiles(boundary_ious)},
        "boundaryF1": {"mean": round(float(np.mean(boundary_f1s)), 8), **percentiles(boundary_f1s)},
        "standardIouCompleteCount": sum(value >= contract["standardIouCompleteGate"] for value in ious),
        "boundaryIouPassCount": sum(value >= contract["boundaryIouGate"] for value in boundary_ious),
        "boundaryF1PassCount": sum(value >= contract["boundaryF1Gate"] for value in boundary_f1s),
        "jointPassCount": joint,
        "jointPassRate": round(joint / len(instances), 8),
    }


def verify_report(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key, binding in report["inputs"].items():
        if key == "datasetFilesSha256":
            continue
        path = Path(binding["path"])
        if sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不匹配：{key}")
    replay = summarize(report["instances"], report["contract"])
    if replay != report["summary"]:
        raise ValueError("实例明细与汇总不一致")
    return {"ok": True, "decision": "verified_without_inference", "summary": replay}


def run(plan_path: Path, output_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    contract = plan["fixedContract"]
    dataset_report_path = Path(plan["inputs"]["datasetMaterializationReport"])
    quality_report_path = Path(plan["inputs"]["qualityReport"])
    weights_path = Path(plan["inputs"]["weights"])
    dataset_report = json.loads(dataset_report_path.read_text(encoding="utf-8"))
    dataset_root = Path(dataset_report["outputDir"])
    image_paths = {path.stem: path for path in (dataset_root / "images" / "val").iterdir() if path.is_file()}
    quality = json.loads(quality_report_path.read_text(encoding="utf-8"))
    model = YOLO(str(weights_path))
    instances: list[dict[str, Any]] = []
    crops: list[np.ndarray] = []
    metadata: list[tuple[str, int, np.ndarray]] = []
    for row in quality["images"]:
        if int(row["truthCount"]) == 0:
            continue
        stem = str(row["stem"])
        image_path = image_paths[stem]
        with Image.open(image_path) as image_source:
            image = np.asarray(image_source.convert("RGB"))
        height, width = image.shape[:2]
        for truth_index, polygon in enumerate(polygons(dataset_root / "labels" / "val" / f"{stem}.txt"), start=1):
            box = square_crop_box(polygon, width, height, float(contract["truthRoiSquareScale"]))
            x1, y1, x2, y2 = box
            crop = image[y1:y2, x1:x2].copy()
            truth = resize_mask(raster_truth(polygon, box, width, height), int(contract["canonicalMetricSize"]))
            crops.append(crop)
            metadata.append((stem, truth_index, truth))
    results = model.predict(
        source=crops,
        imgsz=int(contract["inputSize"]),
        conf=float(contract["scoreThreshold"]),
        iou=float(contract["nmsIouThreshold"]),
        max_det=int(contract["maximumCandidatesPerRoi"]),
        retina_masks=True,
        device=0,
        verbose=False,
        stream=True,
    )
    for result, (stem, truth_index, truth) in zip(results, metadata, strict=True):
        candidate_masks: list[np.ndarray] = []
        if result.masks is not None:
            candidate_masks = [resize_mask(mask.cpu().numpy() > 0.5, int(contract["canonicalMetricSize"])) for mask in result.masks.data]
        candidate_ious = [intersection_over_union(truth, candidate) for candidate in candidate_masks]
        if candidate_ious:
            best_index = int(np.argmax(candidate_ious))
            prediction = candidate_masks[best_index]
            iou = candidate_ious[best_index]
        else:
            best_index = -1
            prediction = np.zeros_like(truth)
            iou = 0.0
        boundary_iou, boundary_f1 = boundary_metrics(truth, prediction, int(contract["boundaryTolerancePixels"]))
        instances.append(
            {
                "stem": stem,
                "truthIndex": truth_index,
                "predictionCount": len(candidate_masks),
                "oraclePredictionIndex": best_index + 1 if best_index >= 0 else None,
                "iou": round(iou, 8),
                "boundaryIou": round(boundary_iou, 8),
                "boundaryF1": round(boundary_f1, 8),
            }
        )
    if len(instances) != 354:
        raise ValueError(f"实例分母错误：{len(instances)}")
    summary = summarize(instances, contract)
    passed = summary["jointPassRate"] >= 0.95
    return {
        "schemaVersion": 1,
        "ok": passed,
        "decision": "stage_b_existing_yolo_oracle_roi_pass" if passed else "stage_b_existing_yolo_oracle_roi_fail",
        "scope": {
            "interpretation": "optimistic truth-ROI and truth-selected upper bound for the existing YOLO weights",
            "trainingUse": "prohibited",
            "candidateUse": "prohibited",
            "releaseUse": "prohibited",
        },
        "inputs": {
            "plan": {"path": str(plan_path.resolve()), "sha256": sha256_file(plan_path)},
            "datasetMaterializationReport": {"path": str(dataset_report_path.resolve()), "sha256": sha256_file(dataset_report_path)},
            "qualityReport": {"path": str(quality_report_path.resolve()), "sha256": sha256_file(quality_report_path)},
            "weights": {"path": str(weights_path.resolve()), "sha256": sha256_file(weights_path)},
            "datasetFilesSha256": dataset_report["datasetFilesSha256"],
        },
        "contract": contract,
        "summary": summary,
        "instances": instances,
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify_report(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.plan or not args.output:
        raise ValueError("执行模式需要--plan与--output")
    plan_path = Path(args.plan).resolve()
    output_path = Path(args.output).resolve()
    install_guard, remove_caches = load_guards()
    install_guard()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]).read_text(encoding="utf-8"))
    dataset_root = Path(dataset_report["outputDir"])
    remove_caches(dataset_root)
    try:
        report = run(plan_path, output_path)
        write_atomic(output_path, report)
    finally:
        remove_caches(dataset_root)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
