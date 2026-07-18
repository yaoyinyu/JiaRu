from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PASS_DECISION = "reviewed_validation_replacements_pass"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def safe_items(document: dict[str, Any], label: str, errors: list[str]) -> list[dict[str, Any]]:
    raw_items = document.get("items", [])
    if not isinstance(raw_items, list):
        errors.append(f"{label} items must be an array")
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            errors.append(f"{label} item {index} must be an object")
            continue
        items.append(item)
    return items


def actual_base_image(manifest_path: Path, item: dict[str, Any]) -> Path:
    candidates = [
        manifest_path.parent / "images" / str(item.get("fileName", "")),
        Path(str(item.get("workspacePath", ""))),
        Path(str(item.get("sourcePath", ""))),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def write_rejection(
    output_path: Path,
    inputs: dict[str, str],
    errors: list[str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": 1,
        "ok": False,
        "decision": "reject_validation_role_extension",
        "inputs": inputs,
        "errors": errors,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Safely extend a reviewed val role manifest with whole source groups that were "
            "not assigned to independent release testing and have no approved train truth."
        )
    )
    parser.add_argument("--base-role-manifest", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--training-truth-index", required=True)
    parser.add_argument("--replacement-decisions", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument(
        "--image-root",
        help="Current image root. Defaults to authorization.root; useful when a historical manifest path is stale.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base_path = Path(args.base_role_manifest).resolve()
    plan_path = Path(args.plan).resolve()
    truth_index_path = Path(args.training_truth_index).resolve()
    decisions_path = Path(args.replacement_decisions).resolve()
    authorization_path = Path(args.authorization).resolve()
    output_path = Path(args.output).resolve()
    input_paths = {
        "baseRoleManifest": base_path,
        "plan": plan_path,
        "trainingTruthIndex": truth_index_path,
        "replacementDecisions": decisions_path,
        "authorization": authorization_path,
    }
    missing = [f"{name} is missing: {path}" for name, path in input_paths.items() if not path.is_file()]
    if missing:
        raise ValueError("; ".join(missing))

    input_evidence: dict[str, str] = {}
    for name, path in input_paths.items():
        input_evidence[name] = str(path)
        input_evidence[f"{name}Sha256"] = sha256_file(path)

    base = read_json(base_path, "base role manifest")
    plan = read_json(plan_path, "first annotation plan")
    truth_index = read_json(truth_index_path, "training truth index")
    decisions = read_json(decisions_path, "replacement decisions")
    authorization = read_json(authorization_path, "authorization evidence")
    errors: list[str] = []

    if base.get("ok") is not True or base.get("decision") != "annotation_workspace_ready_candidate_only":
        errors.append("base role manifest must be a passing candidate-only annotation workspace")
    base_policy = base.get("policy", {})
    if not isinstance(base_policy, dict) or base_policy.get("selectionMode") != "val" or base_policy.get("assignedRole") != "val":
        errors.append("base role manifest policy must be selectionMode=val and assignedRole=val")
    if base.get("inputs", {}).get("planSha256") != sha256_file(plan_path):
        errors.append("base role manifest does not bind the current first annotation plan")
    if base.get("inputs", {}).get("authorizationSha256") != sha256_file(authorization_path):
        errors.append("base role manifest does not bind the current authorization evidence")

    if plan.get("ok") is not True or plan.get("decision") != "first_annotation_batch_plan_ready_mask_review_required":
        errors.append("a passing first annotation plan is required")
    plan_policy = plan.get("policy", {})
    if not isinstance(plan_policy, dict) or plan_policy.get("sourceGroupAtomicAcrossRoles") is not True:
        errors.append("first annotation plan must guarantee sourceGroupAtomicAcrossRoles")
    if plan.get("inputs", {}).get("authorizationSha256") != sha256_file(authorization_path):
        errors.append("first annotation plan does not bind the current authorization evidence")

    if truth_index.get("ok") is not True or truth_index.get("decision") != "approved_unique_training_truth_index":
        errors.append("a passing unique training truth index is required")
    if int(truth_index.get("summary", {}).get("conflictingImageCount", -1)) != 0:
        errors.append("training truth index contains conflicting images")

    if decisions.get("ok") is not True or decisions.get("decision") != PASS_DECISION:
        errors.append(f"replacement decisions must be passing with decision={PASS_DECISION}")
    decision_policy = decisions.get("policy", {})
    if not isinstance(decision_policy, dict) or decision_policy.get("originalResolutionReviewCompleted") is not True:
        errors.append("replacement decisions must confirm originalResolutionReviewCompleted=true")
    if not isinstance(decision_policy, dict) or decision_policy.get("wholeVisibleNailSurfaceRequired") is not True:
        errors.append("replacement decisions must require the whole visible nail surface")
    if not isinstance(decision_policy, dict) or decision_policy.get("sourceGroupAtomicReassignmentRequested") is not True:
        errors.append("replacement decisions must request source-group-atomic reassignment")

    authorization_block = authorization.get("authorization", {})
    if (
        authorization.get("ok") is not True
        or not isinstance(authorization_block, dict)
        or authorization_block.get("status") != "confirmed"
        or authorization_block.get("decision") != "A"
    ):
        errors.append("confirmed authorization decision A is required")
    authorized_uses = set(authorization_block.get("authorizedUses", [])) if isinstance(authorization_block, dict) else set()
    if "commercial-model-training" not in authorized_uses:
        errors.append("authorization evidence does not permit commercial model training")

    raw_authorization_items = authorization.get("entries", [])
    authorization_items: list[dict[str, Any]] = []
    if not isinstance(raw_authorization_items, list):
        errors.append("authorization entries must be an array")
    else:
        for index, item in enumerate(raw_authorization_items, start=1):
            if not isinstance(item, dict):
                errors.append(f"authorization entry {index} must be an object")
                continue
            authorization_items.append(item)
    if authorization.get("entriesSha256") != canonical_sha256(authorization_items):
        errors.append("authorization entriesSha256 mismatch")
    authorization_names = [str(item.get("fileName", "")) for item in authorization_items]
    authorization_duplicates = duplicate_values(authorization_names)
    if "" in authorization_names or authorization_duplicates:
        errors.append(f"authorization contains duplicate or empty fileName values: {authorization_duplicates}")
    authorized_by_file = {str(item.get("fileName", "")): item for item in authorization_items}

    plan_items = safe_items(plan, "plan", errors)
    plan_names = [str(item.get("fileName", "")) for item in plan_items]
    plan_duplicates = duplicate_values(plan_names)
    if "" in plan_names or plan_duplicates:
        errors.append(f"plan contains duplicate or empty fileName values: {plan_duplicates}")
    plan_by_file = {str(item.get("fileName", "")): item for item in plan_items}
    plan_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in plan_items:
        plan_by_group.setdefault(str(item.get("sourceGroup", "")), []).append(item)

    base_items = safe_items(base, "base role manifest", errors)
    base_names = [str(item.get("fileName", "")) for item in base_items]
    base_hashes = [str(item.get("sha256", "")) for item in base_items]
    if "" in base_names or duplicate_values(base_names):
        errors.append(f"base role manifest contains duplicate or empty fileName values: {duplicate_values(base_names)}")
    if "" in base_hashes or duplicate_values(base_hashes):
        errors.append(f"base role manifest contains duplicate or empty image hashes: {duplicate_values(base_hashes)}")
    base_name_set = set(base_names)
    base_hash_set = set(base_hashes)
    base_group_set: set[str] = set()
    for item in base_items:
        file_name = str(item.get("fileName", ""))
        image_hash = str(item.get("sha256", ""))
        source_group = str(item.get("sourceGroup", ""))
        nails = item.get("expectedFullyVisibleNails")
        base_group_set.add(source_group)
        if not SHA256_PATTERN.fullmatch(image_hash) or not source_group or not positive_int(nails):
            errors.append(f"base item has invalid fileName/SHA/sourceGroup/complete nail count: {file_name}")
        if item.get("assignedRole") != "val" or item.get("trainingUse") != "prohibited" or item.get("annotationTruthStatus") != "not-started":
            errors.append(f"base item has unsafe val eligibility state: {file_name}")
        plan_item = plan_by_file.get(file_name)
        if plan_item is None:
            errors.append(f"base item is missing from the original plan: {file_name}")
        elif (
            plan_item.get("sha256") != image_hash
            or plan_item.get("sourceGroup") != source_group
            or plan_item.get("assignedRole") != "val"
            or plan_item.get("fullyVisibleNails") != nails
        ):
            errors.append(f"base item identity or val role differs from the original plan: {file_name}")
        image_path = actual_base_image(base_path, item)
        if not image_path.is_file() or sha256_file(image_path) != image_hash:
            errors.append(f"base source image is missing or changed: {file_name}")

    base_count = base.get("counts", {}).get("images")
    if not isinstance(base_count, int) or base_count != len(base_items):
        errors.append("base role manifest image count differs from its items")

    canonical_truths = truth_index.get("canonicalTruths", [])
    if not isinstance(canonical_truths, list):
        errors.append("training truth index canonicalTruths must be an array")
        canonical_truths = []
    train_truth_groups: dict[str, list[str]] = {}
    train_truth_hashes: dict[str, list[str]] = {}
    for index, truth in enumerate(canonical_truths, start=1):
        if not isinstance(truth, dict):
            errors.append(f"training truth {index} must be an object")
            continue
        group = str(truth.get("sourceGroup", ""))
        file_name = str(truth.get("fileName", ""))
        image_hash = str(truth.get("imageSha256", ""))
        if not group or not file_name:
            errors.append(f"training truth {index} has an empty fileName or sourceGroup")
            continue
        train_truth_groups.setdefault(group, []).append(file_name)
        if SHA256_PATTERN.fullmatch(image_hash):
            train_truth_hashes.setdefault(image_hash, []).append(file_name)

    replacement_items = safe_items(decisions, "replacement decisions", errors)
    replacement_names = [str(item.get("fileName", "")) for item in replacement_items]
    replacement_hashes = [str(item.get("sha256", "")) for item in replacement_items]
    duplicate_replacement_names = duplicate_values(replacement_names)
    duplicate_replacement_hashes = duplicate_values(replacement_hashes)
    if not replacement_items:
        errors.append("replacement decisions must contain at least one reviewed replacement")
    if "" in replacement_names or duplicate_replacement_names:
        errors.append(f"replacement batch contains duplicate or empty fileName values: {duplicate_replacement_names}")
    if "" in replacement_hashes or duplicate_replacement_hashes:
        errors.append(f"replacement batch contains duplicate or empty image hashes: {duplicate_replacement_hashes}")
    replacement_by_file = {str(item.get("fileName", "")): item for item in replacement_items}
    selected_groups = {str(item.get("sourceGroup", "")) for item in replacement_items}

    image_root_value = args.image_root if args.image_root is not None else authorization.get("root", "")
    image_root = Path(str(image_root_value)).resolve()
    input_evidence["imageRoot"] = str(image_root)
    if not image_root.is_dir():
        errors.append(f"image root is missing; pass the current root with --image-root: {image_root}")

    for item in replacement_items:
        file_name = str(item.get("fileName", ""))
        image_hash = str(item.get("sha256", ""))
        source_group = str(item.get("sourceGroup", ""))
        nails = item.get("fullyVisibleNails")
        if item.get("reviewStatus") != "pass":
            errors.append(f"replacement is not an original-resolution visual-review pass: {file_name}")
        if not str(item.get("replacementReason", "")).strip():
            errors.append(f"replacement reason is required: {file_name}")
        if not SHA256_PATTERN.fullmatch(image_hash) or not source_group or not positive_int(nails):
            errors.append(f"replacement has invalid fileName/SHA/sourceGroup/complete nail count: {file_name}")
        if file_name in base_name_set or image_hash in base_hash_set or source_group in base_group_set:
            errors.append(f"replacement duplicates or shares a source group with the base val role: {file_name}")
        if image_hash in train_truth_hashes:
            errors.append(
                f"replacement image already exists in approved train truth: {file_name} "
                f"matches={sorted(train_truth_hashes[image_hash])}"
            )
        plan_item = plan_by_file.get(file_name)
        if plan_item is None:
            errors.append(f"replacement is missing from the original plan: {file_name}")
        else:
            if (
                plan_item.get("sha256") != image_hash
                or plan_item.get("sourceGroup") != source_group
                or plan_item.get("fullyVisibleNails") != nails
            ):
                errors.append(f"replacement identity differs from the original plan: {file_name}")
            if plan_item.get("assignedRole") == "independent-release-test":
                errors.append(f"replacement was assigned to independent release test in the original plan: {file_name}")
            elif plan_item.get("assignedRole") not in {"train", "val"}:
                errors.append(f"replacement has an unsupported original role: {file_name}")
            if plan_item.get("trainingUse") != "prohibited" or plan_item.get("annotationTruthStatus") != "not-started":
                errors.append(f"replacement has unsafe eligibility state in the original plan: {file_name}")
        authorized = authorized_by_file.get(file_name)
        if authorized is None:
            errors.append(f"replacement is missing from authorization evidence: {file_name}")
        elif authorized.get("sha256") != image_hash or authorized.get("sourceGroup") != source_group:
            errors.append(f"replacement identity differs from authorization evidence: {file_name}")
        elif authorized.get("trainingUse") != "prohibited":
            errors.append(f"replacement authorization entry must remain training-prohibited: {file_name}")
        source_path = image_root / file_name
        if not source_path.is_file():
            errors.append(f"replacement source image is missing: {file_name}")
        elif sha256_file(source_path) != image_hash:
            errors.append(f"replacement source image SHA-256 drifted: {file_name}")

    group_evidence: list[dict[str, Any]] = []
    for group in sorted(selected_groups):
        group_plan_items = plan_by_group.get(group, [])
        group_plan_names = sorted(str(item.get("fileName", "")) for item in group_plan_items)
        first_batch_matches = sorted(
            str(item.get("fileName", ""))
            for item in group_plan_items
            if item.get("firstAnnotationBatch") is True
        )
        reviewed_names = sorted(
            file_name
            for file_name, item in replacement_by_file.items()
            if str(item.get("sourceGroup", "")) == group
        )
        roles = sorted({str(item.get("assignedRole", "")) for item in group_plan_items})
        if not group:
            errors.append("replacement sourceGroup must not be empty")
        if not group_plan_items:
            errors.append(f"selected source group is missing from the original plan: {group}")
        if "independent-release-test" in roles:
            errors.append(f"selected source group belongs to independent release test: {group}")
        if len(roles) != 1:
            errors.append(f"selected source group is not atomic in the original plan: {group} roles={roles}")
        if reviewed_names != group_plan_names:
            missing_group_items = sorted(set(group_plan_names) - set(reviewed_names))
            extra_group_items = sorted(set(reviewed_names) - set(group_plan_names))
            errors.append(
                f"selected source group is only partially reviewed for reassignment: {group}; "
                f"missing={missing_group_items}; extra={extra_group_items}"
            )
        truth_matches = sorted(train_truth_groups.get(group, []))
        if truth_matches:
            errors.append(
                f"selected source group already contains approved train truth and the whole group is rejected: "
                f"{group} files={truth_matches}"
            )
        if first_batch_matches:
            errors.append(
                f"selected source group was already materialized in the first train annotation batch and "
                f"the whole group is rejected: {group} files={first_batch_matches}"
            )
        group_evidence.append(
            {
                "sourceGroup": group,
                "originalAssignedRoles": roles,
                "originalPlanEligibleImages": len(group_plan_items),
                "reviewedReplacementImages": len(reviewed_names),
                "planFileNames": group_plan_names,
                "reviewedFileNames": reviewed_names,
                "approvedTrainTruthMatches": truth_matches,
                "firstAnnotationBatchMatches": first_batch_matches,
                "allPlanItemsCovered": reviewed_names == group_plan_names,
                "reassignment": "whole-plan-source-group-to-val",
            }
        )

    if errors:
        write_rejection(output_path, input_evidence, errors)
        raise ValueError("; ".join(errors))

    additions: list[dict[str, Any]] = []
    replacements: list[dict[str, Any]] = []
    for item in sorted(replacement_items, key=lambda value: str(value["fileName"])):
        file_name = str(item["fileName"])
        plan_item = plan_by_file[file_name]
        source_path = (image_root / file_name).resolve()
        additions.append(
            {
                "fileName": file_name,
                "sourcePath": str(source_path),
                "workspacePath": str(source_path),
                "sha256": item["sha256"],
                "sourceGroup": item["sourceGroup"],
                "assignedRole": "val",
                "originalAssignedRole": plan_item["assignedRole"],
                "expectedFullyVisibleNails": item["fullyVisibleNails"],
                "materializationMethod": "authorized-source-reference",
                "trainingUse": "prohibited",
                "annotationTruthStatus": "not-started",
            }
        )
        replacements.append(
            {
                "fileName": file_name,
                "sourceGroup": item["sourceGroup"],
                "originalAssignedRole": plan_item["assignedRole"],
                "replacementReason": str(item["replacementReason"]).strip(),
                "reviewMethod": "original-resolution-whole-image-complete-nail-surface",
            }
        )

    normalized_base_items = [
        {
            **item,
            "workspacePath": str(actual_base_image(base_path, item)),
        }
        for item in base_items
    ]
    combined_items = [*normalized_base_items, *additions]
    combined_groups = {str(item["sourceGroup"]) for item in combined_items}
    base_nails = sum(int(item["expectedFullyVisibleNails"]) for item in base_items)
    added_nails = sum(int(item["expectedFullyVisibleNails"]) for item in additions)
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "annotation_workspace_ready_candidate_only",
        "extensionDecision": "validation_role_extension_ready_candidate_only",
        "inputs": input_evidence,
        "policy": {
            **base_policy,
            "selectionMode": "val",
            "assignedRole": "val",
            "sourceGroupsRemainAtomicAcrossShards": True,
            "sourceGroupsRemainAtomicAcrossRoleExtension": True,
            "approvedTrainTruthGroupsExcluded": True,
            "independentReleaseTestGroupsExcluded": True,
            "workspaceDoesNotApproveMasks": True,
            "workspaceDoesNotGrantTrainingUse": True,
            "originalResolutionReviewRequired": True,
        },
        "imageDir": base.get("imageDir"),
        "counts": {
            "images": len(combined_items),
            "sourceGroups": len(combined_groups),
            "expectedFullyVisibleNails": base_nails + added_nails,
            "baseImages": len(base_items),
            "addedImages": len(additions),
            "combinedImages": len(combined_items),
            "baseSourceGroups": len(base_group_set),
            "addedSourceGroups": len(selected_groups),
            "combinedSourceGroups": len(combined_groups),
            "baseExpectedFullyVisibleNails": base_nails,
            "addedExpectedFullyVisibleNails": added_nails,
            "combinedExpectedFullyVisibleNails": base_nails + added_nails,
            "shards": int(base.get("counts", {}).get("shards", 0)),
            "materializationMethods": {
                **dict(base.get("counts", {}).get("materializationMethods", {})),
                "authorized-source-reference": len(additions),
            },
        },
        "shards": base.get("shards", []),
        "baseShards": base.get("shards", []),
        "extension": {
            "status": "reviewed-source-references-pending-annotation-workspace-materialization",
            "sourceGroupReassignments": group_evidence,
            "replacements": replacements,
        },
        "items": combined_items,
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
