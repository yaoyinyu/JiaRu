#!/usr/bin/env python3
"""Finalize strict per-image decisions for an independent hard-negative batch.

The finalizer replays the workspace, authorization, protected-role evidence,
review-sheet hashes, current image bytes, and every CSV decision. It emits the
candidate-only schema consumed by ``finalize-reviewed-hard-negative-manifest.py``;
it never grants training use by itself.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ALLOWED_DECISIONS = {"pass", "exclude"}
ALLOWED_DEFECT_CODES = {
    "blur-or-low-detail",
    "cropped-or-incomplete-subject",
    "impossible-hand-topology",
    "valid-human-manicure-surface",
    "collage-template-or-independent-nail-tip",
    "not-useful-deployment-negative",
    "watermark-or-generator-marker",
    "other-quality-defect",
}
EXPECTED_CSV_FIELDS = (
    "reviewId",
    "fileName",
    "imageSha256",
    "width",
    "height",
    "sourceGroup",
    "decision",
    "defectCodes",
    "notes",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def require_sha256(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256_PATTERN.fullmatch(result):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return result


def require_current_file(path_value: Any, expected_hash: Any, label: str) -> Path:
    path = Path(str(path_value or "")).resolve()
    expected = require_sha256(expected_hash, f"{label} expected SHA-256")
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{label} SHA-256 drift: expected={expected} actual={actual}: {path}"
        )
    return path


def decode_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise ValueError("image dimensions changed during decode")
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise ValueError(f"image cannot be fully decoded: {path}: {error}") from error
    return width, height


def read_decisions(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != EXPECTED_CSV_FIELDS:
                raise ValueError(
                    f"decisions CSV fields differ from contract: {reader.fieldnames}"
                )
            return [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError(f"decisions CSV is unreadable: {path}: {error}") from error


def split_defects(value: str) -> list[str]:
    return sorted(
        {
            token.strip()
            for token in re.split(r"[;,|]", value)
            if token.strip()
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize original-resolution independent hard-negative review decisions."
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--reviewer",
        default="codex-original-resolution-visual-review",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    workspace_path = Path(args.workspace).resolve()
    decisions_path = Path(args.decisions).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = output_dir / "hard-negative-review-decisions-v1.json"
    manifest_path = output_dir / "hard-negative-candidate-manifest-v1.json"
    for path in (review_path, manifest_path):
        if path.exists() and not args.overwrite:
            raise ValueError(f"refusing to overwrite existing evidence: {path}")

    workspace = read_json(workspace_path, "review workspace")
    if (
        workspace.get("ok") is not True
        or workspace.get("decision") != "review_workspace_ready_no_quality_decisions"
    ):
        raise ValueError("workspace is not a pending quality-review workspace")
    policy = workspace.get("policy")
    required_policy = {
        "aiOriginDoesNotRelaxQualityGate": True,
        "reviewEveryImageAtOriginalResolution": True,
        "reviewSheetsUseSourcePixelsWithoutResampling": True,
        "reviewSheetsDoNotReplaceBoundSourceFiles": True,
        "rejectLowQualityOrBlur": True,
        "rejectImpossibleOrIncompleteTopology": True,
        "rejectValidHumanManicureSurfaceAnywhere": True,
        "rejectCollageTemplateOrIndependentNailTips": True,
        "authorizationDoesNotAssignTrainingRole": True,
        "trainingUseBeforeFinalization": "prohibited",
    }
    if not isinstance(policy, dict):
        raise ValueError("workspace policy is missing")
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"workspace policy {key} differs from the required value")

    inputs = workspace.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("workspace inputs are missing")
    authorization_input = inputs.get("authorization")
    machine_audit_input = inputs.get("machineAudit")
    protected_inputs = inputs.get("protectedRoles")
    if not all(
        isinstance(value, dict)
        for value in (authorization_input, machine_audit_input, protected_inputs)
    ):
        raise ValueError("workspace authorization/audit/protected-role inputs are missing")
    authorization_path = require_current_file(
        authorization_input.get("path"),
        authorization_input.get("sha256"),
        "authorization evidence",
    )
    machine_audit_path = require_current_file(
        machine_audit_input.get("path"),
        machine_audit_input.get("sha256"),
        "machine audit",
    )
    authorization = read_json(authorization_path, "authorization evidence")
    if (
        authorization.get("ok") is not True
        or authorization.get("decision") != "A"
        or authorization.get("status") != "confirmed"
        or authorization.get("currentTrainingUse") != "prohibited"
        or "commercial-model-training"
        not in list(authorization.get("authorizedUses") or [])
        or authorization.get("qualityConstraint")
        != "authorization-does-not-relax-quality-gates"
    ):
        raise ValueError("authorization no longer satisfies the candidate quality contract")
    authorization_entries = authorization.get("entries")
    if not isinstance(authorization_entries, list):
        raise ValueError("authorization entries are missing")
    if canonical_sha256(authorization_entries) != require_sha256(
        authorization.get("entriesSha256"), "authorization entriesSha256"
    ):
        raise ValueError("authorization entries SHA-256 drift")
    authorization_by_name = {
        str(item.get("fileName")): item
        for item in authorization_entries
        if isinstance(item, dict)
    }
    machine_audit = read_json(machine_audit_path, "machine audit")
    audit_records = machine_audit.get("records")
    if not isinstance(audit_records, list) or machine_audit.get("decodeFailures"):
        raise ValueError("machine audit records are invalid")
    audit_by_name = {
        str(item.get("fileName")): item for item in audit_records if isinstance(item, dict)
    }

    if not isinstance(protected_inputs, dict):
        raise ValueError("protected role inputs are missing")
    for role in ("train", "val", "frozenTest"):
        value = protected_inputs.get(role)
        if not isinstance(value, dict):
            raise ValueError(f"protected role input is missing: {role}")
        require_current_file(value.get("path"), value.get("sha256"), f"{role} evidence")

    sheets = workspace.get("reviewSheets")
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("workspace review sheets are missing")
    if canonical_sha256(sheets) != require_sha256(
        workspace.get("reviewSheetsSha256"), "reviewSheetsSha256"
    ):
        raise ValueError("workspace review-sheet index SHA-256 drift")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise ValueError("workspace review-sheet record must be an object")
        require_current_file(sheet.get("path"), sheet.get("sha256"), "review sheet")
        for sheet_item in list(sheet.get("items") or []):
            if sheet_item.get("pixelScale") != "1:1-no-resampling":
                raise ValueError("review sheet contains a resampled source item")

    items = workspace.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("workspace items are missing")
    if canonical_sha256(items) != require_sha256(
        workspace.get("itemsSha256"), "workspace itemsSha256"
    ):
        raise ValueError("workspace items SHA-256 drift")
    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("workspace item must be an object")
        review_id = str(item.get("reviewId") or "")
        if not review_id or review_id in item_by_id:
            raise ValueError(f"duplicate or missing reviewId: {review_id!r}")
        item_by_id[review_id] = item

    rows = read_decisions(decisions_path)
    if len(rows) != len(items):
        raise ValueError(
            f"decision coverage differs from workspace: rows={len(rows)} items={len(items)}"
        )
    row_by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        review_id = str(row.get("reviewId") or "").strip()
        if not review_id or review_id in row_by_id:
            raise ValueError(f"duplicate or missing decision reviewId: {review_id!r}")
        row_by_id[review_id] = row
    if set(row_by_id) != set(item_by_id):
        raise ValueError("decision reviewIds differ from workspace")

    reviewed_candidates: list[dict[str, Any]] = []
    manifest_candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []
    for review_id, item in item_by_id.items():
        row = row_by_id[review_id]
        file_name = str(item["fileName"])
        image_hash = require_sha256(item.get("imageSha256"), f"{file_name} workspace hash")
        source_path = Path(str(item.get("sourcePath") or "")).resolve()
        if (
            row.get("fileName") != file_name
            or row.get("imageSha256") != image_hash
            or row.get("width") != str(item.get("width"))
            or row.get("height") != str(item.get("height"))
            or row.get("sourceGroup") != item.get("sourceGroup")
        ):
            raise ValueError(f"{review_id}: decision identity differs from workspace")
        if not source_path.is_file() or sha256_file(source_path) != image_hash:
            raise ValueError(f"{file_name}: current image SHA-256 drift")
        width, height = decode_dimensions(source_path)
        if width != item.get("width") or height != item.get("height"):
            raise ValueError(f"{file_name}: current dimensions differ from workspace")
        authorized = authorization_by_name.get(file_name)
        audited = audit_by_name.get(file_name)
        if (
            not isinstance(authorized, dict)
            or not isinstance(audited, dict)
            or authorized.get("sha256") != image_hash
            or audited.get("sha256") != image_hash
        ):
            raise ValueError(f"{file_name}: authorization or machine-audit identity mismatch")
        isolation = item.get("sourceIsolationEvidence")
        if not isinstance(isolation, dict) or isolation.get("isolated") is not True:
            raise ValueError(f"{file_name}: source isolation is not proven")
        for key, value in isolation.items():
            if key.endswith("Matches") and value != 0:
                raise ValueError(f"{file_name}: source isolation {key} is not zero")

        decision = str(row.get("decision") or "").strip().lower()
        defects = split_defects(str(row.get("defectCodes") or ""))
        notes = str(row.get("notes") or "").strip()
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"{review_id}: decision must be pass or exclude")
        unknown_defects = sorted(set(defects) - ALLOWED_DEFECT_CODES)
        if unknown_defects:
            raise ValueError(f"{review_id}: unknown defect codes: {unknown_defects}")
        if not notes:
            raise ValueError(f"{review_id}: review notes are required")
        if decision == "pass" and defects:
            raise ValueError(f"{review_id}: passing review cannot contain defect codes")
        if decision == "exclude" and not defects:
            raise ValueError(f"{review_id}: excluded review requires at least one defect code")

        normalized = {
            "reviewId": review_id,
            "fileName": file_name,
            "imageSha256": image_hash,
            "sourceGroup": item["sourceGroup"],
            "decision": decision,
            "defectCodes": defects,
            "notes": notes,
        }
        normalized_rows.append(normalized)
        if decision == "exclude":
            exclusions.append(
                {
                    **normalized,
                    "trainingUse": "prohibited",
                    "candidateStatus": "quality-excluded",
                }
            )
            continue

        review_item = {
            "fileName": file_name,
            "originalFileName": file_name,
            "category": item["promptFamily"],
            "rank": item["promptVariant"],
            "sourcePath": str(source_path),
            "sha256": image_hash,
            "width": width,
            "height": height,
            "sourceGroup": item["sourceGroup"],
            "originalResolutionVisualReview": {
                "reviewed": True,
                "reviewer": args.reviewer,
                "reviewMode": "1x-source-pixels-and-bound-original-source",
                "clearEnoughForHardNegative": True,
                "validHumanManicureSurfaceAnywhere": False,
                "croppedTargetNail": False,
                "collage": False,
                "templateOrIndependentNailTip": False,
                "reviewNote": notes,
            },
            "authorizationEvidence": {
                "decision": "A",
                "authorizationEntryFileNameMatch": True,
                "authorizationEntrySha256Match": True,
                "trainingEligibility": (
                    "permitted-after-visual-review-and-source-isolation"
                ),
            },
            "sourceIsolationEvidence": isolation,
            "role": "hard-negative-candidate",
            "trainingUse": "prohibited",
            "materializationStatus": "not-materialized",
            "candidateStatus": "pass-candidate-only",
        }
        reviewed_candidates.append(review_item)
        manifest_candidates.append(
            {
                "fileName": file_name,
                "originalFileName": file_name,
                "sourcePath": str(source_path),
                "sha256": image_hash,
                "sourceGroup": item["sourceGroup"],
                "authorization": "A",
                "sourceIsolation": "verified-zero-match-train-val-frozen-test",
                "humanManicureSurfaceAnywhere": False,
                "candidatePurpose": "deployment-false-positive-suppression",
                "role": "hard-negative-candidate",
                "trainingUse": "prohibited",
                "materializationStatus": "not-materialized",
            }
        )

    normalized_rows.sort(key=lambda item: item["reviewId"])
    reviewed_candidates.sort(key=lambda item: item["fileName"])
    manifest_candidates.sort(key=lambda item: item["fileName"])
    exclusions.sort(key=lambda item: item["reviewId"])
    generated_at = datetime.now(timezone.utc).isoformat()
    authorization_summary = {
        "path": str(authorization_path),
        "sha256": sha256_file(authorization_path),
        "decision": "A",
        "status": "confirmed",
        "authorizedUses": list(authorization.get("authorizedUses") or []),
    }
    review = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "hard_negative_candidate_scan_complete_candidate_only",
        "inputs": {
            "sourceScreeningBatch": {
                "path": str(workspace_path),
                "sha256": sha256_file(workspace_path),
            },
            "authorization": authorization_summary,
            "protectedRoles": protected_inputs,
            "decisions": {
                "path": str(decisions_path),
                "sha256": sha256_file(decisions_path),
            },
        },
        "policy": {
            "candidateMustBeClear": True,
            "candidateMustContainNoValidHumanManicureSurfaceAnywhere": True,
            "candidateMustBeUsefulForDeploymentFalsePositiveSuppression": True,
            "candidateMustHaveAuthorizationA": True,
            "candidateMustBeSourceIsolatedFromTrainValAndFrozenTest": True,
            "rejectTemplates": True,
            "rejectIndependentNailTips": True,
            "rejectCollages": True,
            "rejectLowQuality": True,
            "rejectCroppedSources": True,
            "rejectImpossibleOrIncompleteTopology": True,
            "candidateOnly": True,
            "trainingUse": "prohibited-until-separate-materialization-and-training-authorization",
        },
        "summary": {
            "originalResolutionReviewed": len(items),
            "passedCandidates": len(reviewed_candidates),
            "failedSelectedCandidates": len(exclusions),
        },
        "normalizedDecisionsSha256": canonical_sha256(normalized_rows),
        "exclusionsSha256": canonical_sha256(exclusions),
        "exclusions": exclusions,
        "candidatesSha256": canonical_sha256(reviewed_candidates),
        "candidates": reviewed_candidates,
    }
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "hard_negative_candidate_manifest_ready_not_materialized",
        "candidateOnly": True,
        "inputs": {
            "reviewDecisionsPath": str(review_path),
            "reviewDecisionsSha256": sha256_file(review_path),
            "sourceScreeningBatchPath": str(workspace_path),
            "sourceScreeningBatchSha256": sha256_file(workspace_path),
            "authorizationPath": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
        },
        "summary": {
            "reviewedImages": len(items),
            "candidateImages": len(manifest_candidates),
            "safeHardNegativeCount": len(manifest_candidates),
            "excludedImages": len(exclusions),
        },
        "candidatesSha256": canonical_sha256(manifest_candidates),
        "candidates": manifest_candidates,
        "gates": {
            "allCandidatesOriginalResolutionReviewed": True,
            "allSourceImageHashesMatchBoundScreeningEvidence": True,
            "allRelevantShardReportAndDecisionHashesMatch": True,
            "authorizationAConfirmed": True,
            "candidateSourceIsolatedFromTrain": True,
            "candidateSourceIsolatedFromVal": True,
            "candidateSourceIsolatedFromFrozenTest": True,
            "officialDatasetUnchanged": True,
            "sharedSplitUnchanged": True,
            "trainingStillProhibited": True,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "reviewedImages": len(items),
                "passedCandidates": len(manifest_candidates),
                "excludedImages": len(exclusions),
                "reviewDecisions": str(review_path),
                "candidateManifest": str(manifest_path),
                "candidateManifestSha256": sha256_file(manifest_path),
                "trainingUse": "prohibited",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
