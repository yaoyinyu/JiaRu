from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_group_order(groups: dict[str, list[dict[str, object]]], seed: str) -> list[tuple[str, int]]:
    return sorted(
        ((group, len(items)) for group, items in groups.items()),
        key=lambda item: (hashlib.sha256(f"{seed}:{item[0]}".encode("utf-8")).hexdigest(), item[0]),
    )


def choose_group_subset(
    ordered_groups: list[tuple[str, int]], target: int, maximum: int | None = None
) -> set[str]:
    limit = maximum if maximum is not None else sum(size for _, size in ordered_groups)
    choices: dict[int, tuple[str, ...]] = {0: ()}
    for group, size in ordered_groups:
        for total, selected in sorted(list(choices.items()), reverse=True):
            next_total = total + size
            if next_total <= limit and next_total not in choices:
                choices[next_total] = (*selected, group)
    eligible = [total for total in choices if total >= target]
    if not eligible:
        raise ValueError(f"cannot satisfy target {target} within maximum {limit}")
    return set(choices[min(eligible)])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan source-group-exclusive train/val/release-test roles and a bounded first annotation batch."
    )
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--screening-batch", required=True)
    parser.add_argument("--near-duplicate-final", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", default="real-material-2026-07-14-first-annotation-v1")
    parser.add_argument("--release-test-target", type=int, default=33)
    parser.add_argument("--val-target", type=int, default=30)
    parser.add_argument("--train-annotation-target", type=int, default=160)
    parser.add_argument("--train-annotation-min", type=int, default=100)
    parser.add_argument("--train-annotation-max", type=int, default=200)
    parser.add_argument("--hard-negative-target", type=int, default=100)
    args = parser.parse_args()

    authorization_path = Path(args.authorization).resolve()
    screening_path = Path(args.screening_batch).resolve()
    near_duplicate_path = Path(args.near_duplicate_final).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    if args.train_annotation_min > args.train_annotation_target or args.train_annotation_target > args.train_annotation_max:
        raise ValueError("train annotation target must be within the configured min/max range")

    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    screening = json.loads(screening_path.read_text(encoding="utf-8"))
    near_duplicate = json.loads(near_duplicate_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if authorization.get("ok") is not True or authorization.get("authorization", {}).get("decision") != "A":
        errors.append("a passing authorization decision A is required")
    authorization_entries = authorization.get("entries", [])
    if authorization.get("entriesSha256") != canonical_sha256(authorization_entries):
        errors.append("authorization entriesSha256 mismatch")
    if screening.get("ok") is not True or screening.get("decision") != "source_screening_batch_pass":
        errors.append("a passing source screening batch is required")
    if near_duplicate.get("ok") is not True or near_duplicate.get("decision") != "near_duplicate_visual_review_pass":
        errors.append("a passing near-duplicate final report is required")

    authorized_by_file = {str(item.get("fileName", "")): item for item in authorization_entries}
    screened_by_file = {str(item.get("fileName", "")): item for item in screening.get("items", [])}
    near_excluded = {
        str(item.get("fileName", "")): item for item in near_duplicate.get("excludedCandidates", [])
    }
    if len(authorized_by_file) != len(authorization_entries):
        errors.append("authorization contains duplicate or empty fileName values")
    if len(screened_by_file) != len(screening.get("items", [])):
        errors.append("screening batch contains duplicate or empty fileName values")
    if len(near_excluded) != len(near_duplicate.get("excludedCandidates", [])):
        errors.append("near-duplicate exclusions contain duplicate or empty fileName values")
    overlap = sorted(set(screened_by_file) & set(near_excluded))
    if overlap:
        errors.append(f"screening and near-duplicate exclusions overlap on {len(overlap)} images")
    covered = set(screened_by_file) | set(near_excluded)
    missing = sorted(set(authorized_by_file) - covered)
    extra = sorted(covered - set(authorized_by_file))
    if missing:
        errors.append(f"planning evidence misses {len(missing)} authorized images")
    if extra:
        errors.append(f"planning evidence contains {len(extra)} unauthorized images")

    kept_groups: dict[str, list[dict[str, object]]] = {}
    for file_name, item in screened_by_file.items():
        authorized = authorized_by_file.get(file_name, {})
        if item.get("sha256") != authorized.get("sha256") or item.get("sourceGroup") != authorized.get("sourceGroup"):
            errors.append(f"screening identity differs from authorization for {file_name}")
        if item.get("trainingUse") != "prohibited" or item.get("annotationTruthStatus") != "not-started":
            errors.append(f"screening item has unsafe eligibility state: {file_name}")
        if item.get("decision") == "keep-for-annotation":
            group = str(item.get("sourceGroup", ""))
            kept_groups.setdefault(group, []).append(item)

    if errors:
        raise ValueError("; ".join(errors))

    ordered = stable_group_order(kept_groups, args.seed)
    release_groups = choose_group_subset(ordered, args.release_test_target)
    remaining = [item for item in ordered if item[0] not in release_groups]
    val_groups = choose_group_subset(remaining, args.val_target)
    train_groups = {group for group in kept_groups if group not in release_groups and group not in val_groups}
    train_ordered = [item for item in remaining if item[0] in train_groups]
    first_batch_groups = choose_group_subset(
        train_ordered, args.train_annotation_target, args.train_annotation_max
    )

    role_by_group = {
        **{group: "independent-release-test" for group in release_groups},
        **{group: "val" for group in val_groups},
        **{group: "train" for group in train_groups},
    }
    review_rows: list[dict[str, str]] = []
    planned_items: list[dict[str, object]] = []
    for file_name in sorted(authorized_by_file):
        screened = screened_by_file.get(file_name)
        if screened is None:
            evidence = near_excluded[file_name]
            review_rows.append(
                {
                    "fileName": file_name,
                    "reviewStatus": "exclude",
                    "assignedRole": "unassigned",
                    "note": f"near-duplicate exclusion: {evidence.get('reason', '')}",
                }
            )
            continue
        if screened.get("decision") != "keep-for-annotation":
            review_rows.append(
                {
                    "fileName": file_name,
                    "reviewStatus": "exclude",
                    "assignedRole": "unassigned",
                    "note": f"source screening exclusion: {screened.get('decision', '')}",
                }
            )
            continue
        group = str(screened.get("sourceGroup", ""))
        role = role_by_group[group]
        review_rows.append(
            {
                "fileName": file_name,
                "reviewStatus": "pass",
                "assignedRole": role,
                "note": "source screening passed; mask truth not started",
            }
        )
        planned_items.append(
            {
                "fileName": file_name,
                "sha256": screened.get("sha256"),
                "sourceGroup": group,
                "assignedRole": role,
                "firstAnnotationBatch": group in first_batch_groups,
                "fullyVisibleNails": screened.get("fullyVisibleNails"),
                "trainingUse": "prohibited",
                "annotationTruthStatus": "not-started",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    review_csv = output_dir / "exclusive-assignment-review.csv"
    with review_csv.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["fileName", "reviewStatus", "assignedRole", "note"])
        writer.writeheader()
        writer.writerows(review_rows)

    by_role = {
        role: sum(1 for item in planned_items if item["assignedRole"] == role)
        for role in ("train", "val", "independent-release-test")
    }
    first_items = [item for item in planned_items if item["firstAnnotationBatch"]]
    first_nails = sum(int(item.get("fullyVisibleNails") or 0) for item in first_items)
    plan = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "first_annotation_batch_plan_ready_mask_review_required",
        "inputs": {
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
            "screeningBatch": str(screening_path),
            "screeningBatchSha256": sha256_file(screening_path),
            "nearDuplicateFinal": str(near_duplicate_path),
            "nearDuplicateFinalSha256": sha256_file(near_duplicate_path),
            "exclusiveAssignmentReviewCsv": str(review_csv),
            "exclusiveAssignmentReviewCsvSha256": sha256_file(review_csv),
        },
        "selection": {
            "seed": args.seed,
            "strategy": "deterministic source-group-atomic subset sums",
            "releaseTestTarget": args.release_test_target,
            "valTarget": args.val_target,
            "trainAnnotationTarget": args.train_annotation_target,
            "trainAnnotationRange": [args.train_annotation_min, args.train_annotation_max],
            "hardNegativeTarget": args.hard_negative_target,
            "hardNegativeEligibleFromThisScreening": 0,
            "hardNegativeStatus": "deferred-separate-source-selection-required",
        },
        "policy": {
            "sourceGroupAtomicAcrossRoles": True,
            "firstAnnotationBatchUsesWholeSourceGroups": True,
            "planningDoesNotApproveMasks": True,
            "planningDoesNotGrantTrainingUse": True,
            "valRequiresOriginalResolutionTruthAudit": True,
            "releaseTestMustRemainTrainingProhibited": True,
        },
        "counts": {
            "authorizationEntries": len(authorized_by_file),
            "nearDuplicateExcluded": len(near_excluded),
            "screenedImages": len(screened_by_file),
            "keptForAnnotation": len(planned_items),
            "keptSourceGroups": len(kept_groups),
            "byRole": by_role,
            "firstAnnotationBatchImages": len(first_items),
            "firstAnnotationBatchSourceGroups": len(first_batch_groups),
            "firstAnnotationBatchExpectedNails": first_nails,
        },
        "roleSourceGroups": {
            "train": sorted(train_groups),
            "val": sorted(val_groups),
            "independent-release-test": sorted(release_groups),
            "firstAnnotationBatch": sorted(first_batch_groups),
        },
        "deferredInputs": [
            {
                "id": "HARD-NEGATIVE-SOURCE-01",
                "status": "deferred",
                "need": f"select about {args.hard_negative_target} clear source-isolated hard-negative images outside the excluded low-quality/collage pool",
            }
        ],
        "items": planned_items,
        "errors": [],
    }
    plan_path = output_dir / "first-annotation-batch-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **plan["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
