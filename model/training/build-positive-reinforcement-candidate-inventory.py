#!/usr/bin/env python3
"""Build a replayable inventory of source-isolated positive reinforcement candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Inventory unused, source-isolated nail-photo candidates.")
    value.add_argument("--source-screening-report")
    value.add_argument("--authorization")
    value.add_argument("--training-truth-index")
    value.add_argument("--validation-truth-index")
    value.add_argument("--frozen-test-manifest")
    value.add_argument("--source-root")
    value.add_argument("--output")
    value.add_argument("--verify-report")
    return value


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_file(value: str | None, field: str) -> Path:
    if not value:
        raise ValueError(f"Missing path: {field}")
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"Missing file for {field}: {path}")
    return path


def require_directory(value: str | None, field: str) -> Path:
    if not value:
        raise ValueError(f"Missing path: {field}")
    path = Path(value).resolve()
    if not path.is_dir():
        raise ValueError(f"Missing directory for {field}: {path}")
    return path


def require_list(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Expected object array: {field}")
    return value


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    screening_path = require_file(args.source_screening_report, "source-screening-report")
    authorization_path = require_file(args.authorization, "authorization")
    training_path = require_file(args.training_truth_index, "training-truth-index")
    validation_path = require_file(args.validation_truth_index, "validation-truth-index")
    test_path = require_file(args.frozen_test_manifest, "frozen-test-manifest")
    source_root = require_directory(args.source_root, "source-root")

    screening = load_object(screening_path)
    authorization = load_object(authorization_path)
    training = load_object(training_path)
    validation = load_object(validation_path)
    frozen_test = load_object(test_path)

    if screening.get("ok") is not True or screening.get("decision") != "source_screening_batch_pass":
        raise ValueError("Source screening is not complete")
    if authorization.get("ok") is not True or authorization.get("authorization", {}).get("status") != "confirmed":
        raise ValueError("Source authorization is not confirmed")
    if training.get("ok") is not True or training.get("decision") != "approved_unique_training_truth_index":
        raise ValueError("Training truth index is not approved")
    if validation.get("ok") is not True or validation.get("decision") != "approved_unique_validation_truth_index":
        raise ValueError("Validation truth index is not approved")
    if frozen_test.get("trainingUse") != "prohibited" or frozen_test.get("decision") != "frozen_reviewed_candidate_not_release_ready":
        raise ValueError("Frozen test manifest is not the protected evaluation snapshot")

    authorization_items = require_list(authorization.get("entries"), "authorization.entries")
    authorization_by_sha = {str(item.get("sha256", "")).lower(): item for item in authorization_items}
    if len(authorization_by_sha) != len(authorization_items):
        raise ValueError("Authorization contains duplicate image SHA-256 values")

    role_items = {
        "train": require_list(training.get("canonicalTruths"), "training.canonicalTruths"),
        "val": require_list(validation.get("canonicalTruths"), "validation.canonicalTruths"),
        "test": require_list(frozen_test.get("items"), "frozenTest.items"),
    }
    used_groups: dict[str, set[str]] = {role: set() for role in role_items}
    used_sha: dict[str, set[str]] = {role: set() for role in role_items}
    for role, items in role_items.items():
        for item in items:
            group = item.get("parentSourceGroup") or item.get("sourceGroup")
            image_sha = item.get("imageSha256") or item.get("sha256")
            if not isinstance(group, str) or not group:
                raise ValueError(f"Missing source group in {role} item")
            if not isinstance(image_sha, str) or len(image_sha) != 64:
                raise ValueError(f"Missing image SHA-256 in {role} item")
            used_groups[role].add(group)
            used_sha[role].add(image_sha.lower())

    all_used_groups = set().union(*used_groups.values())
    all_used_sha = set().union(*used_sha.values())
    screening_items = require_list(screening.get("items"), "screening.items")
    kept = [item for item in screening_items if item.get("decision") == "keep-for-annotation"]
    candidates: list[dict[str, Any]] = []
    excluded_by_group = 0
    excluded_by_sha = 0
    candidate_sha: set[str] = set()

    for item in sorted(kept, key=lambda value: (str(value.get("sourceGroup")), str(value.get("fileName")))):
        group = item.get("sourceGroup")
        image_sha = str(item.get("sha256", "")).lower()
        if group in all_used_groups:
            excluded_by_group += 1
            continue
        if image_sha in all_used_sha:
            excluded_by_sha += 1
            continue
        if image_sha in candidate_sha:
            raise ValueError(f"Duplicate candidate SHA-256: {image_sha}")
        candidate_sha.add(image_sha)
        authorized = authorization_by_sha.get(image_sha)
        if authorized is None:
            raise ValueError(f"Candidate missing from authorization: {item.get('fileName')}")
        if authorized.get("sourceGroup") != group or authorized.get("fileName") != item.get("fileName"):
            raise ValueError(f"Authorization identity mismatch: {item.get('fileName')}")
        image_path = source_root / str(item.get("fileName"))
        if not image_path.is_file():
            raise ValueError(f"Candidate image missing: {image_path}")
        if sha256_path(image_path).lower() != image_sha:
            raise ValueError(f"Candidate image SHA-256 mismatch: {image_path}")
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
            image.load()
        if width != authorized.get("width") or height != authorized.get("height"):
            raise ValueError(f"Candidate dimensions mismatch authorization: {image_path}")
        candidates.append(
            {
                "fileName": item["fileName"],
                "imagePath": str(image_path),
                "imageSha256": image_sha,
                "width": width,
                "height": height,
                "sourceGroup": group,
                "fullyVisibleNails": int(item.get("fullyVisibleNails") or 0),
                "sourceScreeningDecision": "keep-for-annotation",
                "sourceScreeningNote": item.get("note") or "",
                "candidateRole": "positive-reinforcement-candidate",
                "originalResolutionReview": "pending-reconfirmation",
                "exactTrainingAuthorization": "missing",
                "trainingUse": "prohibited",
            }
        )

    candidate_groups = sorted({item["sourceGroup"] for item in candidates})
    items_sha = canonical_sha256(candidates)
    return {
        "schemaVersion": 1,
        "ok": bool(candidates),
        "decision": "candidate_inventory_ready_for_original_resolution_review" if candidates else "hold_no_source_isolated_candidates",
        "inputs": {
            "sourceScreeningReport": str(screening_path),
            "sourceScreeningReportSha256": sha256_path(screening_path),
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_path(authorization_path),
            "trainingTruthIndex": str(training_path),
            "trainingTruthIndexSha256": sha256_path(training_path),
            "validationTruthIndex": str(validation_path),
            "validationTruthIndexSha256": sha256_path(validation_path),
            "frozenTestManifest": str(test_path),
            "frozenTestManifestSha256": sha256_path(test_path),
            "sourceRoot": str(source_root),
        },
        "policy": {
            "sourceGroupsAreAtomic": True,
            "existingTrainValTestGroupsExcluded": True,
            "existingTrainValTestImageHashesExcluded": True,
            "originalResolutionReviewRequired": True,
            "exactFileListCommercialTrainingAuthorizationRequired": True,
            "inventoryDoesNotGrantTrainingUse": True,
            "trainingUse": "prohibited",
        },
        "counts": {
            "screenedImages": len(screening_items),
            "keptForAnnotation": len(kept),
            "excludedBecauseSourceGroupAlreadyUsed": excluded_by_group,
            "excludedBecauseImageHashAlreadyUsed": excluded_by_sha,
            "candidateImages": len(candidates),
            "candidateSourceGroups": len(candidate_groups),
            "usedTrainSourceGroups": len(used_groups["train"]),
            "usedValidationSourceGroups": len(used_groups["val"]),
            "usedFrozenTestSourceGroups": len(used_groups["test"]),
        },
        "candidateSourceGroups": candidate_groups,
        "itemsSha256": items_sha,
        "items": candidates,
        "errors": [],
    }


def main() -> int:
    args = parser().parse_args()
    try:
        if args.verify_report:
            report_path = require_file(args.verify_report, "verify-report")
            existing = load_object(report_path)
            inputs = existing.get("inputs", {})
            replay_args = argparse.Namespace(
                source_screening_report=inputs.get("sourceScreeningReport"),
                authorization=inputs.get("authorization"),
                training_truth_index=inputs.get("trainingTruthIndex"),
                validation_truth_index=inputs.get("validationTruthIndex"),
                frozen_test_manifest=inputs.get("frozenTestManifest"),
                source_root=inputs.get("sourceRoot"),
            )
            current = build_report(replay_args)
            if current != existing:
                raise ValueError("Inventory report does not match current replayed evidence")
            print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
            return 0
        report = build_report(args)
        if not args.output:
            raise ValueError("Missing path: output")
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "decision": report["decision"], "output": str(output)}, ensure_ascii=False))
        return 0 if report["ok"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
