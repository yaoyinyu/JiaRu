#!/usr/bin/env python3
"""在来源隔离 val30 上评估 candidate53 两阶段单甲精修链路。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps
from shapely.geometry import Polygon

from _instance_segmentation_metrics import match_instances, parse_yolo_polygons
from _training_common import load_dataset_config, write_json


THRESHOLDS = tuple(round(value / 100, 2) for value in range(10, 91, 5))
MASK_IOU_THRESHOLD = 0.60
MASK_CONTAINMENT_THRESHOLD = 0.85
MASK_SCORE_TOLERANCE = 0.12
BOX_IOU_THRESHOLD = 0.55


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象：{path}")
    return value


def find_image(images_dir: Path, stem: str) -> Path:
    matches = [path for path in images_dir.glob(f"{stem}.*") if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"{stem}应精确对应一张验证图，实际{len(matches)}张")
    return matches[0]


def square_crop(box: tuple[float, float, float, float], width: int, height: int, context: float) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box
    side = max(16, int(math.ceil(max(x1 - x0, y1 - y0) * (1 + 2 * context))))
    if side > min(width, height):
        return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left = min(max(int(round(cx - side / 2)), 0), width - side)
    top = min(max(int(round(cy - side / 2)), 0), height - side)
    return left, top, left + side, top + side


def polygon_from_stage2(points: np.ndarray, crop: tuple[int, int, int, int], roi_size: int, width: int, height: int) -> Polygon | None:
    if points.ndim != 2 or points.shape[0] < 3 or points.shape[1] != 2:
        return None
    left, top, right, bottom = crop
    side = right - left
    mapped = [
        (
            min(max((left + float(x) * side / roi_size) / width, 0.0), 1.0),
            min(max((top + float(y) * side / roi_size) / height, 0.0), 1.0),
        )
        for x, y in points
    ]
    polygon = Polygon(mapped)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
        if polygon.geom_type == "MultiPolygon":
            polygon = max(polygon.geoms, key=lambda item: item.area)
    return polygon if polygon.geom_type == "Polygon" and not polygon.is_empty and polygon.area > 0 else None


def box_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    x0, y0 = max(left[0], right[0]), max(left[1], right[1])
    x1, y1 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if intersection <= 0:
        return 0.0
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def suppress_duplicates(candidates: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (-item["score"], item["proposalIndex"])):
        duplicate_index = -1
        for index, selected in enumerate(kept):
            intersection = candidate["polygon"].intersection(selected["polygon"]).area
            union = candidate["polygon"].union(selected["polygon"]).area
            iou = intersection / union if union else 0.0
            containment = intersection / min(candidate["polygon"].area, selected["polygon"].area)
            if iou >= MASK_IOU_THRESHOLD or containment >= MASK_CONTAINMENT_THRESHOLD:
                duplicate_index = index
                break
        if duplicate_index < 0:
            kept.append(candidate)
            continue
        selected = kept[duplicate_index]
        if candidate["polygon"].area > selected["polygon"].area and candidate["score"] + MASK_SCORE_TOLERANCE >= selected["score"]:
            kept[duplicate_index] = candidate

    box_kept: list[dict[str, Any]] = []
    for candidate in sorted(kept, key=lambda item: (-item["score"], item["proposalIndex"])):
        if any(box_iou(candidate["bounds"], selected["bounds"]) >= BOX_IOU_THRESHOLD for selected in box_kept):
            continue
        box_kept.append(candidate)
    return box_kept[:maximum]


def polygon_mask(polygon: Polygon, width: int, height: int) -> np.ndarray:
    points = np.asarray(
        [[round(x * (width - 1)), round(y * (height - 1))] for x, y in polygon.exterior.coords],
        dtype=np.int32,
    )
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [points], 1)
    return mask


def boundary(mask: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), dtype=np.uint8)
    return np.logical_xor(mask.astype(bool), cv2.erode(mask, kernel, iterations=1).astype(bool))


def boundary_counts(truth: np.ndarray, prediction: np.ndarray, tolerance: int = 2) -> tuple[int, int, int, int]:
    truth_edge, prediction_edge = boundary(truth), boundary(prediction)
    kernel = np.ones((tolerance * 2 + 1, tolerance * 2 + 1), dtype=np.uint8)
    truth_band = cv2.dilate(truth_edge.astype(np.uint8), kernel, iterations=1).astype(bool)
    prediction_band = cv2.dilate(prediction_edge.astype(np.uint8), kernel, iterations=1).astype(bool)
    return (
        int(np.logical_and(prediction_edge, truth_band).sum()),
        int(prediction_edge.sum()),
        int(np.logical_and(truth_edge, prediction_band).sum()),
        int(truth_edge.sum()),
    )


def validate_truth_audit(path: Path, dataset: Path, replay_output: Path) -> None:
    audit = read_json(path)
    inputs = audit.get("inputs", {})
    if audit.get("decision") != "approved_as_calibration_truth" or audit.get("ok") is not True or audit.get("calibrationTruthEligible") is not True:
        raise ValueError("val30真值审计未批准")
    if Path(str(inputs.get("datasetYaml", ""))).resolve() != dataset or inputs.get("datasetYamlSha256") != sha256_file(dataset):
        raise ValueError("val30真值审计未绑定当前dataset.yaml字节")
    counts = audit.get("counts", {})
    if int(counts.get("expectedImages", -1)) != 30 or int(counts.get("pass", -1)) != 30 or int(counts.get("rework", -1)) != 0 or int(counts.get("exclude", -1)) != 0:
        raise ValueError("val30真值审计不是30/30全通过")
    finalizer_path = Path(__file__).with_name("finalize-validation-materialization-audit.py")
    spec = importlib.util.spec_from_file_location("candidate53_validation_finalizer", finalizer_path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载val30独立深验器")
    finalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finalizer)
    replay = finalizer.build(
        argparse.Namespace(
            dataset=str(dataset),
            truth_index=str(inputs["truthIndex"]),
            materialization_report=str(inputs["materializationReport"]),
            role_isolation_report=str(inputs["roleIsolationReport"]),
            output=str(replay_output),
        )
    )
    if replay != audit:
        raise ValueError("val30真值审计与当前字节独立深验结果不一致")


def main() -> None:
    parser = argparse.ArgumentParser(description="评估candidate53两阶段val30")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--stage2-weights", required=True)
    parser.add_argument("--stage2-weights-sha256", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--truth-audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    stage2_weights = Path(args.stage2_weights).resolve()
    dataset_path = Path(args.dataset).resolve()
    truth_audit_path = Path(args.truth_audit).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise ValueError(f"输出目录必须全新：{output_dir}")
    plan = read_json(plan_path)
    if plan.get("candidate") != "candidate53" or plan.get("decision") != "pre_registered_two_stage_full_image_recall_plus_single_nail_roi_refinement":
        raise ValueError("计划不是预登记candidate53两阶段计划")
    if sha256_file(stage2_weights) != args.stage2_weights_sha256:
        raise ValueError("stage2权重SHA-256不一致")
    stage1 = plan["stage1"]
    stage1_weights = Path(str(stage1["weights"])).resolve()
    if sha256_file(stage1_weights) != stage1["weightsSha256"]:
        raise ValueError("stage1权重SHA-256不一致")
    if tuple(round(0.10 + 0.05 * index, 2) for index in range(17)) != THRESHOLDS:
        raise ValueError("内部阈值表漂移")
    validate_truth_audit(truth_audit_path, dataset_path, output_dir.parent / ".candidate53-val30-truth-replay.json")

    config = load_dataset_config(dataset_path)
    images_dir = (config.dataset_root / config.val).resolve()
    labels_dir = (config.dataset_root / "labels" / Path(config.val).name).resolve()
    truth_paths = sorted(labels_dir.glob("*.txt"), key=lambda item: item.name)
    if len(truth_paths) != 30:
        raise ValueError(f"正式验证必须精确30张，实际{len(truth_paths)}张")

    from ultralytics import YOLO

    stage1_model = YOLO(str(stage1_weights))
    stage2_model = YOLO(str(stage2_weights))
    context = float(plan["runtimeComposition"]["cropContextRatio"])
    roi_size = int(plan["stage2"]["inputSize"])
    maximum = int(stage1["maximumProposalsPerImage"])
    raw_by_stem: dict[str, list[dict[str, Any]]] = {}
    image_sizes: dict[str, tuple[int, int]] = {}

    stage1_results = stage1_model.predict(
        source=str(images_dir), imgsz=int(stage1["inputSize"]), conf=float(stage1["proposalThreshold"]),
        iou=0.7, max_det=maximum, device=args.device, retina_masks=True, stream=True, verbose=False,
    )
    for result in stage1_results:
        image_path = Path(str(result.path)).resolve()
        with Image.open(image_path) as encoded:
            image = ImageOps.exif_transpose(encoded).convert("RGB")
        width, height = image.size
        image_sizes[image_path.stem] = (width, height)
        proposals: list[tuple[int, tuple[int, int, int, int], np.ndarray]] = []
        if result.boxes is not None:
            for index, raw_box in enumerate(result.boxes.xyxy.detach().cpu().numpy()[:maximum]):
                crop_box = square_crop(tuple(float(value) for value in raw_box), width, height, context)
                if crop_box is None:
                    continue
                crop_rgb = np.asarray(
                    image.crop(crop_box).resize((roi_size, roi_size), Image.Resampling.LANCZOS)
                )
                crop = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
                proposals.append((index, crop_box, crop))
        candidates: list[dict[str, Any]] = []
        if proposals:
            refinements = stage2_model.predict(
                source=[item[2] for item in proposals], imgsz=roi_size, conf=0.001, iou=0.7,
                max_det=1, device=args.device, retina_masks=True, verbose=False,
            )
            if len(refinements) != len(proposals):
                raise ValueError("stage2结果数与ROI数不一致")
            for (proposal_index, crop_box, _), refinement in zip(proposals, refinements, strict=True):
                if refinement.boxes is None or refinement.masks is None or len(refinement.boxes) == 0 or not refinement.masks.xy:
                    continue
                polygon = polygon_from_stage2(np.asarray(refinement.masks.xy[0]), crop_box, roi_size, width, height)
                if polygon is None:
                    continue
                score = float(refinement.boxes.conf[0].detach().cpu())
                candidates.append({
                    "proposalIndex": proposal_index, "score": score, "polygon": polygon,
                    "bounds": tuple(float(value) for value in polygon.bounds), "cropBox": list(crop_box),
                })
        raw_by_stem[image_path.stem] = candidates
    if set(raw_by_stem) != {path.stem for path in truth_paths}:
        raise ValueError("stage1没有精确覆盖val30")

    sweep: list[dict[str, Any]] = []
    predictions_by_threshold: dict[float, dict[str, list[dict[str, Any]]]] = {}
    for threshold in THRESHOLDS:
        totals = {"truth": 0, "predictions": 0, "matched": 0, "missed": 0, "falsePositives": 0}
        boundary_totals = [0, 0, 0, 0]
        selected_by_stem: dict[str, list[dict[str, Any]]] = {}
        for truth_path in truth_paths:
            stem = truth_path.stem
            truth = parse_yolo_polygons(truth_path, prediction=False)
            selected = suppress_duplicates(
                [candidate for candidate in raw_by_stem[stem] if candidate["score"] >= threshold], maximum
            )
            predictions = [{"polygon": item["polygon"], "confidence": item["score"]} for item in selected]
            matched = match_instances(truth, predictions, 0.50, 0.75)
            totals["truth"] += len(truth)
            totals["predictions"] += len(predictions)
            totals["matched"] += matched["matchedCount"]
            totals["missed"] += matched["missedCount"]
            totals["falsePositives"] += matched["falsePositiveCount"]
            width, height = image_sizes[stem]
            for item in matched["matches"]:
                counts = boundary_counts(
                    polygon_mask(truth[item["truthIndex"] - 1]["polygon"], width, height),
                    polygon_mask(predictions[item["predictionIndex"] - 1]["polygon"], width, height),
                )
                boundary_totals = [left + right for left, right in zip(boundary_totals, counts, strict=True)]
            selected_by_stem[stem] = predictions
        precision = boundary_totals[0] / boundary_totals[1] if boundary_totals[1] else 0.0
        recall = boundary_totals[2] / boundary_totals[3] if boundary_totals[3] else 0.0
        boundary_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        meets_recognition = (
            totals["matched"] >= int(plan["selection"]["minimumMatched"])
            and totals["missed"] <= int(plan["selection"]["maximumMissed"])
            and totals["falsePositives"] <= int(plan["selection"]["maximumFalsePositives"])
        )
        meets_boundary = boundary_f1 > float(plan["selection"]["minimumMicroBoundaryF1Exclusive"])
        sweep.append({
            "threshold": threshold, **totals, "microBoundaryPrecision": precision,
            "microBoundaryRecall": recall, "microBoundaryF1": boundary_f1,
            "meetsRecognitionGate": meets_recognition, "meetsBoundaryGate": meets_boundary,
            "eligible": meets_recognition and meets_boundary,
        })
        predictions_by_threshold[threshold] = selected_by_stem

    eligible = [item for item in sweep if item["eligible"]]
    chosen = max(
        eligible,
        key=lambda item: (item["microBoundaryF1"], item["matched"], -item["falsePositives"], item["threshold"]),
        default=None,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f"{output_dir.name}-", dir=output_dir.parent))
    try:
        prediction_dir = temporary / "selected-prediction-labels"
        prediction_dir.mkdir(parents=True)
        if chosen is not None:
            for stem, predictions in predictions_by_threshold[float(chosen["threshold"])].items():
                lines = []
                for item in predictions:
                    coordinates = " ".join(f"{value:.8f}" for point in item["polygon"].exterior.coords[:-1] for value in point)
                    lines.append(f"0 {coordinates} {item['confidence']:.8f}")
                (prediction_dir / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
        report = {
            "schemaVersion": 1,
            "ok": chosen is not None,
            "decision": "candidate53_two_stage_val30_pass" if chosen is not None else "candidate53_two_stage_val30_rejected",
            "inputs": {
                "plan": str(plan_path), "planSha256": sha256_file(plan_path),
                "stage1Weights": str(stage1_weights), "stage1WeightsSha256": sha256_file(stage1_weights),
                "stage2Weights": str(stage2_weights), "stage2WeightsSha256": sha256_file(stage2_weights),
                "datasetYaml": str(dataset_path), "datasetYamlSha256": sha256_file(dataset_path),
                "truthAudit": str(truth_audit_path), "truthAuditSha256": sha256_file(truth_audit_path),
            },
            "fixedRuntime": {
                "stage1InputSize": stage1["inputSize"], "stage1ProposalThreshold": stage1["proposalThreshold"],
                "maximumProposalsPerImage": maximum, "cropContextRatio": context, "stage2InputSize": roi_size,
                "maskIouThreshold": MASK_IOU_THRESHOLD, "maskContainmentThreshold": MASK_CONTAINMENT_THRESHOLD,
                "maskScoreTolerance": MASK_SCORE_TOLERANCE, "boxIouThreshold": BOX_IOU_THRESHOLD,
            },
            "selectionContract": plan["selection"],
            "counts": {
                "images": len(truth_paths), "truthInstances": sum(len(parse_yolo_polygons(path, prediction=False)) for path in truth_paths),
                "rawStage1RefinedCandidates": sum(len(items) for items in raw_by_stem.values()), "testImagesRead": 0,
            },
            "thresholdSweep": sweep,
            "selected": chosen,
            "selectedPredictionLabels": str(output_dir / prediction_dir.name) if chosen is not None else None,
            "releaseState": "val-pass-test100-still-required" if chosen is not None else "hold-val-rejected",
        }
        write_json(temporary / "candidate53-two-stage-val30-decision-v1.json", report)
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "selected": chosen, "output": str(output_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
