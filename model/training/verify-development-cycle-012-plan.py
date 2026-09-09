#!/usr/bin/env python3
"""重放循环012单变量预注册合同及其输入证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
QUALITY_SCRIPT = HERE / "build-development-clean-rebaseline-report.py"
PROFILE_SCRIPT = HERE / "profile-development-instance-errors.py"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象：{path}")
    return value


def require_binding(binding: Any, label: str) -> Path:
    if not isinstance(binding, dict):
        raise ValueError(f"{label}绑定缺失")
    path = Path(str(binding.get("path", ""))).resolve()
    if not path.is_file() or sha256_file(path) != binding.get("sha256"):
        raise ValueError(f"{label}缺失或哈希漂移：{path}")
    return path


def replay(script: Path, report: Path, label: str) -> None:
    result = subprocess.run(
        [sys.executable, str(script), "--verify-report", str(report)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"{label}重放失败：{result.stderr.strip()}")


def verify(plan_path: Path) -> dict[str, Any]:
    plan = read_json(plan_path)
    if (
        plan.get("schemaVersion") != 1
        or plan.get("cycleId") != "nail-texture-development-cycle-012"
        or plan.get("decision") != "pre_registered_pending_targeted_positive_truth_materialization"
        or plan.get("releaseState") != "hold"
        or plan.get("hypothesis", {}).get("onlyVariable") != "targetedSourceIsolatedRealPositiveAugmentation"
    ):
        raise ValueError("循环012顶层预注册合同无效")
    evidence = plan.get("evidence", {})
    decision_path = require_binding(evidence.get("cleanRebaselineDecision"), "干净重基线决策")
    quality_path = require_binding(evidence.get("qualityReport"), "干净重基线质量报告")
    profile_path = require_binding(evidence.get("errorProfile"), "干净重基线错误剖面")
    replay(QUALITY_SCRIPT, quality_path, "质量报告")
    replay(PROFILE_SCRIPT, profile_path, "错误剖面")
    decision = read_json(decision_path)
    quality = read_json(quality_path)
    profile = read_json(profile_path)
    if (
        decision.get("decision") != "clean_truth_rebaseline_failed_development_floor_choose_targeted_positive_augmentation"
        or decision.get("evaluationRunCount") != 1
        or decision.get("gates", {}).get("allRequired") is not False
        or quality.get("decision") != "fail_train_internal_development_floor"
        or profile.get("profile", {}).get("recommendation", {}).get("selectedVariable")
        != "targeted_source_isolated_real_positive_augmentation"
    ):
        raise ValueError("循环012选择结论与重基线证据不一致")
    selection = plan.get("targetedPositiveSelectionContract", {})
    if (
        selection.get("images") != 13
        or selection.get("masks") != 65
        or selection.get("sourceGroups") != 13
        or selection.get("exactlyFiveFullyVisibleNailsPerImage") is not True
        or selection.get("trainingUseBeforeFinalReview") != "prohibited"
        or selection.get("sourceGroupOverlapWithExistingTrainOr98Evaluation") != 0
        or selection.get("imageSha256OverlapWithExistingTrainOr98Evaluation") != 0
        or len(selection.get("requiredMorphologyCoverage", [])) != 5
    ):
        raise ValueError("循环012定向正图选择合同漂移")
    training = plan.get("fixedTrainingContract", {})
    legacy_plan = read_json(HERE / "nail-texture-development-cycle-011-plan-v1.json")
    legacy_training = legacy_plan.get("fixedTrainingContract", {})
    matching_fields = (
        "inputSize", "epochs", "patience", "batch", "device", "workers", "optimizer",
        "lr0", "freeze", "mosaic", "closeMosaic", "maskRatio", "overlapMask",
        "hardBoundaryWeight", "distillation", "windowsCudaEpochSync",
    )
    if any(training.get(key) != legacy_training.get(key) for key in matching_fields):
        raise ValueError("循环012训练合同未保持循环011控制变量")
    if training.get("maximumExperiments") != 1:
        raise ValueError("循环012实验次数必须锁定为1")
    evaluation = plan.get("fixedDevelopmentEvaluationContract", {})
    quality_contract = quality.get("contract", {})
    for key in ("split", "inputSize", "scoreThreshold", "matchIou", "completeMaskIou"):
        if evaluation.get(key) != quality_contract.get(key):
            raise ValueError(f"循环012评估合同漂移：{key}")
    floors = plan.get("formalFloorForPromotionToFullTrain")
    if floors != {
        "minimumInstanceRecall": 0.9,
        "minimumCompleteMaskRatio": 0.85,
        "maximumMissingImageRate": 0.1,
        "maximumWeightedSpuriousRate": 0.02,
        "everyEvaluationImageAccountedFor": True,
    }:
        raise ValueError("循环012开发绝对门被修改")
    if plan.get("launchGate", {}).get("status") != "blocked_until_exact_13_image_65_mask_truth_is_final_reviewed_and_materialized":
        raise ValueError("循环012训练启动门漂移")
    return {
        "ok": True,
        "decision": plan["decision"],
        "onlyVariable": plan["hypothesis"]["onlyVariable"],
        "launchGate": plan["launchGate"]["status"],
        "planSha256": sha256_file(plan_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "nail-texture-development-cycle-012-plan-v1.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.plan.resolve()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
