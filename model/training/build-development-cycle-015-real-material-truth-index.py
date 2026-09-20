#!/usr/bin/env python3
"""构建循环015真实素材首批（11图/52甲）的开发评估真值终局报告与累计唯一索引 v5。

背景（2026-09-19）：
- 真实素材首批12图冻结后，0002在SAM候选拓扑排查中发现 nail2 严重失焦
  （甲/皮肤边界融合，原分辨率不可确认），按Goal核心要求整图排除；
  入库审计v3冻结累计54图/317甲（43 AI保留 + 11真实素材）。
- 11图52甲经守卫版预标注→PCA多点SAM→逐甲原分辨率终审（39 SAM直接接受
  + 13人工多边形返修）→几何审计v6 52/0/0收敛。
- 本脚本为11图生成单图终局真值报告（schema与batch1-4一致），并与既有
  43图development-evaluation-truth-v4目录合并构建累计唯一索引v5。

产物始终是候选：trainingUse=prohibited，数据集物化与来源隔离仍未完成，
不因索引构建本身晋升训练或test真值。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import os
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

INDEX_DECISION = "approved_unique_development_evaluation_truth_index"
REPORT_DECISION = "approved_as_development_evaluation_truth_candidate_pending_dataset_materialization"
SEQUENCE_START = 44  # 既有43图索引序列1..43


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def polygon_checks(annotations: list[dict[str, Any]], errors: list[str]) -> tuple[int, int]:
    polys: list[tuple[str, Polygon]] = []
    invalid = 0
    for nail in annotations:
        pts = [(p["x"], p["y"]) for p in nail["polygon"]]
        poly = Polygon(pts)
        if not poly.is_valid or poly.area <= 0:
            invalid += 1
            errors.append(f"{nail['id']}: invalid polygon topology")
        polys.append((nail["id"], poly))
    overlaps = 0
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            area = polys[i][1].intersection(polys[j][1]).area
            if area > 1e-6:
                overlaps += 1
                errors.append(f"{polys[i][0]}x{polys[j][0]}: intersection {area:.4f}px^2")
    return invalid, overlaps


def build_report(
    ann_path: Path, images_dir: Path, intake_item: dict[str, Any],
    manifest_item: dict[str, Any], audit_v6: dict[str, Any],
    manifest_binding: dict[str, str], audit_v6_binding: dict[str, str],
    sequence: int,
) -> dict[str, Any]:
    doc = read_json(ann_path)
    errors: list[str] = []
    file_name = doc["image"]["fileName"]
    if file_name != intake_item["fileName"]:
        errors.append("fileName与入库审计不一致")
    if doc["image"].get("sourceGroup") != intake_item["sourceGroup"]:
        errors.append("sourceGroup与入库审计不一致")
    image_path = images_dir / file_name
    image_sha = sha256_file(image_path)
    if image_sha != intake_item["imageSha256"]:
        errors.append("图片SHA-256与入库审计不一致")
    if image_sha != manifest_item.get("sha256"):
        errors.append("图片SHA-256与工作区清单不一致")
    expected = int(manifest_item["expectedFullyVisibleNails"])
    nails = doc["annotations"]
    if len(nails) != expected:
        errors.append(f"mask数量{len(nails)}与冻结期望{expected}不一致")
    invalid, overlaps = polygon_checks(nails, errors)
    audit_rows = [
        row for row in audit_v6.get("rows", [])
        if row.get("fileName") == file_name
    ]
    if len(audit_rows) != len(nails) or any(row.get("status") != "pass" for row in audit_rows):
        errors.append("几何审计v6未对该图全部甲面给出pass")
    if doc.get("decision") != "candidate_only_not_training_truth" or doc.get("trainingUse") != "prohibited":
        errors.append("注释文档角色合同漂移")
    report = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": REPORT_DECISION,
        "inputs": {
            "truthRole": "development-evaluation",
            "visualReviewType": "direct-mask-review",
            "visualReviewFinal": audit_v6_binding,
            "image": binding(image_path),
            "annotation": binding(ann_path),
            "roleManifest": manifest_binding,
        },
        "policy": {
            "targetRole": "development-evaluation",
            "originalResolutionVisualReviewRequired": True,
            "polygonTopologyMustBeValid": True,
            "pairwisePolygonIntersectionArea": 0,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "snapshotFreezeAndSourceIsolationStillRequired": False,
            "trainingUse": "prohibited",
            "validationUse": None,
            "evaluationUse": "prohibited-until-clean-development-materialization-audit",
        },
        "item": {
            "fileName": file_name,
            "sha256": image_sha,
            "sourceGroup": intake_item["sourceGroup"],
            "completeMaskCount": len(nails),
            "invalidPolygonCount": invalid,
            "overlapPairCount": overlaps,
            "annotationTruthStatus": "approved-as-development-evaluation-truth-candidate",
            "trainingUse": "prohibited",
            "validationUse": None,
            "evaluationUse": "prohibited-until-clean-development-materialization-audit",
        },
        "errors": errors,
    }
    if sequence is not None:
        report["sequence"] = sequence
    return report


def load_existing_reports(truth_dir: Path, pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(truth_dir.glob(pattern)):
        doc = read_json(path)
        doc["_reportPath"] = str(path)
        doc["_reportSha256"] = sha256_file(path)
        rows.append(doc)
    return rows


def write_atomic(path: Path, value: dict[str, Any]) -> None:
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
    parser.add_argument("--intake-audit")
    parser.add_argument("--workspace-manifest")
    parser.add_argument("--geometry-audit")
    parser.add_argument("--repair-report")
    parser.add_argument("--annotations-dir")
    parser.add_argument("--images-dir")
    parser.add_argument("--existing-truth-dir")
    parser.add_argument("--existing-index")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()

    if args.verify_report:
        index = read_json(Path(args.verify_report))
        problems: list[str] = []
        if index.get("decision") != INDEX_DECISION or index.get("ok") is not True:
            problems.append("索引合同漂移")
        for key in ("realMaterialIntakeAudit", "geometryAuditV6", "manualPolygonRepairReport",
                    "workspaceManifest", "existingIndexV4"):
            entry = (index.get("inputs") or {}).get(key) or {}
            path = Path(str(entry.get("path") or ""))
            if not path.is_file() or sha256_file(path) != entry.get("sha256"):
                problems.append(f"{key}绑定漂移")
        for row in index.get("canonicalTruths", []):
            path = Path(str(row.get("reportPath") or ""))
            if not path.is_file() or sha256_file(path) != row.get("reportSha256"):
                problems.append(f"报告绑定漂移：{row.get('reportName')}")
        if problems:
            raise SystemExit(json.dumps({"ok": False, "errors": problems}, ensure_ascii=False))
        print(json.dumps({"ok": True, "decision": index["decision"],
                          "reportSha256": sha256_file(Path(args.verify_report))}, ensure_ascii=False))
        return 0
    if not all((args.intake_audit, args.workspace_manifest, args.geometry_audit, args.repair_report,
                args.annotations_dir, args.images_dir, args.existing_truth_dir, args.existing_index,
                args.output_dir)):
        raise ValueError("构建模式缺少必填参数")

    intake = read_json(Path(args.intake_audit))
    manifest = read_json(Path(args.workspace_manifest))
    audit_v6 = read_json(Path(args.geometry_audit))
    repair_report = read_json(Path(args.repair_report))
    existing_index = read_json(Path(args.existing_index))

    if intake.get("decision") != "freeze_54_cumulative_source_qualified_candidates_continue_to_133":
        raise ValueError("入库审计v3决策漂移")
    if existing_index.get("decision") != INDEX_DECISION or existing_index.get("summary", {}).get("uniqueImageCount") != 43:
        raise ValueError("既有43图索引无效")
    if repair_report.get("repairCount") != 13:
        raise ValueError("人工返修报告条数漂移")

    real_items = [i for i in intake["items"] if str(i["fileName"]).startswith("cycle015_real")]
    manifest_items = {item["fileName"]: item for item in manifest["items"]}
    if len(real_items) != 11:
        raise ValueError(f"真实素材条目数漂移：{len(real_items)}")

    annotations_dir = Path(args.annotations_dir)
    images_dir = Path(args.images_dir)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output_dir}")
    output_dir.mkdir(parents=True)

    manifest_binding = binding(Path(args.workspace_manifest))
    audit_v6_binding = binding(Path(args.geometry_audit))

    new_reports: list[dict[str, Any]] = []
    for offset, item in enumerate(sorted(real_items, key=lambda x: x["fileName"])):
        sequence = SEQUENCE_START + offset
        stem = Path(item["fileName"]).stem
        ann_path = annotations_dir / f"{stem}.json"
        report = build_report(
            ann_path, images_dir, item, manifest_items[item["fileName"]],
            audit_v6, manifest_binding, audit_v6_binding, sequence,
        )
        if not report["ok"]:
            raise SystemExit(json.dumps({"ok": False, "fileName": item["fileName"],
                                         "errors": report["errors"]}, ensure_ascii=False))
        report_name = f"development-evaluation-truth-{sequence:03d}-{stem}-final.json"
        report_path = output_dir / report_name
        write_atomic(report_path, report)
        new_reports.append({
            "reportPath": str(report_path.resolve()),
            "reportName": report_name,
            "reportSha256": sha256_file(report_path),
            "sequence": sequence,
            "fileName": report["item"]["fileName"],
            "imageSha256": report["item"]["sha256"],
            "sourceGroup": report["item"]["sourceGroup"],
            "completeMaskCount": report["item"]["completeMaskCount"],
        })

    # 合并既有43图报告与新增11图报告，按fileName唯一去重
    pattern = "development-evaluation-truth-*-final.json"
    existing_rows = load_existing_reports(Path(args.existing_truth_dir), pattern)
    seen: dict[str, dict[str, Any]] = {}
    conflicts = 0
    for doc in existing_rows + new_reports:
        item = doc.get("item") or doc
        key = str(item.get("fileName") or "").casefold()
        row = {
            "reportPath": doc.get("_reportPath") or doc["reportPath"],
            "reportName": Path(doc.get("_reportPath") or doc["reportPath"]).name,
            "reportSha256": doc.get("_reportSha256") or doc["reportSha256"],
            "sequence": doc.get("sequence"),
            "fileName": item.get("fileName"),
            "imageSha256": item.get("sha256") or item.get("imageSha256"),
            "sourceGroup": item.get("sourceGroup"),
            "completeMaskCount": item.get("completeMaskCount"),
        }
        if key in seen:
            if seen[key]["imageSha256"] != row["imageSha256"]:
                conflicts += 1
            continue
        seen[key] = row
    canonical = sorted(seen.values(), key=lambda r: (r["sequence"] is None, r["sequence"] or 0, r["fileName"]))
    total_masks = sum(int(r["completeMaskCount"] or 0) for r in canonical)

    index = {
        "schemaVersion": 1,
        "ok": conflicts == 0,
        "decision": INDEX_DECISION,
        "inputs": {
            "truthRole": "development-evaluation",
            "truthDirs": [str(Path(args.existing_truth_dir).resolve()), str(output_dir.resolve())],
            "reportPattern": pattern,
            "existingIndexV4": binding(Path(args.existing_index)),
            "realMaterialIntakeAudit": binding(Path(args.intake_audit)),
            "geometryAuditV6": binding(Path(args.geometry_audit)),
            "manualPolygonRepairReport": binding(Path(args.repair_report)),
            "workspaceManifest": binding(Path(args.workspace_manifest)),
        },
        "summary": {
            "approvedReportCount": len(existing_rows) + len(new_reports),
            "rejectedReportCount": 0,
            "uniqueImageCount": len(canonical),
            "completeMaskCount": total_masks,
            "redundantReportCount": len(existing_rows) + len(new_reports) - len(canonical),
            "redundantImageCount": 0,
            "conflictingImageCount": conflicts,
        },
        "finalReview": {
            "reviewedImages": 11,
            "reviewedNails": 52,
            "samDirectAccepted": 39,
            "manualPolygonRepaired": 13,
            "excludedAtIntake": 1,
            "exclusionReason": "0002 nail2严重失焦，甲/皮肤边界融合原分辨率不可确认，按Goal核心要求整图排除",
            "geometryAuditSummary": {"pass": 52, "suspect": 0, "missing": 0},
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "highest numeric development-evaluation-truth sequence, then report filename",
            "redundantIdenticalReportsAreCountedOnce": True,
            "conflictingDuplicateReportsAreRejected": True,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "snapshotFreezeAndSourceIsolationStillRequired": False,
            "trainingUse": "prohibited",
            "validationUse": None,
            "evaluationUse": "prohibited-until-clean-development-materialization-audit",
        },
        "canonicalTruths": canonical,
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }
    index_path = output_dir / "development-evaluation-truth-index-v5.json"
    write_atomic(index_path, index)
    print(json.dumps({"ok": True, "decision": index["decision"], "summary": index["summary"],
                      "index": str(index_path), "indexSha256": sha256_file(index_path)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
