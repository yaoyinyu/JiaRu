#!/usr/bin/env python3
"""从 candidate7 新正样本源图审核报告构建候选标注工作区。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-review", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target-shard-size", type=int, default=20)
    args = parser.parse_args()

    report = json.loads(args.source_review.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("trainingUse") not in {None, "prohibited"}:
        raise ValueError("source review is not a safe passing report")
    items = [item for item in report.get("reviewedItems", []) if item.get("decision") == "keep-for-annotation"]
    if len(items) != int(report.get("counts", {}).get("keptForAnnotation", -1)):
        raise ValueError("source-review kept count mismatch")
    if args.output_dir.exists():
        raise ValueError(f"output directory already exists: {args.output_dir}")
    if args.target_shard_size < 1:
        raise ValueError("target shard size must be positive")

    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["sourceGroup"], []).append(item)
    shards: list[list[dict]] = []
    current: list[dict] = []
    for group in sorted(grouped):
        group_items = sorted(grouped[group], key=lambda value: value["fileName"])
        if current and len(current) + len(group_items) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(group_items)
    if current:
        shards.append(current)

    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.output_dir.name}-", dir=args.output_dir.parent))
    try:
        image_dir = staging / "images"
        shard_dir = staging / "shards"
        image_dir.mkdir()
        shard_dir.mkdir()
        materialized: list[dict] = []
        shard_records: list[dict] = []
        methods: dict[str, int] = {}
        for shard_index, shard_items in enumerate(shards, start=1):
            rows: list[dict] = []
            for item in shard_items:
                source = Path(item["imagePath"])
                if not source.is_file() or sha256_file(source) != item["imageSha256"]:
                    raise ValueError(f"source image missing or hash drifted: {source}")
                target = image_dir / item["fileName"]
                method = "hardlink"
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copy2(source, target)
                    method = "copy"
                if sha256_file(target) != item["imageSha256"]:
                    raise ValueError(f"workspace image hash mismatch: {target}")
                methods[method] = methods.get(method, 0) + 1
                row = {
                    "fileName": item["fileName"],
                    "sourcePath": str(source),
                    "workspacePath": str(args.output_dir / "images" / item["fileName"]),
                    "sha256": item["imageSha256"],
                    "imageSha256": item["imageSha256"],
                    "width": item["width"],
                    "height": item["height"],
                    "sourceGroup": item["sourceGroup"],
                    "expectedFullyVisibleNails": item["fullyVisibleNails"],
                    "assignedRole": "candidate7-train-positive-candidate",
                    "shardIndex": shard_index,
                    "materializationMethod": method,
                    "sourceQualityReview": "passed-original-resolution",
                    "completeMaskReview": "not-started",
                    "annotationTruthStatus": "not-started",
                    "exactCandidate7TrainingAuthorization": "missing",
                    "trainingUse": "prohibited",
                }
                materialized.append(row)
                rows.append(row)
            shard_path = shard_dir / f"annotation-shard-{shard_index:03d}.csv"
            with shard_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails",
                    "candidateMaskCount", "reviewStatus", "issueCodes", "note",
                ])
                writer.writeheader()
                for row in rows:
                    writer.writerow({
                        "fileName": row["fileName"], "sha256": row["sha256"],
                        "sourceGroup": row["sourceGroup"],
                        "expectedFullyVisibleNails": row["expectedFullyVisibleNails"],
                        "candidateMaskCount": "", "reviewStatus": "", "issueCodes": "", "note": "",
                    })
            shard_records.append({
                "index": shard_index, "path": str(args.output_dir / "shards" / shard_path.name),
                "sha256": sha256_file(shard_path), "images": len(rows),
                "sourceGroups": sorted({row["sourceGroup"] for row in rows}),
            })
        manifest = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "candidate7_annotation_workspace_ready_candidate_only",
            "inputs": {"sourceReview": str(args.source_review), "sourceReviewSha256": sha256_file(args.source_review)},
            "policy": {
                "workspaceDoesNotApproveMasks": True,
                "workspaceDoesNotGrantTrainingUse": True,
                "candidateModelOutputIsReviewOnly": True,
                "completeMaskOriginalResolutionReviewRequired": True,
                "exactCommercialTrainingAuthorizationRequiredAfterMaskReview": True,
            },
            "imageDir": str(args.output_dir / "images"),
            "counts": {
                "images": len(materialized), "sourceGroups": len(grouped), "shards": len(shards),
                "expectedFullyVisibleNails": sum(int(item["expectedFullyVisibleNails"]) for item in materialized),
                "materializationMethods": methods,
            },
            "itemsSha256": canonical_sha256(materialized),
            "shards": shard_records,
            "items": materialized,
            "trainingUse": "prohibited",
            "errors": [],
        }
        (staging / "annotation-workspace-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(staging, args.output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    final = args.output_dir / "annotation-workspace-manifest.json"
    print(json.dumps({"ok": True, "manifest": str(final), "counts": manifest["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
