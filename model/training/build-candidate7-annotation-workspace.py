#!/usr/bin/env python3
"""Build and deeply verify the candidate7 mask-rebuild workspace."""

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


DECISION = "candidate7_annotation_workspace_ready_candidate_only"
KEEP_DECISION = "keep-for-complete-mask-rereview"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def require_file(value: str | Path, label: str) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"missing {label}: {path}")
    return path


def deep_verify_source_report(path: Path) -> dict[str, Any]:
    script = Path(__file__).resolve().parent / "finalize-candidate7-source-review-shard.py"
    result = subprocess.run(
        [sys.executable, str(script), "--verify-report", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        detail = detail or result.stdout.decode("utf-8", errors="replace").strip()
        raise ValueError(f"source-review deep verification failed: {path}: {detail}")
    report = read_object(path, "source-review report")
    if report.get("ok") is not True or report.get("decision") != "candidate7_source_review_shard_complete":
        raise ValueError(f"source-review report is not complete: {path}")
    return report


def load_review_set(report_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not report_paths:
        raise ValueError("at least one source-review report is required")
    all_items: list[dict[str, Any]] = []
    report_records: list[dict[str, Any]] = []
    machine_audit_path: Path | None = None
    machine_audit_sha256 = ""
    machine_audit_items_sha256 = ""
    for path in report_paths:
        report = deep_verify_source_report(path)
        inputs = report.get("inputs", {})
        current_audit = require_file(str(inputs.get("machineAudit", "")), "machine audit")
        if sha256_file(current_audit) != inputs.get("machineAuditSha256"):
            raise ValueError(f"machine-audit hash mismatch in {path}")
        if machine_audit_path is None:
            machine_audit_path = current_audit
            machine_audit_sha256 = str(inputs.get("machineAuditSha256", ""))
            machine_audit_items_sha256 = str(inputs.get("machineAuditItemsSha256", ""))
        elif (
            current_audit != machine_audit_path
            or inputs.get("machineAuditSha256") != machine_audit_sha256
            or inputs.get("machineAuditItemsSha256") != machine_audit_items_sha256
        ):
            raise ValueError("source-review reports do not bind one identical machine audit")
        report_records.append({"path": str(path), "sha256": sha256_file(path)})
        items = report.get("items", [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError(f"invalid source-review items: {path}")
        all_items.extend(items)

    assert machine_audit_path is not None
    machine_audit = read_object(machine_audit_path, "machine audit")
    audit_items = machine_audit.get("items", [])
    if canonical_sha256(audit_items) != machine_audit_items_sha256:
        raise ValueError("machine-audit item digest mismatch")
    audit_names = {str(item.get("fileName", "")) for item in audit_items}
    review_names = [str(item.get("fileName", "")) for item in all_items]
    if len(set(review_names)) != len(review_names):
        raise ValueError("source-review reports contain duplicate fileName values")
    if set(review_names) != audit_names:
        raise ValueError("source-review reports do not exactly cover the machine audit")

    kept = sorted(
        (item for item in all_items if item.get("sourceDecision") == KEEP_DECISION),
        key=lambda item: str(item["fileName"]),
    )
    excluded = [item for item in all_items if item.get("sourceDecision") == "exclude-source"]
    if len(kept) + len(excluded) != len(all_items):
        raise ValueError("source-review reports contain an unsupported decision")
    if any(item.get("completeMaskReview") != "pending" or item.get("trainingUse") != "prohibited" for item in kept):
        raise ValueError("kept source has an unsafe mask-review or training-use state")
    evidence = {
        "sourceReviewReports": report_records,
        "machineAudit": str(machine_audit_path),
        "machineAuditSha256": machine_audit_sha256,
        "machineAuditItemsSha256": machine_audit_items_sha256,
        "reviewedImages": len(all_items),
        "keptImages": len(kept),
        "excludedImages": len(excluded),
    }
    return kept, evidence


def group_shards(items: list[dict[str, Any]], target_size: int) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item["sourceGroup"]), []).append(item)
    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for source_group in sorted(grouped):
        group_items = sorted(grouped[source_group], key=lambda item: str(item["fileName"]))
        if current and len(current) + len(group_items) > target_size:
            shards.append(current)
            current = []
        current.extend(group_items)
    if current:
        shards.append(current)
    return shards


def build_workspace(report_paths: list[Path], output_dir: Path, target_size: int) -> Path:
    if target_size < 1:
        raise ValueError("target shard size must be positive")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    kept, evidence = load_review_set(report_paths)
    shards = group_shards(kept, target_size)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        image_dir = staging / "images"
        shard_dir = staging / "shards"
        image_dir.mkdir()
        shard_dir.mkdir()
        materialized: list[dict[str, Any]] = []
        shard_records: list[dict[str, Any]] = []
        link_methods: dict[str, int] = {}
        for shard_index, shard_items in enumerate(shards, start=1):
            rows: list[dict[str, Any]] = []
            for item in shard_items:
                source_path = require_file(str(item.get("imagePath", "")), "source image")
                if sha256_file(source_path) != item.get("imageSha256"):
                    raise ValueError(f"source image hash mismatch: {source_path}")
                target_path = image_dir / str(item["fileName"])
                method = "hardlink"
                try:
                    os.link(source_path, target_path)
                except OSError:
                    shutil.copy2(source_path, target_path)
                    method = "copy"
                if sha256_file(target_path) != item["imageSha256"]:
                    raise ValueError(f"workspace image hash mismatch: {target_path}")
                link_methods[method] = link_methods.get(method, 0) + 1
                record = {
                    "fileName": item["fileName"],
                    "sourcePath": str(source_path),
                    "workspacePath": str(output_dir / "images" / str(item["fileName"])),
                    "sha256": item["imageSha256"],
                    "imageSha256": item["imageSha256"],
                    "width": item["width"],
                    "height": item["height"],
                    "sourceGroup": item["sourceGroup"],
                    "expectedFullyVisibleNails": item["fullyVisibleNails"],
                    "assignedRole": "candidate7-train-positive-candidate",
                    "shardIndex": shard_index,
                    "materializationMethod": method,
                    "sourceQualityReview": "passed-for-complete-mask-rereview",
                    "completeMaskReview": "not-started",
                    "annotationTruthStatus": "not-started",
                    "trainingUse": "prohibited",
                }
                materialized.append(record)
                rows.append(record)
            shard_path = shard_dir / f"annotation-shard-{shard_index:03d}.csv"
            with shard_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails",
                    "candidateMaskCount", "reviewStatus", "issueCodes", "note",
                ])
                writer.writeheader()
                for row in rows:
                    writer.writerow({
                        "fileName": row["fileName"],
                        "sha256": row["sha256"],
                        "sourceGroup": row["sourceGroup"],
                        "expectedFullyVisibleNails": row["expectedFullyVisibleNails"],
                        "candidateMaskCount": "",
                        "reviewStatus": "",
                        "issueCodes": "",
                        "note": "",
                    })
            shard_records.append({
                "index": shard_index,
                "path": str(output_dir / "shards" / shard_path.name),
                "sha256": sha256_file(shard_path),
                "images": len(rows),
                "sourceGroups": sorted({str(row["sourceGroup"]) for row in rows}),
            })
        manifest = {
            "schemaVersion": 1,
            "ok": True,
            "decision": DECISION,
            "inputs": evidence,
            "policy": {
                "assignedRole": "candidate7-train-positive-candidate",
                "sourceGroupsRemainAtomicAcrossShards": True,
                "workspaceDoesNotApproveMasks": True,
                "workspaceDoesNotGrantTrainingUse": True,
                "candidateModelOutputIsReviewOnly": True,
                "completeMaskOriginalResolutionReviewRequired": True,
                "polygonValidityAndZeroOverlapRequired": True,
                "exactCommercialTrainingAuthorizationRequiredAfterMaskReview": True,
                "workspaceMustRemainOutsideGit": True,
            },
            "imageDir": str(output_dir / "images"),
            "counts": {
                "reviewedImages": evidence["reviewedImages"],
                "images": len(materialized),
                "excludedSources": evidence["excludedImages"],
                "sourceGroups": len({item["sourceGroup"] for item in materialized}),
                "shards": len(shards),
                "expectedFullyVisibleNails": sum(int(item["expectedFullyVisibleNails"]) for item in materialized),
                "materializationMethods": link_methods,
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
    manifest = read_object(manifest_path, "candidate7 annotation workspace")
    if manifest.get("schemaVersion") != 1 or manifest.get("ok") is not True or manifest.get("decision") != DECISION:
        raise ValueError("candidate7 workspace schema, status, or decision is invalid")
    if manifest.get("trainingUse") != "prohibited":
        raise ValueError("candidate7 workspace must remain training prohibited")
    report_records = manifest.get("inputs", {}).get("sourceReviewReports", [])
    report_paths = [require_file(str(record.get("path", "")), "source-review report") for record in report_records]
    for path, record in zip(report_paths, report_records, strict=True):
        if sha256_file(path) != record.get("sha256"):
            raise ValueError(f"source-review report bytes drifted: {path}")
    kept, evidence = load_review_set(report_paths)
    for key in ("machineAudit", "machineAuditSha256", "machineAuditItemsSha256", "reviewedImages", "keptImages", "excludedImages"):
        if manifest.get("inputs", {}).get(key) != evidence.get(key):
            raise ValueError(f"candidate7 workspace input evidence drifted: {key}")
    items = manifest.get("items", [])
    if canonical_sha256(items) != manifest.get("itemsSha256"):
        raise ValueError("candidate7 workspace item digest mismatch")
    if {item["fileName"] for item in items} != {item["fileName"] for item in kept}:
        raise ValueError("candidate7 workspace does not exactly contain the kept source set")
    if len(items) != manifest.get("counts", {}).get("images") or sum(int(item["expectedFullyVisibleNails"]) for item in items) != manifest.get("counts", {}).get("expectedFullyVisibleNails"):
        raise ValueError("candidate7 workspace counts are inconsistent")
    item_by_name = {item["fileName"]: item for item in items}
    if len(item_by_name) != len(items):
        raise ValueError("candidate7 workspace contains duplicate fileName values")
    group_to_shard: dict[str, int] = {}
    shard_names: set[str] = set()
    for shard in manifest.get("shards", []):
        shard_path = require_file(str(shard.get("path", "")), "annotation shard")
        if sha256_file(shard_path) != shard.get("sha256"):
            raise ValueError(f"annotation shard bytes drifted: {shard_path}")
        with shard_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != shard.get("images"):
            raise ValueError(f"annotation shard count mismatch: {shard_path}")
        for row in rows:
            file_name = row["fileName"]
            if file_name in shard_names or file_name not in item_by_name:
                raise ValueError(f"annotation shard coverage is invalid: {file_name}")
            shard_names.add(file_name)
            item = item_by_name[file_name]
            if row["sha256"] != item["sha256"] or row["sourceGroup"] != item["sourceGroup"]:
                raise ValueError(f"annotation shard identity mismatch: {file_name}")
            source_group = str(item["sourceGroup"])
            shard_index = int(shard["index"])
            if source_group in group_to_shard and group_to_shard[source_group] != shard_index:
                raise ValueError(f"source group spans multiple shards: {source_group}")
            group_to_shard[source_group] = shard_index
    if shard_names != set(item_by_name):
        raise ValueError("annotation shards do not exactly cover workspace items")
    for item in items:
        if item.get("trainingUse") != "prohibited" or item.get("annotationTruthStatus") != "not-started":
            raise ValueError(f"unsafe candidate7 workspace item state: {item['fileName']}")
        source = require_file(str(item["sourcePath"]), "source image")
        workspace = require_file(str(item["workspacePath"]), "workspace image")
        if sha256_file(source) != item["sha256"] or sha256_file(workspace) != item["sha256"]:
            raise ValueError(f"candidate7 image bytes drifted: {item['fileName']}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a hash-bound candidate7 complete-mask rebuild workspace.")
    parser.add_argument("--source-review-report", action="append")
    parser.add_argument("--output-dir")
    parser.add_argument("--target-shard-size", type=int, default=20)
    parser.add_argument("--verify-workspace")
    args = parser.parse_args()
    if args.verify_workspace:
        path = require_file(args.verify_workspace, "candidate7 workspace manifest")
        manifest = verify_workspace(path)
        print(json.dumps({"ok": True, "decision": "verified", "manifest": str(path), "counts": manifest["counts"]}, ensure_ascii=False))
        return
    if not args.source_review_report or not args.output_dir:
        parser.error("--source-review-report and --output-dir are required when building")
    reports = [require_file(value, "source-review report") for value in args.source_review_report]
    manifest_path = build_workspace(reports, Path(args.output_dir).resolve(), args.target_shard_size)
    manifest = read_object(manifest_path, "candidate7 workspace manifest")
    print(json.dumps({"ok": True, "decision": manifest["decision"], "manifest": str(manifest_path), "counts": manifest["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
