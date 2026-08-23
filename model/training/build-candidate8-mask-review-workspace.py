#!/usr/bin/env python3
"""构建哈希绑定的candidate8原分辨率mask审核工作区，不授予训练资格。"""

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
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


DECISION = "first_annotation_mask_review_workspace_ready_original_resolution_review_required"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象：{path}")
    return value


def require_bound_file(record: dict[str, Any], path_key: str, hash_key: str, label: str) -> Path:
    path = Path(str(record.get(path_key) or "")).resolve()
    if not path.is_file() or sha256_file(path) != record.get(hash_key):
        raise ValueError(f"{label}缺失或字节漂移：{path}")
    return path


def verify_source_workspace(path: Path) -> dict[str, Any]:
    script = Path(__file__).with_name("build-candidate8-unseen-positive-workspace.py")
    result = subprocess.run(
        [sys.executable, str(script), "--verify-workspace", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            "candidate8源工作区深验失败："
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return read_json(path, "candidate8源工作区")


def contain(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    return image


def validate_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Path]]:
    paths = {
        "workspaceManifest": Path(args.workspace_manifest).resolve(),
        "prompts": Path(args.prompts).resolve(),
        "samReport": Path(args.sam_report).resolve(),
        "geometryAudit": Path(args.geometry_audit).resolve(),
        "visualEvidence": Path(args.visual_evidence).resolve(),
    }
    workspace = verify_source_workspace(paths["workspaceManifest"])
    prompts = read_json(paths["prompts"], "candidate8 SAM提示")
    sam = read_json(paths["samReport"], "candidate8 SAM报告")
    geometry = read_json(paths["geometryAudit"], "candidate8几何报告")
    visual = read_json(paths["visualEvidence"], "candidate8视觉证据")
    if (
        prompts.get("decision") != "sam_candidate_only_not_training_truth"
        or prompts.get("trainingUse") != "prohibited"
        or prompts.get("policy", {}).get("originalResolutionReviewRequired") is not True
        or prompts.get("inputs", {}).get("workspaceManifestSha256")
        != sha256_file(paths["workspaceManifest"])
    ):
        raise ValueError("candidate8 SAM提示未保持候选门或未绑定当前源工作区")
    if (
        sam.get("ok") is not True
        or sam.get("decision") != "sam_candidate_only_not_training_truth"
        or sam.get("trainingUse") != "prohibited"
        or sam.get("originalResolutionReviewRequired") is not True
        or sam.get("errors") != []
    ):
        raise ValueError("candidate8 SAM报告不是完整安全候选")
    if geometry.get("decision") != "candidate_only_not_training_truth":
        raise ValueError("candidate8几何报告未保持候选门")
    if (
        visual.get("ok") is not True
        or visual.get("decision") != "sam_visual_review_evidence_ready_not_truth"
        or visual.get("policy", {}).get("trainingUse") != "prohibited"
        or visual.get("policy", {}).get("evidenceDoesNotGrantTruth") is not True
        or visual.get("policy", {}).get("everyPolygonHasSourceAndOverlay2xCrop") is not True
    ):
        raise ValueError("candidate8视觉证据不安全")
    visual_inputs = visual.get("inputs") or {}
    for key in ("prompts", "samReport", "geometryAudit"):
        if Path(str(visual_inputs.get(key) or "")).resolve() != paths[key]:
            raise ValueError(f"candidate8视觉证据路径未绑定：{key}")
        if visual_inputs.get(f"{key}Sha256") != sha256_file(paths[key]):
            raise ValueError(f"candidate8视觉证据哈希未绑定：{key}")

    workspace_items = {str(item["fileName"]): item for item in workspace.get("items", [])}
    prompt_items = {str(item["fileName"]): item for item in prompts.get("images", [])}
    sam_items = {str(item["fileName"]): item for item in sam.get("outputs", [])}
    visual_items = {str(item["fileName"]): item for item in visual.get("items", [])}
    geometry_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in geometry.get("rows", []):
        geometry_rows[str(row.get("fileName") or "")].append(row)
    selected_names = set(prompt_items)
    if (
        len(selected_names) != len(prompts.get("images", []))
        or selected_names != set(sam_items)
        or selected_names != set(visual_items)
        or selected_names != set(geometry_rows)
        or not selected_names.issubset(workspace_items)
    ):
        raise ValueError("candidate8提示、SAM、几何、视觉证据覆盖不一致")
    if (
        prompts.get("imageCount") != len(selected_names)
        or sam.get("completedCount") != len(selected_names)
        or visual.get("summary", {}).get("images") != len(selected_names)
    ):
        raise ValueError("candidate8候选图片汇总计数不一致")

    rows: list[dict[str, Any]] = []
    for file_name in sorted(selected_names):
        source = workspace_items[file_name]
        prompt = prompt_items[file_name]
        sam_item = sam_items[file_name]
        visual_item = visual_items[file_name]
        image_hash = source.get("sha256") or source.get("imageSha256")
        image_path = Path(str(source.get("workspacePath") or "")).resolve()
        if not image_path.is_file() or sha256_file(image_path) != image_hash:
            raise ValueError(f"candidate8源图缺失或漂移：{file_name}")
        if (
            prompt.get("sha256") != image_hash
            or prompt.get("sourceGroup") != source.get("sourceGroup")
            or sam_item.get("sourceGroup") != source.get("sourceGroup")
            or visual_item.get("imageSha256") != image_hash
            or visual_item.get("sourceGroup") != source.get("sourceGroup")
        ):
            raise ValueError(f"candidate8候选身份漂移：{file_name}")
        annotation_path = require_bound_file(
            visual_item, "annotationPath", "annotationSha256", f"{file_name} annotation"
        )
        overlay_path = require_bound_file(
            visual_item, "overlayPath", "overlaySha256", f"{file_name} overlay"
        )
        annotation = read_json(annotation_path, f"{file_name} annotation")
        candidate_count = len(annotation.get("annotations") or [])
        expected = int(source["expectedFullyVisibleNails"])
        current_geometry = geometry_rows[file_name]
        crops = visual_item.get("crops") or []
        if (
            annotation.get("trainingUse") != "prohibited"
            or annotation.get("decision") != "candidate_only_not_training_truth"
            or annotation.get("image", {}).get("fileName") != file_name
            or candidate_count != len(prompt.get("boxes") or [])
            or candidate_count != sam_item.get("polygonCount")
            or candidate_count != visual_item.get("polygonCount")
            or candidate_count != len(current_geometry)
            or candidate_count != len(crops)
        ):
            raise ValueError(f"candidate8候选计数或annotation门漂移：{file_name}")
        for crop in crops:
            require_bound_file(crop, "sourceCrop", "sourceCropSha256", f"{file_name}原图裁片")
            require_bound_file(crop, "overlayCrop", "overlayCropSha256", f"{file_name}叠加裁片")
        suspect_count = sum(row.get("status") != "pass" for row in current_geometry)
        reason_codes = sorted(
            {
                reason
                for row in current_geometry
                if row.get("status") != "pass"
                for reason in row.get("reasons", [])
            }
        )
        rows.append(
            {
                "fileName": file_name,
                "sha256": image_hash,
                "sourceGroup": source["sourceGroup"],
                "expectedFullyVisibleNails": expected,
                "candidateCount": candidate_count,
                "countDelta": candidate_count - expected,
                "geometrySuspectCount": suspect_count,
                "geometryIssueCodes": ";".join(reason_codes),
                "annotationPath": str(annotation_path),
                "annotationSha256": sha256_file(annotation_path),
                "overlayPath": str(overlay_path),
                "overlaySha256": sha256_file(overlay_path),
                "imagePath": str(image_path),
                "riskRank": 1 if suspect_count else 2,
            }
        )
    return workspace, rows, paths


def build(args: argparse.Namespace) -> Path:
    output = Path(args.output_dir).resolve()
    if output.exists():
        raise ValueError(f"输出目录已存在：{output}")
    if args.target_shard_size < 1 or args.images_per_page < 1:
        raise ValueError("分片和页面图片数必须为正整数")
    workspace, rows, paths = validate_inputs(args)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["sourceGroup"]].append(row)
    ordered_groups = sorted(
        groups.items(),
        key=lambda entry: (
            min(row["riskRank"] for row in entry[1]),
            -len(entry[1]),
            entry[0],
        ),
    )
    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for _, group_rows in ordered_groups:
        group_rows.sort(key=lambda row: (-row["geometrySuspectCount"], row["fileName"]))
        if current and len(current) + len(group_rows) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(group_rows)
    if current:
        shards.append(current)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        shard_dir = staging / "shards"
        sheet_dir = staging / "sheets"
        shard_dir.mkdir()
        sheet_dir.mkdir()
        font = ImageFont.load_default()
        fieldnames = [
            "fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails",
            "candidateCount", "countDelta", "geometrySuspectCount", "geometryIssueCodes",
            "riskRank", "annotationSha256", "overlaySha256", "reviewStatus",
            "finalCompleteMaskCount", "issueCodes", "keepPromptIndices",
            "dropPromptIndices", "addPromptBoxesJson", "note",
        ]
        shard_records: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        for shard_index, shard_rows in enumerate(shards, start=1):
            csv_path = shard_dir / f"mask-review-{shard_index:03d}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                for row in shard_rows:
                    writer.writerow({key: row.get(key, "") for key in fieldnames})
            shard_records.append(
                {
                    "index": shard_index,
                    "path": str(output / "shards" / csv_path.name),
                    "sha256": sha256_file(csv_path),
                    "images": len(shard_rows),
                    "sourceGroups": sorted({row["sourceGroup"] for row in shard_rows}),
                }
            )
            for start in range(0, len(shard_rows), args.images_per_page):
                page_index = start // args.images_per_page + 1
                canvas = Image.new("RGB", (2200, 1900), "white")
                draw = ImageDraw.Draw(canvas)
                draw.text(
                    (24, 16),
                    f"Candidate8 mask review shard {shard_index:03d} page {page_index:03d} | original left, SAM right",
                    fill="black",
                    font=font,
                )
                for offset, row in enumerate(shard_rows[start : start + args.images_per_page]):
                    y = 65 + offset * 900
                    original = contain(Path(row["imagePath"]), (1040, 760))
                    overlay = contain(Path(row["overlayPath"]), (1040, 760))
                    canvas.paste(original, (24 + (1040 - original.width) // 2, y + (760 - original.height) // 2))
                    canvas.paste(overlay, (1136 + (1040 - overlay.width) // 2, y + (760 - overlay.height) // 2))
                    draw.text(
                        (24, y + 772),
                        f"{start + offset + 1:03d} {row['fileName']} | expected {row['expectedFullyVisibleNails']} candidate {row['candidateCount']} suspect {row['geometrySuspectCount']}",
                        fill="black",
                        font=font,
                    )
                page_path = sheet_dir / f"mask-review-{shard_index:03d}-page-{page_index:03d}.jpg"
                canvas.save(page_path, quality=94)
                pages.append(
                    {
                        "shardIndex": shard_index,
                        "pageIndex": page_index,
                        "path": str(output / "sheets" / page_path.name),
                        "sha256": sha256_file(page_path),
                        "startRow": start + 1,
                        "endRow": min(start + args.images_per_page, len(shard_rows)),
                    }
                )
        selected_names = {row["fileName"] for row in rows}
        excluded = sorted(
            str(item["fileName"])
            for item in workspace.get("items", [])
            if str(item["fileName"]) not in selected_names
        )
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": DECISION,
            "inputs": {
                key: str(path) for key, path in paths.items()
            } | {
                f"{key}Sha256": sha256_file(path) for key, path in paths.items()
            },
            "policy": {
                "sourceGroupsRemainAtomicAcrossShards": True,
                "contactSheetsAreNavigationOnly": True,
                "originalResolutionReviewRequired": True,
                "reviewWorkspaceDoesNotApproveMasks": True,
                "trainingUse": "prohibited",
                "promptIndicesAreOneBased": True,
            },
            "counts": {
                "images": len(rows),
                "sourceGroups": len(groups),
                "expectedFullyVisibleNails": sum(row["expectedFullyVisibleNails"] for row in rows),
                "candidatePolygons": sum(row["candidateCount"] for row in rows),
                "geometrySuspects": sum(row["geometrySuspectCount"] for row in rows),
                "excludedCandidateImages": len(excluded),
                "shards": len(shards),
                "pages": len(pages),
            },
            "excludedCandidateFiles": excluded,
            "shards": shard_records,
            "pages": pages,
            "trainingUse": "prohibited",
            "errors": [],
        }
        report_path = staging / "mask-review-workspace-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, output)
        return output / report_path.name
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if output.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--sam-report", required=True)
    parser.add_argument("--geometry-audit", required=True)
    parser.add_argument("--visual-evidence", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-shard-size", type=int, default=12)
    parser.add_argument("--images-per-page", type=int, default=2)
    try:
        args = parser.parse_args()
        output = build(args)
        report = read_json(output, "candidate8审核工作区报告")
        print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
