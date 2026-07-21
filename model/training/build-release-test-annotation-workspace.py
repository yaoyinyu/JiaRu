#!/usr/bin/env python3
"""Materialize the reviewed 33-image release-test annotation workspace."""

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


EXPECTED_IMAGES = 33
EXPECTED_NAILS = 170
EXPECTED_ROLE = "independent-release-test"
ROLE_DECISION = "release_test_role_replacement_manifest_ready_candidate_only"
WORKSPACE_DECISION = "annotation_workspace_ready_candidate_only"
VERIFIER_DECISION = "release_test_role_replacement_manifest_verified"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def verifier_script() -> Path:
    path = Path(__file__).resolve().with_name(
        "build-release-test-role-replacement-manifest.py"
    )
    if not path.is_file():
        raise ValueError(f"role manifest verifier is missing: {path}")
    return path


def run_role_verifier(role_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(verifier_script()), "--verify-report", str(role_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"role replacement manifest deep verifier rejected input: {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("role verifier did not return JSON") from error
    if result.get("ok") is not True or result.get("decision") != VERIFIER_DECISION:
        raise ValueError("role verifier result is not a passing deep replay")
    if result.get("reportSha256") != sha256_file(role_path):
        raise ValueError("role verifier result does not bind the current role manifest")
    return result


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def require_outside_repository(path: Path) -> None:
    try:
        path.relative_to(repository_root())
    except ValueError:
        return
    raise ValueError(f"output must remain outside the Git workspace: {path}")


def validate_role(
    role_path: Path, verification: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    role = read_json(role_path, "role replacement manifest")
    if role.get("ok") is not True or role.get("decision") != ROLE_DECISION:
        raise ValueError("a passing role replacement manifest is required")
    counts = role.get("counts")
    if (
        not isinstance(counts, dict)
        or counts.get("finalImages") != EXPECTED_IMAGES
        or counts.get("finalExpectedFullyVisibleNails") != EXPECTED_NAILS
        or verification.get("finalImages") != EXPECTED_IMAGES
        or verification.get("finalExpectedFullyVisibleNails") != EXPECTED_NAILS
    ):
        raise ValueError("role manifest must bind exactly 33 images and 170 expected nails")
    raw_items = role.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != EXPECTED_IMAGES:
        raise ValueError("role manifest items must contain exactly 33 entries")
    items: list[dict[str, Any]] = []
    names: set[str] = set()
    hashes: set[str] = set()
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"role item {index} must be an object")
        file_name = str(raw.get("fileName") or "")
        image_hash = str(raw.get("imageSha256") or "")
        source_group = str(raw.get("sourceGroup") or "")
        nails = raw.get("fullyVisibleNails")
        if (
            not file_name
            or Path(file_name).name != file_name
            or file_name in names
            or len(image_hash) != 64
            or image_hash in hashes
            or not source_group
            or not isinstance(nails, int)
            or isinstance(nails, bool)
            or nails < 1
        ):
            raise ValueError(f"role item has invalid or duplicate identity: {file_name}")
        if (
            raw.get("assignedRole") != EXPECTED_ROLE
            or raw.get("trainingUse") != "prohibited"
            or raw.get("annotationTruthStatus") != "not-started"
            or raw.get("originalResolutionReviewed") is not True
        ):
            raise ValueError(f"role item has unsafe state: {file_name}")
        names.add(file_name)
        hashes.add(image_hash)
        items.append(raw)
    if sum(int(item["fullyVisibleNails"]) for item in items) != EXPECTED_NAILS:
        raise ValueError("role item nail counts do not sum to 170")
    if role.get("aggregates", {}).get("finalItemsSha256") != canonical_sha256(items):
        raise ValueError("role manifest finalItemsSha256 mismatch")
    image_root_record = role.get("inputs", {}).get("imageRoot")
    if not isinstance(image_root_record, dict):
        raise ValueError("role manifest imageRoot is missing")
    image_root = Path(str(image_root_record.get("path") or "")).resolve()
    if not image_root.is_dir():
        raise ValueError(f"role image root is missing: {image_root}")
    return role, items, image_root


def shard_items(
    by_group: dict[str, list[dict[str, Any]]], target_size: int
) -> list[list[dict[str, Any]]]:
    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for _, group_items in sorted(by_group.items()):
        ordered = sorted(group_items, key=lambda item: str(item["fileName"]))
        if current and len(current) + len(ordered) > target_size:
            shards.append(current)
            current = []
        current.extend(ordered)
    if current:
        shards.append(current)
    return shards


def validate_workspace(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    workspace_root = manifest_path.parent
    require_outside_repository(workspace_root)
    manifest = read_json(manifest_path, "annotation workspace manifest")
    if manifest.get("ok") is not True or manifest.get("decision") != WORKSPACE_DECISION:
        raise ValueError("workspace manifest is not a passing candidate-only workspace")
    role_record = manifest.get("inputs", {}).get("roleReplacementManifest")
    verifier_record = manifest.get("inputs", {}).get("roleManifestVerifier")
    if not isinstance(role_record, dict) or not isinstance(verifier_record, dict):
        raise ValueError("workspace does not bind role manifest and verifier")
    role_path = Path(str(role_record.get("path") or "")).resolve()
    if not role_path.is_file() or role_record.get("sha256") != sha256_file(role_path):
        raise ValueError("workspace role manifest binding drifted")
    verification = run_role_verifier(role_path)
    if (
        verifier_record.get("scriptPath") != str(verifier_script())
        or verifier_record.get("scriptSha256") != sha256_file(verifier_script())
        or verifier_record.get("result") != verification
        or verifier_record.get("resultSha256") != canonical_sha256(verification)
    ):
        raise ValueError("workspace role verifier binding differs from current deep replay")
    _, role_items, image_root = validate_role(role_path, verification)
    role_by_name = {str(item["fileName"]): item for item in role_items}
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != EXPECTED_IMAGES:
        raise ValueError("workspace must contain exactly 33 items")
    image_dir = workspace_root / "images"
    shard_dir = workspace_root / "shards"
    if Path(str(manifest.get("imageDir") or "")).resolve() != image_dir:
        raise ValueError("workspace imageDir is not canonical")
    names: set[str] = set()
    hashes: set[str] = set()
    group_shards: dict[str, set[int]] = {}
    methods: dict[str, int] = {}
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("workspace items must be objects")
        file_name = str(raw.get("fileName") or "")
        image_hash = str(raw.get("sha256") or "")
        role_item = role_by_name.get(file_name)
        workspace_path = image_dir / file_name
        source_path = image_root / file_name
        if file_name in names or image_hash in hashes or role_item is None:
            raise ValueError(f"workspace contains duplicate or unknown identity: {file_name}")
        if (
            image_hash != role_item["imageSha256"]
            or raw.get("sourceGroup") != role_item["sourceGroup"]
            or raw.get("expectedFullyVisibleNails") != role_item["fullyVisibleNails"]
            or raw.get("assignedRole") != EXPECTED_ROLE
            or raw.get("trainingUse") != "prohibited"
            or raw.get("annotationTruthStatus") != "not-started"
            or Path(str(raw.get("sourcePath") or "")).resolve() != source_path
            or Path(str(raw.get("workspacePath") or "")).resolve() != workspace_path
        ):
            raise ValueError(f"workspace item differs from role manifest: {file_name}")
        if (
            not source_path.is_file()
            or not workspace_path.is_file()
            or sha256_file(source_path) != image_hash
            or sha256_file(workspace_path) != image_hash
        ):
            raise ValueError(f"workspace source/materialized image drift: {file_name}")
        method = str(raw.get("materializationMethod") or "")
        if method not in {"hardlink", "copy"}:
            raise ValueError(f"invalid materialization method: {file_name}")
        if method == "hardlink" and not os.path.samefile(source_path, workspace_path):
            raise ValueError(f"declared hardlink is not a hardlink: {file_name}")
        shard_index = raw.get("shardIndex")
        if not isinstance(shard_index, int) or isinstance(shard_index, bool) or shard_index < 1:
            raise ValueError(f"invalid shard index: {file_name}")
        group_shards.setdefault(str(raw["sourceGroup"]), set()).add(shard_index)
        methods[method] = methods.get(method, 0) + 1
        names.add(file_name)
        hashes.add(image_hash)
    if set(role_by_name) != names or any(len(value) != 1 for value in group_shards.values()):
        raise ValueError("workspace has partial role coverage or split source groups")
    if sorted(path.name for path in image_dir.iterdir() if path.is_file()) != sorted(names):
        raise ValueError("workspace image directory contains missing or extra files")
    counts = manifest.get("counts")
    if (
        not isinstance(counts, dict)
        or counts.get("images") != EXPECTED_IMAGES
        or counts.get("sourceGroups") != len(group_shards)
        or counts.get("expectedFullyVisibleNails") != EXPECTED_NAILS
        or counts.get("materializationMethods") != methods
        or manifest.get("itemsSha256") != canonical_sha256(items)
    ):
        raise ValueError("workspace counts or items aggregate mismatch")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or counts.get("shards") != len(shards):
        raise ValueError("workspace shard count mismatch")
    csv_names: set[str] = set()
    expected_shard_files: set[str] = set()
    for expected_index, shard in enumerate(shards, start=1):
        if not isinstance(shard, dict) or shard.get("index") != expected_index:
            raise ValueError("workspace shard indexes must be consecutive")
        shard_path = shard_dir / f"annotation-shard-{expected_index:03d}.csv"
        expected_shard_files.add(shard_path.name)
        if (
            Path(str(shard.get("path") or "")).resolve() != shard_path
            or not shard_path.is_file()
            or shard.get("sha256") != sha256_file(shard_path)
        ):
            raise ValueError(f"workspace shard binding drift: {expected_index}")
        with shard_path.open("r", encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        row_names = {str(row.get("fileName") or "") for row in rows}
        manifest_names = {
            str(item["fileName"]) for item in items if item["shardIndex"] == expected_index
        }
        if row_names != manifest_names or len(rows) != len(row_names):
            raise ValueError(f"workspace shard CSV coverage mismatch: {expected_index}")
        csv_names.update(row_names)
    if csv_names != names or {path.name for path in shard_dir.iterdir()} != expected_shard_files:
        raise ValueError("workspace shard files do not exactly cover the manifest")
    # The annotation workspace is intentionally extended in place with downstream
    # candidate-generation, review, and truth-finalization directories. Those
    # derived artifacts are outside this manifest's trust boundary. Verification
    # remains exact for the managed image/shard inventories above while staying
    # repeatable after legitimate downstream work has been added.
    return {
        "ok": True,
        "decision": "release_test_annotation_workspace_verified",
        "manifest": str(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        **dict(counts),
        "itemsSha256": manifest["itemsSha256"],
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    role_path = Path(args.role_replacement_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    require_outside_repository(output_dir)
    if not role_path.is_file():
        raise ValueError(f"role replacement manifest is missing: {role_path}")
    if args.target_shard_size < 1:
        raise ValueError("target shard size must be positive")
    verification = run_role_verifier(role_path)
    role_hash = sha256_file(role_path)
    _, items, image_root = validate_role(role_path, verification)
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")

    by_group: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        source_path = image_root / str(item["fileName"])
        if not source_path.is_file():
            raise ValueError(f"source image is missing: {source_path}")
        if sha256_file(source_path) != item["imageSha256"]:
            raise ValueError(f"source image SHA-256 drift: {item['fileName']}")
        by_group.setdefault(str(item["sourceGroup"]), []).append(item)
    shards = shard_items(by_group, args.target_shard_size)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent)
    )
    output_existed = output_dir.exists()
    try:
        temp_images = temporary / "images"
        temp_shards = temporary / "shards"
        temp_images.mkdir()
        temp_shards.mkdir()
        final_images = output_dir / "images"
        final_shards = output_dir / "shards"
        materialized: list[dict[str, Any]] = []
        methods: dict[str, int] = {}
        shard_records: list[dict[str, Any]] = []
        for shard_index, shard in enumerate(shards, start=1):
            rows: list[dict[str, Any]] = []
            for item in shard:
                file_name = str(item["fileName"])
                source_path = image_root / file_name
                temp_path = temp_images / file_name
                method = "hardlink"
                try:
                    os.link(source_path, temp_path)
                except OSError:
                    shutil.copy2(source_path, temp_path)
                    method = "copy"
                if sha256_file(temp_path) != item["imageSha256"]:
                    raise ValueError(f"materialized image SHA-256 mismatch: {file_name}")
                methods[method] = methods.get(method, 0) + 1
                record = {
                    "fileName": file_name,
                    "sourcePath": str(source_path),
                    "workspacePath": str(final_images / file_name),
                    "sha256": item["imageSha256"],
                    "sourceGroup": item["sourceGroup"],
                    "assignedRole": EXPECTED_ROLE,
                    "originalAssignedRole": item.get("originalAssignedRole"),
                    "roleOrigin": item.get("roleOrigin"),
                    "expectedFullyVisibleNails": item["fullyVisibleNails"],
                    "shardIndex": shard_index,
                    "materializationMethod": method,
                    "trainingUse": "prohibited",
                    "annotationTruthStatus": "not-started",
                }
                materialized.append(record)
                rows.append(record)
            temp_csv = temp_shards / f"annotation-shard-{shard_index:03d}.csv"
            with temp_csv.open("w", encoding="utf-8", newline="") as target:
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
                    "path": str(final_shards / temp_csv.name),
                    "sha256": sha256_file(temp_csv),
                    "images": len(rows),
                    "sourceGroups": sorted({str(row["sourceGroup"]) for row in rows}),
                }
            )

        verification_after = run_role_verifier(role_path)
        if verification_after != verification or sha256_file(role_path) != role_hash:
            raise ValueError("role evidence changed while materializing workspace")
        for item in materialized:
            source_path = Path(str(item["sourcePath"]))
            if sha256_file(source_path) != item["sha256"]:
                raise ValueError(f"source image changed while materializing: {item['fileName']}")
        manifest = {
            "schemaVersion": 1,
            "ok": True,
            "decision": WORKSPACE_DECISION,
            "inputs": {
                "roleReplacementManifest": {"path": str(role_path), "sha256": role_hash},
                "roleManifestVerifier": {
                    "scriptPath": str(verifier_script()),
                    "scriptSha256": sha256_file(verifier_script()),
                    "result": verification,
                    "resultSha256": canonical_sha256(verification),
                },
            },
            "policy": {
                "selectionMode": EXPECTED_ROLE,
                "assignedRole": EXPECTED_ROLE,
                "sourceGroupsRemainAtomicAcrossShards": True,
                "workspaceDoesNotApproveMasks": True,
                "workspaceDoesNotGrantTrainingUse": True,
                "originalResolutionReviewRequired": True,
                "workspaceMustRemainOutsideGit": True,
            },
            "imageDir": str(final_images),
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
            "itemsSha256": canonical_sha256(materialized),
            "items": materialized,
            "errors": [],
        }
        (temporary / "annotation-workspace-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if output_existed:
            if any(output_dir.iterdir()):
                raise ValueError(f"output directory became non-empty: {output_dir}")
            output_dir.rmdir()
        os.rename(temporary, output_dir)
        temporary = Path()
        try:
            return validate_workspace(output_dir / "annotation-workspace-manifest.json")
        except Exception:
            shutil.rmtree(output_dir)
            if output_existed:
                output_dir.mkdir()
            raise
    finally:
        if temporary != Path() and temporary.exists():
            shutil.rmtree(temporary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or deeply verify the 33-image release-test annotation workspace."
    )
    parser.add_argument("--role-replacement-manifest")
    parser.add_argument("--output-dir")
    parser.add_argument("--target-shard-size", type=int, default=10)
    parser.add_argument("--verify-workspace-manifest")
    args = parser.parse_args()
    if args.verify_workspace_manifest:
        if args.role_replacement_manifest or args.output_dir:
            parser.error("--verify-workspace-manifest cannot be combined with build arguments")
    elif not args.role_replacement_manifest or not args.output_dir:
        parser.error("build requires --role-replacement-manifest and --output-dir")
    return args


def main() -> None:
    args = parse_args()
    result = (
        validate_workspace(Path(args.verify_workspace_manifest))
        if args.verify_workspace_manifest
        else build(args)
    )
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
