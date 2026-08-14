#!/usr/bin/env python3
"""Build a replayable candidate7 re-review intake from legacy real train data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def object_array(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Expected object array: {field}")
    return value


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset_root = Path(args.dataset_root).resolve()
    sources_path = dataset_root / "metadata" / "sources.csv"
    split_path = dataset_root / "metadata" / "split.json"
    training_path = Path(args.training_truth_index).resolve()
    validation_path = Path(args.validation_truth_index).resolve()
    test_path = Path(args.frozen_test_manifest).resolve()
    for path in (sources_path, split_path, training_path, validation_path, test_path):
        if not path.is_file():
            raise ValueError(f"Missing input: {path}")

    with sources_path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    split = load_object(split_path)
    training = load_object(training_path)
    validation = load_object(validation_path)
    frozen_test = load_object(test_path)
    if training.get("decision") != "approved_unique_training_truth_index":
        raise ValueError("Training truth index is not approved")
    if validation.get("decision") != "approved_unique_validation_truth_index":
        raise ValueError("Validation truth index is not approved")
    if frozen_test.get("trainingUse") != "prohibited":
        raise ValueError("Frozen test is not protected")

    train_names = split.get("train")
    if not isinstance(train_names, list) or any(not isinstance(item, str) for item in train_names):
        raise ValueError("metadata/split.json train must be a string array")
    train_name_set = set(train_names)
    if len(train_name_set) != len(train_names):
        raise ValueError("Legacy train split contains duplicate filenames")

    role_items = {
        "currentTrain": object_array(training.get("canonicalTruths"), "training.canonicalTruths"),
        "validation": object_array(validation.get("canonicalTruths"), "validation.canonicalTruths"),
        "frozenTest": object_array(frozen_test.get("items"), "frozenTest.items"),
    }
    used_hashes: dict[str, set[str]] = {}
    for role, items in role_items.items():
        hashes: set[str] = set()
        for item in items:
            image_hash = str(item.get("imageSha256") or item.get("sha256") or "").lower()
            if len(image_hash) != 64:
                raise ValueError(f"Missing image hash in {role}")
            hashes.add(image_hash)
        used_hashes[role] = hashes

    eligible_origin_types = {"reference", "user"}
    items: list[dict[str, Any]] = []
    skipped_non_real = 0
    skipped_not_train = 0
    skipped_exact_overlap = {role: 0 for role in used_hashes}
    for row in sorted(source_rows, key=lambda value: value.get("fileName", "")):
        file_name = row.get("fileName", "")
        if file_name not in train_name_set:
            skipped_not_train += 1
            continue
        if row.get("originType") not in eligible_origin_types:
            skipped_non_real += 1
            continue
        image_path = (dataset_root / row.get("imagePath", "")).resolve()
        annotation_path = (dataset_root / row.get("annotationPath", "")).resolve()
        if not image_path.is_file() or not annotation_path.is_file():
            raise ValueError(f"Missing legacy image or annotation: {file_name}")
        image_hash = sha256_path(image_path)
        overlap_roles = [role for role, hashes in used_hashes.items() if image_hash in hashes]
        if overlap_roles:
            for role in overlap_roles:
                skipped_exact_overlap[role] += 1
            continue
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
            image.load()
        license_value = row.get("license", "")
        authorized_licenses = {
            "owner-authorized-commercial-training-and-regression",
            "user-authorized-commercial-training-and-long-term-regression",
        }
        if license_value not in authorized_licenses:
            raise ValueError(f"Legacy candidate lacks commercial training authorization: {file_name}")
        annotation_count = int(row.get("annotationCount") or 0)
        items.append(
            {
                "fileName": file_name,
                "imagePath": str(image_path),
                "imageSha256": image_hash,
                "width": width,
                "height": height,
                "sourceGroup": row.get("sourceGroup", ""),
                "originType": row.get("originType", ""),
                "originRef": row.get("originRef", ""),
                "license": license_value,
                "legacyAnnotationPath": str(annotation_path),
                "legacyAnnotationSha256": sha256_path(annotation_path),
                "legacyPolygonCount": annotation_count,
                "legacyNeedsManualFix": "needs_manual_fix=true" in row.get("notes", ""),
                "candidateRole": "candidate7-positive-rereview-intake",
                "sourceQualityReview": "required-current-original-resolution-review",
                "completeMaskReview": "required-current-original-resolution-review",
                "exactCandidate7Authorization": "missing",
                "trainingUse": "prohibited",
            }
        )

    if len({item["imageSha256"] for item in items}) != len(items):
        raise ValueError("Candidate intake contains duplicate image hashes")
    counts_by_origin: dict[str, int] = {}
    counts_by_legacy_polygons: dict[str, int] = {}
    for item in items:
        counts_by_origin[item["originType"]] = counts_by_origin.get(item["originType"], 0) + 1
        key = str(item["legacyPolygonCount"])
        counts_by_legacy_polygons[key] = counts_by_legacy_polygons.get(key, 0) + 1

    return {
        "schemaVersion": 1,
        "ok": bool(items),
        "decision": "candidate7_legacy_real_rereview_intake_ready" if items else "hold_no_candidates",
        "inputs": {
            "datasetRoot": str(dataset_root),
            "sourcesCsv": str(sources_path),
            "sourcesCsvSha256": sha256_path(sources_path),
            "split": str(split_path),
            "splitSha256": sha256_path(split_path),
            "trainingTruthIndex": str(training_path),
            "trainingTruthIndexSha256": sha256_path(training_path),
            "validationTruthIndex": str(validation_path),
            "validationTruthIndexSha256": sha256_path(validation_path),
            "frozenTestManifest": str(test_path),
            "frozenTestManifestSha256": sha256_path(test_path),
        },
        "policy": {
            "legacyPolygonsAreDiagnosticOnly": True,
            "originalResolutionSourceAndCompleteMaskReviewRequired": True,
            "exactCandidate7FileListAuthorizationRequired": True,
            "currentTrainValidationFrozenTestExactHashesExcluded": True,
            "sameRoleSiblingSourcesRequireExplicitProvenanceReview": True,
            "inventoryDoesNotGrantTrainingUse": True,
            "trainingUse": "prohibited",
        },
        "counts": {
            "legacySourceRows": len(source_rows),
            "legacyTrainRows": len(train_names),
            "skippedNotLegacyTrain": skipped_not_train,
            "skippedNonRealTrain": skipped_non_real,
            "skippedExactOverlapByRole": skipped_exact_overlap,
            "candidateImages": len(items),
            "candidateSourceGroups": len({item["sourceGroup"] for item in items}),
            "legacyPolygonCount": sum(item["legacyPolygonCount"] for item in items),
            "legacyNeedsManualFixImages": sum(bool(item["legacyNeedsManualFix"]) for item in items),
            "byOriginType": counts_by_origin,
            "byLegacyPolygonCount": dict(sorted(counts_by_legacy_polygons.items(), key=lambda pair: int(pair[0]))),
        },
        "itemsSha256": canonical_sha256(items),
        "items": items,
        "errors": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root")
    parser.add_argument("--training-truth-index")
    parser.add_argument("--validation-truth-index")
    parser.add_argument("--frozen-test-manifest")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify_report:
            report_path = Path(args.verify_report).resolve()
            existing = load_object(report_path)
            inputs = existing.get("inputs", {})
            replay_args = argparse.Namespace(
                dataset_root=inputs.get("datasetRoot"),
                training_truth_index=inputs.get("trainingTruthIndex"),
                validation_truth_index=inputs.get("validationTruthIndex"),
                frozen_test_manifest=inputs.get("frozenTestManifest"),
            )
            current = build_report(replay_args)
            if current != existing:
                raise ValueError("Report does not match current replayed evidence")
            print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
            return 0
        required = (args.dataset_root, args.training_truth_index, args.validation_truth_index, args.frozen_test_manifest, args.output)
        if any(not value for value in required):
            raise ValueError("Generation requires all input paths and --output")
        report = build_report(args)
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "decision": report["decision"], "output": str(output)}, ensure_ascii=False))
        return 0 if report["ok"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
