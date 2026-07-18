from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("role extension manifest must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize only the reviewed additions from a passing validation role-extension manifest."
    )
    parser.add_argument("--role-extension-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-shard-size", type=int, default=4)
    args = parser.parse_args()

    role_path = Path(args.role_extension_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not role_path.is_file():
        raise ValueError(f"role extension manifest is missing: {role_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    if args.target_shard_size < 1:
        raise ValueError("target shard size must be positive")

    role = read_json(role_path)
    errors: list[str] = []
    if (
        role.get("ok") is not True
        or role.get("decision") != "annotation_workspace_ready_candidate_only"
        or role.get("extensionDecision") != "validation_role_extension_ready_candidate_only"
    ):
        errors.append("a passing validation role-extension manifest is required")
    policy = role.get("policy", {})
    if (
        not isinstance(policy, dict)
        or policy.get("selectionMode") != "val"
        or policy.get("assignedRole") != "val"
        or policy.get("sourceGroupsRemainAtomicAcrossRoleExtension") is not True
        or policy.get("approvedTrainTruthGroupsExcluded") is not True
        or policy.get("independentReleaseTestGroupsExcluded") is not True
    ):
        errors.append("role-extension safety policy is incomplete")
    extension = role.get("extension", {})
    if not isinstance(extension, dict):
        errors.append("role extension block must be an object")
        extension = {}
    replacement_rows = extension.get("replacements", [])
    if not isinstance(replacement_rows, list) or not replacement_rows:
        errors.append("role extension must contain reviewed replacements")
        replacement_rows = []
    replacement_names = {
        str(item.get("fileName", ""))
        for item in replacement_rows
        if isinstance(item, dict) and str(item.get("fileName", ""))
    }
    group_rows = extension.get("sourceGroupReassignments", [])
    if not isinstance(group_rows, list) or not group_rows:
        errors.append("role extension must contain source-group reassignment evidence")
        group_rows = []
    for row in group_rows:
        if not isinstance(row, dict):
            errors.append("source-group reassignment evidence must contain objects")
            continue
        if (
            row.get("allPlanItemsCovered") is not True
            or row.get("approvedTrainTruthMatches") != []
            or row.get("firstAnnotationBatchMatches") != []
            or row.get("reassignment") != "whole-plan-source-group-to-val"
        ):
            errors.append(f"unsafe source-group reassignment: {row.get('sourceGroup')}")

    raw_items = role.get("items", [])
    items = [
        item
        for item in raw_items
        if isinstance(item, dict) and str(item.get("fileName", "")) in replacement_names
    ] if isinstance(raw_items, list) else []
    if len(items) != len(replacement_names):
        errors.append("reviewed replacement identities are not covered exactly once by role items")
    if int(role.get("counts", {}).get("addedImages", -1)) != len(items):
        errors.append("role-extension added image count differs from reviewed replacements")

    seen_files: set[str] = set()
    seen_hashes: set[str] = set()
    by_group: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        file_name = str(item.get("fileName", ""))
        image_hash = str(item.get("sha256", ""))
        source_group = str(item.get("sourceGroup", ""))
        source_path = Path(str(item.get("sourcePath", ""))).resolve()
        nails = item.get("expectedFullyVisibleNails")
        if not file_name or file_name in seen_files or not image_hash or image_hash in seen_hashes:
            errors.append(f"duplicate or empty replacement identity: {file_name}")
        seen_files.add(file_name)
        seen_hashes.add(image_hash)
        if (
            item.get("assignedRole") != "val"
            or item.get("trainingUse") != "prohibited"
            or item.get("annotationTruthStatus") != "not-started"
            or not isinstance(nails, int)
            or isinstance(nails, bool)
            or nails < 1
            or not source_group
        ):
            errors.append(f"unsafe replacement role or nail count: {file_name}")
        if not source_path.is_file() or sha256_file(source_path) != image_hash:
            errors.append(f"replacement source image is missing or changed: {file_name}")
        by_group.setdefault(source_group, []).append(item)
    expected_groups = {
        str(row.get("sourceGroup", "")) for row in group_rows if isinstance(row, dict)
    }
    if set(by_group) != expected_groups:
        errors.append("materialized source groups differ from reassignment evidence")
    if errors:
        raise ValueError("; ".join(errors))

    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for _, group_items in sorted(by_group.items()):
        ordered = sorted(group_items, key=lambda item: str(item["fileName"]))
        if current and len(current) + len(ordered) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(ordered)
    if current:
        shards.append(current)

    image_dir = output_dir / "images"
    shard_dir = output_dir / "shards"
    image_dir.mkdir(parents=True)
    shard_dir.mkdir(parents=True)
    materialized: list[dict[str, Any]] = []
    methods: dict[str, int] = {}
    shard_records: list[dict[str, Any]] = []
    for shard_index, shard_items in enumerate(shards, start=1):
        rows: list[dict[str, Any]] = []
        for item in shard_items:
            source_path = Path(str(item["sourcePath"])).resolve()
            target_path = image_dir / str(item["fileName"])
            method = "hardlink"
            try:
                os.link(source_path, target_path)
            except OSError:
                shutil.copy2(source_path, target_path)
                method = "copy"
            if sha256_file(target_path) != item["sha256"]:
                raise RuntimeError(f"materialized image SHA-256 mismatch: {item['fileName']}")
            methods[method] = methods.get(method, 0) + 1
            record = {
                "fileName": item["fileName"],
                "sourcePath": str(source_path),
                "workspacePath": str(target_path),
                "sha256": item["sha256"],
                "sourceGroup": item["sourceGroup"],
                "assignedRole": "val",
                "originalAssignedRole": item.get("originalAssignedRole"),
                "expectedFullyVisibleNails": item["expectedFullyVisibleNails"],
                "shardIndex": shard_index,
                "materializationMethod": method,
                "trainingUse": "prohibited",
                "annotationTruthStatus": "not-started",
            }
            materialized.append(record)
            rows.append(record)
        shard_path = shard_dir / f"annotation-shard-{shard_index:03d}.csv"
        with shard_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=[
                    "fileName",
                    "sha256",
                    "sourceGroup",
                    "expectedFullyVisibleNails",
                    "candidateCount",
                    "reviewStatus",
                    "issueCodes",
                    "note",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "fileName": row["fileName"],
                        "sha256": row["sha256"],
                        "sourceGroup": row["sourceGroup"],
                        "expectedFullyVisibleNails": row["expectedFullyVisibleNails"],
                        "candidateCount": "",
                        "reviewStatus": "",
                        "issueCodes": "",
                        "note": "",
                    }
                )
        shard_records.append(
            {
                "index": shard_index,
                "path": str(shard_path),
                "sha256": sha256_file(shard_path),
                "images": len(rows),
                "sourceGroups": sorted({str(row["sourceGroup"]) for row in rows}),
            }
        )

    manifest = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "annotation_workspace_ready_candidate_only",
        "inputs": {
            "roleExtensionManifest": str(role_path),
            "roleExtensionManifestSha256": sha256_file(role_path),
        },
        "policy": {
            "selectionMode": "val",
            "assignedRole": "val",
            "extensionOnly": True,
            "sourceGroupsRemainAtomicAcrossShards": True,
            "workspaceDoesNotApproveMasks": True,
            "workspaceDoesNotGrantTrainingUse": True,
            "originalResolutionReviewRequired": True,
            "workspaceMustRemainOutsideGit": True,
        },
        "imageDir": str(image_dir),
        "counts": {
            "images": len(materialized),
            "sourceGroups": len(by_group),
            "shards": len(shards),
            "expectedFullyVisibleNails": sum(
                int(item["expectedFullyVisibleNails"]) for item in materialized
            ),
            "materializationMethods": methods,
        },
        "shards": shard_records,
        "items": materialized,
        "errors": [],
    }
    manifest_path = output_dir / "annotation-workspace-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, **manifest["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
