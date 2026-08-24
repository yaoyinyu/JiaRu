from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from _instance_segmentation_metrics import match_instances, parse_yolo_polygons
from _training_common import load_dataset_config, write_json


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_bound_file(inputs: dict[str, Any], key: str) -> Path:
    path = Path(str(inputs.get(key, ""))).resolve()
    expected = inputs.get(f"{key}Sha256")
    if not path.is_file() or not isinstance(expected, str) or sha256(path) != expected:
        raise ValueError(f"calibration input is missing or drifted: {key}")
    return path


def prediction_paths(artifact_index_path: Path) -> dict[str, Path]:
    artifact_index = read_json(artifact_index_path)
    if artifact_index.get("split") != "val":
        raise ValueError("prediction artifact index must use split=val")
    records = artifact_index.get("prediction_records")
    if not isinstance(records, list) or artifact_index.get(
        "prediction_records_sha256"
    ) != canonical_sha256(records):
        raise ValueError("prediction record coverage is missing or drifted")
    result: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("prediction record is malformed")
        stem = str(record.get("stem", ""))
        path = (artifact_index_path.parent / str(record.get("path", ""))).resolve()
        try:
            path.relative_to(artifact_index_path.parent.resolve())
        except ValueError as error:
            raise ValueError(f"prediction path escapes artifact root: {stem}") from error
        if not stem or stem in result or not path.is_file() or sha256(path) != record.get("sha256"):
            raise ValueError(f"prediction evidence is missing or drifted: {stem}")
        result[stem] = path
    return result


def classify_truth(polygon: Any, best_iou: float) -> list[str]:
    min_x, min_y, max_x, max_y = polygon.bounds
    width = max_x - min_x
    height = max_y - min_y
    area = float(polygon.area)
    aspect = height / width if width > 0 else float("inf")
    edge_distance = min(min_x, min_y, 1 - max_x, 1 - max_y)
    categories = [
        "localization_failure" if best_iou >= 0.10 else "complete_miss"
    ]
    if area <= 0.0045:
        categories.append("tiny_area")
    elif area <= 0.008:
        categories.append("small_area")
    if aspect <= 0.70:
        categories.append("wide_or_foreshortened")
    elif aspect >= 1.80:
        categories.append("narrow_or_elongated")
    if edge_distance <= 0.08:
        categories.append("edge_adjacent")
    return categories


def build_report(calibration_path: Path) -> dict[str, Any]:
    calibration = read_json(calibration_path)
    if (
        calibration.get("decision") != "calibrated_threshold_ready_for_candidate_manifest"
        or calibration.get("calibrationEligible") is not True
        or calibration.get("inputs", {}).get("split") != "val"
    ):
        raise ValueError("calibration report is not eligible canonical validation evidence")
    inputs = calibration["inputs"]
    dataset_yaml = validate_bound_file(inputs, "datasetYaml")
    validate_bound_file(inputs, "datasetReport")
    validate_bound_file(inputs, "metrics")
    artifact_index_path = validate_bound_file(inputs, "artifactIndex")
    validate_bound_file(inputs, "weights")
    validate_bound_file(inputs, "truthAudit")
    dataset = load_dataset_config(dataset_yaml)
    truth_root = (dataset.dataset_root / dataset.val.replace("images/", "labels/")).resolve()
    truth_paths = sorted(truth_root.glob("*.txt"))
    predictions = prediction_paths(artifact_index_path)
    if {path.stem for path in truth_paths} != set(predictions):
        raise ValueError("truth and prediction image coverage differ")

    threshold = float(calibration["manifestScoreThreshold"])
    match_iou = float(calibration["thresholds"]["matchIou"])
    strong_iou = float(calibration["thresholds"]["strongIou"])
    category_counts: Counter[str] = Counter()
    failure_count_histogram: Counter[int] = Counter()
    image_truth_histogram: Counter[int] = Counter()
    totals: Counter[str] = Counter()
    for truth_path in truth_paths:
        truth = parse_yolo_polygons(truth_path, prediction=False)
        predicted = parse_yolo_polygons(
            predictions[truth_path.stem], prediction=True, minimum_confidence=threshold
        )
        result = match_instances(truth, predicted, match_iou, strong_iou)
        totals.update(
            truth_masks=result["truthCount"],
            predictions=result["predictionCount"],
            matched_masks=result["matchedCount"],
            missed_masks=result["missedCount"],
            false_positives=result["falsePositiveCount"],
            weak_shape_matches=result["weakShapeCount"],
        )
        image_truth_histogram[result["truthCount"]] += 1
        failure_count_histogram[result["missedCount"]] += 1
        for missed in result["unmatchedTruth"]:
            polygon = truth[int(missed["truthIndex"]) - 1]["polygon"]
            category_counts.update(classify_truth(polygon, float(missed["bestPredictionIou"])))

    aggregate = {
        "images": len(truth_paths),
        **dict(totals),
        "failureCategoryCounts": dict(sorted(category_counts.items())),
        "truthMasksPerImageHistogram": {
            str(key): value for key, value in sorted(image_truth_histogram.items())
        },
        "missedMasksPerImageHistogram": {
            str(key): value for key, value in sorted(failure_count_histogram.items())
        },
    }
    return {
        "ok": True,
        "schemaVersion": 1,
        "decision": "anonymous_validation_failure_profile_ready_for_training_curriculum",
        "trainingUse": "prohibited",
        "identityDisclosure": "prohibited",
        "itemsIncluded": False,
        "curriculumUse": "abstract_categories_only",
        "inputs": {
            "calibrationReport": str(calibration_path),
            "calibrationReportSha256": sha256(calibration_path),
            "datasetYamlSha256": inputs["datasetYamlSha256"],
            "artifactIndexSha256": inputs["artifactIndexSha256"],
            "weightsSha256": inputs["weightsSha256"],
            "scoreThreshold": threshold,
            "matchIouThreshold": match_iou,
            "strongIouThreshold": strong_iou,
        },
        "aggregate": aggregate,
        "aggregateSha256": canonical_sha256(aggregate),
        "policy": {
            "allowed": "Use aggregate categories to select source-isolated train-role examples.",
            "prohibited": "Expose validation identities or copy validation images, labels, crops, source groups, or predictions into training.",
        },
    }


def first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    if type(expected) is not type(actual):
        return f"{path}: type differs"
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return f"{path}: keys differ"
        for key in sorted(expected):
            difference = first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: length differs"
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference:
                return difference
        return None
    return None if expected == actual else f"{path}: value differs"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an identity-free instance failure profile from canonical val evidence."
    )
    parser.add_argument("--calibration-report")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        if args.calibration_report or args.output:
            parser.error("--verify-report does not accept generation arguments")
        report_path = Path(args.verify_report).resolve()
        persisted = read_json(report_path)
        calibration_path = Path(persisted.get("inputs", {}).get("calibrationReport", "")).resolve()
        recomputed = build_report(calibration_path)
        difference = first_difference(persisted, recomputed)
        if difference:
            raise ValueError(f"failure profile replay mismatch at {difference}")
        print(json.dumps({"ok": True, "report": str(report_path), "reportSha256": sha256(report_path)}, ensure_ascii=False, indent=2))
        return
    if not args.calibration_report or not args.output:
        parser.error("generation requires --calibration-report and --output")
    report = build_report(Path(args.calibration_report).resolve())
    output = Path(args.output).resolve()
    write_json(output, report)
    print(json.dumps({"ok": True, "output": str(output), "aggregate": report["aggregate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
