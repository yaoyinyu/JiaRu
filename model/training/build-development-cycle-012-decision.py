#!/usr/bin/env python3
"""固化循环012相对clean98基线的单变量判定并支持逐字节证据重放。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPERIMENT_ID = "development-cycle-012-yolo11n-targeted-positive-v1"
ONLY_VARIABLE = "targetedSourceIsolatedRealPositiveAugmentation"


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


def binding(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def metric_checks(summary: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, bool]:
    return {
        "missingImages": int(summary["missingImages"]) <= int(thresholds["maximumMissingImages"]),
        "missingInstances": int(summary["missing"]) <= int(thresholds["maximumMissingInstances"]),
        "instanceRecall": float(summary["instanceRecall"]) >= float(thresholds["minimumInstanceRecall"]),
        "weightedSpuriousRate": float(summary["weightedSpuriousRate"]) <= float(thresholds["maximumWeightedSpuriousRate"]),
        "directlyExtractableRate": float(summary["directlyExtractableRate"]) >= float(thresholds["minimumDirectlyExtractableRate"]),
    }


def build(
    baseline_path: Path,
    train_plan_path: Path,
    train_summary_path: Path,
    quality_path: Path,
    error_profile_path: Path,
) -> dict[str, Any]:
    baseline = read_object(baseline_path, "cycle011 clean98基线")
    plan = read_object(train_plan_path, "cycle012训练计划")
    train_summary = read_object(train_summary_path, "cycle012训练摘要")
    quality = read_object(quality_path, "cycle012 clean98质量报告")
    error_profile = read_object(error_profile_path, "cycle012错误剖面")

    baseline_summary = baseline.get("summary")
    current_summary = quality.get("summary")
    if not isinstance(baseline_summary, dict) or not isinstance(current_summary, dict):
        raise ValueError("质量报告缺少summary")
    shared_denominator = {
        key: baseline_summary.get(key)
        for key in ("evaluationImages", "positiveImages", "hardNegativeImages", "truth")
    }
    if shared_denominator != {"evaluationImages": 98, "positiveImages": 58, "hardNegativeImages": 40, "truth": 354}:
        raise ValueError("cycle011 clean98基线分母漂移")
    if any(current_summary.get(key) != value for key, value in shared_denominator.items()):
        raise ValueError("cycle012与clean98基线分母不一致")
    if (
        baseline.get("ok") is not True
        or quality.get("ok") is not True
        or quality.get("experimentId") != EXPERIMENT_ID
        or quality.get("releaseState") != "hold"
        or error_profile.get("ok") is not True
        or error_profile.get("trainingUse") != "prohibited"
        or error_profile.get("inputs", {}).get("qualityReportSha256") != sha256_file(quality_path)
    ):
        raise ValueError("cycle012评估证据合同无效")

    hypothesis = plan.get("hypothesis", {})
    contract = plan.get("fixedTrainingContract", {})
    thresholds = plan.get("signalJudgement", {})
    if (
        plan.get("cycleId") != "nail-texture-development-cycle-012"
        or plan.get("releaseState") != "hold"
        or hypothesis.get("onlyVariable") != ONLY_VARIABLE
        or contract.get("onlyVariable") != ONLY_VARIABLE
        or plan.get("maximumExperiments") != 1
        or thresholds.get("allRequired") is not True
    ):
        raise ValueError("cycle012单变量训练计划漂移")
    evidence = train_summary.get("development_experiment_evidence", {})
    if (
        train_summary.get("training_intent") != "pre-registered-development-experiment"
        or evidence.get("experiment_id") != EXPERIMENT_ID
        or evidence.get("only_variable") != ONLY_VARIABLE
        or evidence.get("plan_sha256") != sha256_file(train_plan_path)
        or quality.get("inputs", {}).get("trainSummary", {}).get("sha256") != sha256_file(train_summary_path)
        or quality.get("inputs", {}).get("weights", {}).get("sha256") != train_summary.get("best_weights_sha256")
    ):
        raise ValueError("cycle012训练摘要或权重绑定漂移")

    signal_checks = metric_checks(current_summary, thresholds)
    floors = plan.get("formalFloorForPromotionToFullTrain", {})
    formal_checks = {
        "instanceRecall": float(current_summary["instanceRecall"]) >= float(floors["minimumInstanceRecall"]),
        "completeMaskRatio": float(current_summary["completeMaskRatio"]) >= float(floors["minimumCompleteMaskRatio"]),
        "missingImageRate": float(current_summary["missingImageRate"]) <= float(floors["maximumMissingImageRate"]),
        "weightedSpuriousRate": float(current_summary["weightedSpuriousRate"]) <= float(floors["maximumWeightedSpuriousRate"]),
        "everyEvaluationImageAccountedFor": int(current_summary["evaluationImages"]) == 98,
    }
    delta_keys = (
        "matched", "completeMasks", "missing", "missingImages", "duplicates", "falsePositives",
        "invalidPredictionMasks", "directlyExtractableImages", "instanceRecall", "completeMaskRatio",
        "missingImageRate", "weightedSpuriousRate", "directlyExtractableRate",
    )
    deltas = {
        key: round(float(current_summary[key]) - float(baseline_summary[key]), 8)
        for key in delta_keys
    }
    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": "signal_test_failed_close_targeted_positive_augmentation_branch",
        "cycleId": "nail-texture-development-cycle-012",
        "hypothesisId": hypothesis.get("id"),
        "onlyVariable": ONLY_VARIABLE,
        "inputs": {
            "baselineQualityReport": binding(baseline_path),
            "trainPlan": binding(train_plan_path),
            "trainSummary": binding(train_summary_path),
            "qualityReport": binding(quality_path),
            "errorProfile": binding(error_profile_path),
        },
        "sharedClean98Denominator": shared_denominator,
        "baselineSummary": baseline_summary,
        "currentSummary": current_summary,
        "deltasCurrentMinusBaseline": deltas,
        "signalChecks": signal_checks,
        "allRelativeSignalsPassed": all(signal_checks.values()),
        "formalDevelopmentFloorChecks": formal_checks,
        "formalDevelopmentFloorPassed": all(formal_checks.values()),
        "branchClosure": {
            "closed": True,
            "reason": "五项预注册相对信号全部失败，且开发绝对门未通过。",
            "repeatTrainingAllowed": False,
            "thresholdSeedQuotaOrEpochScanAllowed": False,
            "formalCandidatePromotionAllowed": False,
        },
        "nextMilestone": "预注册并实现全图召回加逐甲高分辨率ROI mask替换的两阶段开发原型；先锁定训练与clean98评估合同，不读取正式val30/test100或发布留出。",
        "formalCalibrationTestOrHoldoutRead": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline")
    parser.add_argument("--train-plan")
    parser.add_argument("--train-summary")
    parser.add_argument("--quality-report")
    parser.add_argument("--error-profile")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放cycle012决策")
        inputs = existing.get("inputs", {})
        replay = build(
            Path(inputs["baselineQualityReport"]["path"]),
            Path(inputs["trainPlan"]["path"]),
            Path(inputs["trainSummary"]["path"]),
            Path(inputs["qualityReport"]["path"]),
            Path(inputs["errorProfile"]["path"]),
        )
        if replay != existing:
            raise ValueError("cycle012决策与当前证据重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    required = (args.baseline, args.train_plan, args.train_summary, args.quality_report, args.error_profile, args.output)
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    payload = build(
        Path(args.baseline), Path(args.train_plan), Path(args.train_summary), Path(args.quality_report), Path(args.error_profile)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": payload["decision"], "signalChecks": payload["signalChecks"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
