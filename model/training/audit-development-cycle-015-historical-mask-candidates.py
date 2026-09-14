#!/usr/bin/env python3
"""审计循环015唯一现有源图的历史mask候选，仅允许作为返修定位输入。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_FILE = "nail_01063_69417639000000001f005854_0.jpg"
EXPECTED_MASKS = 15


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


def audit(source_review_path: Path, historical_final_path: Path) -> dict[str, Any]:
    source_review_path = source_review_path.resolve()
    historical_final_path = historical_final_path.resolve()
    source_review = read_object(source_review_path, "循环015源图复核")
    historical_final = read_object(historical_final_path, "历史mask终审")
    if source_review.get("decision") != "one_source_image_ready_for_complete_mask_repair_new_acquisition_required":
        raise ValueError("循环015源图复核决策无效")
    if source_review.get("keptFileNames") != [EXPECTED_FILE]:
        raise ValueError("循环015保留源图不是精确唯一项")
    source_item = next((item for item in source_review.get("items", []) if item.get("fileName") == EXPECTED_FILE), None)
    if not source_item or source_item.get("reviewedFullyVisibleNails") != EXPECTED_MASKS:
        raise ValueError("循环015唯一源图的完整甲面分母漂移")
    final_item = historical_final.get("item") or {}
    if final_item.get("fileName") != EXPECTED_FILE:
        raise ValueError("历史mask终审文件身份不匹配")
    for field, source_field in (("sha256", "imageSha256"), ("sourceGroup", "sourceGroup")):
        if final_item.get(field) != source_item.get(source_field):
            raise ValueError(f"历史mask终审{field}与循环015源图不一致")
    if final_item.get("expectedFullyVisibleNails") != EXPECTED_MASKS:
        raise ValueError("历史mask终审分母不是15")
    if final_item.get("reviewStatus") != "rework" or final_item.get("trainingUse") != "prohibited":
        raise ValueError("历史mask终审不得是已批准训练真值")
    inputs = historical_final.get("inputs") or {}
    annotation_path = Path(str(inputs.get("annotation") or "")).resolve()
    annotation = read_object(annotation_path, "历史SAM标注")
    annotation_sha = sha256_file(annotation_path)
    if inputs.get("annotationSha256") != annotation_sha:
        raise ValueError("历史SAM标注哈希与终审绑定不一致")
    if annotation.get("decision") != "candidate_only_not_training_truth" or annotation.get("trainingUse") != "prohibited":
        raise ValueError("历史SAM标注角色不安全")
    image = annotation.get("image") or {}
    if image.get("fileName") != EXPECTED_FILE or image.get("sourceGroup") != source_item.get("sourceGroup"):
        raise ValueError("历史SAM标注图片身份或来源组不一致")
    polygon_count = len(annotation.get("annotations") or [])
    if polygon_count != EXPECTED_MASKS or final_item.get("polygonCount") != EXPECTED_MASKS:
        raise ValueError("历史SAM候选未覆盖15个定位槽位")
    geometry_pass = int(final_item.get("geometryPass") or 0)
    geometry_suspect = int(final_item.get("geometrySuspect") or 0)
    if geometry_pass + geometry_suspect != EXPECTED_MASKS:
        raise ValueError("历史几何审计计数不闭合")
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "historical_candidates_prompt_only_rebuild_15_complete_masks",
        "inputs": {
            "sourceReview": str(source_review_path),
            "sourceReviewSha256": sha256_file(source_review_path),
            "historicalFinal": str(historical_final_path),
            "historicalFinalSha256": sha256_file(historical_final_path),
            "historicalAnnotation": str(annotation_path),
            "historicalAnnotationSha256": annotation_sha,
        },
        "item": {
            "fileName": EXPECTED_FILE,
            "imageSha256": source_item["imageSha256"],
            "sourceGroup": source_item["sourceGroup"],
            "requiredFinalMasks": EXPECTED_MASKS,
            "historicalCandidatePolygons": polygon_count,
            "historicalGeometryPass": geometry_pass,
            "historicalGeometrySuspect": geometry_suspect,
            "approvedReusableMasks": 0,
            "promptOnlyCandidateSlots": polygon_count,
            "repairMode": "reuse_15_candidate_slots_for_localization_then_original_resolution_polygon_repair",
            "finalReviewStatus": "not-started",
            "trainingUse": "prohibited",
        },
        "policy": {
            "geometryPassDoesNotApproveMask": True,
            "historicalReworkCannotBecomeTruthByReuse": True,
            "originalResolutionVisualReviewRequiredForEveryFinalMask": True,
            "polygonValidityAndZeroOverlapRequired": True,
            "modelInferenceRequiredForLocalization": False,
        },
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-review")
    parser.add_argument("--historical-final")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放历史候选审计")
        replay = audit(Path(existing["inputs"]["sourceReview"]), Path(existing["inputs"]["historicalFinal"]))
        if replay != existing:
            raise ValueError("历史候选审计与绑定输入重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    if not args.source_review or not args.historical_final or not args.output:
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = audit(Path(args.source_review), Path(args.historical_final))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "item": report["item"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
