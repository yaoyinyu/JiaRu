#!/usr/bin/env python3
"""固化循环015恢复候选的原分辨率源图复核，不授予训练资格。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DECISIONS = {
    "keep-for-complete-mask-annotation",
    "exclude-cropped-or-occluded",
    "exclude-quality",
    "exclude-watermark-shortcut",
    "exclude-prior-authoritative-source-gate",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def finalize(supply_path: Path, decisions_path: Path) -> dict[str, Any]:
    supply = read_object(supply_path, "循环015供给审计")
    decisions = read_object(decisions_path, "原分辨率源图复核声明")
    if supply.get("decision") != "recover_7_candidates_and_acquire_at_least_43_for_first_50_batch":
        raise ValueError("供给审计决策无效")
    if decisions.get("schemaVersion") != 1 or decisions.get("reviewScale") != "original-resolution":
        raise ValueError("复核声明合同无效")
    if decisions.get("supplyAuditSha256") != sha256_file(supply_path):
        raise ValueError("复核声明未绑定当前供给审计字节")
    prior_source_gate_path = Path(str(decisions.get("priorSourceGateReport") or "")).resolve()
    prior_source_gate = read_object(prior_source_gate_path, "既有权威源图门报告")
    if decisions.get("priorSourceGateReportSha256") != sha256_file(prior_source_gate_path):
        raise ValueError("复核声明未绑定既有权威源图门报告字节")
    if prior_source_gate.get("decision") != "no_new_training_truth_all_reviewed_remaining_items_rejected_by_original_resolution_source_gate":
        raise ValueError("既有权威源图门报告决策无效")
    if (prior_source_gate.get("policy") or {}).get("rejectedItemsRemainExcluded") is not True:
        raise ValueError("既有权威源图门报告未冻结拒绝项")
    prior_rejected = {
        str(item.get("fileName")): str(item.get("reason") or "")
        for item in (prior_source_gate.get("reviewedItems") or [])
        if item.get("decision") == "exclude"
    }
    candidates = supply.get("recoveredCandidates") or []
    by_file = {str(item.get("fileName")): item for item in candidates}
    if len(by_file) != 7:
        raise ValueError("供给审计候选不是精确7项")
    declared = decisions.get("items")
    if not isinstance(declared, list) or len(declared) != len(by_file):
        raise ValueError("复核声明未覆盖精确7项")
    declared_by_file: dict[str, dict[str, Any]] = {}
    for item in declared:
        file_name = str(item.get("fileName") or "")
        if not file_name or file_name in declared_by_file:
            raise ValueError("复核声明存在空或重复文件名")
        declared_by_file[file_name] = item
    if set(declared_by_file) != set(by_file):
        raise ValueError("复核声明与供给审计候选集合不一致")

    resolved: list[dict[str, Any]] = []
    kept_names: list[str] = []
    for candidate in candidates:
        file_name = str(candidate["fileName"])
        item = declared_by_file[file_name]
        decision = str(item.get("decision") or "")
        if decision not in DECISIONS:
            raise ValueError(f"{file_name}复核决策无效")
        if file_name in prior_rejected and decision == "keep-for-complete-mask-annotation":
            raise ValueError(f"{file_name}违反既有权威源图门的持续排除结论")
        if item.get("imageSha256") != candidate.get("imageSha256"):
            raise ValueError(f"{file_name}图片哈希漂移")
        if item.get("sourceGroup") != candidate.get("sourceGroup"):
            raise ValueError(f"{file_name}来源组漂移")
        reviewed_count = item.get("fullyVisibleNails")
        if decision == "keep-for-complete-mask-annotation":
            if not isinstance(reviewed_count, int) or reviewed_count <= 0:
                raise ValueError(f"{file_name}保留项缺少有效完整甲面计数")
            if item.get("assignedRole") != "development-evaluation-extension":
                raise ValueError(f"{file_name}保留项必须在标注前冻结为开发扩容角色")
            kept_names.append(file_name)
        else:
            if reviewed_count is not None:
                raise ValueError(f"{file_name}排除项不得计入完整甲面")
            if item.get("assignedRole") != "excluded":
                raise ValueError(f"{file_name}排除项角色必须为excluded")
        note = str(item.get("note") or "").strip()
        if not note:
            raise ValueError(f"{file_name}缺少复核理由")
        resolved.append({
            "fileName": file_name,
            "imageSha256": candidate["imageSha256"],
            "sourceGroup": candidate["sourceGroup"],
            "inventoryFullyVisibleNails": candidate["fullyVisibleNails"],
            "reviewedFullyVisibleNails": reviewed_count,
            "decision": decision,
            "assignedRole": item["assignedRole"],
            "note": note,
            "completeMaskReview": "not-started" if decision == "keep-for-complete-mask-annotation" else "not-applicable",
            "trainingUse": "prohibited",
        })

    kept = [item for item in resolved if item["decision"] == "keep-for-complete-mask-annotation"]
    excluded = [item for item in resolved if item["decision"] != "keep-for-complete-mask-annotation"]
    if len(kept) != 1 or len({item["sourceGroup"] for item in kept}) != 1:
        raise ValueError("保守源图复核通过容量漂移")
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "one_source_image_ready_for_complete_mask_repair_new_acquisition_required",
        "inputs": {
            "supplyAudit": str(supply_path.resolve()),
            "supplyAuditSha256": sha256_file(supply_path),
            "sourceReviewDecisions": str(decisions_path.resolve()),
            "sourceReviewDecisionsSha256": sha256_file(decisions_path),
            "priorAuthoritativeSourceGate": str(prior_source_gate_path),
            "priorAuthoritativeSourceGateSha256": sha256_file(prior_source_gate_path),
        },
        "review": {
            "reviewer": decisions.get("reviewer"),
            "reviewedAt": decisions.get("reviewedAt"),
            "method": decisions.get("method"),
            "reviewScale": "original-resolution",
            "modelAssistanceUsed": False,
        },
        "counts": {
            "reviewedImages": len(resolved),
            "keptForCompleteMaskAnnotation": len(kept),
            "keptSourceGroups": len({item["sourceGroup"] for item in kept}),
            "expectedCompleteMasks": sum(int(item["reviewedFullyVisibleNails"]) for item in kept),
            "excludedImages": len(excluded),
            "firstBatchTargetImages": 50,
            "minimumNewCandidateImagesForFirstBatch": 50 - len(kept),
            "minimumNewApprovedPositiveImagesIfAllKeptPassMasks": 424 - len(kept),
        },
        "keptFileNames": kept_names,
        "keptFileNamesSha256": canonical_sha256(kept_names),
        "items": resolved,
        "policy": {
            "sourceReviewDoesNotApproveMasks": True,
            "sourceReviewDoesNotGrantTrainingUse": True,
            "completeMaskOriginalResolutionReviewRequired": True,
            "keptRoleFrozenBeforeCompleteMaskAnnotation": "development-evaluation-extension",
            "priorRejectedItemsRemainExcluded": True,
        },
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supply-audit")
    parser.add_argument("--decisions")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放源图复核报告")
        replay = finalize(Path(existing["inputs"]["supplyAudit"]), Path(existing["inputs"]["sourceReviewDecisions"]))
        if replay != existing:
            raise ValueError("源图复核报告与绑定声明重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    if not args.supply_audit or not args.decisions or not args.output:
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = finalize(Path(args.supply_audit).resolve(), Path(args.decisions).resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
