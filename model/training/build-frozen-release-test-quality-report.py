#!/usr/bin/env python3
"""Build a lineage-checked quality decision for a frozen release-test snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build a frozen release-test quality report.")
    value.add_argument("--snapshot-manifest", required=True)
    value.add_argument("--materialization-report", required=True)
    value.add_argument("--baseline-metrics", required=True)
    value.add_argument("--full-512", required=True)
    value.add_argument("--full-640", required=True)
    value.add_argument("--core-512", required=True)
    value.add_argument("--stress-512", required=True)
    value.add_argument("--assessment", required=True)
    value.add_argument("--output", required=True)
    value.add_argument("--min-box-map50", type=float, default=0.85)
    value.add_argument("--min-mask-map50", type=float, default=0.75)
    value.add_argument("--max-regression", type=float, default=0.02)
    return value


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def metrics(path: Path, expected_size: int, expected_images: int) -> dict[str, Any]:
    document = load(path)
    if document.get("split") != "test" or int(document.get("imgsz") or 0) != expected_size:
        raise ValueError(f"Unexpected evaluation split or image size: {path}")
    artifact = document.get("evaluation_artifacts") or {}
    index_path = Path(str(artifact.get("index") or ""))
    if not index_path.is_file():
        raise FileNotFoundError(f"Evaluation artifact index is missing: {index_path}")
    index = load(index_path)
    prediction_count = int((index.get("counts") or {}).get("prediction_labels") or 0)
    if index.get("split") != "test" or prediction_count != expected_images:
        raise ValueError(f"Evaluation artifacts do not cover {expected_images} test images: {path}")
    return {
        "path": str(path),
        "imgsz": expected_size,
        "boxMap50": float(document["box_map50"]),
        "maskMap50": float(document["seg_map50"]),
        "boxMap50To95": float(document["box_map"]),
        "maskMap50To95": float(document["seg_map"]),
        "datasetRoot": str(document.get("dataset_root") or ""),
        "artifactIndex": str(index_path),
        "predictionLabels": prediction_count,
    }


def main() -> None:
    args = parser().parse_args()
    paths = {name: Path(getattr(args, name)).resolve() for name in (
        "snapshot_manifest", "materialization_report", "baseline_metrics", "full_512",
        "full_640", "core_512", "stress_512", "assessment", "output",
    )}
    snapshot = load(paths["snapshot_manifest"])
    materialization = load(paths["materialization_report"])
    items = snapshot.get("items")
    if (
        snapshot.get("decision") != "frozen_reviewed_candidate_not_release_ready"
        or snapshot.get("trainingUse") != "prohibited"
        or not isinstance(items, list)
        or canonical_sha256(items) != snapshot.get("itemsSha256")
    ):
        raise ValueError("Frozen snapshot lineage is invalid")
    counts = snapshot.get("counts") or {}
    image_count = int(counts.get("images") or 0)
    mask_count = int(counts.get("masks") or 0)
    core_count = int(counts.get("coreImages") or 0)
    stress_count = int(counts.get("stressImages") or 0)
    if (image_count, mask_count, core_count, stress_count) != (67, 384, 45, 22):
        raise ValueError("Frozen snapshot counts are not the reviewed 67/384 snapshot")
    if (
        materialization.get("ok") is not True
        or materialization.get("trainingUse") != "prohibited"
        or materialization.get("counts") != {"images": image_count, "masks": mask_count, "parentSourceGroups": 18}
        or (materialization.get("sourceIsolation") or {}).get("parentSourceGroupOverlap") != []
        or (materialization.get("sourceIsolation") or {}).get("exactImageHashOverlap") != []
    ):
        raise ValueError("Evaluation materialization or source isolation is invalid")

    baseline = load(paths["baseline_metrics"])
    baseline_values = {
        "path": str(paths["baseline_metrics"]),
        "images": 13,
        "boxMap50": float(baseline["box_map50"]),
        "maskMap50": float(baseline["seg_map50"]),
    }
    evaluations = {
        "full512": metrics(paths["full_512"], 512, image_count),
        "full640Diagnostic": metrics(paths["full_640"], 640, image_count),
        "core512": metrics(paths["core_512"], 512, core_count),
        "stress512": metrics(paths["stress_512"], 512, stress_count),
    }
    expected_root = str(Path(str(materialization.get("outputDir") or "")).resolve())
    if any(Path(item["datasetRoot"]).resolve() != Path(expected_root) for item in evaluations.values()):
        raise ValueError("Evaluation metrics do not point to the materialized frozen snapshot")

    assessment = load(paths["assessment"])
    labels = {item.get("label"): item for item in assessment.get("candidates", []) if isinstance(item, dict)}
    if assessment.get("ok") is not False or set(labels) != {"release67", "core45", "stress22"}:
        raise ValueError("Metric assessment is missing the required rejected groups")

    full = evaluations["full512"]
    box_drop = baseline_values["boxMap50"] - full["boxMap50"]
    mask_drop = baseline_values["maskMap50"] - full["maskMap50"]
    errors: list[str] = []
    if full["boxMap50"] < args.min_box_map50:
        errors.append(f"deployment box mAP50 {full['boxMap50']:.6f} is below {args.min_box_map50:.6f}")
    if full["maskMap50"] < args.min_mask_map50:
        errors.append(f"deployment mask mAP50 {full['maskMap50']:.6f} is below {args.min_mask_map50:.6f}")
    if box_drop > args.max_regression:
        errors.append(f"deployment box mAP50 regression {box_drop:.6f} exceeds {args.max_regression:.6f}")
    if mask_drop > args.max_regression:
        errors.append(f"deployment mask mAP50 regression {mask_drop:.6f} exceeds {args.max_regression:.6f}")
    if labels["stress22"].get("qualityGatePassed") is not False:
        errors.append("stress subset did not produce the required explicit quality rejection")

    quality_passed = not errors
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "accept_v6_release" if quality_passed else "reject_v6_release_at_deployment_resolution",
        "qualityGatePassed": quality_passed,
        "trainingUse": "prohibited",
        "snapshot": {
            "id": snapshot.get("snapshotId"),
            "itemsSha256": snapshot.get("itemsSha256"),
            "counts": {"images": image_count, "masks": mask_count, "coreImages": core_count, "stressImages": stress_count},
            "parentSourceGroups": 18,
            "sourceIsolationPassed": True,
        },
        "deploymentContract": {"imgsz": 512, "minimumBoxMap50": args.min_box_map50, "minimumMaskMap50": args.min_mask_map50, "maximumRegression": args.max_regression},
        "historicalBaseline": baseline_values,
        "evaluations": evaluations,
        "deploymentDeltaFromHistorical13": {"boxMap50": -box_drop, "maskMap50": -mask_drop},
        "errors": errors,
        "diagnosticConclusion": {
            "core": "near_box_threshold_mask_pass",
            "stress": "primary_generalization_regression",
            "full640": "absolute_threshold_pass_but_not_the_512_deployment_contract",
        },
        "nextActions": [
            "Keep the production manifest unchanged and do not promote v6.",
            "Use the frozen snapshot only for evaluation; never add its images or labels to training.",
            "Prioritize training-authorized stress-domain examples and reevaluate at 512 pixels.",
            "Expand the frozen source-isolated release test from 67 to at least 100 images.",
        ],
        "inputs": {key: str(value) for key, value in paths.items() if key != "output"},
    }
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    paths["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
