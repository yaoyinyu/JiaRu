from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
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


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_validation_finalizer() -> ModuleType:
    script = Path(__file__).with_name("finalize-validation-materialization-audit.py")
    spec = importlib.util.spec_from_file_location(
        "validation_materialization_finalizer_for_calibration", script
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"validation finalizer cannot be loaded: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protect_direct_output(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    direct_inputs = {
        Path(value).resolve()
        for value in (
            args.dataset,
            args.dataset_report,
            args.metrics,
            args.truth_audit,
        )
        if value
    }
    if output in direct_inputs:
        raise ValueError("output must not overwrite a calibration input")


def resolve_truth_audit(
    raw_path: str | None,
    dataset_yaml: Path,
    truth_paths: list[Path],
) -> dict[str, Any]:
    if not raw_path:
        return {"status": "unreviewed", "path": None, "sha256": None, "decision": None}
    path = Path(raw_path).resolve()
    audit = read_json(path)
    decision = audit.get("decision")
    if decision == "rejected_as_calibration_truth":
        if audit.get("calibrationTruthEligible") is not False:
            raise ValueError("rejected truth audit must set calibrationTruthEligible=false")
        return {
            "status": "rejected",
            "path": path,
            "sha256": sha256(path),
            "decision": decision,
        }
    if decision != "approved_as_calibration_truth":
        raise ValueError("truth audit decision is not approved_as_calibration_truth or rejected_as_calibration_truth")
    if audit.get("ok") is not True or audit.get("calibrationTruthEligible") is not True:
        raise ValueError("approved truth audit must be ok and calibrationTruthEligible")
    inputs = audit.get("inputs", {})
    if inputs.get("split") != "val":
        raise ValueError("truth audit must be restricted to split=val")
    if Path(str(inputs.get("datasetYaml", ""))).resolve() != dataset_yaml:
        raise ValueError("truth audit dataset path does not match calibration dataset")
    if inputs.get("datasetYamlSha256") != sha256(dataset_yaml):
        raise ValueError("truth audit dataset hash does not match current input")
    counts = audit.get("counts", {})
    expected = len(truth_paths)
    if (
        int(counts.get("expectedImages", -1)) != expected
        or int(counts.get("reviewedImages", -1)) != expected
        or int(counts.get("pass", -1)) != expected
        or int(counts.get("rework", -1)) != 0
        or int(counts.get("exclude", -1)) != 0
    ):
        raise ValueError("truth audit does not prove all validation images passed review")
    label_hashes = audit.get("labelSha256")
    if not isinstance(label_hashes, dict) or set(label_hashes) != {item.name for item in truth_paths}:
        raise ValueError("truth audit label hash coverage does not match validation labels")
    for truth_path in truth_paths:
        if label_hashes.get(truth_path.name) != sha256(truth_path):
            raise ValueError(f"truth audit label hash drift: {truth_path.name}")
    return {
        "status": "approved",
        "path": path,
        "sha256": sha256(path),
        "decision": decision,
    }


