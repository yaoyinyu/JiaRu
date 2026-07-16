from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from _instance_segmentation_metrics import match_instances, parse_yolo_polygons


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record[key])].append(record)
    output: list[dict[str, Any]] = []
    for name, items in groups.items():
        truth = sum(item["truthCount"] for item in items)
        matched = sum(item["matchedCount"] for item in items)
        output.append({
            key: name,
            "images": len(items),
            "truthCount": truth,
            "matchedCount": matched,
            "recallAtThreshold": matched / truth if truth else 0.0,
            "missedCount": sum(item["missedCount"] for item in items),
            "falsePositiveCount": sum(item["falsePositiveCount"] for item in items),
            "weakShapeCount": sum(item["weakShapeCount"] for item in items),
            "severityScore": sum(item["severityScore"] for item in items),
        })
    return sorted(output, key=lambda item: (-item["severityScore"], item[key]))


def draw_overlay(
    image_path: Path,
    output_path: Path,
    truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    result: dict[str, Any],
) -> None:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    line_width = max(2, round(max(width, height) / 400))
    matched_predictions = {item["predictionIndex"] - 1 for item in result["matches"]}
    matched_truth = {item["truthIndex"] - 1 for item in result["matches"]}
    for index, item in enumerate(truth):
        points = [(round(x * width), round(y * height)) for x, y in item["polygon"].exterior.coords]
        color = (0, 220, 80) if index in matched_truth else (255, 210, 0)
        draw.line(points, fill=color, width=line_width, joint="curve")
    for index, item in enumerate(predictions):
        points = [(round(x * width), round(y * height)) for x, y in item["polygon"].exterior.coords]
        color = (0, 210, 255) if index in matched_predictions else (255, 45, 45)
        draw.line(points, fill=color, width=line_width, joint="curve")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evaluation_root = Path(args.evaluation_root).resolve()
    manifest_path = evaluation_root / "evaluation-manifest.json"
    manifest = read_json(manifest_path)
    artifact_index_path = Path(args.artifact_index).resolve()
    artifact_index = read_json(artifact_index_path)
    prediction_root = artifact_index_path.parent / "labels"

    if manifest.get("decision") != "evaluation_only_frozen_reviewed_snapshot":
        raise ValueError("evaluation manifest decision is not frozen evaluation-only")
    if manifest.get("trainingUse") != "prohibited":
        raise ValueError("frozen evaluation data must prohibit training")
    if manifest.get("sourceIsolation", {}).get("parentSourceGroupOverlap") != []:
        raise ValueError("evaluation data overlaps a formal training source group")
    if manifest.get("sourceIsolation", {}).get("exactImageHashOverlap") != []:
        raise ValueError("evaluation data contains a formal training image")
    if artifact_index.get("split") != "test":
        raise ValueError("prediction artifact index must use the test split")

    records = manifest.get("records", [])
    if len(records) != manifest.get("counts", {}).get("images"):
        raise ValueError("evaluation manifest record count drift")
    if artifact_index.get("counts", {}).get("prediction_labels") != len(records):
        raise ValueError("prediction label count does not cover every frozen image")

    profiled: list[dict[str, Any]] = []
    visual_inputs: dict[tuple[str, str], tuple[Path, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]] = {}
    for record in records:
        lane = record["lane"]
        file_name = record["materializedFileName"]
        stem = Path(file_name).stem
        truth_path = evaluation_root / "labels" / "test" / lane / f"{stem}.txt"
        prediction_path = prediction_root / f"{lane}__{stem}.txt"
        if not truth_path.is_file() or not prediction_path.is_file():
            raise FileNotFoundError(f"missing truth or prediction label for {lane}/{file_name}")
        if sha256(truth_path) != record["materializedLabelSha256"]:
            raise ValueError(f"truth label hash drift for {lane}/{file_name}")
        truth = parse_yolo_polygons(truth_path, prediction=False)
        predictions = parse_yolo_polygons(prediction_path, prediction=True, minimum_confidence=args.confidence)
        result = match_instances(truth, predictions, args.match_iou, args.strong_iou)
        if result["truthCount"] != record["maskCount"]:
            raise ValueError(f"truth mask count drift for {lane}/{file_name}")
        profiled.append({
            "lane": lane,
            "fileName": file_name,
            "parentSourceGroup": record["parentSourceGroup"],
            **result,
        })
        image_path = evaluation_root / "images" / "test" / lane / file_name
        visual_inputs[(lane, file_name)] = (image_path, truth, predictions, result)

    truth_total = sum(item["truthCount"] for item in profiled)
    matched_total = sum(item["matchedCount"] for item in profiled)
    top_failures = sorted(profiled, key=lambda item: (-item["severityScore"], item["lane"], item["fileName"]))
    selected_failures = top_failures[: min(args.top, len(top_failures))]
    if args.overlay_dir:
        overlay_root = Path(args.overlay_dir).resolve()
        for item in selected_failures:
            lane, file_name = item["lane"], item["fileName"]
            image_path, truth, predictions, result = visual_inputs[(lane, file_name)]
            if not image_path.is_file():
                raise FileNotFoundError(f"missing frozen evaluation image for overlay: {image_path}")
            output_path = overlay_root / f"{lane}__{Path(file_name).stem}.jpg"
            draw_overlay(image_path, output_path, truth, predictions, result)
            item["overlayPath"] = str(output_path)
    return {
        "ok": True,
        "schemaVersion": 1,
        "decision": "diagnostic_only_do_not_train_on_frozen_test",
        "trainingUse": "prohibited",
        "inputs": {
            "evaluationManifest": str(manifest_path),
            "sourceItemsSha256": manifest.get("sourceItemsSha256"),
            "artifactIndex": str(artifact_index_path),
            "confidenceThreshold": args.confidence,
            "matchIouThreshold": args.match_iou,
            "strongIouThreshold": args.strong_iou,
        },
        "counts": {
            "images": len(profiled),
            "truthMasks": truth_total,
            "predictionsAtThreshold": sum(item["predictionCount"] for item in profiled),
            "matchedMasks": matched_total,
            "strongMatches": sum(item["strongMatchCount"] for item in profiled),
            "weakShapeMatches": sum(item["weakShapeCount"] for item in profiled),
            "missedMasks": sum(item["missedCount"] for item in profiled),
            "falsePositives": sum(item["falsePositiveCount"] for item in profiled),
            "recallAtThreshold": matched_total / truth_total if truth_total else 0.0,
        },
        "byLane": aggregate(profiled, "lane"),
        "byParentSourceGroup": aggregate(profiled, "parentSourceGroup"),
        "topFailureImages": selected_failures,
        "records": profiled,
        "trainingGuidance": {
            "allowed": "collect training-authorized examples from new source groups with analogous failure patterns",
            "prohibited": "copying any frozen test image, label, crop, or parent source group into training",
        },
        "overlayLegend": {
            "green": "matched ground-truth nail",
            "yellow": "unmatched ground-truth nail",
            "cyan": "matched prediction",
            "red": "unmatched prediction",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile instance-level failures on a frozen release-test snapshot.")
    parser.add_argument("--evaluation-root", required=True)
    parser.add_argument("--artifact-index", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--match-iou", type=float, default=0.50)
    parser.add_argument("--strong-iou", type=float, default=0.75)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--overlay-dir", default="")
    parser.add_argument("--confidence-sweep", default="0.20,0.25,0.30,0.35,0.40,0.45")
    args = parser.parse_args()
    if not (0 <= args.confidence <= 1 and 0 < args.match_iou <= args.strong_iou <= 1):
        raise ValueError("invalid confidence or IoU thresholds")
    report = build_report(args)
    sweep: list[dict[str, Any]] = []
    for raw_threshold in args.confidence_sweep.split(","):
        threshold = float(raw_threshold.strip())
        if not 0 <= threshold <= 1:
            raise ValueError("invalid confidence sweep threshold")
        sweep_args = argparse.Namespace(**vars(args))
        sweep_args.confidence = threshold
        sweep_args.overlay_dir = ""
        sweep_args.top = 0
        item = build_report(sweep_args)
        counts = item["counts"]
        precision = counts["matchedMasks"] / counts["predictionsAtThreshold"] if counts["predictionsAtThreshold"] else 0.0
        recall = counts["recallAtThreshold"]
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        lanes = {entry["lane"]: entry for entry in item["byLane"]}
        sweep.append({
            "confidence": threshold,
            "predictions": counts["predictionsAtThreshold"],
            "matched": counts["matchedMasks"],
            "missed": counts["missedMasks"],
            "falsePositives": counts["falsePositives"],
            "precisionAtIou50": precision,
            "recallAtIou50": recall,
            "f1AtIou50": f1,
            "coreRecallAtIou50": lanes.get("core", {}).get("recallAtThreshold"),
            "stressRecallAtIou50": lanes.get("stress", {}).get("recallAtThreshold"),
        })
    report["thresholdSweep"] = sweep
    report["thresholdSweepNote"] = "Diagnostic only. A threshold change requires browser candidate-count, false-positive, and Beta review gates."
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "counts": report["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
