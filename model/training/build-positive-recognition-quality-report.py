#!/usr/bin/env python3
"""Build a replayable, per-instance positive nail recognition quality report.

Gate modes:
- ``weighted`` (default, schema v2): structural gates (minimum images, instance
  recall, complete-mask ratio, missing-image rate, per-image model output) plus a
  single severity-weighted spurious-instance-rate gate. Replaces the legacy
  zero-defect gates, whose false-negative and false-positive risk budgets were
  strongly asymmetric on a finite sample.
- ``zero-defect`` (schema v1): legacy eight-gate semantics, byte-compatible with
  historical reports. Only intended for replaying schema v1 evidence via
  ``--verify-report``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

from shapely import make_valid
from shapely.geometry import Polygon


MATCH_IOU = 0.50
COMPLETE_MASK_IOU = 0.75

# Business-severity weights for spurious predictions (schema v2 weighted gate).
# A false positive (background treated as a nail) is the worst product outcome;
# an invalid prediction mask is unusable output; a duplicate is redundant but
# still nail-related and is the mildest defect.
SPURIOUS_WEIGHTS = {
    "duplicates": 1.0,
    "invalidPredictionMasks": 1.5,
    "falsePositives": 2.0,
}

FORMAL_CONTRACT = {
    "minimumImages": 100,
    "minimumInstanceRecall": 0.90,
    "minimumCompleteMaskRatio": 0.85,
    "maximumMissingImageRate": 0.10,
    "maximumWeightedSpuriousRate": 0.02,
}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Audit complete visible-nail recognition per image.")
    value.add_argument("--snapshot-manifest")
    value.add_argument("--materialization-report")
    value.add_argument("--artifact-index")
    value.add_argument("--weights")
    value.add_argument(
        "--runtime-selection-lock",
        help="Optional immutable composite-runtime lock; the artifact index must bind its path and SHA-256.",
    )
    value.add_argument("--score-threshold", type=float)
    value.add_argument("--output")
    value.add_argument("--verify-report")
    value.add_argument("--min-images", type=int, default=100)
    value.add_argument("--min-instance-recall", type=float, default=0.90)
    value.add_argument("--min-complete-mask-ratio", type=float, default=0.85)
    value.add_argument("--max-missing-image-rate", type=float, default=0.10)
    value.add_argument(
        "--gate-mode",
        choices=("weighted", "zero-defect"),
        default="weighted",
        help="weighted: schema v2 severity-weighted spurious-rate gate (default); "
        "zero-defect: legacy schema v1 all-zero gates for replaying historical reports",
    )
    value.add_argument(
        "--max-weighted-spurious-rate",
        type=float,
        default=0.02,
        help="weighted mode only: maximum allowed (1.0*duplicates + 1.5*invalid + "
        "2.0*falsePositives) / truthCount",
    )
    return value


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing path: {field}")
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"Missing file for {field}: {path}")
    return path


def parse_polygon_line(line: str, *, prediction: bool) -> tuple[Polygon, float, bool]:
    values = [float(value) for value in line.split()]
    minimum = 8 if prediction else 7
    if len(values) < minimum:
        raise ValueError("Segmentation label must contain a class and at least three points")
    score = values[-1] if prediction else 1.0
    coords = values[1:-1] if prediction else values[1:]
    if len(coords) < 6 or len(coords) % 2:
        raise ValueError("Segmentation polygon coordinate count is invalid")
    if prediction and (not math.isfinite(score) or score < 0 or score > 1):
        raise ValueError("Prediction score is invalid")
    polygon = Polygon(list(zip(coords[0::2], coords[1::2])))
    originally_valid = polygon.is_valid and not polygon.is_empty and polygon.area > 0
    if not originally_valid:
        if not prediction:
            raise ValueError("Ground-truth segmentation polygon is invalid")
        repaired = make_valid(polygon)
        candidates = [repaired] if isinstance(repaired, Polygon) else [
            geometry for geometry in getattr(repaired, "geoms", []) if isinstance(geometry, Polygon)
        ]
        if not candidates:
            polygon = Polygon([(2.0, 2.0), (2.000001, 2.0), (2.0, 2.000001)])
        else:
            polygon = max(candidates, key=lambda value: value.area)
    return polygon, score, originally_valid


def parse_label(path: Path, *, prediction: bool, threshold: float) -> list[tuple[Polygon, float, bool]]:
    rows: list[tuple[Polygon, float, bool]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if prediction:
            values = line.split()
            try:
                raw_score = float(values[-1])
            except (IndexError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: Prediction score is invalid") from error
            if raw_score < threshold:
                continue
        try:
            polygon, score, originally_valid = parse_polygon_line(line, prediction=prediction)
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
        rows.append((polygon, score, originally_valid))
    return rows


def polygon_iou(left: Polygon, right: Polygon) -> float:
    intersection = left.intersection(right).area
    union = left.union(right).area
    return 0.0 if union <= 0 else float(intersection / union)


def match_instances(
    truth: list[tuple[Polygon, float, bool]], predictions: list[tuple[Polygon, float, bool]]
) -> tuple[list[tuple[int, int, float]], list[int], list[int]]:
    pairs = sorted(
        (
            (polygon_iou(truth_polygon, prediction_polygon), truth_index, prediction_index)
            for truth_index, (truth_polygon, _, _) in enumerate(truth)
            for prediction_index, (prediction_polygon, _, _) in enumerate(predictions)
        ),
        reverse=True,
    )
    matched_truth: set[int] = set()
    matched_predictions: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for iou, truth_index, prediction_index in pairs:
        if iou < MATCH_IOU:
            break
        if truth_index in matched_truth or prediction_index in matched_predictions:
            continue
        matched_truth.add(truth_index)
        matched_predictions.add(prediction_index)
        matches.append((truth_index, prediction_index, iou))
    return (
        matches,
        [index for index in range(len(truth)) if index not in matched_truth],
        [index for index in range(len(predictions)) if index not in matched_predictions],
    )


def validate_lineage(
    snapshot_path: Path, materialization_path: Path, artifact_path: Path
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], Path, dict[str, Path]]:
    snapshot = load_object(snapshot_path)
    materialization = load_object(materialization_path)
    artifacts = load_object(artifact_path)
    items = snapshot.get("items")
    if (
        snapshot.get("trainingUse") != "prohibited"
        or not isinstance(items, list)
        or canonical_sha256(items) != snapshot.get("itemsSha256")
    ):
        raise ValueError("Frozen positive snapshot lineage is invalid")
    if (
        materialization.get("decision") != "evaluation_only_frozen_reviewed_snapshot"
        or materialization.get("trainingUse") != "prohibited"
        or Path(str(materialization.get("sourceFrozenManifest", ""))).resolve() != snapshot_path
        or materialization.get("sourceFrozenManifestSha256") != sha256_path(snapshot_path)
        or materialization.get("sourceItemsSha256") != snapshot.get("itemsSha256")
    ):
        raise ValueError("Evaluation materialization is not bound to the frozen snapshot")
    records = materialization.get("records")
    if not isinstance(records, list) or canonical_sha256(records) != materialization.get("recordsSha256"):
        raise ValueError("Evaluation materialization records are invalid")
    by_stem: dict[str, dict[str, Any]] = {}
    output_dir = Path(str(materialization.get("outputDir", ""))).resolve()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid materialization record")
        label = output_dir / str(record.get("materializedLabel", ""))
        if not label.is_file() or sha256_path(label) != record.get("materializedLabelSha256"):
            raise ValueError(f"Materialized truth label drift: {label}")
        stem = Path(str(record.get("materializedFileName", ""))).stem
        if stem in by_stem:
            raise ValueError(f"Duplicate materialized image stem: {stem}")
        by_stem[stem] = record
    prediction_records = artifacts.get("prediction_records")
    if (
        artifacts.get("split") != "test"
        or not isinstance(prediction_records, list)
        or canonical_sha256(prediction_records) != artifacts.get("prediction_records_sha256")
    ):
        raise ValueError("Prediction artifact index is invalid")
    artifacts_dir = Path(str(artifacts.get("artifacts_dir", ""))).resolve()
    predictions: dict[str, Path] = {}
    for record in prediction_records:
        path = artifacts_dir / str(record.get("path", ""))
        if not path.is_file() or sha256_path(path) != record.get("sha256"):
            raise ValueError(f"Prediction label drift: {path}")
        stem = str(record.get("stem", ""))
        if stem in predictions:
            raise ValueError(f"Duplicate prediction stem: {stem}")
        predictions[stem] = path
    expected_stems = set(by_stem)
    if set(predictions) != expected_stems or len(items) != len(records):
        raise ValueError("Frozen snapshot, truth labels and prediction labels do not cover the same images")
    return items, by_stem, output_dir, predictions


def validate_formal_build_contract(args: argparse.Namespace) -> None:
    """Reject any public build contract weaker than the release floor.

    Callers may tighten a gate, but cannot use CLI flags to create a formally
    accepted report with fewer images or weaker quality thresholds. Legacy
    schema-v1 reports are rebuilt only inside ``verify``.
    """
    if args.gate_mode != "weighted":
        raise ValueError("zero-defect gate mode is replay-only; new reports must use weighted mode")
    checks = (
        (args.min_images >= FORMAL_CONTRACT["minimumImages"], "min-images cannot be below 100"),
        (
            args.min_instance_recall >= FORMAL_CONTRACT["minimumInstanceRecall"],
            "min-instance-recall cannot be below 0.90",
        ),
        (
            args.min_complete_mask_ratio >= FORMAL_CONTRACT["minimumCompleteMaskRatio"],
            "min-complete-mask-ratio cannot be below 0.85",
        ),
        (
            args.max_missing_image_rate <= FORMAL_CONTRACT["maximumMissingImageRate"],
            "max-missing-image-rate cannot exceed 0.10",
        ),
        (
            args.max_weighted_spurious_rate <= FORMAL_CONTRACT["maximumWeightedSpuriousRate"],
            "max-weighted-spurious-rate cannot exceed 0.02",
        ),
    )
    for valid, message in checks:
        if not valid:
            raise ValueError(message)


def build(
    args: argparse.Namespace,
    *,
    allow_legacy_replay: bool = False,
) -> dict[str, Any]:
    if not allow_legacy_replay:
        validate_formal_build_contract(args)
    snapshot_path = require_path(args.snapshot_manifest, "snapshot-manifest")
    materialization_path = require_path(args.materialization_report, "materialization-report")
    artifact_path = require_path(args.artifact_index, "artifact-index")
    weights_path = require_path(args.weights, "weights")
    threshold = float(args.score_threshold)
    if not 0 < threshold < 1:
        raise ValueError("score-threshold must be between zero and one")
    if not 0 <= args.max_weighted_spurious_rate <= 1:
        raise ValueError("max-weighted-spurious-rate must be between zero and one")
    items, records, output_dir, predictions = validate_lineage(
        snapshot_path, materialization_path, artifact_path
    )
    runtime_lock_value = getattr(args, "runtime_selection_lock", None)
    runtime_lock_path = (
        require_path(runtime_lock_value, "runtime-selection-lock")
        if runtime_lock_value
        else None
    )
    if runtime_lock_path is not None:
        artifacts = load_object(artifact_path)
        bound_lock = Path(str(artifacts.get("runtime_selection_lock", ""))).resolve()
        if (
            bound_lock != runtime_lock_path
            or artifacts.get("runtime_selection_lock_sha256") != sha256_path(runtime_lock_path)
        ):
            raise ValueError("Prediction artifact index is not bound to the runtime selection lock")

    image_rows: list[dict[str, Any]] = []
    totals = {"truth": 0, "predictions": 0, "matched": 0, "completeMasks": 0, "missing": 0, "duplicates": 0, "falsePositives": 0, "invalidPredictionMasks": 0}
    for stem in sorted(records):
        record = records[stem]
        truth_path = output_dir / str(record["materializedLabel"])
        truth = parse_label(truth_path, prediction=False, threshold=threshold)
        predicted = parse_label(predictions[stem], prediction=True, threshold=threshold)
        matches, missing, unmatched = match_instances(truth, predicted)
        duplicates = 0
        false_positives = 0
        for prediction_index in unmatched:
            maximum_iou = max(
                (polygon_iou(truth_polygon, predicted[prediction_index][0]) for truth_polygon, _, _ in truth),
                default=0.0,
            )
            if maximum_iou >= 0.10:
                duplicates += 1
            else:
                false_positives += 1
        complete_masks = sum(1 for _, _, iou in matches if iou >= COMPLETE_MASK_IOU)
        invalid_prediction_masks = sum(1 for _, _, originally_valid in predicted if not originally_valid)
        row = {
            "stem": stem,
            "lane": record.get("lane"),
            "truthCount": len(truth),
            "predictionCount": len(predicted),
            "matchedCount": len(matches),
            "completeMaskCount": complete_masks,
            "missingCount": len(missing),
            "duplicateCount": duplicates,
            "falsePositiveCount": false_positives,
            "invalidPredictionMaskCount": invalid_prediction_masks,
            "allVisibleNailsRecognized": len(missing) == 0,
            "directlyExtractable": len(missing) == 0 and duplicates == 0 and false_positives == 0 and invalid_prediction_masks == 0 and complete_masks == len(truth),
            "matchIous": [round(iou, 6) for _, _, iou in sorted(matches)],
        }
        image_rows.append(row)
        totals["truth"] += len(truth)
        totals["predictions"] += len(predicted)
        totals["matched"] += len(matches)
        totals["completeMasks"] += complete_masks
        totals["missing"] += len(missing)
        totals["duplicates"] += duplicates
        totals["falsePositives"] += false_positives
        totals["invalidPredictionMasks"] += invalid_prediction_masks

    image_count = len(image_rows)
    missing_images = sum(1 for row in image_rows if row["missingCount"] > 0)
    directly_extractable = sum(1 for row in image_rows if row["directlyExtractable"])
    instance_recall = totals["matched"] / totals["truth"] if totals["truth"] else 0.0
    complete_mask_ratio = totals["completeMasks"] / totals["truth"] if totals["truth"] else 0.0
    missing_image_rate = missing_images / image_count if image_count else 1.0
    direct_rate = directly_extractable / image_count if image_count else 0.0
    weighted_spurious = (
        SPURIOUS_WEIGHTS["duplicates"] * totals["duplicates"]
        + SPURIOUS_WEIGHTS["invalidPredictionMasks"] * totals["invalidPredictionMasks"]
        + SPURIOUS_WEIGHTS["falsePositives"] * totals["falsePositives"]
    )
    weighted_spurious_rate = weighted_spurious / totals["truth"] if totals["truth"] else 0.0
    structural_gates = {
        "minimumImages": image_count >= args.min_images,
        "instanceRecall": instance_recall >= args.min_instance_recall,
        "completeMaskRatio": complete_mask_ratio >= args.min_complete_mask_ratio,
        "missingImageRate": missing_image_rate <= args.max_missing_image_rate,
    }
    every_image_has_output = all(row["predictionCount"] > 0 for row in image_rows)
    base_summary = {
        "images": image_count,
        **totals,
        "missingImages": missing_images,
        "directlyExtractableImages": directly_extractable,
        "instanceRecall": round(instance_recall, 8),
        "completeMaskRatio": round(complete_mask_ratio, 8),
        "missingImageRate": round(missing_image_rate, 8),
        "directlyExtractableRate": round(direct_rate, 8),
    }
    base_contract = {
        "imgsz": 512,
        "scoreThreshold": threshold,
        "matchIou": MATCH_IOU,
        "completeMaskIou": COMPLETE_MASK_IOU,
        "minimumImages": args.min_images,
        "minimumInstanceRecall": args.min_instance_recall,
        "minimumCompleteMaskRatio": args.min_complete_mask_ratio,
        "maximumMissingImageRate": args.max_missing_image_rate,
    }
    if args.gate_mode == "weighted":
        gates = {
            **structural_gates,
            "weightedSpuriousRate": weighted_spurious_rate <= args.max_weighted_spurious_rate,
            "everyImageHasModelOutput": every_image_has_output,
        }
        schema_version = 2
        contract = {
            **base_contract,
            "maximumWeightedSpuriousRate": args.max_weighted_spurious_rate,
            "spuriousWeights": dict(SPURIOUS_WEIGHTS),
        }
        summary = {
            **base_summary,
            "weightedSpuriousInstances": round(weighted_spurious, 8),
            "weightedSpuriousRate": round(weighted_spurious_rate, 8),
        }
        diagnostics = {
            "zeroDefectDiagnostics": {
                "zeroDuplicates": totals["duplicates"] == 0,
                "zeroFalsePositives": totals["falsePositives"] == 0,
                "zeroInvalidPredictionMasks": totals["invalidPredictionMasks"] == 0,
            },
        }
    else:
        gates = {
            **structural_gates,
            "zeroDuplicates": totals["duplicates"] == 0,
            "zeroFalsePositives": totals["falsePositives"] == 0,
            "zeroInvalidPredictionMasks": totals["invalidPredictionMasks"] == 0,
            "everyImageHasModelOutput": every_image_has_output,
        }
        schema_version = 1
        contract = {
            **base_contract,
            "zeroDuplicates": True,
            "zeroFalsePositives": True,
        }
        summary = dict(base_summary)
        diagnostics = {}
    ok = all(gates.values())
    candidate = {"weights": str(weights_path), "weightsSha256": sha256_path(weights_path)}
    if runtime_lock_path is not None:
        candidate.update(
            {
                "runtimeSelectionLock": str(runtime_lock_path),
                "runtimeSelectionLockSha256": sha256_path(runtime_lock_path),
            }
        )
        contract.update(
            {
                "selectionMode": "locked-composite-runtime",
                "scoreThresholdMeaning": "minimum emitted stage1 confidence after locked composite selection",
            }
        )
    return {
        "schemaVersion": schema_version,
        "ok": ok,
        "decision": "accept_positive_recognition_gate" if ok else "hold_positive_recognition_gate",
        "trainingUse": "prohibited",
        "deploymentContract": contract,
        "candidate": candidate,
        "summary": summary,
        "gates": gates,
        **diagnostics,
        "itemsSha256": canonical_sha256(image_rows),
        "items": image_rows,
        "inputs": {
            "snapshotManifest": str(snapshot_path),
            "snapshotManifestSha256": sha256_path(snapshot_path),
            "materializationReport": str(materialization_path),
            "materializationReportSha256": sha256_path(materialization_path),
            "artifactIndex": str(artifact_path),
            "artifactIndexSha256": sha256_path(artifact_path),
        },
    }


def verify(report_path: Path) -> dict[str, Any]:
    report = load_object(report_path)
    inputs = report.get("inputs")
    contract = report.get("deploymentContract")
    candidate = report.get("candidate")
    if not isinstance(inputs, dict) or not isinstance(contract, dict) or not isinstance(candidate, dict):
        raise ValueError("Recognition report is missing replay inputs")
    for field in ("snapshotManifest", "materializationReport", "artifactIndex"):
        path = require_path(inputs.get(field), field)
        if sha256_path(path) != inputs.get(f"{field}Sha256"):
            raise ValueError(f"Recognition report input drift: {field}")
    weights = require_path(candidate.get("weights"), "weights")
    if sha256_path(weights) != candidate.get("weightsSha256"):
        raise ValueError("Recognition report weights drift")
    runtime_lock = candidate.get("runtimeSelectionLock")
    runtime_lock_path = None
    if runtime_lock is not None:
        runtime_lock_path = require_path(runtime_lock, "runtimeSelectionLock")
        if sha256_path(runtime_lock_path) != candidate.get("runtimeSelectionLockSha256"):
            raise ValueError("Recognition report runtime selection lock drift")
    schema_version = report.get("schemaVersion")
    if schema_version == 2:
        gate_mode = "weighted"
        max_weighted_spurious_rate = float(contract["maximumWeightedSpuriousRate"])
        allow_legacy_replay = False
    elif schema_version == 1:
        gate_mode = "zero-defect"
        max_weighted_spurious_rate = FORMAL_CONTRACT["maximumWeightedSpuriousRate"]
        allow_legacy_replay = True
    else:
        raise ValueError(f"Unsupported recognition report schema version: {schema_version}")
    replay_args = argparse.Namespace(
        snapshot_manifest=str(inputs["snapshotManifest"]),
        materialization_report=str(inputs["materializationReport"]),
        artifact_index=str(inputs["artifactIndex"]),
        weights=str(weights),
        runtime_selection_lock=str(runtime_lock_path) if runtime_lock_path else None,
        score_threshold=float(contract["scoreThreshold"]),
        output=None,
        verify_report=None,
        min_images=int(contract["minimumImages"]),
        min_instance_recall=float(contract["minimumInstanceRecall"]),
        min_complete_mask_ratio=float(contract["minimumCompleteMaskRatio"]),
        max_missing_image_rate=float(contract["maximumMissingImageRate"]),
        gate_mode=gate_mode,
        max_weighted_spurious_rate=max_weighted_spurious_rate,
    )
    rebuilt = build(replay_args, allow_legacy_replay=allow_legacy_replay)
    if rebuilt != report:
        raise ValueError("Recognition report does not match replayed evidence")
    return report


def main() -> int:
    args = parser().parse_args()
    try:
        if args.verify_report:
            report = verify(require_path(args.verify_report, "verify-report"))
        else:
            required = (args.snapshot_manifest, args.materialization_report, args.artifact_index, args.weights, args.score_threshold, args.output)
            if any(value is None for value in required):
                raise ValueError("Build mode requires all inputs and --output")
            report = build(args)
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "decision": report["decision"], "summary": report["summary"]}, ensure_ascii=False))
        return 0 if report["ok"] else 1
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
