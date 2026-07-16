#!/usr/bin/env python3
"""Audit whether a validation split is eligible for release-candidate training."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

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


def label_geometry(path: Path) -> tuple[int, list[str]]:
    shapes: list[Polygon] = []
    errors: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        parts = raw.split()
        try:
            values = [float(value) for value in parts[1:]]
        except ValueError:
            errors.append(f"{path.name}:{line_number} has non-numeric coordinates")
            continue
        if len(parts) < 7 or len(values) % 2 or any(value < 0 or value > 1 for value in values):
            errors.append(f"{path.name}:{line_number} has invalid normalized coordinates")
            continue
        shape = Polygon(list(zip(values[0::2], values[1::2])))
        if not shape.is_valid or shape.is_empty or shape.area <= 0:
            errors.append(f"{path.name}:{line_number} has invalid polygon topology")
        shapes.append(shape)
    for left_index, left in enumerate(shapes, start=1):
        if not left.is_valid:
            continue
        for right_index in range(left_index + 1, len(shapes) + 1):
            right = shapes[right_index - 1]
            if not right.is_valid:
                continue
            overlap = left.intersection(right).area
            if overlap > 1e-10:
                errors.append(
                    f"{path.name}:{left_index}/{right_index} overlap {overlap:.10f}"
                )
    return len(shapes), errors


def build(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = Path(args.dataset).resolve()
    dataset = load_dataset_config(dataset_path)
    source_report_path = Path(args.source_isolation_report).resolve()
    source_report = read_json(source_report_path)
    truth_audit_path = Path(args.truth_audit).resolve() if args.truth_audit else None
    truth_audit = read_json(truth_audit_path) if truth_audit_path else None
    errors: list[str] = []

    if source_report.get("decision") not in {
        "experiment_only_source_isolated_real_dataset",
        "approved_dataset_source_isolation",
    }:
        errors.append("source report is not an approved source-isolated dataset")
    if Path(str(source_report.get("outputDir", ""))).resolve() != dataset.dataset_root:
        errors.append("source report outputDir does not match dataset root")
    val_groups: list[str] = []
    group_counts = source_report.get("groupCounts")
    if not isinstance(group_counts, dict) or not group_counts:
        errors.append("source report groupCounts are required")
    else:
        for group, raw_counts in group_counts.items():
            if not isinstance(raw_counts, dict):
                errors.append(f"source group {group} has invalid counts")
                continue
            val_count = int(raw_counts.get("val", 0))
            if val_count <= 0:
                continue
            if int(raw_counts.get("train", 0)) or int(raw_counts.get("test", 0)):
                errors.append(f"validation source group leaks into train or test: {group}")
            val_groups.append(str(group))
    if not val_groups:
        errors.append("no validation-only source group is present")

    labels_root = dataset.dataset_root / "labels" / "val"
    if not labels_root.is_dir():
        labels_root = dataset.dataset_root / "labels-yolo-seg" / "val"
    truth_paths = sorted(labels_root.glob("*.txt")) if labels_root.is_dir() else []
    val_images_root = dataset.dataset_root / Path(dataset.val)
    val_images = sorted(
        path for path in val_images_root.glob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ) if val_images_root.is_dir() else []
    expected_val = int(source_report.get("splitCounts", {}).get("val", -1))
    if len(truth_paths) != len(val_images) or len(truth_paths) != expected_val:
        errors.append(
            f"validation coverage drift: images={len(val_images)} labels={len(truth_paths)} report={expected_val}"
        )
    if len(val_images) < args.min_validation_images:
        errors.append(
            f"validation image count {len(val_images)} is below required {args.min_validation_images}"
        )

    if truth_audit is None:
        errors.append("approved original-resolution truth audit is required")
    else:
        if truth_audit.get("decision") != "approved_as_calibration_truth":
            errors.append("truth audit is not approved_as_calibration_truth")
        if truth_audit.get("ok") is not True or truth_audit.get("calibrationTruthEligible") is not True:
            errors.append("truth audit is not eligible")
        audit_inputs = truth_audit.get("inputs", {})
        if audit_inputs.get("split") != "val":
            errors.append("truth audit is not restricted to split=val")
        if Path(str(audit_inputs.get("datasetYaml", ""))).resolve() != dataset_path:
            errors.append("truth audit dataset path does not match")
        if audit_inputs.get("datasetYamlSha256") != sha256(dataset_path):
            errors.append("truth audit dataset hash does not match")
        counts = truth_audit.get("counts", {})
        if (
            int(counts.get("expectedImages", -1)) != len(truth_paths)
            or int(counts.get("reviewedImages", -1)) != len(truth_paths)
            or int(counts.get("pass", -1)) != len(truth_paths)
            or int(counts.get("rework", -1)) != 0
            or int(counts.get("exclude", -1)) != 0
        ):
            errors.append("truth audit does not prove full pass coverage")
        label_hashes = truth_audit.get("labelSha256")
        if not isinstance(label_hashes, dict) or set(label_hashes) != {path.name for path in truth_paths}:
            errors.append("truth audit label hash coverage does not match validation labels")
        elif any(label_hashes[path.name] != sha256(path) for path in truth_paths):
            errors.append("truth audit label hashes have drifted")

    mask_count = 0
    geometry_errors: list[str] = []
    for path in truth_paths:
        count, file_errors = label_geometry(path)
        mask_count += count
        geometry_errors.extend(file_errors)
    errors.extend(geometry_errors)
    eligible = not errors
    return {
        "ok": eligible,
        "schemaVersion": 1,
        "decision": (
            "approved_candidate_training_validation"
            if eligible
            else "rejected_candidate_training_validation"
        ),
        "candidateTrainingEligible": eligible,
        "inputs": {
            "datasetYaml": str(dataset_path),
            "datasetYamlSha256": sha256(dataset_path),
            "datasetRoot": str(dataset.dataset_root),
            "sourceIsolationReport": str(source_report_path),
            "sourceIsolationReportSha256": sha256(source_report_path),
            "truthAudit": str(truth_audit_path) if truth_audit_path else None,
            "truthAuditSha256": sha256(truth_audit_path) if truth_audit_path else None,
            "split": "val",
        },
        "counts": {
            "validationImages": len(val_images),
            "validationLabels": len(truth_paths),
            "validationMasks": mask_count,
            "minimumValidationImages": args.min_validation_images,
            "validationOnlySourceGroups": len(val_groups),
            "geometryErrors": len(geometry_errors),
        },
        "validationSourceGroups": sorted(val_groups),
        "errors": errors,
        "policy": "Candidate training requires source-isolated validation groups, full approved original-resolution truth review, bound label hashes, valid polygons, and zero pairwise overlap.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit candidate-training validation evidence.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--source-isolation-report", required=True)
    parser.add_argument("--truth-audit")
    parser.add_argument("--min-validation-images", type=int, default=30)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.min_validation_images <= 0:
        raise ValueError("minimum validation image count must be positive")
    report = build(args)
    output = Path(args.output).resolve()
    write_json(output, report)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"], "errors": report["errors"], "output": str(output)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
