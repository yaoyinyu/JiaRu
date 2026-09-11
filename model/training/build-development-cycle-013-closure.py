#!/usr/bin/env python3
"""以零推理可达性证据关闭循环013逐甲mask替换分支，并支持深度重放。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
EXPECTED_DECISION = "unreachable_close_development_cycle_013_mask_replacement_branch"
EXPECTED_CEILING_DECISION = "unreachable_by_mask_replacement_stage2"
EXPECTED_HEADLINE = {
    "epsilon": 0.05,
    "missingInstances": 16,
    "missingImages": 11,
    "instanceRecall": 0.95480226,
    "completeMaskRatio": 0.85310734,
    "weightedSpuriousNumerator": 27.0,
    "weightedSpuriousRate": 0.07627119,
}
EXPECTED_REQUIRED_SAMPLE_SIZES = {
    "missingImageRate 0.2241 vs 0.1724": 932,
    "missingImageRate 0.1724 vs 0.1000": 352,
    "weightedSpuriousRate 0.0960 vs 0.0200": 148,
}


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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def headline_from(ceiling: dict[str, Any]) -> dict[str, Any]:
    epsilon = float(ceiling.get("headlineEpsilon", -1))
    rows = ceiling.get("epsilonSweep")
    if not isinstance(rows, list):
        raise ValueError("可达性报告缺少epsilonSweep")
    row = next((candidate for candidate in rows if float(candidate.get("epsilon", -1)) == epsilon), None)
    if not isinstance(row, dict) or not isinstance(row.get("summary"), dict):
        raise ValueError("可达性报告缺少headline行")
    summary = row["summary"]
    return {
        "epsilon": epsilon,
        "missingInstances": int(summary["missing"]),
        "missingImages": int(summary["missingImages"]),
        "instanceRecall": float(summary["instanceRecall"]),
        "completeMaskRatio": float(summary["completeMaskRatio"]),
        "weightedSpuriousNumerator": float(summary["weightedSpuriousNumerator"]),
        "weightedSpuriousRate": float(summary["weightedSpuriousRate"]),
    }


def validate_evidence(
    plan: dict[str, Any],
    ceiling: dict[str, Any],
    wilson: dict[str, Any],
    output_roots_exist: dict[str, bool],
) -> dict[str, Any]:
    if (
        plan.get("cycleId") != "nail-texture-development-cycle-013"
        or plan.get("decision") != "pre_registered_high_resolution_roi_pixel_mask_replacement"
        or plan.get("releaseState") != "hold"
    ):
        raise ValueError("循环013计划身份或HOLD状态漂移")
    if ceiling.get("decision") != EXPECTED_CEILING_DECISION:
        raise ValueError("循环013不可达结论漂移")
    fidelity = ceiling.get("reconstructionFidelity", {})
    if fidelity != {"checks": 1190, "mismatchCount": 0, "ok": True}:
        raise ValueError("可达性重建保真门漂移")
    if headline_from(ceiling) != EXPECTED_HEADLINE:
        raise ValueError("循环013理论最优headline漂移")
    margin = ceiling.get("margin", {})
    if (
        int(margin.get("missingTruthsWithoutAttachableCandidate", -1)) != 16
        or float(margin.get("weightedSpuriousNumeratorCeiling", -1)) != 27.0
        or margin.get("spuriousAxisReachable") is not False
    ):
        raise ValueError("不可附着真值或杂散轴上限漂移")
    wilson_fidelity = wilson.get("reconstructionFidelity", {})
    resolution = wilson.get("relativeGateResolvability", {})
    if (
        wilson_fidelity != {"checks": 1190, "mismatchCount": 0, "ok": True}
        or resolution.get("relativeGateInsideBaselineInterval") is not True
        or float(resolution.get("minDetectableDifferenceAtSameN", -1)) != 0.14480412
    ):
        raise ValueError("Wilson判定分辨率结论漂移")
    required = {
        str(row.get("comparison")): int(row.get("requiredImagesPerGroup", -1))
        for row in wilson.get("requiredSampleSizes", [])
        if isinstance(row, dict)
    }
    if required != EXPECTED_REQUIRED_SAMPLE_SIZES:
        raise ValueError("Wilson最小样本量漂移")
    expected_root_keys = {"datasetRoot", "trainingRoot", "clean98EvaluationRoot"}
    if set(output_roots_exist) != expected_root_keys or any(output_roots_exist.values()):
        raise ValueError("循环013已有计划输出，不能声明零预算关闭")
    return {
        "headline": EXPECTED_HEADLINE,
        "unattachedMissingTruths": 16,
        "relativeGateInsideBaselineWilson95": True,
        "minDetectableDifferenceAtSameN": 0.14480412,
        "requiredImagesPerGroup": required,
    }


def build(plan_path: Path, ceiling_path: Path, wilson_path: Path) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    ceiling_path = ceiling_path.resolve()
    wilson_path = wilson_path.resolve()

    plan_verifier = load_module("cycle013_plan_verifier", HERE / "verify-development-cycle-013-plan.py")
    analyzer = load_module("cycle013_ceiling_analyzer", HERE / "analyze-development-cycle-013-candidate-ceiling.py")
    plan = plan_verifier.verify_plan(plan_path)
    ceiling = read_object(ceiling_path, "循环013可达性报告")
    wilson = read_object(wilson_path, "循环013 Wilson报告")
    if not analyzer.verify_content_sha256(ceiling) or not analyzer.verify_content_sha256(wilson):
        raise ValueError("循环013分析报告内容哈希漂移")
    analyzer.verify_ceiling_payload(ceiling)
    analyzer.verify_wilson_payload(wilson)

    planned = plan.get("executionLock", {}).get("plannedOutputs", {})
    output_roots = {key: str(planned.get(key, "")) for key in ("datasetRoot", "trainingRoot", "clean98EvaluationRoot")}
    if any(not value for value in output_roots.values()):
        raise ValueError("循环013计划输出路径不完整")
    output_roots_exist = {key: Path(value).exists() for key, value in output_roots.items()}
    facts = validate_evidence(plan, ceiling, wilson, output_roots_exist)

    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": EXPECTED_DECISION,
        "cycleId": "nail-texture-development-cycle-013",
        "onlyVariable": "highResolutionSingleNailPixelMaskReplacement",
        "releaseState": "hold",
        "productState": "hold",
        "inputs": {
            "plan": binding(plan_path),
            "candidateCeiling": binding(ceiling_path),
            "wilsonResolution": binding(wilson_path),
            "planVerifier": binding(HERE / "verify-development-cycle-013-plan.py"),
            "ceilingAnalyzer": binding(HERE / "analyze-development-cycle-013-candidate-ceiling.py"),
        },
        "replayFacts": facts,
        "plannedOutputRoots": {
            key: {"path": value, "exists": output_roots_exist[key]} for key, value in output_roots.items()
        },
        "budgetConsumption": {
            "proposalMaterializationRuns": 0,
            "stage2TrainingRuns": 0,
            "clean98InferenceRuns": 0,
            "protectedVal30Reads": 0,
            "protectedTest100Reads": 0,
            "releaseHoldoutReads": 0,
        },
        "branchClosure": {
            "closed": True,
            "reason": "在假设完美逐甲mask替换后，漏甲图与杂散率绝对门仍同时不可达；继续训练不能改变候选供给上限。",
            "repeatOrParameterScanAllowed": False,
            "trainingOrInferenceAllowedUnderCycle013": False,
            "formalCandidatePromotionAllowed": False,
        },
        "technicalDecision": {
            "developmentEvaluationCapacity": {
                "minimumPositiveImagesForAbsoluteGateResolution": 352,
                "minimumPositiveImagesPerGroupForRelativeComparison": 932,
                "currentCleanPositiveImages": 58,
                "formalUseBeforeCapacityReached": False,
            },
            "productAbstentionOrManualConfirmationAllowed": True,
            "formalEligibleMissesRemainCounted": True,
            "dataSupplyIsFirstClassRisk": True,
        },
        "nextMilestone": {
            "cycleId": "nail-texture-development-cycle-014",
            "onlyVariable": "fullImageCandidateSupply",
            "objective": "先以来源隔离数据容量审计和零推理可达性合同锁定新候选供给路线，再决定是否消耗一次训练预算。",
            "stage2MaskReplacementBranchRemainsClosed": True,
        },
        "protectedDataRolesChanged": False,
        "historicalFailuresRewritten": False,
        "formalCalibrationTestOrHoldoutRead": False,
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--candidate-ceiling")
    parser.add_argument("--wilson-resolution")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放循环013关闭报告")
        inputs = existing.get("inputs", {})
        replay = build(
            Path(inputs["plan"]["path"]),
            Path(inputs["candidateCeiling"]["path"]),
            Path(inputs["wilsonResolution"]["path"]),
        )
        if replay != existing:
            raise ValueError("循环013关闭报告与当前证据深重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    required = (args.plan, args.candidate_ceiling, args.wilson_resolution, args.output)
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    payload = build(Path(args.plan), Path(args.candidate_ceiling), Path(args.wilson_resolution))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": payload["decision"], "budgetConsumption": payload["budgetConsumption"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
