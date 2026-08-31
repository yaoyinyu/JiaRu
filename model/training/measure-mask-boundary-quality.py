from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from _instance_segmentation_metrics import match_instances, parse_yolo_polygons
from _training_common import load_dataset_config, write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def polygon_mask(points: list[tuple[float, float]], width: int, height: int) -> np.ndarray:
    scaled = np.asarray(
        [[round(x * (width - 1)), round(y * (height - 1))] for x, y in points],
        dtype=np.int32,
    )
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [scaled], 1)
    return mask


def boundary(mask: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), dtype=np.uint8)
    return np.logical_xor(mask.astype(bool), cv2.erode(mask, kernel, iterations=1).astype(bool))


def boundary_counts(truth: np.ndarray, prediction: np.ndarray, tolerance: int) -> tuple[int, int, int, int]:
    truth_edge = boundary(truth)
    prediction_edge = boundary(prediction)
    kernel = np.ones((tolerance * 2 + 1, tolerance * 2 + 1), dtype=np.uint8)
    truth_band = cv2.dilate(truth_edge.astype(np.uint8), kernel, iterations=1).astype(bool)
    prediction_band = cv2.dilate(prediction_edge.astype(np.uint8), kernel, iterations=1).astype(bool)
    matched_prediction = int(np.logical_and(prediction_edge, truth_band).sum())
    matched_truth = int(np.logical_and(truth_edge, prediction_band).sum())
    return matched_prediction, int(prediction_edge.sum()), matched_truth, int(truth_edge.sum())


def find_image(images_dir: Path, stem: str) -> Path:
    matches = [path for path in images_dir.glob(f"{stem}.*") if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one image for {stem}, found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure matched-mask boundary F1 on a source-isolated YOLO validation split.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--prediction-labels", required=True)
    parser.add_argument("--threshold", required=True, type=float)
    parser.add_argument("--match-iou", type=float, default=0.50)
    parser.add_argument("--strong-iou", type=float, default=0.75)
    parser.add_argument("--tolerance-pixels", type=int, default=2)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        raise ValueError("threshold must be in [0, 1]")
    if args.tolerance_pixels < 0:
        raise ValueError("tolerance-pixels must be non-negative")

    dataset_yaml = Path(args.dataset).resolve()
    prediction_dir = Path(args.prediction_labels).resolve()
    output = Path(args.output).resolve()
    config = load_dataset_config(dataset_yaml)
    images_dir = (config.dataset_root / config.val).resolve()
    labels_dir = (config.dataset_root / "labels" / Path(config.val).name).resolve()

    totals = {"matchedPredictionBoundaryPixels": 0, "predictionBoundaryPixels": 0, "matchedTruthBoundaryPixels": 0, "truthBoundaryPixels": 0}
    records: list[dict[str, Any]] = []
    for truth_path in sorted(labels_dir.glob("*.txt"), key=lambda path: path.name):
        prediction_path = prediction_dir / truth_path.name
        image_path = find_image(images_dir, truth_path.stem)
        with Image.open(image_path) as image:
            width, height = image.size
        truth = parse_yolo_polygons(truth_path, prediction=False)
        predictions = parse_yolo_polygons(prediction_path, prediction=True, minimum_confidence=args.threshold) if prediction_path.is_file() else []
        matched = match_instances(truth, predictions, args.match_iou, args.strong_iou)
        image_counts = [0, 0, 0, 0]
        for match in matched["matches"]:
            truth_polygon = truth[match["truthIndex"] - 1]["polygon"]
            prediction_polygon = predictions[match["predictionIndex"] - 1]["polygon"]
            counts = boundary_counts(
                polygon_mask(list(truth_polygon.exterior.coords), width, height),
                polygon_mask(list(prediction_polygon.exterior.coords), width, height),
                args.tolerance_pixels,
            )
            image_counts = [left + right for left, right in zip(image_counts, counts)]
        for key, value in zip(totals, image_counts):
            totals[key] += value
        precision = image_counts[0] / image_counts[1] if image_counts[1] else 0.0
        recall = image_counts[2] / image_counts[3] if image_counts[3] else 0.0
        records.append({"stem": truth_path.stem, "truthCount": len(truth), "predictionCount": len(predictions), "matchedCount": matched["matchedCount"], "meanMatchedIou": matched["meanMatchedIou"], "boundaryPrecision": precision, "boundaryRecall": recall, "boundaryF1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0})

    precision = totals["matchedPredictionBoundaryPixels"] / totals["predictionBoundaryPixels"] if totals["predictionBoundaryPixels"] else 0.0
    recall = totals["matchedTruthBoundaryPixels"] / totals["truthBoundaryPixels"] if totals["truthBoundaryPixels"] else 0.0
    report = {
        "schemaVersion": "jiaru-mask-boundary-quality/v1",
        "ok": True,
        "decision": "boundary_quality_measured_on_matched_val_instances",
        "inputs": {"datasetYaml": str(dataset_yaml), "datasetYamlSha256": sha256(dataset_yaml), "predictionLabels": str(prediction_dir), "threshold": args.threshold, "matchIou": args.match_iou, "strongIou": args.strong_iou, "tolerancePixelsAtOriginalResolution": args.tolerance_pixels},
        "counts": {"images": len(records), "truthInstances": sum(item["truthCount"] for item in records), "predictionInstances": sum(item["predictionCount"] for item in records), "matchedInstances": sum(item["matchedCount"] for item in records), **totals},
        "metrics": {"microBoundaryPrecision": precision, "microBoundaryRecall": recall, "microBoundaryF1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0, "meanImageBoundaryF1": sum(item["boundaryF1"] for item in records) / len(records) if records else 0.0, "meanMatchedIou": sum(item["meanMatchedIou"] * item["matchedCount"] for item in records) / sum(item["matchedCount"] for item in records) if sum(item["matchedCount"] for item in records) else 0.0},
        "records": records,
    }
    write_json(output, report)
    print(json.dumps({"ok": True, "output": str(output), "counts": report["counts"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
