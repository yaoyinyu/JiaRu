#!/usr/bin/env python3
"""Build a hash-bound 33-image release-test role replacement manifest.

The builder keeps or excludes every original release-test candidate after
original-resolution review, then atomically withdraws complete, unmaterialized
train source groups to replace the exclusions.  It never materializes images,
grants training use, or overwrites an existing output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_RELEASE_IMAGES = 33
EXPECTED_TRAIN_TRUTH_IMAGES = 100
EXPECTED_VALIDATION_TRUTH_IMAGES = 30
EXPECTED_FROZEN_RELEASE_IMAGES = 67
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PLAN_DECISION = "first_annotation_batch_plan_ready_mask_review_required"
SCREENING_DECISION = "source_screening_batch_pass"
REVIEW_DECISION = "reviewed_release_test_role_replacements"
OUTPUT_DECISION = "release_test_role_replacement_manifest_ready_candidate_only"
RELEASE_ROLE = "independent-release-test"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def require_nonempty(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{label} is missing")
    return result


def require_sha256(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256_PATTERN.fullmatch(result):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return result


def require_positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def require_items(document: dict[str, Any], key: str, label: str) -> list[dict[str, Any]]:
    raw_items = document.get(key)
    if not isinstance(raw_items, list):
        raise ValueError(f"{label}.{key} must be an array")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{label}.{key}[{index}] must be an object")
        items.append(item)
    return items


def unique_by_file_name(items: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items, start=1):
        file_name = require_nonempty(item.get("fileName"), f"{label}[{index}].fileName")
        if Path(file_name).name != file_name or "/" in file_name or "\\" in file_name:
            raise ValueError(f"{label}[{index}].fileName must be a basename: {file_name!r}")
        if file_name in result:
            raise ValueError(f"duplicate {label} fileName: {file_name}")
        result[file_name] = item
    return result


def identity(item: dict[str, Any], hash_key: str = "sha256") -> tuple[str, str, str]:
    return (
        require_nonempty(item.get("fileName"), "identity fileName"),
        require_sha256(item.get(hash_key), "identity image SHA-256"),
        require_nonempty(item.get("sourceGroup"), "identity sourceGroup"),
    )


def identity_sets(
    items: list[dict[str, Any]], label: str, hash_key: str = "imageSha256"
) -> dict[str, set[str]]:
    names: set[str] = set()
    hashes: set[str] = set()
    groups: set[str] = set()
    for index, item in enumerate(items, start=1):
        file_name = require_nonempty(item.get("fileName"), f"{label}[{index}].fileName")
        image_hash = require_sha256(item.get(hash_key), f"{label}[{index}] image SHA-256")
        source_group = require_nonempty(
            item.get("sourceGroup"), f"{label}[{index}].sourceGroup"
        )
        names.add(file_name)
        hashes.add(image_hash)
        groups.add(source_group)
    return {"fileName": names, "imageSha256": hashes, "sourceGroup": groups}


def frozen_identity_sets(items: list[dict[str, Any]]) -> dict[str, set[str]]:
    identities = identity_sets(items, "frozen release item")
    for index, item in enumerate(items, start=1):
        parent_file = str(item.get("parentFileName") or "").strip()
        parent_group = str(item.get("parentSourceGroup") or "").strip()
        if parent_file:
            identities["fileName"].add(parent_file)
        if parent_group:
            identities["sourceGroup"].add(parent_group)
        if item.get("trainingUse") != "prohibited":
            raise ValueError(
                f"frozen release item {index} must remain trainingUse=prohibited"
            )
    return identities


def ensure_zero_overlap(
    items: list[dict[str, Any]],
    other: dict[str, set[str]],
    label: str,
    hash_key: str = "sha256",
) -> None:
    overlaps: dict[str, list[str]] = {"fileName": [], "imageSha256": [], "sourceGroup": []}
    for item in items:
        file_name, image_hash, source_group = identity(item, hash_key)
        if file_name in other["fileName"]:
            overlaps["fileName"].append(file_name)
        if image_hash in other["imageSha256"]:
            overlaps["imageSha256"].append(image_hash)
        if source_group in other["sourceGroup"]:
            overlaps["sourceGroup"].append(source_group)
    populated = {key: sorted(set(values)) for key, values in overlaps.items() if values}
    if populated:
        raise ValueError(f"{label} identity overlap is not zero: {populated}")


def input_record(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def validate_truth_index(
    document: dict[str, Any], label: str, expected_images: int
) -> list[dict[str, Any]]:
    if document.get("ok") is not True or document.get("decision") not in {
        "approved_unique_training_truth_index",
        "approved_unique_validation_truth_index",
    }:
        raise ValueError(f"{label} must be a passing unique truth index")
    summary = document.get("summary")
    if not isinstance(summary, dict) or summary.get("conflictingImageCount") != 0:
        raise ValueError(f"{label} must report conflictingImageCount=0")
    items = require_items(document, "canonicalTruths", label)
    expected = summary.get("uniqueImageCount")
    if expected != len(items):
        raise ValueError(f"{label} uniqueImageCount differs from canonicalTruths")
    if len(items) != expected_images:
        raise ValueError(
            f"{label} must contain exactly {expected_images} canonical truths; found {len(items)}"
        )
    return items


def normalize_plan_item(item: dict[str, Any], label: str) -> dict[str, Any]:
    file_name, image_hash, source_group = identity(item)
    nails = require_positive_int(item.get("fullyVisibleNails"), f"{label} complete nail count")
    if item.get("trainingUse") != "prohibited":
        raise ValueError(f"{label} must remain trainingUse=prohibited")
    if item.get("annotationTruthStatus") != "not-started":
        raise ValueError(f"{label} must remain annotationTruthStatus=not-started")
    return {
        "fileName": file_name,
        "sha256": image_hash,
        "sourceGroup": source_group,
        "assignedRole": require_nonempty(item.get("assignedRole"), f"{label} assignedRole"),
        "firstAnnotationBatch": item.get("firstAnnotationBatch") is True,
        "fullyVisibleNails": nails,
        "trainingUse": "prohibited",
        "annotationTruthStatus": "not-started",
    }


def validate_review_item(
    review: dict[str, Any], plan_item: dict[str, Any], label: str
) -> tuple[str, str]:
    decision = str(review.get("decision") or "")
    if decision not in {"keep", "exclude"}:
        raise ValueError(f"{label} decision must be keep or exclude")
    if review.get("originalResolutionReviewed") is not True:
        raise ValueError(f"{label} must set originalResolutionReviewed=true")
    reason = require_nonempty(review.get("reason"), f"{label} reason")
    reviewed_hash = require_sha256(review.get("sha256"), f"{label} SHA-256")
    reviewed_group = require_nonempty(review.get("sourceGroup"), f"{label} sourceGroup")
    reviewed_nails = require_positive_int(
        review.get("fullyVisibleNails"), f"{label} complete nail count"
    )
    if (
        reviewed_hash != plan_item["sha256"]
        or reviewed_group != plan_item["sourceGroup"]
        or reviewed_nails != plan_item["fullyVisibleNails"]
    ):
        raise ValueError(f"{label} identity or complete nail count differs from the plan")
    return decision, reason


def write_transactionally(output_path: Path, report: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(temporary_path, output_path)
        except FileExistsError as error:
            raise FileExistsError(
                f"output already exists and will not be overwritten: {output_path}"
            ) from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build(
    args: argparse.Namespace, *, require_new_output: bool = True
) -> dict[str, Any]:
    paths = {
        "firstAnnotationPlan": Path(args.first_annotation_plan).resolve(),
        "authorization": Path(args.authorization).resolve(),
        "screeningFinal": Path(args.screening_final).resolve(),
        "trainingTruthIndex": Path(args.training_truth_index).resolve(),
        "validationTruthIndex": Path(args.validation_truth_index).resolve(),
        "frozenReleaseTestManifest": Path(args.frozen_release_test_manifest).resolve(),
        "reviewDecisions": Path(args.review_decisions).resolve(),
    }
    output_path = Path(args.output).resolve()
    if require_new_output and output_path.exists():
        raise FileExistsError(f"output already exists and will not be overwritten: {output_path}")
    resolved_inputs = {str(path).casefold() for path in paths.values()}
    if str(output_path).casefold() in resolved_inputs:
        raise ValueError("output must not overwrite an input evidence file")
    for label, path in paths.items():
        if not path.is_file():
            raise ValueError(f"{label} is missing: {path}")
    bound_input_records = {label: input_record(path) for label, path in paths.items()}

    plan = read_json(paths["firstAnnotationPlan"], "first annotation plan")
    authorization = read_json(paths["authorization"], "authorization evidence")
    screening = read_json(paths["screeningFinal"], "screening final")
    training_truth = read_json(paths["trainingTruthIndex"], "training truth index")
    validation_truth = read_json(paths["validationTruthIndex"], "validation truth index")
    frozen = read_json(paths["frozenReleaseTestManifest"], "frozen release-test manifest")
    reviews = read_json(paths["reviewDecisions"], "review decisions")

    if plan.get("ok") is not True or plan.get("decision") != PLAN_DECISION:
        raise ValueError("first annotation plan is not a passing role plan")
    policy = plan.get("policy")
    if not isinstance(policy, dict) or policy.get("sourceGroupAtomicAcrossRoles") is not True:
        raise ValueError("first annotation plan must guarantee sourceGroupAtomicAcrossRoles")
    plan_inputs = plan.get("inputs")
    if not isinstance(plan_inputs, dict):
        raise ValueError("first annotation plan inputs are missing")
    if plan_inputs.get("authorizationSha256") != bound_input_records["authorization"]["sha256"]:
        raise ValueError("first annotation plan does not bind the current authorization evidence")
    if plan_inputs.get("screeningBatchSha256") != bound_input_records["screeningFinal"]["sha256"]:
        raise ValueError("first annotation plan does not bind the current screening final")

    authorization_block = authorization.get("authorization")
    if (
        authorization.get("ok") is not True
        or not isinstance(authorization_block, dict)
        or authorization_block.get("decision") != "A"
        or authorization_block.get("status") != "confirmed"
        or "independent-release-test"
        not in set(authorization_block.get("authorizedUses") or [])
    ):
        raise ValueError("confirmed authorization A must permit independent-release-test")
    authorization_items = require_items(authorization, "entries", "authorization")
    if authorization.get("entriesSha256") != canonical_sha256(authorization_items):
        raise ValueError("authorization entriesSha256 mismatch")
    authorization_by_name = unique_by_file_name(authorization_items, "authorization entry")

    if screening.get("ok") is not True or screening.get("decision") != SCREENING_DECISION:
        raise ValueError("screening final is not a passing source-screening batch")
    screening_items = require_items(screening, "items", "screening final")
    screening_by_name = unique_by_file_name(screening_items, "screening item")
    screening_keep_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in screening_items:
        if item.get("decision") == "keep-for-annotation":
            source_group = require_nonempty(
                item.get("sourceGroup"), "screening keep sourceGroup"
            )
            screening_keep_by_group.setdefault(source_group, []).append(item)

    plan_raw_items = require_items(plan, "items", "first annotation plan")
    plan_by_name_raw = unique_by_file_name(plan_raw_items, "plan item")
    plan_by_name = {
        name: normalize_plan_item(item, f"plan item {name}")
        for name, item in plan_by_name_raw.items()
    }
    plan_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in plan_by_name.values():
        plan_by_group.setdefault(item["sourceGroup"], []).append(item)

    original_items = sorted(
        (item for item in plan_by_name.values() if item["assignedRole"] == RELEASE_ROLE),
        key=lambda item: item["fileName"],
    )
    if len(original_items) != EXPECTED_RELEASE_IMAGES:
        raise ValueError(
            f"original release role must contain exactly {EXPECTED_RELEASE_IMAGES} images; "
            f"found {len(original_items)}"
        )
    original_names = {item["fileName"] for item in original_items}

    if reviews.get("ok") is not True or reviews.get("decision") != REVIEW_DECISION:
        raise ValueError(f"review decisions must be passing with decision={REVIEW_DECISION}")
    review_policy = reviews.get("policy")
    required_review_policy = {
        "originalResolutionReviewCompleted": True,
        "completeVisibleNailSurfaceRequired": True,
        "sourceGroupAtomicReplacementRequired": True,
    }
    if not isinstance(review_policy, dict) or any(
        review_policy.get(key) is not expected
        for key, expected in required_review_policy.items()
    ):
        raise ValueError("review decisions policy does not assert all required review gates")
    review_items = require_items(reviews, "items", "review decisions")
    review_by_name = unique_by_file_name(review_items, "review decision")
    review_names = set(review_by_name)
    missing_original = sorted(original_names - review_names)
    if missing_original:
        raise ValueError(f"original 33 review coverage is incomplete: missing={missing_original}")

    unsupported = sorted(review_names - set(plan_by_name))
    if unsupported:
        raise ValueError(f"review decisions contain files outside the plan: {unsupported}")

    original_kept: list[dict[str, Any]] = []
    original_excluded: list[dict[str, Any]] = []
    reviewed_replacements: list[dict[str, Any]] = []
    review_reasons: dict[str, str] = {}
    for file_name, review in review_by_name.items():
        plan_item = plan_by_name[file_name]
        decision, reason = validate_review_item(review, plan_item, f"review {file_name}")
        review_reasons[file_name] = reason
        if file_name in original_names:
            target = original_kept if decision == "keep" else original_excluded
            target.append(plan_item)
        else:
            if plan_item["assignedRole"] != "train":
                raise ValueError(
                    f"replacement must come from assignedRole=train: {file_name} "
                    f"role={plan_item['assignedRole']}"
                )
            if decision != "keep":
                raise ValueError(f"replacement review must be keep: {file_name}")
            reviewed_replacements.append(plan_item)

    original_kept.sort(key=lambda item: item["fileName"])
    original_excluded.sort(key=lambda item: item["fileName"])
    reviewed_replacements.sort(key=lambda item: item["fileName"])
    replacement_groups = sorted({item["sourceGroup"] for item in reviewed_replacements})
    reviewed_replacement_names = {item["fileName"] for item in reviewed_replacements}
    for source_group in replacement_groups:
        group_items = plan_by_group.get(source_group, [])
        group_names = {item["fileName"] for item in group_items}
        screening_group_names = {
            require_nonempty(item.get("fileName"), "screening group fileName")
            for item in screening_keep_by_group.get(source_group, [])
        }
        if not group_items:
            raise ValueError(f"replacement source group is missing from plan: {source_group}")
        if any(item["assignedRole"] != "train" for item in group_items):
            raise ValueError(f"replacement source group is not wholly assignedRole=train: {source_group}")
        if any(item["firstAnnotationBatch"] for item in group_items):
            raise ValueError(
                f"replacement source group contains firstAnnotationBatch=true: {source_group}"
            )
        if group_names != screening_group_names:
            raise ValueError(
                "replacement source group is incomplete against screening evidence: "
                f"{source_group}; missingFromPlan={sorted(screening_group_names - group_names)}; "
                f"extraInPlan={sorted(group_names - screening_group_names)}"
            )
        if not group_names.issubset(reviewed_replacement_names):
            missing = sorted(group_names - reviewed_replacement_names)
            raise ValueError(
                f"replacement source group is only partially reviewed: {source_group}; missing={missing}"
            )

    image_root_value = args.image_root or authorization.get("root")
    image_root = Path(require_nonempty(image_root_value, "image root")).resolve()
    if not image_root.is_dir():
        raise ValueError(f"image root is missing: {image_root}")

    all_reviewed_plan_items = [plan_by_name[name] for name in sorted(review_by_name)]
    for item in all_reviewed_plan_items:
        file_name = item["fileName"]
        authorized = authorization_by_name.get(file_name)
        if authorized is None:
            raise ValueError(f"authorization entry is missing: {file_name}")
        authorized_uses = set(authorized.get("authorizedUses") or [])
        if (
            authorized.get("sha256") != item["sha256"]
            or authorized.get("sourceGroup") != item["sourceGroup"]
            or "independent-release-test" not in authorized_uses
            or authorized.get("trainingUse") != "prohibited"
        ):
            raise ValueError(f"authorization identity/use/state mismatch: {file_name}")
        screened = screening_by_name.get(file_name)
        if screened is None:
            raise ValueError(f"screening entry is missing: {file_name}")
        if (
            screened.get("sha256") != item["sha256"]
            or screened.get("sourceGroup") != item["sourceGroup"]
            or screened.get("decision") != "keep-for-annotation"
            or screened.get("fullyVisibleNails") != item["fullyVisibleNails"]
            or screened.get("trainingUse") != "prohibited"
        ):
            raise ValueError(f"screening identity/keep/complete-nail replay failed: {file_name}")
        source_path = image_root / file_name
        if not source_path.is_file():
            raise ValueError(f"current source image is missing: {source_path}")
        actual_hash = sha256_file(source_path)
        if actual_hash != item["sha256"]:
            raise ValueError(
                f"current source image SHA-256 drift: {file_name}; "
                f"expected={item['sha256']} actual={actual_hash}"
            )

    training_truth_items = validate_truth_index(
        training_truth, "training truth index", EXPECTED_TRAIN_TRUTH_IMAGES
    )
    validation_truth_items = validate_truth_index(
        validation_truth, "validation truth index", EXPECTED_VALIDATION_TRUTH_IMAGES
    )
    frozen_items = require_items(frozen, "items", "frozen release-test manifest")
    if frozen.get("trainingUse") != "prohibited":
        raise ValueError("frozen release-test manifest must remain trainingUse=prohibited")
    if frozen.get("itemsSha256") != canonical_sha256(frozen_items):
        raise ValueError("frozen release-test manifest itemsSha256 mismatch")
    frozen_counts = frozen.get("counts")
    if not isinstance(frozen_counts, dict) or frozen_counts.get("images") != len(frozen_items):
        raise ValueError("frozen release-test manifest image count differs from items")
    if len(frozen_items) != EXPECTED_FROZEN_RELEASE_IMAGES:
        raise ValueError(
            f"frozen release-test manifest must contain exactly "
            f"{EXPECTED_FROZEN_RELEASE_IMAGES} images; found {len(frozen_items)}"
        )

    final_plan_items = sorted(
        [*original_kept, *reviewed_replacements], key=lambda item: item["fileName"]
    )
    if len(reviewed_replacements) != len(original_excluded):
        raise ValueError(
            "replacement count must equal excluded original count: "
            f"excluded={len(original_excluded)} replacements={len(reviewed_replacements)}"
        )
    if len(final_plan_items) != EXPECTED_RELEASE_IMAGES:
        raise ValueError(
            f"final release-test role must contain exactly {EXPECTED_RELEASE_IMAGES} images; "
            f"found {len(final_plan_items)}"
        )
    final_names = [item["fileName"] for item in final_plan_items]
    final_hashes = [item["sha256"] for item in final_plan_items]
    if len(set(final_names)) != len(final_names) or len(set(final_hashes)) != len(final_hashes):
        raise ValueError("final release-test role contains duplicate fileName or image SHA-256")

    train_identities = identity_sets(training_truth_items, "training truth")
    val_identities = identity_sets(validation_truth_items, "validation truth")
    frozen_identities = frozen_identity_sets(frozen_items)
    ensure_zero_overlap(final_plan_items, train_identities, "final vs training truth")
    ensure_zero_overlap(final_plan_items, val_identities, "final vs validation truth")
    ensure_zero_overlap(final_plan_items, frozen_identities, "final vs frozen release test")
    retained_identities = identity_sets(original_kept, "retained original", hash_key="sha256")
    ensure_zero_overlap(
        reviewed_replacements,
        retained_identities,
        "replacements vs retained original release",
    )

    final_items: list[dict[str, Any]] = []
    for item in final_plan_items:
        is_replacement = item["fileName"] in reviewed_replacement_names
        final_items.append(
            {
                "fileName": item["fileName"],
                "imageSha256": item["sha256"],
                "sourceGroup": item["sourceGroup"],
                "assignedRole": RELEASE_ROLE,
                "originalAssignedRole": item["assignedRole"],
                "roleOrigin": "withdrawn-train-replacement" if is_replacement else "original-release-keep",
                "fullyVisibleNails": item["fullyVisibleNails"],
                "originalResolutionReviewed": True,
                "reviewReason": review_reasons[item["fileName"]],
                "trainingUse": "prohibited",
                "annotationTruthStatus": "not-started",
            }
        )

    excluded_items = [
        {
            "fileName": item["fileName"],
            "imageSha256": item["sha256"],
            "sourceGroup": item["sourceGroup"],
            "fullyVisibleNails": item["fullyVisibleNails"],
            "originalResolutionReviewed": True,
            "reviewDecision": "exclude",
            "reviewReason": review_reasons[item["fileName"]],
            "trainingUse": "prohibited",
        }
        for item in original_excluded
    ]
    withdrawn_train_items = [
        {
            "fileName": item["fileName"],
            "imageSha256": item["sha256"],
            "sourceGroup": item["sourceGroup"],
            "originalAssignedRole": "train",
            "firstAnnotationBatch": False,
            "fullyVisibleNails": item["fullyVisibleNails"],
            "withdrawnToRole": RELEASE_ROLE,
            "trainingUse": "prohibited",
            "annotationTruthStatus": "not-started",
        }
        for item in reviewed_replacements
    ]
    withdrawn_train_groups = [
        {
            "sourceGroup": source_group,
            "itemCount": sum(
                1 for item in reviewed_replacements if item["sourceGroup"] == source_group
            ),
            "fileNames": sorted(
                item["fileName"]
                for item in reviewed_replacements
                if item["sourceGroup"] == source_group
            ),
            "allPlanMembersReviewedKeep": True,
            "allOriginallyAssignedTrain": True,
            "allFirstAnnotationBatchFalse": True,
        }
        for source_group in replacement_groups
    ]
    original_projection = [
        {
            "fileName": item["fileName"],
            "imageSha256": item["sha256"],
            "sourceGroup": item["sourceGroup"],
            "fullyVisibleNails": item["fullyVisibleNails"],
        }
        for item in original_items
    ]

    for label, path in paths.items():
        current_hash = sha256_file(path)
        if current_hash != bound_input_records[label]["sha256"]:
            raise ValueError(
                f"input evidence changed while building: {label}; "
                f"expected={bound_input_records[label]['sha256']} actual={current_hash}"
            )
    for item in all_reviewed_plan_items:
        source_path = image_root / item["fileName"]
        current_hash = sha256_file(source_path)
        if current_hash != item["sha256"]:
            raise ValueError(
                f"source image changed while building: {item['fileName']}; "
                f"expected={item['sha256']} actual={current_hash}"
            )

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "decision": OUTPUT_DECISION,
        "trainingUse": "prohibited",
        "annotationTruthStatus": "not-started",
        "inputs": {
            **bound_input_records,
            "imageRoot": {"path": str(image_root)},
        },
        "policy": {
            "expectedReleaseImages": EXPECTED_RELEASE_IMAGES,
            "originalCandidatesRequireCompleteReviewCoverage": True,
            "originalResolutionReviewRequired": True,
            "completeVisibleNailSurfaceRequired": True,
            "replacementSourceGroupsWithdrawnAtomicallyFromTrain": True,
            "firstAnnotationBatchReplacementForbidden": True,
            "trainingTruthOverlapForbidden": True,
            "validationTruthOverlapForbidden": True,
            "frozenReleaseTestOverlapForbidden": True,
            "retainedOriginalReleaseOverlapForbidden": True,
            "workspaceDoesNotApproveAnnotationTruth": True,
            "workspaceDoesNotGrantTrainingUse": True,
        },
        "counts": {
            "originalCandidates": len(original_items),
            "originalKept": len(original_kept),
            "originalExcluded": len(original_excluded),
            "replacementImages": len(reviewed_replacements),
            "withdrawnTrainGroups": len(withdrawn_train_groups),
            "finalImages": len(final_items),
            "finalExpectedFullyVisibleNails": sum(
                int(item["fullyVisibleNails"]) for item in final_items
            ),
        },
        "aggregates": {
            "originalCandidatesSha256": canonical_sha256(original_projection),
            "replacementItemsSha256": canonical_sha256(withdrawn_train_items),
            "finalItemsSha256": canonical_sha256(final_items),
        },
        "originalExcludedItems": excluded_items,
        "withdrawnTrainGroups": withdrawn_train_groups,
        "withdrawnTrainItems": withdrawn_train_items,
        "items": final_items,
        "invariants": {
            "allOriginalCandidatesReviewedExactlyOnce": True,
            "allReviewedItemsOriginalResolutionReviewed": True,
            "allCurrentImageHashesMatch": True,
            "allItemsAuthorizedForIndependentReleaseTest": True,
            "allItemsReplayScreeningKeepAndCompleteNailCount": True,
            "allReplacementSourceGroupsMovedWhole": True,
            "allFinalIdentitiesIsolated": True,
            "finalCountExactly33": True,
            "allFinalItemsTrainingProhibited": True,
            "allFinalItemsAnnotationTruthNotStarted": True,
        },
        "errors": [],
    }
    return report


def verify_report(report_path: Path) -> dict[str, Any]:
    """Replay every bound input and compare the complete stable report payload."""

    report_path = report_path.resolve()
    if not report_path.is_file():
        raise ValueError(f"report is missing: {report_path}")
    report = read_json(report_path, "release-test role replacement report")
    if (
        report.get("schemaVersion") != 1
        or report.get("ok") is not True
        or report.get("decision") != OUTPUT_DECISION
    ):
        raise ValueError("report is not a passing release-test role replacement manifest")
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("report inputs are missing")

    input_keys = {
        "firstAnnotationPlan": "first_annotation_plan",
        "authorization": "authorization",
        "screeningFinal": "screening_final",
        "trainingTruthIndex": "training_truth_index",
        "validationTruthIndex": "validation_truth_index",
        "frozenReleaseTestManifest": "frozen_release_test_manifest",
        "reviewDecisions": "review_decisions",
    }
    replay_values: dict[str, str] = {}
    for report_key, argument_key in input_keys.items():
        record = inputs.get(report_key)
        if not isinstance(record, dict):
            raise ValueError(f"report input record is missing: {report_key}")
        bound_path = Path(require_nonempty(record.get("path"), f"{report_key} path")).resolve()
        expected_hash = require_sha256(record.get("sha256"), f"{report_key} bound SHA-256")
        if not bound_path.is_file():
            raise ValueError(f"bound input is missing: {report_key}: {bound_path}")
        actual_hash = sha256_file(bound_path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"bound input SHA-256 drift: {report_key}; "
                f"expected={expected_hash} actual={actual_hash}"
            )
        replay_values[argument_key] = str(bound_path)

    image_root_record = inputs.get("imageRoot")
    if not isinstance(image_root_record, dict):
        raise ValueError("report imageRoot input is missing")
    image_root = Path(
        require_nonempty(image_root_record.get("path"), "report imageRoot path")
    ).resolve()
    replay_args = argparse.Namespace(
        **replay_values,
        image_root=str(image_root),
        output=str(report_path),
        verify_report=None,
    )
    expected = build(replay_args, require_new_output=False)
    stable_report = {key: value for key, value in report.items() if key != "generatedAt"}
    stable_expected = {key: value for key, value in expected.items() if key != "generatedAt"}
    if stable_report != stable_expected:
        raise ValueError(
            "report content differs from the replayed current evidence; "
            f"stored={canonical_sha256(stable_report)} "
            f"replayed={canonical_sha256(stable_expected)}"
        )
    return {
        "ok": True,
        "decision": "release_test_role_replacement_manifest_verified",
        "report": str(report_path),
        "reportSha256": sha256_file(report_path),
        **dict(report["counts"]),
        **dict(report["aggregates"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a transaction-safe 33-image release-test role replacement manifest."
    )
    parser.add_argument("--first-annotation-plan")
    parser.add_argument("--authorization")
    parser.add_argument("--screening-final")
    parser.add_argument("--training-truth-index")
    parser.add_argument("--validation-truth-index")
    parser.add_argument("--frozen-release-test-manifest")
    parser.add_argument("--review-decisions")
    parser.add_argument(
        "--image-root",
        help="Current image root; defaults to authorization.root.",
    )
    parser.add_argument("--output")
    parser.add_argument(
        "--verify-report",
        help="Read-only deep replay of an existing generated manifest.",
    )
    args = parser.parse_args()
    build_arguments = (
        "first_annotation_plan",
        "authorization",
        "screening_final",
        "training_truth_index",
        "validation_truth_index",
        "frozen_release_test_manifest",
        "review_decisions",
        "output",
    )
    if args.verify_report:
        supplied = [name for name in build_arguments if getattr(args, name) is not None]
        if supplied or args.image_root is not None:
            parser.error("--verify-report cannot be combined with build arguments")
    else:
        missing = [name for name in build_arguments if getattr(args, name) is None]
        if missing:
            parser.error(
                "building requires all evidence and output arguments; missing: "
                + ", ".join(missing)
            )
    return args


def main() -> None:
    args = parse_args()
    if args.verify_report:
        print(json.dumps(verify_report(Path(args.verify_report)), ensure_ascii=True))
        return
    output_path = Path(args.output).resolve()
    report = build(args)
    write_transactionally(output_path, report)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output_path),
                **report["counts"],
                **report["aggregates"],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
