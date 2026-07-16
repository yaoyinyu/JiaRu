from __future__ import annotations

from pathlib import Path
from typing import Any

from shapely.geometry import Polygon


def parse_yolo_polygons(
    path: Path,
    prediction: bool,
    minimum_confidence: float = 0.0,
    repair_invalid: bool = False,
) -> list[dict[str, Any]]:
    polygons: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        parts = raw.split()
        minimum = 2 if prediction else 7
        if len(parts) < minimum:
            raise ValueError(f"{path}: line {line_number} is too short")
        values = [float(value) for value in parts[1:]]
        confidence = values[-1] if prediction else None
        if prediction and confidence < minimum_confidence:
            continue
        coordinates = values[:-1] if prediction else values
        if len(coordinates) < 6 or len(coordinates) % 2:
            raise ValueError(f"{path}: line {line_number} has invalid polygon coordinates")
        polygon = Polygon(list(zip(coordinates[0::2], coordinates[1::2])))
        repaired = False
        if (prediction or repair_invalid) and (not polygon.is_valid or polygon.area <= 0):
            polygon = polygon.buffer(0)
            if polygon.geom_type == "MultiPolygon":
                polygon = max(polygon.geoms, key=lambda item: item.area)
            repaired = True
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            raise ValueError(f"{path}: line {line_number} has an invalid polygon")
        polygons.append(
            {
                "polygon": polygon,
                "confidence": confidence,
                "line": line_number,
                "repaired": repaired,
            }
        )
    return polygons


def polygon_iou(left: Polygon, right: Polygon) -> float:
    union = left.union(right).area
    return float(left.intersection(right).area / union) if union > 0 else 0.0


def match_instances(
    truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    match_iou: float,
    strong_iou: float,
) -> dict[str, Any]:
    candidates = sorted(
        (
            (polygon_iou(gt["polygon"], pred["polygon"]), gt_index, pred_index)
            for gt_index, gt in enumerate(truth)
            for pred_index, pred in enumerate(predictions)
        ),
        reverse=True,
    )
    used_truth: set[int] = set()
    used_predictions: set[int] = set()
    matches: list[dict[str, Any]] = []
    for iou, gt_index, pred_index in candidates:
        if iou < match_iou:
            break
        if gt_index in used_truth or pred_index in used_predictions:
            continue
        used_truth.add(gt_index)
        used_predictions.add(pred_index)
        matches.append(
            {
                "truthIndex": gt_index + 1,
                "predictionIndex": pred_index + 1,
                "iou": iou,
                "confidence": predictions[pred_index]["confidence"],
                "quality": "strong" if iou >= strong_iou else "weak_shape",
            }
        )

    unmatched_truth: list[dict[str, Any]] = []
    for gt_index, gt in enumerate(truth):
        if gt_index in used_truth:
            continue
        best_iou = max(
            (polygon_iou(gt["polygon"], pred["polygon"]) for pred in predictions),
            default=0.0,
        )
        unmatched_truth.append(
            {
                "truthIndex": gt_index + 1,
                "bestPredictionIou": best_iou,
                "failure": "localization_failure" if best_iou >= 0.10 else "missed_detection",
            }
        )

    false_positives = [
        {
            "predictionIndex": pred_index + 1,
            "confidence": pred["confidence"],
            "bestTruthIou": max(
                (polygon_iou(pred["polygon"], gt["polygon"]) for gt in truth),
                default=0.0,
            ),
        }
        for pred_index, pred in enumerate(predictions)
        if pred_index not in used_predictions
    ]
    weak_matches = sum(match["quality"] == "weak_shape" for match in matches)
    severity = len(unmatched_truth) * 3 + len(false_positives) * 2 + weak_matches
    return {
        "truthCount": len(truth),
        "predictionCount": len(predictions),
        "matchedCount": len(matches),
        "strongMatchCount": len(matches) - weak_matches,
        "weakShapeCount": weak_matches,
        "missedCount": len(unmatched_truth),
        "falsePositiveCount": len(false_positives),
        "meanMatchedIou": sum(item["iou"] for item in matches) / len(matches) if matches else 0.0,
        "severityScore": severity,
        "matches": matches,
        "unmatchedTruth": unmatched_truth,
        "falsePositives": false_positives,
    }
