#!/usr/bin/env python3
"""审计循环012的13图65个完整甲面候选，放行到物化门而不直接授权训练。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


ALLOWED_ANNOTATION_DECISIONS = {
    "candidate_only_not_training_truth",
    "candidate_only_not_training_or_test_truth",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def polygon_for(annotation: dict[str, Any], width: int, height: int, label: str) -> Polygon:
    points = annotation.get("polygon")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError(f"{label}缺少有效polygon")
    coordinates: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError(f"{label}坐标项不是对象")
        x, y = point.get("x"), point.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError(f"{label}坐标不是数值")
        if not 0 <= float(x) <= width or not 0 <= float(y) <= height:
            raise ValueError(f"{label}坐标越界")
        coordinates.append((float(x), float(y)))
    polygon = Polygon(coordinates)
    if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
        raise ValueError(f"{label}polygon无效")
    return polygon


def build(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = Path(args.plan).resolve()
    source_path = Path(args.source_selection_audit).resolve()
    review_path = Path(args.review_manifest).resolve()
    image_dir = Path(args.image_dir).resolve()
    annotation_dir = Path(args.annotation_dir).resolve()
    plan = read_object(plan_path, "循环计划")
    source = read_object(source_path, "来源审计")
    review = read_object(review_path, "原分辨率mask审核")
    contract = plan.get("targetedPositiveSelectionContract") or {}
    if plan.get("cycleId") != "nail-texture-development-cycle-012":
        raise ValueError("循环计划身份不匹配")
    if contract.get("images") != 13 or contract.get("masks") != 65:
        raise ValueError("循环计划不再是13图65 mask合同")
    if source.get("ok") is not True or source.get("decision") != "development_cycle_012_source_selection_pass_candidate_only":
        raise ValueError("来源审计未通过候选门")
    if source.get("trainingUse") != "prohibited" or source.get("counts") != {
        "images": 13, "sourceGroups": 13, "expectedFullyVisibleNails": 65
    }:
        raise ValueError("来源审计计数或训练禁用状态无效")
    if review.get("decision") != "development_cycle_012_original_resolution_mask_review_pass_candidate_only":
        raise ValueError("mask审核决策无效")
    if review.get("trainingUse") != "prohibited":
        raise ValueError("mask审核必须保持训练禁用")
    source_binding = review.get("sourceSelectionAudit") or {}
    if source_binding != binding(source_path):
        raise ValueError("mask审核没有绑定当前来源审计")
    source_items = source.get("items")
    review_items = review.get("items")
    if not isinstance(source_items, list) or len(source_items) != 13:
        raise ValueError("来源审计不是13图")
    if not isinstance(review_items, list) or len(review_items) != 13:
        raise ValueError("mask审核不是13图")
    review_by_name = {str(item.get("fileName")): item for item in review_items if isinstance(item, dict)}
    if len(review_by_name) != 13:
        raise ValueError("mask审核文件名重复")

    canonical_truths: list[dict[str, Any]] = []
    total_masks = 0
    for source_item in source_items:
        name = str(source_item.get("fileName") or "")
        image_path = image_dir / name
        annotation_path = annotation_dir / f"{Path(name).stem}.json"
        if not image_path.is_file() or not annotation_path.is_file():
            raise ValueError(f"图片或标注不存在：{name}")
        image_hash = sha256_file(image_path)
        if image_hash != source_item.get("sha256"):
            raise ValueError(f"图片SHA不匹配：{name}")
        review_item = review_by_name.get(name)
        if not review_item:
            raise ValueError(f"缺少mask审核项：{name}")
        annotation_hash = sha256_file(annotation_path)
        required_review = {
            "imageSha256": image_hash,
            "annotationPath": str(annotation_path),
            "annotationSha256": annotation_hash,
            "sourceGroup": source_item.get("sourceGroup"),
            "reviewScale": "original-resolution",
            "reviewDecision": "pass_complete_mask_candidate_only",
            "expectedFullyVisibleNails": 5,
            "completeMaskCount": 5,
            "missingNails": 0,
            "duplicateMasks": 0,
            "contaminatedMasks": 0,
            "trainingUse": "prohibited",
        }
        if any(review_item.get(key) != value for key, value in required_review.items()):
            raise ValueError(f"mask审核项字段无效：{name}")
        evidence_path = Path(str(review_item.get("evidencePath") or "")).resolve()
        if not evidence_path.is_file() or sha256_file(evidence_path) != review_item.get("evidenceSha256"):
            raise ValueError(f"视觉证据绑定无效：{name}")
        annotation = read_object(annotation_path, f"标注{name}")
        image = annotation.get("image") or {}
        if (
            annotation.get("decision") not in ALLOWED_ANNOTATION_DECISIONS
            or annotation.get("trainingUse") != "prohibited"
            or annotation.get("originalResolutionReviewRequired") is not True
            or image.get("fileName") != name
            or image.get("sourceGroup") != source_item.get("sourceGroup")
        ):
            raise ValueError(f"候选标注合同无效：{name}")
        with Image.open(image_path) as opened:
            width, height = opened.size
        if image.get("width") != width or image.get("height") != height:
            raise ValueError(f"标注图片尺寸无效：{name}")
        annotations = annotation.get("annotations")
        if not isinstance(annotations, list) or len(annotations) != 5:
            raise ValueError(f"标注不是5个mask：{name}")
        polygons: list[Polygon] = []
        for index, item in enumerate(annotations, start=1):
            if not isinstance(item, dict) or item.get("label") != "nail_texture":
                raise ValueError(f"标注标签无效：{name}#{index}")
            polygons.append(polygon_for(item, width, height, f"{name}#{index}"))
        for left in range(len(polygons)):
            for right in range(left + 1, len(polygons)):
                if polygons[left].intersection(polygons[right]).area > 0:
                    raise ValueError(f"同图mask交叠：{name}#{left + 1}/#{right + 1}")
        total_masks += len(polygons)
        canonical_truths.append({
            "fileName": name,
            "imagePath": str(image_path),
            "imageSha256": image_hash,
            "annotationPath": str(annotation_path),
            "annotationSha256": annotation_hash,
            "sourceGroup": source_item.get("sourceGroup"),
            "maskCount": len(polygons),
            "coverageIntents": source_item.get("coverageIntents"),
            "trainingUse": "prohibited-until-materialization-audit",
        })
    if total_masks != 65 or len({item["sourceGroup"] for item in canonical_truths}) != 13:
        raise ValueError("最终真值不是13来源组/65 mask")
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "development_cycle_012_positive_truth_ready_for_materialization",
        "inputs": {"plan": binding(plan_path), "sourceSelectionAudit": binding(source_path), "reviewManifest": binding(review_path)},
        "imageRoot": str(image_dir),
        "annotationRoot": str(annotation_dir),
        "counts": {"images": 13, "sourceGroups": 13, "masks": 65, "invalidPolygons": 0, "pairwiseOverlaps": 0},
        "canonicalTruthsSha256": canonical_sha256(canonical_truths),
        "canonicalTruths": canonical_truths,
        "trainingUse": "prohibited-until-materialization-audit",
        "nextGate": "materialize the fixed cycle012 training dataset and verify its hashes before the one authorized short run",
        "errors": [],
    }


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"输出不得覆盖既有证据：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--source-selection-audit")
    parser.add_argument("--review-manifest")
    parser.add_argument("--image-dir")
    parser.add_argument("--annotation-dir")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放报告")
        inputs = existing.get("inputs") or {}
        replay = argparse.Namespace(
            plan=inputs["plan"]["path"],
            source_selection_audit=inputs["sourceSelectionAudit"]["path"],
            review_manifest=inputs["reviewManifest"]["path"],
            image_dir=existing["imageRoot"],
            annotation_dir=existing["annotationRoot"],
        )
        if build(replay) != existing:
            raise ValueError("报告与当前磁盘重放结果不一致")
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0
    required = [args.plan, args.source_selection_audit, args.review_manifest, args.image_dir, args.annotation_dir, args.output]
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    report = build(args)
    output = Path(args.output).resolve()
    write_atomic(output, report)
    print(json.dumps({"ok": True, "counts": report["counts"], "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
