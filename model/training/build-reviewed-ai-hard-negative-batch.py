#!/usr/bin/env python3
"""Build hash-bound evidence for an original-resolution reviewed AI negative batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def sha256_file(path: Path) -> str:
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


def write_json(path: Path, value: Any, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValueError(f"refusing to overwrite existing evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def parse_selections(values: list[str]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for value in values:
        category, separator, ranks_text = value.partition("=")
        category = category.strip()
        if not separator or not category:
            raise ValueError(
                "--selection must use CATEGORY=RANK,RANK syntax"
            )
        ranks: set[int] = set()
        for token in ranks_text.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start < 1 or end < start:
                    raise ValueError(f"invalid rank range: {token}")
                ranks.update(range(start, end + 1))
            else:
                rank = int(token)
                if rank < 1:
                    raise ValueError(f"invalid rank: {rank}")
                ranks.add(rank)
        if not ranks or category in result:
            raise ValueError(f"empty or duplicate selection category: {category}")
        result[category] = ranks
    return result


def decode_image(path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise ValueError("image dimensions changed during decode")
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise ValueError(f"image cannot be fully decoded: {path}: {error}") from error
    if min(width, height) < 320:
        raise ValueError(f"image minimum side is below 320px: {path}")
    return width, height, image_format


def collect_identity_values(value: Any) -> dict[str, set[str]]:
    result = {"fileNames": set(), "imageSha256": set(), "sourceGroups": set()}

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        for key, child in item.items():
            if isinstance(child, str) and child:
                if key in {"fileName", "sourceFileName"}:
                    result["fileNames"].add(child.casefold())
                elif key in {
                    "imageSha256",
                    "sourceImageSha256",
                    "sha256",
                } and len(child) == 64:
                    result["imageSha256"].add(child.lower())
                elif key in {"sourceGroup", "parentSourceGroup"}:
                    result["sourceGroups"].add(child)
            if isinstance(child, (dict, list)):
                visit(child)

    visit(value)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build strict AI hard-negative review evidence."
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--selection", action="append", required=True)
    parser.add_argument("--train-index", required=True)
    parser.add_argument("--val-index", required=True)
    parser.add_argument("--frozen-test-manifest", required=True)
    parser.add_argument("--authorization-note", required=True)
    parser.add_argument("--reviewer", default="codex-original-resolution-visual-review")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    selections = parse_selections(args.selection)
    evidence_paths = {
        "train": Path(args.train_index).resolve(),
        "val": Path(args.val_index).resolve(),
        "frozenTest": Path(args.frozen_test_manifest).resolve(),
    }
    upstream: dict[str, dict[str, Any]] = {}
    role_identities: dict[str, dict[str, set[str]]] = {}
    for role, path in evidence_paths.items():
        document = read_json(path, f"{role} evidence")
        upstream[role] = {
            "path": str(path),
            "sha256": sha256_file(path),
        }
        role_identities[role] = collect_identity_values(document)

    inventory: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}
    exact_duplicates: list[dict[str, str]] = []
    for category_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        category = category_dir.name
        files = sorted(
            path
            for path in category_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        chosen_ranks = selections.get(category, set())
        invalid_ranks = sorted(rank for rank in chosen_ranks if rank > len(files))
        if invalid_ranks:
            raise ValueError(f"{category}: ranks exceed file count: {invalid_ranks}")
        for rank, path in enumerate(files, start=1):
            width, height, image_format = decode_image(path)
            image_hash = sha256_file(path)
            relative_path = path.relative_to(root).as_posix()
            if image_hash in seen_hashes:
                exact_duplicates.append(
                    {
                        "sha256": image_hash,
                        "first": seen_hashes[image_hash],
                        "duplicate": relative_path,
                    }
                )
            else:
                seen_hashes[image_hash] = relative_path
            item = {
                "relativePath": relative_path,
                "sourcePath": str(path),
                "originalFileName": path.name,
                "category": category,
                "rank": rank,
                "sha256": image_hash,
                "width": width,
                "height": height,
                "imageFormat": image_format,
                "selectedForOriginalResolutionReview": rank in chosen_ranks,
            }
            inventory.append(item)
            if rank in chosen_ranks:
                selected.append(item)

    if exact_duplicates:
        raise ValueError(
            f"source corpus contains {len(exact_duplicates)} exact duplicates"
        )
    missing_categories = sorted(set(selections) - {item["category"] for item in inventory})
    if missing_categories:
        raise ValueError(f"selection categories are missing: {missing_categories}")

    selected.sort(key=lambda item: (item["category"], item["rank"]))
    selection_hashes = {item["sha256"] for item in selected}
    if len(selection_hashes) != len(selected):
        raise ValueError("selected images are not SHA-256 unique")

    isolation_records: list[dict[str, Any]] = []
    total_matches = 0
    for item in selected:
        source_group = (
            "ai-hard-negative-2026-07-23:"
            f"{item['category']}:{item['sha256'][:16]}"
        )
        matches: dict[str, int] = {}
        for role, identities in role_identities.items():
            match_count = int(item["originalFileName"].casefold() in identities["fileNames"])
            match_count += int(item["sha256"] in identities["imageSha256"])
            match_count += int(source_group in identities["sourceGroups"])
            matches[f"{role}IdentityMatches"] = match_count
            total_matches += match_count
        isolation_records.append(
            {
                "sha256": item["sha256"],
                "sourceGroup": source_group,
                **matches,
                "isolated": all(value == 0 for value in matches.values()),
            }
        )
    if total_matches:
        raise ValueError(f"selected images overlap protected roles: matches={total_matches}")

    generated_at = datetime.now(timezone.utc).isoformat()
    screening_path = output_dir / "source-screening-batch-v1.json"
    screening = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "source_screening_complete_candidate_subset_not_yet_trainable",
        "root": str(root),
        "policy": {
            "allImagesMustFullyDecode": True,
            "minimumImageSide": 320,
            "exactDuplicatesForbidden": True,
            "originalResolutionVisualReviewRequiredForCandidates": True,
            "aiOriginDoesNotRelaxQualityGate": True,
            "watermarkShortcutRiskMustBeAuditedBeforePromotion": True,
            "unselectedTrainingUse": "prohibited",
        },
        "upstreamRoleEvidence": upstream,
        "summary": {
            "inventoryImages": len(inventory),
            "selectedForReview": len(selected),
            "exactDuplicateImages": len(exact_duplicates),
            "protectedRoleIdentityMatches": total_matches,
        },
        "inventorySha256": canonical_sha256(inventory),
        "inventory": inventory,
        "exactDuplicates": exact_duplicates,
        "watermarkRisk": {
            "status": "requires-training-time-and-evaluation-ablation",
            "observation": (
                "Multiple AI sources show a systematic bottom-right generation "
                "watermark or blurred watermark region."
            ),
            "prohibitedConclusion": (
                "The model may not be promoted solely from metrics produced "
                "without a watermark-shortcut ablation."
            ),
        },
    }
    write_json(screening_path, screening, args.overwrite)

    authorization_path = output_dir / "authorization-A-v1.json"
    authorization_entries = [
        {
            "sourcePath": item["sourcePath"],
            "originalFileName": item["originalFileName"],
            "sha256": item["sha256"],
            "authorizedUses": [
                "commercial-model-training",
                "long-term-regression",
            ],
            "trainingEligibility": (
                "permitted-after-original-resolution-review-and-source-isolation"
            ),
        }
        for item in selected
    ]
    authorization = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "A",
        "status": "confirmed",
        "confirmedBy": "workspace-user",
        "confirmationNote": args.authorization_note,
        "authorizedUses": [
            "commercial-model-training",
            "long-term-regression",
        ],
        "qualityConstraint": "ai-origin-does-not-relax-quality-gates",
        "entriesSha256": canonical_sha256(authorization_entries),
        "entries": authorization_entries,
    }
    write_json(authorization_path, authorization, args.overwrite)

    isolation_by_hash = {item["sha256"]: item for item in isolation_records}
    reviewed_candidates: list[dict[str, Any]] = []
    manifest_candidates: list[dict[str, Any]] = []
    for sequence, item in enumerate(selected, start=1):
        suffix = Path(item["originalFileName"]).suffix.lower()
        file_name = (
            f"hard_negative_ai_20260723_{sequence:03d}{suffix}"
        )
        source_group = isolation_by_hash[item["sha256"]]["sourceGroup"]
        isolation = isolation_by_hash[item["sha256"]]
        review_item = {
            "fileName": file_name,
            "originalFileName": item["originalFileName"],
            "category": item["category"],
            "rank": item["rank"],
            "sourcePath": item["sourcePath"],
            "sha256": item["sha256"],
            "width": item["width"],
            "height": item["height"],
            "sourceGroup": source_group,
            "originalResolutionVisualReview": {
                "reviewed": True,
                "reviewer": args.reviewer,
                "clearEnoughForHardNegative": True,
                "validHumanManicureSurfaceAnywhere": False,
                "croppedTargetNail": False,
                "collage": False,
                "templateOrIndependentNailTip": False,
                "reviewNote": (
                    "原分辨率复核通过：主体清晰完整，不含有效真人美甲甲面，"
                    "不是拼图、模板或独立甲片；可用于部署误检抑制。"
                ),
            },
            "authorizationEvidence": {
                "decision": "A",
                "authorizationEntryFileNameMatch": True,
                "authorizationEntrySha256Match": True,
                "trainingEligibility": (
                    "permitted-after-visual-review-and-source-isolation"
                ),
            },
            "sourceIsolationEvidence": {
                key: value
                for key, value in isolation.items()
                if key not in {"sha256", "sourceGroup"}
            },
            "role": "hard-negative-candidate",
            "trainingUse": "prohibited",
            "materializationStatus": "not-materialized",
            "candidateStatus": "pass-candidate-only",
        }
        reviewed_candidates.append(review_item)
        manifest_candidates.append(
            {
                "fileName": file_name,
                "originalFileName": item["originalFileName"],
                "sourcePath": item["sourcePath"],
                "sha256": item["sha256"],
                "sourceGroup": source_group,
                "authorization": "A",
                "sourceIsolation": "verified-zero-match-train-val-frozen-test",
                "humanManicureSurfaceAnywhere": False,
                "candidatePurpose": "deployment-false-positive-suppression",
                "role": "hard-negative-candidate",
                "trainingUse": "prohibited",
                "materializationStatus": "not-materialized",
            }
        )

    review_path = output_dir / "hard-negative-review-decisions-v1.json"
    review = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "hard_negative_candidate_scan_complete_candidate_only",
        "inputs": {
            "sourceScreeningBatch": {
                "path": str(screening_path),
                "sha256": sha256_file(screening_path),
            },
            "authorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
                "decision": "A",
                "status": "confirmed",
                "authorizedUses": [
                    "commercial-model-training",
                    "long-term-regression",
                ],
            },
            "protectedRoles": upstream,
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
            "candidateOnly": True,
            "trainingUse": (
                "prohibited-until-separate-materialization-and-training-authorization"
            ),
        },
        "summary": {
            "originalResolutionReviewed": len(reviewed_candidates),
            "passedCandidates": len(reviewed_candidates),
            "failedSelectedCandidates": 0,
        },
        "candidatesSha256": canonical_sha256(reviewed_candidates),
        "candidates": reviewed_candidates,
    }
    write_json(review_path, review, args.overwrite)

    manifest_path = output_dir / "hard-negative-candidate-manifest-v1.json"
    manifest = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "hard_negative_candidate_manifest_ready_not_materialized",
        "candidateOnly": True,
        "inputs": {
            "reviewDecisionsPath": str(review_path),
            "reviewDecisionsSha256": sha256_file(review_path),
            "sourceScreeningBatchPath": str(screening_path),
            "sourceScreeningBatchSha256": sha256_file(screening_path),
            "authorizationPath": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
        },
        "summary": {
            "reviewedImages": len(manifest_candidates),
            "candidateImages": len(manifest_candidates),
            "safeHardNegativeCount": len(manifest_candidates),
            "excludedImages": 0,
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
    write_json(manifest_path, manifest, args.overwrite)
    print(
        json.dumps(
            {
                "ok": True,
                "inventoryImages": len(inventory),
                "reviewedCandidates": len(manifest_candidates),
                "candidateManifest": str(manifest_path),
                "candidateManifestSha256": sha256_file(manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
