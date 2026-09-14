#!/usr/bin/env python3
"""以原分辨率可见性和历史返修失败证据关闭循环015唯一恢复源图。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


FILE_NAME = "nail_01063_69417639000000001f005854_0.jpg"
SOURCE_REVIEW_DECISION = "one_source_image_ready_for_complete_mask_repair_new_acquisition_required"
HISTORICAL_AUDIT_DECISION = "historical_candidates_prompt_only_rebuild_15_complete_masks"
STOPLOSS_DECISION = "exclude-repeated-repair-and-occluded-required-nail"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def bound_object(entry: dict[str, Any], path_key: str, sha_key: str, label: str) -> tuple[Path, dict[str, Any]]:
    path = Path(str(entry.get(path_key) or "")).resolve()
    value = read_object(path, label)
    if entry.get(sha_key) != sha256_file(path):
        raise ValueError(f"{label}字节哈希漂移")
    return path, value


def audit(decision_path: Path) -> dict[str, Any]:
    decision_path = decision_path.resolve()
    decision = read_object(decision_path, "止损审核声明")
    if decision.get("schemaVersion") != 1 or decision.get("decision") != STOPLOSS_DECISION:
        raise ValueError("止损审核声明合同无效")
    if decision.get("reviewScale") != "original-resolution" or decision.get("newModelInferenceUsed") is not False:
        raise ValueError("止损审核必须是零新增推理的原分辨率视觉判定")
    if decision.get("fileName") != FILE_NAME:
        raise ValueError("止损审核文件身份漂移")
    issues = set(decision.get("issueCodes") or [])
    required_issues = {
        "partially_occluded_required_nail",
        "duplicate_candidate_for_same_nail",
        "repeated_mask_repair_failure",
    }
    if not required_issues.issubset(issues):
        raise ValueError("止损审核缺少必要失败原因")
    inputs = decision.get("inputs") or {}
    source_review_path, source_review = bound_object(inputs, "sourceReview", "sourceReviewSha256", "循环015源图复核")
    historical_audit_path, historical_audit = bound_object(inputs, "historicalAudit", "historicalAuditSha256", "历史候选审计")
    if source_review.get("decision") != SOURCE_REVIEW_DECISION or source_review.get("keptFileNames") != [FILE_NAME]:
        raise ValueError("循环015源图复核不是当前唯一保留项")
    if historical_audit.get("decision") != HISTORICAL_AUDIT_DECISION:
        raise ValueError("历史候选审计决策无效")
    source_item = next(item for item in source_review.get("items", []) if item.get("fileName") == FILE_NAME)
    if (historical_audit.get("item") or {}).get("imageSha256") != source_item.get("imageSha256"):
        raise ValueError("历史候选审计与源图身份不一致")

    ordinary_entries = inputs.get("ordinarySamAnnotations")
    if not isinstance(ordinary_entries, list) or len(ordinary_entries) != 3:
        raise ValueError("普通SAM快照必须精确覆盖v1/v2/v3")
    ordinary_hashes: list[str] = []
    ordinary_paths: list[str] = []
    for index, entry in enumerate(ordinary_entries, start=1):
        path, annotation = bound_object(entry, "path", "sha256", f"普通SAM v{index} annotation")
        if annotation.get("decision") != "candidate_only_not_training_truth" or annotation.get("trainingUse") != "prohibited":
            raise ValueError("普通SAM快照角色不安全")
        if len(annotation.get("annotations") or []) != 15:
            raise ValueError("普通SAM快照候选数不是15")
        ordinary_paths.append(str(path))
        ordinary_hashes.append(sha256_file(path))
    if len(set(ordinary_hashes)) != 1:
        raise ValueError("普通SAM v1/v2/v3并非同一字节快照")

    geometry_path, geometry = bound_object(inputs, "ordinaryGeometry", "ordinaryGeometrySha256", "普通SAM几何审计")
    rows = [row for row in geometry.get("rows", []) if row.get("fileName") == FILE_NAME]
    if len(rows) != 15:
        raise ValueError("普通SAM几何审计未覆盖15项")
    suspects = sorted(int(row["nailIndex"]) for row in rows if row.get("status") == "suspect")
    if suspects != [13, 15]:
        raise ValueError("普通SAM重复冲突项漂移")
    if any("peer_polygon_intersection_area_above_maximum" not in (row.get("reasons") or []) for row in rows if row.get("status") == "suspect"):
        raise ValueError("普通SAM疑点不是同甲重叠")

    ranked_path, ranked_final = bound_object(inputs, "rankedFinal", "rankedFinalSha256", "排序SAM终审")
    ranked_item = ranked_final.get("item") or {}
    if ranked_item.get("fileName") != FILE_NAME or ranked_item.get("reviewStatus") != "rework":
        raise ValueError("排序SAM终审未保持返修失败")
    if "duplicate_or_overlapping_mask" not in (ranked_item.get("issueCodes") or []):
        raise ValueError("排序SAM终审缺少重复交叠证据")

    later_path, later_final = bound_object(inputs, "laterFinal", "laterFinalSha256", "后续SAM终审")
    later_item = next((item for item in later_final.get("items", []) if item.get("fileName") == FILE_NAME), None)
    if not later_item or later_item.get("reviewStatus") != "rework" or later_item.get("candidateCount") != 18:
        raise ValueError("后续SAM终审未保持18候选返修失败")
    if "missing_or_misaligned_nails" not in (later_item.get("issueCodes") or []):
        raise ValueError("后续SAM终审缺少漏甲或错位证据")

    visual_path, visual = bound_object(inputs, "laterVisualEvidence", "laterVisualEvidenceSha256", "后续SAM视觉证据")
    visual_item = next((item for item in visual.get("items", []) if item.get("fileName") == FILE_NAME), None)
    if not visual_item or visual_item.get("imageSha256") != source_item.get("imageSha256"):
        raise ValueError("后续SAM视觉证据与源图身份不一致")
    partial_index = int(decision.get("partiallyOccludedNailEvidenceIndex") or 0)
    partial_crop = next((crop for crop in visual_item.get("crops", []) if crop.get("nailIndex") == partial_index), None)
    if not partial_crop:
        raise ValueError("未找到部分遮挡甲面局部证据")
    crop_path = Path(str(partial_crop.get("sourceCrop") or "")).resolve()
    if sha256_file(crop_path) != partial_crop.get("sourceCropSha256"):
        raise ValueError("部分遮挡甲面局部证据哈希漂移")
    if decision.get("partiallyOccludedNailCropSha256") != partial_crop.get("sourceCropSha256"):
        raise ValueError("止损审核未绑定部分遮挡甲面局部证据")

    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "exclude_only_recovered_source_acquire_50_new_candidates",
        "inputs": {
            "decision": str(decision_path),
            "decisionSha256": sha256_file(decision_path),
            "sourceReview": str(source_review_path),
            "sourceReviewSha256": sha256_file(source_review_path),
            "historicalAudit": str(historical_audit_path),
            "historicalAuditSha256": sha256_file(historical_audit_path),
            "ordinarySamAnnotations": ordinary_paths,
            "ordinarySamAnnotationSha256": ordinary_hashes[0],
            "ordinaryGeometry": str(geometry_path),
            "ordinaryGeometrySha256": sha256_file(geometry_path),
            "rankedFinal": str(ranked_path),
            "rankedFinalSha256": sha256_file(ranked_path),
            "laterFinal": str(later_path),
            "laterFinalSha256": sha256_file(later_path),
            "laterVisualEvidence": str(visual_path),
            "laterVisualEvidenceSha256": sha256_file(visual_path),
            "partiallyOccludedNailSourceCrop": str(crop_path),
            "partiallyOccludedNailSourceCropSha256": sha256_file(crop_path),
        },
        "counts": {
            "recoveredCandidatesBeforeStoploss": 1,
            "eligibleForMaskRepairAfterStoploss": 0,
            "excludedAfterStoploss": 1,
            "ordinarySamSnapshots": 3,
            "uniqueOrdinarySamSnapshots": 1,
            "independentHistoricalCandidateFamilies": 3,
            "firstBatchTargetImages": 50,
            "minimumNewCandidateImagesForFirstBatch": 50,
            "minimumNewApprovedPositiveImages": 424,
        },
        "item": {
            "fileName": FILE_NAME,
            "imageSha256": source_item["imageSha256"],
            "sourceGroup": source_item["sourceGroup"],
            "priorExpectedFullyVisibleNails": 15,
            "finalDisposition": "excluded",
            "issueCodes": sorted(required_issues),
            "note": str(decision.get("note") or ""),
            "trainingUse": "prohibited",
        },
        "policy": {
            "sourceWithRequiredOccludedNailIsExcluded": True,
            "repeatedRepairFailureTriggersStoploss": True,
            "historicalFailuresRemainFailures": True,
            "newModelInferenceUsed": False,
        },
        "nextAction": "acquire_and_freeze_50_new_source_isolated_candidates_before_annotation_or_model_assistance",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放止损报告")
        replay = audit(Path(existing["inputs"]["decision"]))
        if replay != existing:
            raise ValueError("止损报告与绑定输入重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    if not args.decision or not args.output:
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = audit(Path(args.decision))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