def resolve_canonical_truth_audit(
    raw_path: str | None,
    dataset_yaml: Path,
    dataset_report_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if not raw_path:
        raise ValueError("canonical validation calibration requires --truth-audit")
    path = Path(raw_path).resolve()
    audit = read_json(path)
    decision = audit.get("decision")
    if decision == "rejected_as_calibration_truth":
        if audit.get("calibrationTruthEligible") is not False:
            raise ValueError("rejected truth audit must set calibrationTruthEligible=false")
        return {
            "status": "rejected",
            "path": path,
            "sha256": sha256(path),
            "decision": decision,
            "report": audit,
        }
    if decision != "approved_as_calibration_truth":
        raise ValueError("canonical truth audit is not approved_as_calibration_truth")
    inputs = audit.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("canonical truth audit inputs are missing")
    if Path(str(inputs.get("datasetYaml", ""))).resolve() != dataset_yaml:
        raise ValueError("canonical truth audit dataset path does not match calibration dataset")
    if inputs.get("datasetYamlSha256") != sha256(dataset_yaml):
        raise ValueError("canonical truth audit dataset hash does not match current input")
    if Path(str(inputs.get("materializationReport", ""))).resolve() != dataset_report_path:
        raise ValueError("canonical truth audit materialization report path differs")
    if inputs.get("materializationReportSha256") != sha256(dataset_report_path):
        raise ValueError("canonical truth audit materialization report hash differs")

    truth_index_path = Path(str(inputs.get("truthIndex", ""))).resolve()
    role_isolation_path = Path(str(inputs.get("roleIsolationReport", ""))).resolve()
    finalizer = load_validation_finalizer()
    replay_args = argparse.Namespace(
        dataset=str(dataset_yaml),
        truth_index=str(truth_index_path),
        materialization_report=str(dataset_report_path),
        role_isolation_report=str(role_isolation_path),
        output=str(output_path),
    )
    recomputed = finalizer.build(replay_args)
    if audit != recomputed:
        raise ValueError(
            "canonical truth audit differs from an independent replay of current bytes"
        )
    return {
        "status": "approved",
        "path": path,
        "sha256": sha256(path),
        "decision": decision,
        "report": recomputed,
    }


def parse_probability(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0 or parsed >= 1:
        raise argparse.ArgumentTypeError("must be a finite number between 0 and 1 (exclusive)")
    return parsed


def parse_thresholds(value: str) -> list[float]:
    thresholds = sorted({parse_probability(item.strip()) for item in value.split(",")})
    if not thresholds:
        raise ValueError("confidence sweep must not be empty")
    return thresholds


def validate_formal_artifact_index(
    artifact_index_path: Path,
    artifact_index: dict[str, Any],
    truth_stems: set[str],
) -> dict[str, Path]:
    artifact_root = artifact_index_path.parent.resolve()
    if artifact_index.get("schema_version") != 1:
        raise ValueError("formal artifact index schema_version must be 1")
    if Path(str(artifact_index.get("artifacts_dir", ""))).resolve() != artifact_root:
        raise ValueError("formal artifact index artifacts_dir differs from its location")

    raw_files = artifact_index.get("files")
    raw_records = artifact_index.get("file_records")
    if not isinstance(raw_files, list) or not isinstance(raw_records, list):
        raise ValueError("formal artifact index requires files and file_records")
    files = [str(item) for item in raw_files]
    if files != sorted(files) or len(files) != len(set(files)):
        raise ValueError("formal artifact file list must be sorted and unique")
    records: list[dict[str, str]] = []
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"formal artifact file record {index} is malformed")
        relative = str(item.get("path", ""))
        relative_path = Path(relative)
        artifact = (artifact_root / relative_path).resolve()
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or not is_within(artifact, artifact_root)
        ):
            raise ValueError(f"formal artifact path is unsafe: {relative}")
        expected_hash = str(item.get("sha256", ""))
        if not artifact.is_file() or sha256(artifact) != expected_hash:
            raise ValueError(f"formal artifact hash drift: {relative}")
        records.append({"path": relative_path.as_posix(), "sha256": expected_hash})
    if [item["path"] for item in records] != files:
        raise ValueError("formal artifact files and file_records differ")
    if artifact_index.get("files_sha256") != canonical_sha256(records):
        raise ValueError("formal artifact files_sha256 drift")
    actual_files = sorted(
        path.relative_to(artifact_root).as_posix()
        for path in artifact_root.rglob("*")
        if path.is_file() and path.resolve() != artifact_index_path
    )
    if actual_files != files:
        raise ValueError(
            "formal artifact inventory has missing or orphan files: "
            f"registered={files} actual={actual_files}"
        )

    counts = artifact_index.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("formal artifact counts are missing")
    expected_counts = {
        "total": len(files),
        "plots": sum(
            1 for item in files if item.lower().endswith((".png", ".jpg", ".jpeg"))
        ),
        "prediction_labels": sum(
            1 for item in files if item.startswith("labels/") and item.endswith(".txt")
        ),
        "json": sum(1 for item in files if item.lower().endswith(".json")),
    }
    if counts != expected_counts:
        raise ValueError("formal artifact counts differ from the exact inventory")

    prediction_records = artifact_index.get("prediction_records")
    if not isinstance(prediction_records, list):
        raise ValueError("formal artifact index requires explicit prediction_records")
    if artifact_index.get("prediction_records_sha256") != canonical_sha256(
        prediction_records
    ):
        raise ValueError("formal prediction_records_sha256 drift")
    predictions_by_stem: dict[str, Path] = {}
    seen_stems: set[str] = set()
    for index, item in enumerate(prediction_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"formal prediction record {index} is malformed")
        stem = str(item.get("stem", ""))
        if not stem or stem in seen_stems:
            raise ValueError("formal prediction records have missing or duplicate stems")
        seen_stems.add(stem)
        raw_path = item.get("path")
        prediction_count = int(item.get("prediction_count", -1))
        if raw_path is None:
            if item.get("sha256") is not None or prediction_count != 0:
                raise ValueError(f"zero-prediction record is inconsistent: {stem}")
            continue
        relative = str(raw_path)
        expected_relative = f"labels/{stem}.txt"
        if Path(relative).as_posix() != expected_relative:
            raise ValueError(f"formal prediction label path differs from stem: {stem}")
        prediction_path = (artifact_root / relative).resolve()
        if not is_within(prediction_path, artifact_root) or not prediction_path.is_file():
            raise ValueError(f"formal prediction label is missing or unsafe: {stem}")
        if item.get("sha256") != sha256(prediction_path):
            raise ValueError(f"formal prediction label hash drift: {stem}")
        actual_count = sum(
            1
            for line in prediction_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if prediction_count != actual_count or prediction_count <= 0:
            raise ValueError(f"formal prediction count differs from label: {stem}")
        predictions_by_stem[stem] = prediction_path
    if seen_stems != truth_stems:
        raise ValueError("formal prediction records do not cover every validation image")
    registered_prediction_files = {
        f"labels/{stem}.txt" for stem in predictions_by_stem
    }
    actual_prediction_files = {
        item for item in files if item.startswith("labels/") and item.endswith(".txt")
    }
    if registered_prediction_files != actual_prediction_files:
        raise ValueError("formal prediction labels include unregistered or missing files")
    return predictions_by_stem


def resolve_validation_evidence(args: argparse.Namespace) -> dict[str, Any]:
    dataset_yaml = Path(args.dataset).resolve()
    dataset = load_dataset_config(dataset_yaml)
    dataset_report_path = Path(args.dataset_report).resolve()
    dataset_report = read_json(dataset_report_path)
    metrics_path = Path(args.metrics).resolve()
    metrics = read_json(metrics_path)

    report_decision = dataset_report.get("decision")
    if report_decision == "canonical_validation_dataset_materialized_pending_role_isolation_audit":
        evidence_mode = "canonical-validation"
    elif report_decision == "experiment_only_source_isolated_real_dataset":
        evidence_mode = "legacy-experiment-diagnostic"
    else:
        raise ValueError("dataset report is neither canonical validation nor a legacy experiment")
    if Path(str(dataset_report.get("outputDir", ""))).resolve() != dataset.dataset_root:
        raise ValueError("dataset report outputDir does not match dataset root")

    val_groups: list[str] = []
    if evidence_mode == "legacy-experiment-diagnostic":
        group_counts = dataset_report.get("groupCounts")
        if not isinstance(group_counts, dict) or not group_counts:
            raise ValueError("dataset report groupCounts are required")
        for group, raw_counts in group_counts.items():
            if not isinstance(raw_counts, dict):
                raise ValueError(f"dataset report group {group} has invalid counts")
            val_count = int(raw_counts.get("val", 0))
            if val_count <= 0:
                continue
            if int(raw_counts.get("train", 0)) != 0 or int(raw_counts.get("test", 0)) != 0:
                raise ValueError(f"validation source group leaks into train or test: {group}")
            val_groups.append(str(group))
        if not val_groups:
            raise ValueError("dataset report has no validation-only source group")

    if metrics.get("split") != "val":
        raise ValueError("threshold calibration requires metrics from split=val")
    if Path(str(metrics.get("dataset_root", ""))).resolve() != dataset.dataset_root:
        raise ValueError("metrics dataset root does not match calibration dataset")
    artifact_index_raw = metrics.get("evaluation_artifacts", {}).get("index")
    if not isinstance(artifact_index_raw, str) or not artifact_index_raw:
        raise ValueError("metrics evaluation artifact index is required")
    artifact_index_path = Path(artifact_index_raw).resolve()
    artifact_index = read_json(artifact_index_path)
    if artifact_index.get("split") != "val":
        raise ValueError("prediction artifact index must use the validation split")

    weights_raw = metrics.get("weights")
    if not isinstance(weights_raw, str) or not weights_raw:
        raise ValueError("metrics weights path is required")
    weights = Path(weights_raw).resolve()
    if not weights.is_file():
        raise FileNotFoundError(f"model weights are missing: {weights}")

    labels_root = dataset.dataset_root / Path(dataset.val).parent.parent / "labels" / Path(dataset.val).name
    if not labels_root.is_dir():
        labels_root = dataset.dataset_root / "labels" / "val"
    truth_paths = sorted(labels_root.glob("*.txt"))
    expected_val_images = (
        int(dataset_report.get("counts", {}).get("validationImages", 0))
        if evidence_mode == "canonical-validation"
        else int(dataset_report.get("splitCounts", {}).get("val", 0))
    )
    if not truth_paths or len(truth_paths) != expected_val_images:
        raise ValueError(
            f"validation truth count drift: labels={len(truth_paths)}, report={expected_val_images}"
        )
    truth_stems = {path.stem for path in truth_paths}
    if evidence_mode == "canonical-validation":
        truth_audit = resolve_canonical_truth_audit(
            args.truth_audit,
            dataset_yaml,
            dataset_report_path,
            Path(args.output).resolve(),
        )
        audit_items = truth_audit["report"].get("items", [])
        val_groups = sorted(
            {
                str(item.get("sourceGroup"))
                for item in audit_items
                if isinstance(item, dict) and str(item.get("sourceGroup", "")).strip()
            }
        )
        if not val_groups:
            raise ValueError("canonical truth audit has no validation source groups")
        if Path(str(metrics.get("dataset_yaml", ""))).resolve() != dataset_yaml:
            raise ValueError("formal metrics dataset_yaml differs from calibration dataset")
        if metrics.get("dataset_yaml_sha256") != sha256(dataset_yaml):
            raise ValueError("formal metrics dataset_yaml_sha256 drift")
        if metrics.get("weights_sha256") != sha256(weights):
            raise ValueError("formal metrics weights_sha256 drift")
        artifact_evidence = metrics.get("evaluation_artifacts")
        if not isinstance(artifact_evidence, dict):
            raise ValueError("formal metrics evaluation_artifacts are missing")
        if artifact_evidence.get("index_sha256") != sha256(artifact_index_path):
            raise ValueError("formal metrics artifact index hash drift")
        if artifact_evidence.get("files_sha256") != artifact_index.get("files_sha256"):
            raise ValueError("formal metrics artifact inventory hash drift")
        predictions_by_stem = validate_formal_artifact_index(
            artifact_index_path, artifact_index, truth_stems
        )
    else:
        truth_audit = resolve_truth_audit(args.truth_audit, dataset_yaml, truth_paths)
        prediction_root = artifact_index_path.parent / "labels"
        prediction_paths = sorted(prediction_root.rglob("*.txt")) if prediction_root.is_dir() else []
        predictions_by_stem = {}
        for prediction_path in prediction_paths:
            if prediction_path.stem in predictions_by_stem:
                raise ValueError(f"duplicate prediction label stem: {prediction_path.stem}")
            predictions_by_stem[prediction_path.stem] = prediction_path
        unknown_predictions = sorted(set(predictions_by_stem) - truth_stems)
        if unknown_predictions:
            raise ValueError(f"prediction labels contain unknown validation images: {unknown_predictions}")

    output_path = Path(args.output).resolve()
    protected_inputs = {dataset_yaml, dataset_report_path, metrics_path, artifact_index_path, weights}
    if truth_audit["path"] is not None:
        protected_inputs.add(Path(truth_audit["path"]).resolve())
    if output_path in protected_inputs:
        raise ValueError("output must not overwrite resolved calibration evidence")
    if evidence_mode == "canonical-validation" and is_within(
        output_path, artifact_index_path.parent.resolve()
    ):
        raise ValueError("formal calibration output must be outside the artifact directory")

    return {
        "datasetYaml": dataset_yaml,
        "datasetRoot": dataset.dataset_root,
        "datasetReport": dataset_report_path,
        "metrics": metrics_path,
        "artifactIndex": artifact_index_path,
        "weights": weights,
        "truthPaths": truth_paths,
        "predictionsByStem": predictions_by_stem,
        "validationSourceGroups": sorted(val_groups),
        "truthAudit": truth_audit,
        "evidenceMode": evidence_mode,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence = resolve_validation_evidence(args)
    thresholds = parse_thresholds(args.confidence_sweep)
    parsed_truth = {
        path.stem: parse_yolo_polygons(path, prediction=False, repair_invalid=True)
        for path in evidence["truthPaths"]
    }
    parsed_predictions = {
        stem: parse_yolo_polygons(
            path,
            prediction=True,
            minimum_confidence=thresholds[0],
        )
        for stem, path in evidence["predictionsByStem"].items()
    }
    image_count = len(parsed_truth)
    truth_count = sum(len(items) for items in parsed_truth.values())
    repaired_truth_count = sum(
        bool(item["repaired"])
        for items in parsed_truth.values()
        for item in items
    )
    repaired_truth_records = [
        {"fileName": f"{stem}.txt", "line": int(item["line"])}
        for stem, items in parsed_truth.items()
        for item in items
        if item["repaired"]
    ]
    if truth_count <= 0:
        raise ValueError("validation split contains no ground-truth instances")

    sweep: list[dict[str, Any]] = []
    for threshold in thresholds:
        results: list[dict[str, Any]] = []
        for stem, truth in parsed_truth.items():
            predictions = [
                item
                for item in parsed_predictions.get(stem, [])
                if float(item["confidence"]) >= threshold
            ]
            results.append(match_instances(truth, predictions, args.match_iou, args.strong_iou))
        predictions = sum(item["predictionCount"] for item in results)
        matched = sum(item["matchedCount"] for item in results)
        false_positives = sum(item["falsePositiveCount"] for item in results)
        missed = sum(item["missedCount"] for item in results)
        precision = matched / predictions if predictions else 0.0
        recall = matched / truth_count
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        false_positives_per_image = false_positives / image_count
        max_predictions_per_image = max((item["predictionCount"] for item in results), default=0)
        qualifies = (
            recall >= args.min_recall
            and false_positives_per_image <= args.max_false_positives_per_image
            and max_predictions_per_image <= args.max_candidates_per_image
        )
        sweep.append(
            {
                "confidence": threshold,
                "predictions": predictions,
                "matched": matched,
                "missed": missed,
                "falsePositives": false_positives,
                "precisionAtIou50": precision,
                "recallAtIou50": recall,
                "f1AtIou50": f1,
                "falsePositivesPerImage": false_positives_per_image,
                "maxPredictionsPerImage": max_predictions_per_image,
                "qualifies": qualifies,
            }
        )

    qualifying = [item for item in sweep if item["qualifies"]]
    selected = max(
        qualifying,
        key=lambda item: (
            item["f1AtIou50"],
            item["precisionAtIou50"],
            item["recallAtIou50"],
            item["confidence"],
        ),
        default=None,
    )
    calibration_eligible = (
        selected is not None
        and image_count >= args.min_validation_images
        and repaired_truth_count == 0
        and evidence["truthAudit"]["status"] == "approved"
        and evidence["evidenceMode"] == "canonical-validation"
    )
    if evidence["truthAudit"]["status"] == "rejected":
        decision = "diagnostic_only_validation_truth_rejected"
    elif evidence["evidenceMode"] == "legacy-experiment-diagnostic":
        decision = "diagnostic_only_legacy_experiment_dataset"
    elif repaired_truth_count > 0:
        decision = "diagnostic_only_validation_truth_requires_repair"
    elif evidence["truthAudit"]["status"] == "unreviewed":
        decision = "diagnostic_only_validation_truth_unreviewed"
    elif selected is None:
        decision = "no_threshold_meets_validation_constraints"
    elif not calibration_eligible:
        decision = "diagnostic_only_insufficient_validation_images"
    else:
        decision = "calibrated_threshold_ready_for_candidate_manifest"

    return {
        "ok": True,
        "schemaVersion": 1,
        "decision": decision,
        "calibrationEligible": calibration_eligible,
        "manifestScoreThreshold": selected["confidence"] if calibration_eligible else None,
        "diagnosticBestThreshold": selected["confidence"] if selected else None,
        "inputs": {
            "datasetYaml": str(evidence["datasetYaml"]),
            "datasetYamlSha256": sha256(evidence["datasetYaml"]),
            "datasetRoot": str(evidence["datasetRoot"]),
            "datasetReport": str(evidence["datasetReport"]),
            "datasetReportSha256": sha256(evidence["datasetReport"]),
            "metrics": str(evidence["metrics"]),
            "metricsSha256": sha256(evidence["metrics"]),
            "artifactIndex": str(evidence["artifactIndex"]),
            "artifactIndexSha256": sha256(evidence["artifactIndex"]),
            "weights": str(evidence["weights"]),
            "weightsSha256": sha256(evidence["weights"]),
            "split": "val",
            "validationSourceGroups": evidence["validationSourceGroups"],
            "truthAudit": str(evidence["truthAudit"]["path"]) if evidence["truthAudit"]["path"] else None,
            "truthAuditSha256": evidence["truthAudit"]["sha256"],
            "truthAuditDecision": evidence["truthAudit"]["decision"],
            "evidenceMode": evidence["evidenceMode"],
        },
        "counts": {
            "validationImages": image_count,
            "truthMasks": truth_count,
            "repairedTruthPolygons": repaired_truth_count,
            "predictionLabelFiles": len(evidence["predictionsByStem"]),
        },
        "repairedTruthRecords": repaired_truth_records,
        "thresholds": {
            "matchIou": args.match_iou,
            "strongIou": args.strong_iou,
            "minimumRecall": args.min_recall,
            "maximumFalsePositivesPerImage": args.max_false_positives_per_image,
            "maximumCandidatesPerImage": args.max_candidates_per_image,
            "minimumValidationImages": args.min_validation_images,
        },
        "selected": selected,
        "thresholdSweep": sweep,
        "releaseTestPolicy": "Calibration accepts validation-only evidence. Frozen test and release-test predictions are prohibited inputs.",
        "formalEvidencePolicy": "Only the canonical validation dataset with an independently replayed approved truth audit may authorize a candidate manifest threshold; legacy experiment reports are diagnostic-only.",
        "nextSteps": (
            ["Write manifestScoreThreshold into the candidate manifest, then rerun untouched release-test and Beta gates."]
            if calibration_eligible
            else [
                "Repair and re-audit any invalid validation polygons before calibration can become manifest evidence.",
                "Obtain an approved full-coverage original-resolution validation-truth audit bound to every label hash.",
                "Expand a source-isolated validation split to the minimum sample count without using frozen release-test sources.",
                "Rerun calibration before writing any threshold into a candidate manifest.",
            ]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate a model score threshold using source-isolated validation predictions only."
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset-report", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--truth-audit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--confidence-sweep", default="0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50")
    parser.add_argument("--match-iou", type=parse_probability, default=0.50)
    parser.add_argument("--strong-iou", type=parse_probability, default=0.75)
    parser.add_argument("--min-recall", type=parse_probability, default=0.75)
    parser.add_argument("--max-false-positives-per-image", type=float, default=1.0)
    parser.add_argument("--max-candidates-per-image", type=int, default=10)
    parser.add_argument("--min-validation-images", type=int, default=30)
    args = parser.parse_args()
    if args.match_iou > args.strong_iou:
        raise ValueError("match IoU must not exceed strong IoU")
    if args.max_false_positives_per_image < 0:
        raise ValueError("maximum false positives per image must be non-negative")
    if args.max_candidates_per_image <= 0 or args.min_validation_images <= 0:
        raise ValueError("candidate and validation image limits must be positive")
    protect_direct_output(args)
    report = build_report(args)
    output = Path(args.output).resolve()
    write_json(output, report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "decision": report["decision"],
                "calibrationEligible": report["calibrationEligible"],
                "manifestScoreThreshold": report["manifestScoreThreshold"],
                "diagnosticBestThreshold": report["diagnosticBestThreshold"],
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
