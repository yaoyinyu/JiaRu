#!/usr/bin/env python3
"""Build and verify a candidate-only annotation workspace for authorized positives."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build a positive reinforcement annotation workspace.")
    source = value.add_mutually_exclusive_group()
    source.add_argument("--authorization")
    source.add_argument(
        "--inventory",
        help="Passing, replayable source-isolated inventory covered by the project standing commercial authorization.",
    )
    value.add_argument(
        "--selection-plan",
        help="Optional source selection frozen before model-assisted prelabeling; valid only with --inventory.",
    )
    value.add_argument("--output-dir")
    value.add_argument("--target-shard-size", type=int, default=20)
    value.add_argument("--verify-workspace")
    return value


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object for {label}: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_file(value: str | None, label: str) -> Path:
    if not value:
        raise ValueError(f"Missing {label} path")
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"Missing {label}: {path}")
    return path


def verify_authorization(path: Path) -> dict[str, Any]:
    script = Path(__file__).resolve().parent / "record-positive-reinforcement-authorization.py"
    result = subprocess.run(
        [sys.executable, str(script), "--verify-authorization", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or result.stdout.decode(
            "utf-8", errors="replace"
        ).strip()
        raise ValueError(f"Authorization deep verification failed: {detail}")
    authorization = read_object(path, "authorization")
    if authorization.get("authorizationStatus") != "confirmed":
        raise ValueError("Authorization is not confirmed")
    if authorization.get("trainingUse") != "prohibited-until-complete-mask-review-and-training-input-audit":
        raise ValueError("Authorization training-use state is unsafe")
    return authorization


def verify_inventory(path: Path) -> dict[str, Any]:
    script = Path(__file__).resolve().parent / "build-positive-reinforcement-candidate-inventory.py"
    result = subprocess.run(
        [sys.executable, str(script), "--verify-report", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or result.stdout.decode(
            "utf-8", errors="replace"
        ).strip()
        raise ValueError(f"Inventory deep verification failed: {detail}")
    inventory = read_object(path, "source-isolated inventory")
    if (
        inventory.get("schemaVersion") != 1
        or inventory.get("ok") is not True
        or inventory.get("decision") != "candidate_inventory_ready_for_original_resolution_review"
    ):
        raise ValueError("Inventory is not a passing source-isolated candidate inventory")
    items = inventory.get("items")
    if not isinstance(items, list) or not items or any(not isinstance(item, dict) for item in items):
        raise ValueError("Inventory must contain a non-empty item array")
    if canonical_sha256(items) != inventory.get("itemsSha256"):
        raise ValueError("Inventory item digest mismatch")
    if any(item.get("trainingUse") != "prohibited" for item in items):
        raise ValueError("Inventory contains an item that is not training-prohibited")
    return inventory


def verify_selection_plan(path: Path, inventory_path: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    plan = read_object(path, "source selection plan")
    if (
        plan.get("schemaVersion") != 1
        or plan.get("ok") is not True
        or plan.get("decision") != "source_selection_frozen_before_model_assistance"
    ):
        raise ValueError("Source selection plan schema or decision is invalid")
    inputs = plan.get("inputs", {})
    if Path(str(inputs.get("inventory", ""))).resolve() != inventory_path:
        raise ValueError("Source selection plan inventory path drifted")
    if inputs.get("inventorySha256") != sha256_path(inventory_path):
        raise ValueError("Source selection plan inventory bytes drifted")
    if inputs.get("inventoryItemsSha256") != inventory.get("itemsSha256"):
        raise ValueError("Source selection plan inventory item digest drifted")
    selected_names = plan.get("selectedFileNames")
    if (
        not isinstance(selected_names, list)
        or not selected_names
        or any(not isinstance(name, str) or not name for name in selected_names)
        or len(selected_names) != len(set(selected_names))
    ):
        raise ValueError("Source selection plan must contain unique selected file names")
    if canonical_sha256(selected_names) != plan.get("selectedFileNamesSha256"):
        raise ValueError("Source selection plan file-name digest mismatch")
    inventory_names = {str(item.get("fileName")) for item in inventory["items"]}
    missing = sorted(set(selected_names) - inventory_names)
    if missing:
        raise ValueError(f"Source selection plan contains files absent from inventory: {missing[:3]}")
    counts = plan.get("counts", {})
    if counts.get("selectedImages") != len(selected_names):
        raise ValueError("Source selection plan image count mismatch")
    if plan.get("trainingUse") != "prohibited":
        raise ValueError("Source selection plan must remain training prohibited")
    return plan


def group_shards(items: list[dict[str, Any]], target_size: int) -> list[list[dict[str, Any]]]:
    by_group: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_group.setdefault(str(item["sourceGroup"]), []).append(item)
    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for group in sorted(by_group):
        group_items = sorted(by_group[group], key=lambda item: str(item["fileName"]))
        if current and len(current) + len(group_items) > target_size:
            shards.append(current)
            current = []
        current.extend(group_items)
    if current:
        shards.append(current)
    return shards


def build_workspace(
    authorization_path: Path | None,
    inventory_path: Path | None,
    selection_plan_path: Path | None,
    output_dir: Path,
    target_size: int,
) -> Path:
    if target_size < 1:
        raise ValueError("target-shard-size must be positive")
    if output_dir.exists():
        raise ValueError(f"Output directory already exists: {output_dir}")
    authorization: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    if authorization_path is not None:
        if selection_plan_path is not None:
            raise ValueError("selection-plan is valid only with inventory")
        authorization = verify_authorization(authorization_path)
        items = authorization.get("authorizedItems")
        if not isinstance(items, list) or len(items) != 160 or any(not isinstance(item, dict) for item in items):
            raise ValueError("Authorization must bind exactly 160 item objects")
        if canonical_sha256(items) != authorization.get("authorizedItemsSha256"):
            raise ValueError("Authorized item digest mismatch")
        input_evidence = {
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_path(authorization_path),
            "authorizationMode": "exact-file-list-record",
            "requestedItemsSha256": authorization["requestedItemsSha256"],
            "authorizedItemsSha256": authorization["authorizedItemsSha256"],
        }
    elif inventory_path is not None:
        inventory = verify_inventory(inventory_path)
        items = inventory["items"]
        input_evidence = {
            "inventory": str(inventory_path),
            "inventorySha256": sha256_path(inventory_path),
            "inventoryItemsSha256": inventory["itemsSha256"],
            "authorizationMode": "project-standing-commercial-authorization",
        }
        if selection_plan_path is not None:
            selection_plan = verify_selection_plan(selection_plan_path, inventory_path, inventory)
            selected_names = set(selection_plan["selectedFileNames"])
            items = [item for item in items if item["fileName"] in selected_names]
            input_evidence.update(
                {
                    "selectionPlan": str(selection_plan_path),
                    "selectionPlanSha256": sha256_path(selection_plan_path),
                    "selectedFileNamesSha256": selection_plan["selectedFileNamesSha256"],
                }
            )
    else:
        raise ValueError("Either authorization or inventory is required")
    shards = group_shards(items, target_size)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        image_dir = staging / "images"
        shard_dir = staging / "shards"
        image_dir.mkdir()
        shard_dir.mkdir()
        materialized: list[dict[str, Any]] = []
        shard_records: list[dict[str, Any]] = []
        method_counts: dict[str, int] = {}
        for shard_index, shard_items in enumerate(shards, start=1):
            rows: list[dict[str, Any]] = []
            for item in shard_items:
                source_path = require_file(item.get("imagePath"), f"source image {item.get('fileName')}")
                if sha256_path(source_path) != item.get("imageSha256"):
                    raise ValueError(f"Source image SHA-256 mismatch: {source_path}")
                target_path = image_dir / str(item["fileName"])
                method = "hardlink"
                try:
                    os.link(source_path, target_path)
                except OSError:
                    shutil.copy2(source_path, target_path)
                    method = "copy"
                if sha256_path(target_path) != item["imageSha256"]:
                    raise ValueError(f"Materialized image SHA-256 mismatch: {target_path}")
                method_counts[method] = method_counts.get(method, 0) + 1
                record = {
                    "fileName": item["fileName"],
                    "sourcePath": str(source_path),
                    "workspacePath": str(output_dir / "images" / str(item["fileName"])),
                    "imageSha256": item["imageSha256"],
                    "width": item["width"],
                    "height": item["height"],
                    "sourceGroup": item["sourceGroup"],
                    "expectedFullyVisibleNails": item["fullyVisibleNails"],
                    "assignedRole": "train-positive-reinforcement-candidate",
                    "shardIndex": shard_index,
                    "materializationMethod": method,
                    "sourceQualityReview": "passed-for-annotation-candidate",
                    "completeMaskReview": "not-started",
                    "annotationTruthStatus": "not-started",
                    "trainingUse": "prohibited",
                }
                materialized.append(record)
                rows.append(record)
            shard_path = shard_dir / f"annotation-shard-{shard_index:03d}.csv"
            with shard_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "fileName",
                        "imageSha256",
                        "sourceGroup",
                        "expectedFullyVisibleNails",
                        "candidateMaskCount",
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
                            "imageSha256": row["imageSha256"],
                            "sourceGroup": row["sourceGroup"],
                            "expectedFullyVisibleNails": row["expectedFullyVisibleNails"],
                            "candidateMaskCount": "",
                            "reviewStatus": "",
                            "issueCodes": "",
                            "note": "",
                        }
                    )
            shard_records.append(
                {
                    "index": shard_index,
                    "path": str(output_dir / "shards" / shard_path.name),
                    "sha256": sha256_path(shard_path),
                    "images": len(rows),
                    "sourceGroups": sorted({str(row["sourceGroup"]) for row in rows}),
                }
            )
        manifest = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "positive_reinforcement_annotation_workspace_ready_candidate_only",
            "inputs": input_evidence,
            "policy": {
                "assignedRole": "train-positive-reinforcement-candidate",
                "sourceGroupsRemainAtomicAcrossShards": True,
                "workspaceDoesNotApproveMasks": True,
                "workspaceDoesNotGrantTrainingUse": True,
                "completeMaskOriginalResolutionReviewRequired": True,
                "polygonValidityAndZeroOverlapRequired": True,
                "workspaceMustRemainOutsideGit": True,
                "standingAuthorizationDoesNotApproveMasks": True,
            },
            "imageDir": str(output_dir / "images"),
            "counts": {
                "images": len(materialized),
                "sourceGroups": len({item["sourceGroup"] for item in materialized}),
                "shards": len(shards),
                "expectedFullyVisibleNails": sum(int(item["expectedFullyVisibleNails"]) for item in materialized),
                "materializationMethods": method_counts,
            },
            "itemsSha256": canonical_sha256(materialized),
            "shards": shard_records,
            "items": materialized,
            "trainingUse": "prohibited",
            "errors": [],
        }
        manifest_path = staging / "annotation-workspace-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, output_dir)
        final_manifest = output_dir / manifest_path.name
        verify_workspace(final_manifest)
        return final_manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
        raise


def verify_workspace(manifest_path: Path) -> dict[str, Any]:
    manifest = read_object(manifest_path, "workspace manifest")
    if manifest.get("schemaVersion") != 1 or manifest.get("ok") is not True:
        raise ValueError("Workspace manifest schema or status is invalid")
    if manifest.get("decision") != "positive_reinforcement_annotation_workspace_ready_candidate_only":
        raise ValueError("Workspace decision is invalid")
    if manifest.get("trainingUse") != "prohibited":
        raise ValueError("Workspace must remain training prohibited")
    inputs = manifest.get("inputs", {})
    authorization: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    if inputs.get("authorizationMode") == "exact-file-list-record":
        authorization_path = require_file(inputs.get("authorization"), "authorization")
        if sha256_path(authorization_path) != inputs.get("authorizationSha256"):
            raise ValueError("Workspace authorization bytes drifted")
        authorization = verify_authorization(authorization_path)
        if inputs.get("authorizedItemsSha256") != authorization.get("authorizedItemsSha256"):
            raise ValueError("Workspace authorized item digest drifted")
        eligible_items = authorization["authorizedItems"]
        expected_count = 160
    elif inputs.get("authorizationMode") == "project-standing-commercial-authorization":
        inventory_path = require_file(inputs.get("inventory"), "source-isolated inventory")
        if sha256_path(inventory_path) != inputs.get("inventorySha256"):
            raise ValueError("Workspace inventory bytes drifted")
        inventory = verify_inventory(inventory_path)
        if inputs.get("inventoryItemsSha256") != inventory.get("itemsSha256"):
            raise ValueError("Workspace inventory item digest drifted")
        eligible_items = inventory["items"]
        selection_plan_value = inputs.get("selectionPlan")
        if selection_plan_value:
            selection_plan_path = require_file(selection_plan_value, "source selection plan")
            if sha256_path(selection_plan_path) != inputs.get("selectionPlanSha256"):
                raise ValueError("Workspace source selection plan bytes drifted")
            selection_plan = verify_selection_plan(selection_plan_path, inventory_path, inventory)
            if inputs.get("selectedFileNamesSha256") != selection_plan.get("selectedFileNamesSha256"):
                raise ValueError("Workspace selected file-name digest drifted")
            selected_names = set(selection_plan["selectedFileNames"])
            eligible_items = [item for item in eligible_items if item["fileName"] in selected_names]
        expected_count = len(eligible_items)
    else:
        raise ValueError("Workspace authorization mode is invalid")
    items = manifest.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Workspace items are invalid")
    if canonical_sha256(items) != manifest.get("itemsSha256"):
        raise ValueError("Workspace item digest mismatch")
    if len(items) != manifest.get("counts", {}).get("images") or len(items) != expected_count:
        raise ValueError("Workspace image count mismatch")
    authorized_by_sha = {item["imageSha256"]: item for item in eligible_items}
    seen_files: set[str] = set()
    seen_sha: set[str] = set()
    for item in items:
        file_name = str(item.get("fileName", ""))
        image_sha = str(item.get("imageSha256", ""))
        if not file_name or file_name in seen_files or image_sha in seen_sha:
            raise ValueError(f"Duplicate workspace identity: {file_name}")
        seen_files.add(file_name)
        seen_sha.add(image_sha)
        authorized = authorized_by_sha.get(image_sha)
        if authorized is None or authorized.get("fileName") != file_name:
            raise ValueError(f"Workspace item is absent from its bound eligible input: {file_name}")
        if item.get("sourceGroup") != authorized.get("sourceGroup"):
            raise ValueError(f"Workspace source group drifted: {file_name}")
        if item.get("trainingUse") != "prohibited" or item.get("completeMaskReview") != "not-started":
            raise ValueError(f"Workspace role state is unsafe: {file_name}")
        workspace_path = require_file(item.get("workspacePath"), f"workspace image {file_name}")
        if sha256_path(workspace_path) != image_sha:
            raise ValueError(f"Workspace image bytes drifted: {file_name}")
    shard_rows: list[dict[str, str]] = []
    group_to_shard: dict[str, int] = {}
    for shard in manifest.get("shards", []):
        shard_path = require_file(shard.get("path"), "workspace shard")
        if sha256_path(shard_path) != shard.get("sha256"):
            raise ValueError(f"Workspace shard bytes drifted: {shard_path}")
        with shard_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != shard.get("images"):
            raise ValueError(f"Workspace shard count mismatch: {shard_path}")
        shard_rows.extend(rows)
        for group in shard.get("sourceGroups", []):
            if group in group_to_shard:
                raise ValueError(f"Source group split across workspace shards: {group}")
            group_to_shard[group] = int(shard["index"])
    if {row["fileName"] for row in shard_rows} != seen_files or len(shard_rows) != len(items):
        raise ValueError("Workspace shard coverage mismatch")
    if len(group_to_shard) != manifest.get("counts", {}).get("sourceGroups"):
        raise ValueError("Workspace source-group count mismatch")
    return manifest


def main() -> int:
    args = parser().parse_args()
    try:
        if args.verify_workspace:
            manifest_path = require_file(args.verify_workspace, "workspace manifest")
            manifest = verify_workspace(manifest_path)
            print(
                json.dumps(
                    {"ok": True, "decision": "verified", "manifest": str(manifest_path), **manifest["counts"]},
                    ensure_ascii=False,
                )
            )
            return 0
        authorization_path = require_file(args.authorization, "authorization") if args.authorization else None
        inventory_path = require_file(args.inventory, "source-isolated inventory") if args.inventory else None
        selection_plan_path = require_file(args.selection_plan, "source selection plan") if args.selection_plan else None
        if authorization_path is None and inventory_path is None:
            raise ValueError("authorization or inventory is required")
        if not args.output_dir:
            raise ValueError("output-dir is required")
        manifest_path = build_workspace(
            authorization_path,
            inventory_path,
            selection_plan_path,
            Path(args.output_dir).resolve(),
            args.target_shard_size,
        )
        manifest = read_object(manifest_path, "workspace manifest")
        print(
            json.dumps(
                {"ok": True, "decision": manifest["decision"], "manifest": str(manifest_path), **manifest["counts"]},
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
