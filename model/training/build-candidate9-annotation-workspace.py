#!/usr/bin/env python3
"""从哈希绑定的 candidate9 源图增量构建完整甲面标注工作区。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


DECISION = "candidate9_annotation_workspace_ready_candidate_only"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON不是对象：{path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target-shard-size", type=int, default=15)
    args = parser.parse_args()
    source_path = args.source_manifest.resolve()
    output_dir = args.output_dir.resolve()
    source = read_json(source_path)
    items = list(source.get("items") or [])
    counts = source.get("counts") or {}
    if (
        source.get("ok") is not True
        or source.get("decision") != "candidate9_source_delta_ready_for_complete_mask_annotation"
        or source.get("trainingUse") != "prohibited"
        or source.get("itemsSha256") != canonical_sha256(items)
        or len(items) != counts.get("images")
    ):
        raise ValueError("candidate9源图增量状态、计数或摘要不安全")
    if output_dir.exists():
        raise ValueError(f"输出目录已存在：{output_dir}")
    if args.target_shard_size < 1:
        raise ValueError("target-shard-size必须为正整数")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if (
            item.get("sourceReview") != "passed-by-hash-bound-original-resolution-screening"
            or item.get("annotationTruthStatus") != "not-started"
            or item.get("trainingUse") != "prohibited"
        ):
            raise ValueError(f"源图门不安全：{item.get('fileName')}")
        grouped.setdefault(str(item["sourceGroup"]), []).append(item)
    if len(grouped) != counts.get("sourceGroups"):
        raise ValueError("来源组计数漂移")

    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for group in sorted(grouped):
        group_items = sorted(grouped[group], key=lambda row: str(row["fileName"]))
        if current and len(current) + len(group_items) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(group_items)
    if current:
        shards.append(current)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        image_dir = staging / "images"
        shard_dir = staging / "shards"
        image_dir.mkdir()
        shard_dir.mkdir()
        materialized: list[dict[str, Any]] = []
        shard_records: list[dict[str, Any]] = []
        methods: dict[str, int] = {}
        for shard_index, shard_items in enumerate(shards, start=1):
            rows: list[dict[str, Any]] = []
            for item in shard_items:
                source_image = Path(str(item["sourceImage"])).resolve()
                if not source_image.is_file() or sha256_file(source_image) != item["imageSha256"]:
                    raise ValueError(f"源图缺失或漂移：{source_image}")
                target = image_dir / str(item["fileName"])
                method = "hardlink"
                try:
                    os.link(source_image, target)
                except OSError:
                    shutil.copy2(source_image, target)
                    method = "copy"
                methods[method] = methods.get(method, 0) + 1
                row = {
                    "fileName": item["fileName"],
                    "sourcePath": str(source_image),
                    "workspacePath": str(output_dir / "images" / str(item["fileName"])),
                    "sha256": item["imageSha256"],
                    "imageSha256": item["imageSha256"],
                    "width": item["width"],
                    "height": item["height"],
                    "sourceGroup": item["sourceGroup"],
                    "expectedFullyVisibleNails": item["expectedFullyVisibleNails"],
                    "assignedRole": "candidate9-train-positive-candidate",
                    "shardIndex": shard_index,
                    "materializationMethod": method,
                    "sourceQualityReview": "passed-original-resolution-hash-bound",
                    "completeMaskReview": "not-started",
                    "annotationTruthStatus": "not-started",
                    "trainingUse": "prohibited",
                }
                materialized.append(row)
                rows.append(row)
            csv_path = shard_dir / f"annotation-shard-{shard_index:03d}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
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
                    })
            shard_records.append({
                "index": shard_index,
                "path": str(output_dir / "shards" / csv_path.name),
                "sha256": sha256_file(csv_path),
                "images": len(rows),
                "sourceGroups": sorted({str(row["sourceGroup"]) for row in rows}),
            })

        manifest = {
            "schemaVersion": 1,
            "ok": True,
            "decision": DECISION,
            "inputs": {"sourceManifest": str(source_path), "sourceManifestSha256": sha256_file(source_path)},
            "policy": {
                "workspaceDoesNotApproveMasks": True,
                "candidateModelOutputIsReviewOnly": True,
                "completeMaskOriginalResolutionReviewRequired": True,
            },
            "imageDir": str(output_dir / "images"),
            "counts": {
                "images": len(materialized), "sourceGroups": len(grouped), "shards": len(shards),
                "expectedFullyVisibleNails": sum(int(row["expectedFullyVisibleNails"]) for row in materialized),
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
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"ok": True, "manifest": str(output_dir / "annotation-workspace-manifest.json"), "counts": manifest["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
