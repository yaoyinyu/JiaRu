#!/usr/bin/env python3
"""Audit complete original-resolution review coverage for validation truth."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from _training_common import write_json


ALLOWED_DECISIONS = {"pass", "rework", "exclude"}
ALLOWED_DEFECTS = {
    "invalid-topology",
    "overlap",
    "missing-nail",
    "false-positive",
    "duplicate-mask",
    "partial-mask",
    "skin-contamination",
    "cropped-required-nail",
    "background-contamination",
    "empty-positive-label",
    "out-of-domain",
}


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


def build(candidate_path: Path, review_path: Path) -> dict[str, Any]:
    candidate = read_json(candidate_path)
    review = read_json(review_path)
    if candidate.get("decision") not in {
        "candidate_only_requires_original_resolution_review",
        "blocked_undeclared_validation_truth_overlaps",
    }:
        raise ValueError("candidate report has an unsupported decision")
    if candidate.get("inputs", {}).get("split") != "val":
        raise ValueError("candidate report is not restricted to validation truth")
    if review.get("candidateReportSha256") != sha256(candidate_path):
        raise ValueError("review is not bound to the current candidate report hash")
    if review.get("reviewMode") != "original-resolution-full-image-and-repaired-crops":
        raise ValueError("review mode does not prove original-resolution inspection")
    reviewer = str(review.get("reviewer", "")).strip()
    if not reviewer:
        raise ValueError("reviewer is required")

    outputs = candidate.get("outputs", [])
    expected = {str(item["fileName"]): item for item in outputs}
    items = review.get("items", [])
    reviewed: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for item in items:
        file_name = str(item.get("fileName", ""))
        if file_name in reviewed:
            errors.append(f"duplicate review item: {file_name}")
            continue
        reviewed[file_name] = item
        if file_name not in expected:
            errors.append(f"unknown review item: {file_name}")
            continue
        decision = item.get("decision")
        defects = item.get("defects")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"{file_name}: invalid decision {decision}")
        if not isinstance(defects, list) or any(defect not in ALLOWED_DEFECTS for defect in defects):
            errors.append(f"{file_name}: invalid defect list")
            defects = []
        if decision == "pass" and defects:
            errors.append(f"{file_name}: pass item must have no remaining defects")
        if decision in {"rework", "exclude"} and not defects:
            errors.append(f"{file_name}: {decision} item must name at least one defect")
        if decision == "exclude" and not ({"cropped-required-nail", "out-of-domain"} & set(defects)):
            errors.append(f"{file_name}: exclusion requires a cropped or out-of-domain reason")
        if not str(item.get("notes", "")).strip():
            errors.append(f"{file_name}: review notes are required")

        evidence = expected[file_name]
        image_path = Path(str(evidence.get("imagePath", ""))).resolve()
        overlay_path = Path(str(evidence.get("overlayPath", ""))).resolve()
        if not image_path.is_file() or not overlay_path.is_file():
            errors.append(f"{file_name}: full-image evidence is missing")
        for zoom in evidence.get("zoomPaths", []):
            if not Path(str(zoom.get("source", ""))).is_file() or not Path(str(zoom.get("candidate", ""))).is_file():
                errors.append(f"{file_name}: repaired-nail zoom evidence is missing")

    missing = sorted(set(expected) - set(reviewed))
    if missing:
        errors.append(f"missing review items: {missing}")
    counts = {decision: sum(item.get("decision") == decision for item in reviewed.values()) for decision in ALLOWED_DECISIONS}
    eligible = not errors and counts["pass"] == len(expected) and bool(candidate.get("ok"))
    return {
        "ok": not errors,
        "schemaVersion": 1,
        "decision": (
            "approved_as_calibration_truth_candidate"
            if eligible
            else "rejected_as_calibration_truth"
        ),
        "calibrationTruthEligible": eligible,
        "inputs": {
            "candidateReport": str(candidate_path),
            "candidateReportSha256": sha256(candidate_path),
            "reviewManifest": str(review_path),
            "reviewManifestSha256": sha256(review_path),
            "split": "val",
        },
        "reviewer": reviewer,
        "reviewMode": review.get("reviewMode"),
        "counts": {
            "expectedImages": len(expected),
            "reviewedImages": len(reviewed),
            "pass": counts["pass"],
            "rework": counts["rework"],
            "exclude": counts["exclude"],
            "candidateOverlapBlockers": len(candidate.get("overlapBlockers", [])),
        },
        "items": items,
        "errors": errors,
        "policy": "A validation truth split is eligible only when every image passes complete original-resolution review and the candidate topology report has no blockers.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a complete validation-truth visual review.")
    parser.add_argument("--candidate-report", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate_path = Path(args.candidate_report).resolve()
    review_path = Path(args.review).resolve()
    report = build(candidate_path, review_path)
    output = Path(args.output).resolve()
    write_json(output, report)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "calibrationTruthEligible": report["calibrationTruthEligible"], "counts": report["counts"], "output": str(output)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
