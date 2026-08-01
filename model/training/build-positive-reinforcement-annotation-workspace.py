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
    value.add_argument("--authorization")
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


def build_workspace(authorization_path: Path, output_dir: Path, target_size: int) -> Path:
    if target_size < 1:
        raise ValueError("target-shard-size must be positive")
    if output_dir.exists():
        raise ValueError(f"Output directory already exists: {output_dir}")
    authorization = verify_authorization(authorization_path)
    items = authorization.get("authorizedItems")
    if not isinstance(items, list) or len(items) != 160 or any(not isinstance(item, dict) for item in items):
        raise ValueError("Authorization must bind exactly 160 item objects")
    if canonical_sha256(items) != authorization.get("authorizedItemsSha256"):
        raise ValueError("Authorized item digest mismatch")
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
            "inputs": {
                "authorization": str(authorization_path),
                "authorizationSha256": sha256_path(authorization_path),
                "requestedItemsSha256": authorization["requestedItemsSha256"],
                "authorizedItemsSha256": authorization["authorizedItemsSha256"],
            },
            "policy": {
                "assignedRole": "train-positive-reinforcement-candidate",
                "sourceGroupsRemainAtomicAcrossShards": True,
                "workspaceDoesNotApproveMasks": True,
                "workspaceDoesNotGrantTrainingUse": True,
                "completeMaskOriginalResolutionReviewRequired": True,
                "polygonValidityAndZeroOverlapRequired": True,
                "workspaceMustRemainOutsideGit": True,
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
    authorization_path = require_file(manifest.get("inputs", {}).get("authorization"), "authorization")
    if sha256_path(authorization_path) != manifest.get("inputs", {}).get("authorizationSha256"):
        raise ValueError("Workspace authorization bytes drifted")
    authorization = verify_authorization(authorization_path)
    if manifest.get("inputs", {}).get("authorizedItemsSha256") != authorization.get("authorizedItemsSha256"):
        raise ValueError("Workspace authorized item digest drifted")
    items = manifest.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Workspace items are invalid")
    if canonical_sha256(items) != manifest.get("itemsSha256"):
        raise ValueError("Workspace item digest mismatch")
    if len(items) != manifest.get("counts", {}).get("images") or len(items) != 160:
        raise ValueError("Workspace image count mismatch")
    authorized_by_sha = {item["imageSha256"]: item for item in authorization["authorizedItems"]}
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
            raise ValueError(f"Workspace item is not exactly authorized: {file_name}")
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
        authorization_path = require_file(args.authorization, "authorization")
        if not args.output_dir:
            raise ValueError("output-dir is required")
        manifest_path = build_workspace(
            authorization_path,
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
