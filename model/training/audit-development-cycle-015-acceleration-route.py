#!/usr/bin/env python3
"""用历史源图/真值漏斗与训练吞吐证据验证循环015提速路线。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any


DECISION = "replace_50_candidate_intake_with_133_source_qualified_development_cohort"


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


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("Wilson区间计数无效")
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half_width = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - half_width, center + half_width


def bound(path: Path, label: str) -> tuple[dict[str, Any], dict[str, str]]:
    resolved = path.resolve()
    return read_object(resolved, label), {"path": str(resolved), "sha256": sha256_file(resolved)}


def build_report(
    source_screening_path: Path,
    authorization_path: Path,
    truth_index_path: Path,
    capacity_path: Path,
    stoploss_path: Path,
    throughput_path: Path,
) -> dict[str, Any]:
    source, source_input = bound(source_screening_path, "历史源图审核")
    authorization, authorization_input = bound(authorization_path, "历史候选授权")
    truth, truth_input = bound(truth_index_path, "历史最终真值索引")
    capacity, capacity_input = bound(capacity_path, "开发容量审计")
    stoploss, stoploss_input = bound(stoploss_path, "循环015止损审计")
    throughput, throughput_input = bound(throughput_path, "训练吞吐诊断")

    source_counts = source.get("counts") or {}
    if source.get("decision") != "source_screening_batch_pass":
        raise ValueError("历史源图审核未通过")
    if (source_counts.get("images"), source_counts.get("keptForAnnotation"), source_counts.get("excluded")) != (1166, 565, 601):
        raise ValueError("历史源图漏斗计数漂移")

    authorization_counts = authorization.get("counts") or {}
    if authorization.get("decision") != "exact_positive_training_authorization_recorded":
        raise ValueError("历史候选授权合同无效")
    if authorization_counts.get("authorizedImages") != 160:
        raise ValueError("历史候选分母不是160")

    truth_summary = truth.get("summary") or {}
    if truth.get("decision") != "approved_unique_training_truth_index":
        raise ValueError("历史最终真值索引未通过")
    if (truth_summary.get("uniqueImageCount"), truth_summary.get("completeMaskCount")) != (120, 636):
        raise ValueError("历史最终真值计数漂移")
    if (truth.get("policy") or {}).get("trainingUse") != "prohibited-until-materialization-audit":
        raise ValueError("历史最终真值角色证据漂移")

    shortages = capacity.get("developmentResolutionShortages") or {}
    spurious = shortages.get("spuriousRateResolution") or {}
    if capacity.get("ok") is not True or spurious.get("targetPositiveImages") != 148:
        raise ValueError("开发容量审计未绑定148图触发点")
    if (spurious.get("currentCleanDevelopmentImages"), spurious.get("additionalImagesToExtendCurrentCohort")) != (58, 90):
        raise ValueError("开发容量审计90图缺口漂移")

    if stoploss.get("decision") != "exclude_only_recovered_source_acquire_50_new_candidates":
        raise ValueError("循环015止损审计不是当前旧库存归零证据")
    if (stoploss.get("counts") or {}).get("eligibleForMaskRepairAfterStoploss") != 0:
        raise ValueError("循环015旧库存并未归零")

    levers = throughput.get("levers") or []
    workers = next((item for item in levers if item.get("change") == "workers: 0 -> 8"), None)
    if not workers or workers.get("projectedSpeedupPercent") != 22.3:
        raise ValueError("训练吞吐22.3%证据漂移")

    source_total = int(source_counts["images"])
    source_kept = int(source_counts["keptForAnnotation"])
    authorized = int(authorization_counts["authorizedImages"])
    truth_approved = int(truth_summary["uniqueImageCount"])
    approved_needed = int(spurious["additionalImagesToExtendCurrentCohort"])
    source_rate = source_kept / source_total
    truth_rate = truth_approved / authorized
    source_lower, source_upper = wilson_interval(source_kept, source_total)
    truth_lower, truth_upper = wilson_interval(truth_approved, authorized)
    qualified_point = math.ceil(approved_needed / truth_rate)
    qualified_conservative = math.ceil(approved_needed / truth_lower)
    raw_point = math.ceil(approved_needed / (source_rate * truth_rate))
    raw_conservative = math.ceil(approved_needed / (source_lower * truth_lower))
    first_batch = 50

    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": DECISION,
        "analysisKind": "metadata_only_historical_funnel_and_throughput_replay",
        "readImagePixels": False,
        "runTraining": False,
        "runInference": False,
        "inputs": {
            "sourceScreening": source_input,
            "historicalAuthorization": authorization_input,
            "historicalTruthIndex": truth_input,
            "developmentCapacity": capacity_input,
            "repairStoploss": stoploss_input,
            "trainingThroughput": throughput_input,
        },
        "historicalFunnel": {
            "rawReviewedImages": source_total,
            "sourceQualifiedImages": source_kept,
            "sourceQualificationRate": round(source_rate, 8),
            "sourceQualificationWilson95": [round(source_lower, 8), round(source_upper, 8)],
            "authorizedSourceQualifiedImages": authorized,
            "approvedTruthImages": truth_approved,
            "approvedCompleteMasks": int(truth_summary["completeMaskCount"]),
            "truthApprovalRate": round(truth_rate, 8),
            "truthApprovalWilson95": [round(truth_lower, 8), round(truth_upper, 8)],
        },
        "nextTrainingTrigger": {
            "currentCleanDevelopmentImages": 58,
            "targetCleanDevelopmentImages": 148,
            "approvedImagesNeeded": approved_needed,
        },
        "routeSizing": {
            "oldMilestoneSourceQualifiedCandidates": first_batch,
            "oldMilestoneExpectedApprovedAtPointRate": round(first_batch * truth_rate, 8),
            "oldMilestoneExpectedApprovedAtWilsonLower": round(first_batch * truth_lower, 8),
            "oldMilestoneCanReachTrainingTrigger": False,
            "sourceQualifiedCandidatesPointEstimate": qualified_point,
            "sourceQualifiedCandidatesConservativeFloor": qualified_conservative,
            "rawImagesPointEstimate": raw_point,
            "rawImagesConservativePlanningEnvelope": raw_conservative,
            "planningRule": "continue_raw_acquisition_until_133_source_qualified_candidates_are_frozen",
        },
        "validatedAccelerators": {
            "stopRepeatedRepair": True,
            "skipPrematureTrainingBefore90ApprovedImages": True,
            "freezeRolesBeforeAnnotationOrModelAssistance": True,
            "pipelineSourceScreeningAnnotationAndOriginalResolutionReviewByAtomicSourceGroup": True,
            "workers8ProjectedTrainingSpeedupPercent": 22.3,
            "workers8RequiresSameDataSameSeedMetricNeutralityTest": True,
        },
        "limits": {
            "historicalRatesArePlanningEvidenceNotAnApprovalGuarantee": True,
            "calendarSpeedupForParallelHumanReviewNotYetMeasured": True,
            "qualityThresholdsChanged": False,
            "protectedOrConsumedDataReused": False,
        },
        "nextAction": "acquire_screen_and_freeze_133_new_source_qualified_development_candidates_before_annotation_or_model_assistance",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-screening")
    parser.add_argument("--authorization")
    parser.add_argument("--truth-index")
    parser.add_argument("--capacity")
    parser.add_argument("--stoploss")
    parser.add_argument("--throughput")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放提速路线报告")
        inputs = existing.get("inputs") or {}
        replay = build_report(
            Path(inputs["sourceScreening"]["path"]),
            Path(inputs["historicalAuthorization"]["path"]),
            Path(inputs["historicalTruthIndex"]["path"]),
            Path(inputs["developmentCapacity"]["path"]),
            Path(inputs["repairStoploss"]["path"]),
            Path(inputs["trainingThroughput"]["path"]),
        )
        if replay != existing:
            raise ValueError("提速路线报告与绑定输入重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    required = [args.source_screening, args.authorization, args.truth_index, args.capacity, args.stoploss, args.throughput, args.output]
    if any(not value for value in required):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = build_report(
        Path(args.source_screening), Path(args.authorization), Path(args.truth_index),
        Path(args.capacity), Path(args.stoploss), Path(args.throughput),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "routeSizing": report["routeSizing"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
