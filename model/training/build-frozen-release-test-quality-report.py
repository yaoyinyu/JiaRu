#!/usr/bin/env python3
"""Build a lineage-checked quality decision for a frozen release-test snapshot.

The snapshot population is intentionally derived from reviewed evidence rather
than fixed to the first 67-image release set.  The deployment contract remains
fixed at 512 pixels and every full/core/stress candidate must satisfy the same
absolute and regression gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEPLOYMENT_IMAGE_SIZE = 512
MIN_REVIEWED_IMAGES = 67
REQUIRED_LANES = ("core", "stress")
MATERIALIZATION_V2_INVARIANTS = {
    "sourceFrozenManifestHashBound",
    "sourceItemsHashRecomputed",
    "sourceFilesHashRecomputed",
    "materializedImagesMatchFrozenManifest",
    "materializedLabelsHashBound",
    "fixedEvaluationOnlySplit",
    "testSplitNonEmpty",
    "trainSplitEmpty",
    "validationSplitEmpty",
    "coreStressNestedLayout",
    "validPolygons",
    "pairwiseZeroOverlap",
    "trainingIdentityIsolationRecomputed",
    "transactionalMaterialization",
    "targetsNotReused",
    "noOrphans",
}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build a frozen release-test quality report.")
    value.add_argument("--snapshot-manifest")
    value.add_argument("--materialization-report")
    value.add_argument("--baseline-metrics")
    value.add_argument("--full-512")
    value.add_argument("--full-640")
    value.add_argument("--core-512")
    value.add_argument("--stress-512")
    value.add_argument("--assessment")
    value.add_argument("--output")
    value.add_argument("--verify-report")
    value.add_argument("--min-box-map50", type=float, default=0.85)
    value.add_argument("--min-mask-map50", type=float, default=0.75)
    value.add_argument("--max-regression", type=float, default=0.02)
    return value


BUILD_ARGUMENTS = (
    "snapshot_manifest",
    "materialization_report",
    "baseline_metrics",
    "full_512",
    "full_640",
    "core_512",
    "stress_512",
    "assessment",
)


BUILD_FLAGS = {
    "snapshot_manifest": "--snapshot-manifest",
    "materialization_report": "--materialization-report",
    "baseline_metrics": "--baseline-metrics",
    "full_512": "--full-512",
    "full_640": "--full-640",
    "core_512": "--core-512",
    "stress_512": "--stress-512",
    "assessment": "--assessment",
}


def load(path: Path) -> dict[str, Any]:
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


def require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid integer {field}: {value!r}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid integer {field}: {value!r}") from error
    if parsed < minimum or parsed != value:
        raise ValueError(f"Invalid integer {field}: {value!r}")
    return parsed


def require_metric(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid metric {field}: {value!r}") from error
    if not math.isfinite(parsed) or parsed < 0.0 or parsed > 1.0:
        raise ValueError(f"Invalid metric {field}: {value!r}")
    return parsed


def same_number(left: Any, right: float) -> bool:
    try:
        return math.isclose(float(left), right, rel_tol=0.0, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False


def same_path(left: Any, right: Path) -> bool:
    if not str(left or "").strip():
        return False
    return Path(str(left)).resolve() == right.resolve()


def snapshot_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    items = snapshot.get("items")
    if (
        snapshot.get("decision") != "frozen_reviewed_candidate_not_release_ready"
        or snapshot.get("trainingUse") != "prohibited"
        or not isinstance(items, list)
        or canonical_sha256(items) != snapshot.get("itemsSha256")
    ):
        raise ValueError("Frozen snapshot lineage is invalid")

    counts = snapshot.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("Frozen snapshot counts are missing")
    image_count = require_int(counts.get("images"), "snapshot.counts.images", minimum=1)
    mask_count = require_int(counts.get("masks"), "snapshot.counts.masks", minimum=1)
    core_count = require_int(counts.get("coreImages"), "snapshot.counts.coreImages", minimum=1)
    stress_count = require_int(counts.get("stressImages"), "snapshot.counts.stressImages", minimum=1)
    parent_count = require_int(
        counts.get("parentSourceGroups"),
        "snapshot.counts.parentSourceGroups",
        minimum=1,
    )
    if image_count < MIN_REVIEWED_IMAGES:
        raise ValueError(f"Frozen snapshot has fewer than {MIN_REVIEWED_IMAGES} reviewed images")
    if image_count != len(items) or image_count != core_count + stress_count:
        raise ValueError("Frozen snapshot image/lane counts drifted")

    lane_counts = {lane: 0 for lane in REQUIRED_LANES}
    seen_files: set[str] = set()
    parent_groups: set[str] = set()
    observed_masks = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Frozen snapshot item {index} is not an object")
        lane = str(item.get("lane") or "")
        if lane not in lane_counts:
            raise ValueError(f"Frozen snapshot item {index} has an invalid lane")
        file_name = str(item.get("fileName") or "")
        parent_group = str(item.get("parentSourceGroup") or "")
        if not file_name or file_name in seen_files or not parent_group:
            raise ValueError(f"Frozen snapshot item {index} identity is invalid")
        seen_files.add(file_name)
        parent_groups.add(parent_group)
        lane_counts[lane] += 1
        observed_masks += require_int(item.get("maskCount"), f"snapshot.items[{index}].maskCount", minimum=1)
        if item.get("trainingUse") != "prohibited":
            raise ValueError(f"Frozen snapshot item {index} is not training-prohibited")
    if lane_counts != {"core": core_count, "stress": stress_count}:
        raise ValueError("Frozen snapshot lane counts differ from items")
    if observed_masks != mask_count or len(parent_groups) != parent_count:
        raise ValueError("Frozen snapshot mask or parent-source count drifted")

    source_isolation = snapshot.get("sourceIsolation")
    if isinstance(source_isolation, dict):
        if source_isolation.get("ok") is not True:
            raise ValueError("Frozen snapshot source isolation is not approved")
        overlap_fields = [key for key in source_isolation if key.endswith("Overlap")]
        if not overlap_fields or any(source_isolation.get(key) != 0 for key in overlap_fields):
            raise ValueError("Frozen snapshot source isolation evidence drifted")

    representative_gate = snapshot.get("representativeReleaseGate")
    representative_required = 100
    representative_passed = image_count >= representative_required
    if representative_gate is not None:
        if not isinstance(representative_gate, dict):
            raise ValueError("Frozen snapshot representative release gate is invalid")
        actual = require_int(representative_gate.get("actual"), "representativeReleaseGate.actual")
        required = require_int(
            representative_gate.get("required"),
            "representativeReleaseGate.required",
            minimum=1,
        )
        expected_shortfall = max(0, required - image_count)
        representative_required = required
        representative_passed = image_count >= required
        if (
            actual != image_count
            or representative_gate.get("ok") is not (image_count >= required)
            or require_int(representative_gate.get("shortfall"), "representativeReleaseGate.shortfall")
            != expected_shortfall
        ):
            raise ValueError("Frozen snapshot representative release gate drifted")

    return {
        "images": image_count,
        "masks": mask_count,
        "coreImages": core_count,
        "stressImages": stress_count,
        "parentSourceGroups": parent_count,
        "representativeRequired": representative_required,
        "representativeGatePassed": representative_passed,
    }


def materialization_evidence(
    report: dict[str, Any], snapshot_path: Path, snapshot: dict[str, Any], expected: dict[str, Any]
) -> str:
    counts = report.get("counts")
    isolation = report.get("sourceIsolation")
    if (
        report.get("ok") is not True
        or report.get("trainingUse") != "prohibited"
        or not isinstance(counts, dict)
        or not isinstance(isolation, dict)
    ):
        raise ValueError("Evaluation materialization or source isolation is invalid")
    for key in ("images", "masks", "parentSourceGroups"):
        if require_int(counts.get(key), f"materialization.counts.{key}") != expected[key]:
            raise ValueError("Evaluation materialization counts drifted")
    for key in ("coreImages", "stressImages"):
        if key in counts and require_int(counts.get(key), f"materialization.counts.{key}") != expected[key]:
            raise ValueError("Evaluation materialization lane counts drifted")
    for key, expected_value in (("trainImages", 0), ("validationImages", 0), ("testImages", expected["images"])):
        if key in counts and require_int(counts.get(key), f"materialization.counts.{key}") != expected_value:
            raise ValueError("Evaluation materialization split counts drifted")

    legacy = report.get("schemaVersion") is None
    required_overlap_fields = (
        ("parentSourceGroupOverlap", "exactImageHashOverlap")
        if legacy
        else ("sourceGroupOverlap", "parentSourceGroupOverlap", "exactImageHashOverlap", "fileNameOverlap")
    )
    if any(isolation.get(key) != [] for key in required_overlap_fields):
        raise ValueError("Evaluation materialization source isolation drifted")
    output_dir = str(report.get("outputDir") or "").strip()
    if not output_dir:
        raise ValueError("Evaluation materialization outputDir is missing")

    if not legacy:
        if (
            require_int(report.get("schemaVersion"), "materialization.schemaVersion", minimum=2) < 2
            or report.get("status") != "PASS"
            or report.get("decision") != "evaluation_only_frozen_reviewed_snapshot"
            or report.get("errors") != []
        ):
            raise ValueError("Evaluation materialization approval evidence drifted")
        snapshot_sha256 = sha256_path(snapshot_path)
        source_input = (report.get("inputs") or {}).get("sourceFrozenManifest")
        if not isinstance(source_input, dict):
            raise ValueError("Evaluation materialization snapshot input binding is missing")
        if (
            not same_path(report.get("sourceFrozenManifest"), snapshot_path)
            or report.get("sourceFrozenManifestSha256") != snapshot_sha256
            or report.get("sourceItemsSha256") != snapshot.get("itemsSha256")
            or not same_path(source_input.get("path"), snapshot_path)
            or source_input.get("sha256") != snapshot_sha256
            or source_input.get("itemsSha256") != snapshot.get("itemsSha256")
        ):
            raise ValueError("Evaluation materialization snapshot binding drifted")
        invariants = report.get("invariants")
        if not isinstance(invariants, dict) or any(invariants.get(key) is not True for key in MATERIALIZATION_V2_INVARIANTS):
            raise ValueError("Evaluation materialization invariant evidence drifted")
        records = report.get("records")
        if (
            not isinstance(records, list)
            or len(records) != expected["images"]
            or canonical_sha256(records) != report.get("recordsSha256")
        ):
            raise ValueError("Evaluation materialization record evidence drifted")
        snapshot_by_file = {str(item["fileName"]): item for item in snapshot["items"]}
        materialized_source_files: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Evaluation materialization record is invalid")
            source_item = snapshot_by_file.get(str(record.get("sourceFileName") or ""))
            source_file_name = str(record.get("sourceFileName") or "")
            if source_file_name in materialized_source_files:
                raise ValueError("Evaluation materialization contains duplicate source records")
            materialized_source_files.add(source_file_name)
            if source_item is None or any(
                record.get(record_key) != source_item.get(item_key)
                for record_key, item_key in (
                    ("lane", "lane"),
                    ("sourceGroup", "sourceGroup"),
                    ("parentSourceGroup", "parentSourceGroup"),
                    ("maskCount", "maskCount"),
                    ("sourceImageSha256", "imageSha256"),
                    ("sourceAnnotationSha256", "annotationSha256"),
                )
            ):
                raise ValueError("Evaluation materialization records differ from frozen items")
        if materialized_source_files != set(snapshot_by_file):
            raise ValueError("Evaluation materialization record coverage drifted")
        file_records = report.get("file_records")
        dataset_files = report.get("datasetFiles")
        if (
            not isinstance(file_records, list)
            or len(file_records) != expected["images"] * 2 + 4
            or len({str(item.get("path") or "") for item in file_records if isinstance(item, dict)})
            != len(file_records)
            or file_records != dataset_files
            or canonical_sha256(file_records) != report.get("files_sha256")
            or report.get("datasetFilesSha256") != report.get("files_sha256")
        ):
            raise ValueError("Evaluation materialization file inventory evidence drifted")

    return str(Path(output_dir).resolve())


def evaluation_artifact(path: Path, document: dict[str, Any]) -> tuple[Path, int]:
    artifact = document.get("evaluation_artifacts") or {}
    index_path = Path(str(artifact.get("index") or ""))
    if not index_path.is_absolute():
        index_path = path.parent / index_path
    index_path = index_path.resolve()
    if not index_path.is_file():
        raise FileNotFoundError(f"Evaluation artifact index is missing: {index_path}")
    index = load(index_path)
    prediction_count = require_int((index.get("counts") or {}).get("prediction_labels"), "prediction_labels", minimum=1)
    if index.get("split") != "test":
        raise ValueError(f"Evaluation artifact index does not describe test: {path}")
    embedded_count = (artifact.get("counts") or {}).get("prediction_labels")
    if embedded_count is not None and require_int(embedded_count, "evaluation_artifacts.prediction_labels") != prediction_count:
        raise ValueError(f"Evaluation artifact count drifted: {path}")
    return index_path, prediction_count


def resolved_weights(path: Path, document: dict[str, Any]) -> Path:
    value = str(document.get("weights") or "").strip()
    if not value:
        raise ValueError(f"Evaluation weights identity is missing: {path}")
    weights = Path(value)
    if not weights.is_absolute():
        weights = path.parent / weights
    weights = weights.resolve()
    if not weights.is_file():
        raise FileNotFoundError(f"Evaluation weights are missing: {weights}")
    return weights


def metrics(path: Path, expected_size: int, expected_images: int) -> dict[str, Any]:
    document = load(path)
    if document.get("split") != "test" or require_int(document.get("imgsz"), f"{path}.imgsz") != expected_size:
        raise ValueError(f"Unexpected evaluation split or image size: {path}")
    index_path, prediction_count = evaluation_artifact(path, document)
    if prediction_count != expected_images:
        raise ValueError(f"Evaluation artifacts do not cover {expected_images} test images: {path}")
    weights = resolved_weights(path, document)
    return {
        "path": str(path),
        "imgsz": expected_size,
        "boxMap50": require_metric(document.get("box_map50"), f"{path}.box_map50"),
        "maskMap50": require_metric(document.get("seg_map50"), f"{path}.seg_map50"),
        "boxMap50To95": require_metric(document.get("box_map"), f"{path}.box_map"),
        "maskMap50To95": require_metric(document.get("seg_map"), f"{path}.seg_map"),
        "datasetRoot": str(document.get("dataset_root") or ""),
        "artifactIndex": str(index_path),
        "predictionLabels": prediction_count,
        "weights": str(weights),
    }


def baseline_metrics(path: Path) -> dict[str, Any]:
    document = load(path)
    if (
        document.get("split") != "test"
        or require_int(document.get("imgsz"), f"{path}.imgsz") != DEPLOYMENT_IMAGE_SIZE
    ):
        raise ValueError("Historical baseline is not a deployment-512 test evaluation")
    index_path, prediction_count = evaluation_artifact(path, document)
    weights = resolved_weights(path, document)
    return {
        "path": str(path),
        "images": prediction_count,
        "boxMap50": require_metric(document.get("box_map50"), "baseline.box_map50"),
        "maskMap50": require_metric(document.get("seg_map50"), "baseline.seg_map50"),
        "datasetRoot": str(document.get("dataset_root") or ""),
        "artifactIndex": str(index_path),
        "weights": str(weights),
    }


def protect_output_path(paths: dict[str, Path]) -> None:
    output = paths["output"]
    for name, input_path in paths.items():
        if name == "output":
            continue
        if output == input_path:
            raise ValueError(f"Output must not overwrite input {name}")
        if output.exists() and input_path.exists():
            try:
                if output.samefile(input_path):
                    raise ValueError(f"Output hard-link alias must not overwrite input {name}")
            except OSError as error:
                raise ValueError(f"Cannot verify output identity against input {name}: {error}") from error


def gate_errors(values: dict[str, Any], baseline: dict[str, Any], args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    box_drop = baseline["boxMap50"] - values["boxMap50"]
    mask_drop = baseline["maskMap50"] - values["maskMap50"]
    if values["boxMap50"] < args.min_box_map50:
        errors.append(f"box mAP50 {values['boxMap50']:.6f} is below {args.min_box_map50:.6f}")
    if values["maskMap50"] < args.min_mask_map50:
        errors.append(f"mask mAP50 {values['maskMap50']:.6f} is below {args.min_mask_map50:.6f}")
    if box_drop > args.max_regression:
        errors.append(f"box mAP50 drop {box_drop:.6f} exceeds {args.max_regression:.6f}")
    if mask_drop > args.max_regression:
        errors.append(f"mask mAP50 drop {mask_drop:.6f} exceeds {args.max_regression:.6f}")
    return errors


def validate_assessment(
    assessment: dict[str, Any], paths: dict[str, Path], evaluations: dict[str, dict[str, Any]],
    baseline: dict[str, Any], expected: dict[str, Any], args: argparse.Namespace,
) -> dict[str, bool]:
    expected_candidates = {
        f"release{expected['images']}": (paths["full_512"], evaluations["full512"]),
        f"core{expected['coreImages']}": (paths["core_512"], evaluations["core512"]),
        f"stress{expected['stressImages']}": (paths["stress_512"], evaluations["stress512"]),
    }
    candidates = assessment.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != len(expected_candidates):
        raise ValueError("Metric assessment candidate count drifted")
    labels = [item.get("label") for item in candidates if isinstance(item, dict)]
    if len(labels) != len(candidates) or len(set(labels)) != len(labels) or set(labels) != set(expected_candidates):
        raise ValueError("Metric assessment labels do not match the frozen snapshot")
    thresholds = assessment.get("thresholds") or {}
    if not (
        same_number(thresholds.get("maxBoxMap50Drop"), args.max_regression)
        and same_number(thresholds.get("maxMaskMap50Drop"), args.max_regression)
        and same_number(thresholds.get("minBoxMap50"), args.min_box_map50)
        and same_number(thresholds.get("minMaskMap50"), args.min_mask_map50)
    ):
        raise ValueError("Metric assessment thresholds differ from the deployment contract")
    assessed_baseline = assessment.get("baseline") or {}
    assessed_baseline_metrics = assessed_baseline.get("metrics") or {}
    if (
        not same_path(assessed_baseline.get("metricsPath"), paths["baseline_metrics"])
        or not same_number(assessed_baseline_metrics.get("boxMap50"), baseline["boxMap50"])
        or not same_number(assessed_baseline_metrics.get("maskMap50"), baseline["maskMap50"])
    ):
        raise ValueError("Metric assessment baseline evidence drifted")

    passed: dict[str, bool] = {}
    for candidate in candidates:
        label = str(candidate["label"])
        metric_path, values = expected_candidates[label]
        assessed_metrics = candidate.get("metrics") or {}
        metric_match = all(
            same_number(assessed_metrics.get(key), values[key])
            for key in ("boxMap50", "maskMap50", "boxMap50To95", "maskMap50To95")
        )
        expected_pass = not gate_errors(values, baseline, args)
        if (
            not same_path(candidate.get("metricsPath"), metric_path)
            or not metric_match
            or candidate.get("qualityGatePassed") is not expected_pass
        ):
            raise ValueError(f"Metric assessment evidence drifted for {label}")
        passed[label] = expected_pass
    if assessment.get("ok") is not all(passed.values()):
        raise ValueError("Metric assessment aggregate decision drifted")
    return passed


def protect_report_path(report_path: Path, input_paths: dict[str, Path]) -> None:
    for name, input_path in input_paths.items():
        if report_path == input_path:
            raise ValueError(f"Quality report must not overwrite input {name}")
        if report_path.exists() and input_path.exists():
            try:
                if report_path.samefile(input_path):
                    raise ValueError(f"Quality report hard-link alias must not replace input {name}")
            except OSError as error:
                raise ValueError(f"Cannot verify quality report identity against input {name}: {error}") from error


def verify_report(report_path: Path) -> dict[str, Any]:
    report = load(report_path)
    if report.get("schemaVersion") != 2:
        raise ValueError("Frozen release-test quality report schemaVersion must be 2")
    if report.get("ok") is not True or report.get("trainingUse") != "prohibited":
        raise ValueError("Frozen release-test quality report outer contract is invalid")
    if report.get("decision") not in {
        "accept_candidate_release",
        "reject_candidate_release_at_deployment_resolution",
    } or not isinstance(report.get("qualityGatePassed"), bool):
        raise ValueError("Frozen release-test quality report decision contract is invalid")

    contract = report.get("deploymentContract")
    if not isinstance(contract, dict) or not (
        contract.get("imgsz") == DEPLOYMENT_IMAGE_SIZE
        and same_number(contract.get("minimumBoxMap50"), 0.85)
        and same_number(contract.get("minimumMaskMap50"), 0.75)
        and same_number(contract.get("maximumRegression"), 0.02)
        and contract.get("allSubsetsMustPass") is True
    ):
        raise ValueError("Frozen release-test quality report deployment contract is not the formal default")

    raw_inputs = report.get("inputs")
    if not isinstance(raw_inputs, dict) or set(raw_inputs) != set(BUILD_ARGUMENTS):
        raise ValueError("Frozen release-test quality report input set is incomplete")
    input_paths: dict[str, Path] = {}
    for name in BUILD_ARGUMENTS:
        value = raw_inputs.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Frozen release-test quality report input is missing: {name}")
        input_paths[name] = Path(value).resolve()
    protect_report_path(report_path, input_paths)

    with tempfile.TemporaryDirectory(prefix="nail-frozen-quality-verify-") as temp_dir:
        replay_path = Path(temp_dir) / "replayed-quality.json"
        command = [sys.executable, str(Path(__file__).resolve())]
        for name in BUILD_ARGUMENTS:
            command.extend((BUILD_FLAGS[name], str(input_paths[name])))
        command.extend(("--output", str(replay_path)))
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise ValueError(f"Frozen release-test quality evidence replay failed: {detail}")
        replay = load(replay_path)
    if replay != report:
        raise ValueError("Frozen release-test quality report differs from the deep replay result")
    return {
        "ok": True,
        "decision": report["decision"],
        "qualityGatePassed": report["qualityGatePassed"],
        "reportPath": str(report_path),
        "reportSha256": sha256_path(report_path),
        "snapshotManifest": str(input_paths["snapshot_manifest"]),
        "inputPaths": {name: str(value) for name, value in input_paths.items()},
    }


def main() -> None:
    args = parser().parse_args()
    if args.verify_report:
        if any(getattr(args, name) is not None for name in (*BUILD_ARGUMENTS, "output")):
            raise ValueError("--verify-report cannot be combined with build inputs or --output")
        result = verify_report(Path(args.verify_report).resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    missing = [name for name in (*BUILD_ARGUMENTS, "output") if getattr(args, name) is None]
    if missing:
        raise ValueError(f"Missing required build arguments: {', '.join(missing)}")
    paths = {name: Path(getattr(args, name)).resolve() for name in (
        "snapshot_manifest", "materialization_report", "baseline_metrics", "full_512",
        "full_640", "core_512", "stress_512", "assessment", "output",
    )}
    protect_output_path(paths)
    snapshot = load(paths["snapshot_manifest"])
    expected = snapshot_evidence(snapshot)
    materialization = load(paths["materialization_report"])
    expected_root = materialization_evidence(
        materialization, paths["snapshot_manifest"], snapshot, expected
    )

    baseline_values = baseline_metrics(paths["baseline_metrics"])
    evaluations = {
        "full512": metrics(paths["full_512"], DEPLOYMENT_IMAGE_SIZE, expected["images"]),
        "full640Diagnostic": metrics(paths["full_640"], 640, expected["images"]),
        "core512": metrics(paths["core_512"], DEPLOYMENT_IMAGE_SIZE, expected["coreImages"]),
        "stress512": metrics(paths["stress_512"], DEPLOYMENT_IMAGE_SIZE, expected["stressImages"]),
    }
    if any(not same_path(item["datasetRoot"], Path(expected_root)) for item in evaluations.values()):
        raise ValueError("Evaluation metrics do not point to the materialized frozen snapshot")
    evidence_weights = Path(baseline_values["weights"])
    if any(not same_path(item["weights"], evidence_weights) for item in evaluations.values()):
        raise ValueError("Baseline and frozen evaluations do not use the same candidate weights")

    assessment = load(paths["assessment"])
    assessment_passed = validate_assessment(
        assessment, paths, evaluations, baseline_values, expected, args
    )
    group_labels = {
        "full": f"release{expected['images']}",
        "core": f"core{expected['coreImages']}",
        "stress": f"stress{expected['stressImages']}",
    }
    errors: list[str] = []
    if expected["representativeGatePassed"] is not True:
        errors.append(
            f"representative release-test scale {expected['images']}/{expected['representativeRequired']} is incomplete"
        )
    for group, evaluation_key in (("full", "full512"), ("core", "core512"), ("stress", "stress512")):
        for error in gate_errors(evaluations[evaluation_key], baseline_values, args):
            errors.append(f"{group_labels[group]}: {error}")

    quality_passed = not errors and all(assessment_passed.values())
    full = evaluations["full512"]
    box_drop = baseline_values["boxMap50"] - full["boxMap50"]
    mask_drop = baseline_values["maskMap50"] - full["maskMap50"]
    next_actions = [
        "Keep the production manifest unchanged unless this report and all downstream release gates pass.",
        "Use the frozen snapshot only for evaluation; never add its images or labels to training.",
        "Prioritize training-authorized examples for failed domains and reevaluate at 512 pixels.",
    ]
    if expected["images"] < 100:
        next_actions.append("Expand the frozen source-isolated release test from 67 to at least 100 images.")
    else:
        next_actions.append("Keep the 100-image representative snapshot frozen for subsequent candidate comparison.")

    report = {
        "schemaVersion": 2,
        "ok": True,
        "decision": "accept_candidate_release" if quality_passed else "reject_candidate_release_at_deployment_resolution",
        "qualityGatePassed": quality_passed,
        "trainingUse": "prohibited",
        "snapshot": {
            "id": snapshot.get("snapshotId"),
            "itemsSha256": snapshot.get("itemsSha256"),
            "counts": {key: expected[key] for key in ("images", "masks", "coreImages", "stressImages")},
            "parentSourceGroups": expected["parentSourceGroups"],
            "sourceIsolationPassed": True,
        },
        "deploymentContract": {
            "imgsz": DEPLOYMENT_IMAGE_SIZE,
            "minimumBoxMap50": args.min_box_map50,
            "minimumMaskMap50": args.min_mask_map50,
            "maximumRegression": args.max_regression,
            "requiredAssessmentLabels": list(group_labels.values()),
            "allSubsetsMustPass": True,
        },
        "candidateEvidence": {
            "weights": str(evidence_weights),
            "weightsSha256": sha256_path(evidence_weights),
            "sameWeightsAcrossBaselineAndFrozenEvaluations": True,
        },
        "historicalBaseline": baseline_values,
        "evaluations": evaluations,
        "deploymentDeltaFromHistoricalBaseline": {
            "baselineImages": baseline_values["images"],
            "boxMap50": -box_drop,
            "maskMap50": -mask_drop,
        },
        "assessmentPassed": assessment_passed,
        "errors": errors,
        "diagnosticConclusion": {
            "core": "quality_gate_pass" if assessment_passed[group_labels["core"]] else "quality_gate_failed",
            "stress": "quality_gate_pass" if assessment_passed[group_labels["stress"]] else "quality_gate_failed",
            "full640": "diagnostic_only_not_the_512_deployment_contract",
        },
        "nextActions": next_actions,
        "inputs": {key: str(value) for key, value in paths.items() if key != "output"},
    }
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    paths["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
