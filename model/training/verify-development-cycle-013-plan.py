#!/usr/bin/env python3
"""深度核验循环013高分辨率ROI像素mask替换的预注册计划。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
EXPECTED_DECISION = "pre_registered_high_resolution_roi_pixel_mask_replacement"
EXPECTED_ONLY_VARIABLE = "highResolutionSingleNailPixelMaskReplacement"
EXPECTED_GEOMETRY_CONTRACT = {
    "minimumStage2Score": 0.25,
    "maskThreshold": 0.5,
    "minimumAreaRatioToStage1": 0.25,
    "maximumAreaRatioToStage1": 3.0,
    "minimumMaskIouWithStage1": 0.05,
    "maximumCenterShiftToStage1Diagonal": 1.0,
}
EXPECTED_RELATIVE_GATES = {
    "maximumMissingImages": 10,
    "maximumMissingInstances": 16,
    "minimumInstanceRecall": 0.94067797,
    "minimumCompleteMaskRatio": 0.85,
    "maximumWeightedSpuriousRate": 0.0960452,
    "minimumDirectlyExtractableRate": 0.5,
}
EXPECTED_ABSOLUTE_GATES = {
    "minimumInstanceRecall": 0.9,
    "minimumCompleteMaskRatio": 0.85,
    "maximumMissingImageRate": 0.1,
    "maximumWeightedSpuriousRate": 0.02,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象：{path}")
    return value


def bound_file(binding: Any, label: str) -> Path:
    if not isinstance(binding, dict):
        raise ValueError(f"{label}绑定缺失")
    path = Path(str(binding.get("path", ""))).resolve()
    if not path.is_file() or sha256_file(path) != binding.get("sha256"):
        raise ValueError(f"{label}缺失或哈希漂移：{path}")
    return path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_contract(plan: dict[str, Any]) -> None:
    if (
        plan.get("schemaVersion") != 1
        or plan.get("cycleId") != "nail-texture-development-cycle-013"
        or plan.get("decision") != EXPECTED_DECISION
        or plan.get("releaseState") != "hold"
    ):
        raise ValueError("循环013顶层合同无效")
    hypothesis = plan.get("hypothesis")
    if not isinstance(hypothesis, dict) or hypothesis.get("onlyVariable") != EXPECTED_ONLY_VARIABLE:
        raise ValueError("循环013唯一变量漂移")
    if hypothesis.get("oldScoreOnlyStage2RemainsClosed") is not True:
        raise ValueError("旧只重打分stage2未保持关闭")
    stage1 = plan.get("stage1")
    stage2 = plan.get("stage2")
    if not isinstance(stage1, dict) or not isinstance(stage2, dict):
        raise ValueError("两阶段合同缺失")
    if (
        stage1.get("role") != "frozen_full_image_recall_and_candidate_generator"
        or int(stage1.get("inputSize", 0)) != 512
        or float(stage1.get("scoreThreshold", 0)) != 0.25
        or int(stage1.get("maximumCandidatesPerImage", 0)) != 10
        or stage1.get("productDeduplicationUnchanged") is not True
    ):
        raise ValueError("stage1固定合同漂移")
    if (
        stage2.get("role") != "single_nail_high_resolution_pixel_mask_replacement"
        or int(stage2.get("inputSize", 0)) != 384
        or float(stage2.get("cropContextRatio", -1)) != 0.65
        or int(stage2.get("maximumInstancesPerRoi", 0)) != 1
        or stage2.get("outputSemantics") != "two_dimensional_binary_mask_mapped_to_full_image_then_replaces_stage1_mask"
        or stage2.get("failureSemantics") != "fallback_to_same_stage1_candidate_and_record_reason"
        or stage2.get("geometryAcceptance") != EXPECTED_GEOMETRY_CONTRACT
    ):
        raise ValueError("stage2像素mask替换合同漂移")
    data = plan.get("stage2TrainingData")
    if not isinstance(data, dict) or (
        data.get("parentRole") != "train-only"
        or data.get("proposalSource") != "frozen-stage1-on-train-images-only"
        or data.get("labelSource") != "original-resolution-reviewed-parent-ground-truth"
        or data.get("sourceGroupAtomicSplit") is not True
        or int(data.get("validationSourceGroups", 0)) != 18
        or int(data.get("splitSeed", 0)) != 20260910
        or data.get("formalVal30Test100OrHoldoutUsed") is not False
        or data.get("trainVariants") != ["base", "shift_x_neg06", "shift_x_pos06"]
        or int(data.get("minimumUniqueAssociatedTruths", 0)) != 1400
    ):
        raise ValueError("stage2训练数据角色或来源组合同漂移")
    training = plan.get("training")
    if not isinstance(training, dict) or (
        training.get("architecture") != "yolo11n-seg"
        or training.get("initialization") != "frozen-cycle011-stage1-weights"
        or int(training.get("epochs", 0)) != 12
        or int(training.get("patience", 0)) != 4
        or int(training.get("batch", 0)) != 4
        or training.get("optimizer") != "AdamW"
        or float(training.get("lr0", 0)) != 0.0002
        or int(training.get("workers", -1)) != 0
        or int(training.get("mosaic", -1)) != 0
        or int(training.get("maskRatio", 0)) != 1
        or training.get("overlapMask") is not False
        or training.get("distillation") is not False
    ):
        raise ValueError("stage2唯一训练合同漂移")
    execution = plan.get("executionLock")
    if not isinstance(execution, dict) or (
        int(execution.get("maximumProposalMaterializationRuns", 0)) != 1
        or int(execution.get("maximumStage2TrainingRuns", 0)) != 1
        or int(execution.get("maximumClean98InferenceRuns", 0)) != 1
        or execution.get("allOutputRootsMustBeNew") is not True
        or execution.get("implementationHashesLockedBeforeFirstInference") is not True
    ):
        raise ValueError("循环013执行次数锁漂移")
    judgement = plan.get("signalJudgement")
    if not isinstance(judgement, dict) or (
        judgement.get("relativeToCycle011Clean98") != EXPECTED_RELATIVE_GATES
        or judgement.get("developmentAbsoluteFloor") != EXPECTED_ABSOLUTE_GATES
        or judgement.get("allRelativeAndAbsoluteRequired") is not True
        or judgement.get("failureClosesBranchWithoutParameterScan") is not True
    ):
        raise ValueError("循环013信号或绝对门漂移")
    prohibited = plan.get("prohibited")
    required_prohibitions = {
        "reuse_old_score_only_stage2",
        "read_or_infer_old_val30_test100_or_release_holdout",
        "train_on_clean98",
        "scan_stage2_score_mask_threshold_roi_size_context_loss_seed_or_epochs",
        "describe_fallback_stage1_mask_as_stage2_success",
        "promote_before_all_relative_and_absolute_gates_pass",
    }
    if not isinstance(prohibited, list) or not required_prohibitions.issubset(set(prohibited)):
        raise ValueError("循环013禁止项不完整")


def verify_plan(path: Path) -> dict[str, Any]:
    path = path.resolve()
    plan = read_json(path)
    validate_contract(plan)
    inputs = plan.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("循环013输入绑定缺失")
    cycle012_decision_path = bound_file(inputs.get("cycle012Decision"), "循环012失败决策")
    cycle012_decision = read_json(cycle012_decision_path)
    if (
        cycle012_decision.get("decision") != "signal_test_failed_close_targeted_positive_augmentation_branch"
        or any(cycle012_decision.get("signalChecks", {}).values())
        or cycle012_decision.get("branchClosure", {}).get("closed") is not True
    ):
        raise ValueError("循环012失败终局未锁定")
    materialization_path = bound_file(inputs.get("cycle012Materialization"), "循环012开发物化")
    cycle012_materializer = load_module(
        "cycle013_cycle012_materializer", HERE / "materialize-development-cycle-012-dataset.py"
    )
    materialization = cycle012_materializer.verify_report(materialization_path)
    if materialization.get("counts") != {
        "trainImages": 350,
        "trainPositiveImages": 290,
        "trainPositiveMasks": 1731,
        "trainHardNegativeImages": 60,
        "evaluationImages": 106,
        "evaluationPositiveImages": 66,
        "evaluationPositiveMasks": 405,
        "evaluationHardNegativeImages": 40,
        "testImages": 0,
        "sourceGroupOverlap": 0,
    }:
        raise ValueError("循环012开发物化计数漂移")
    if inputs["cycle012Materialization"].get("datasetFilesSha256") != materialization.get("datasetFilesSha256"):
        raise ValueError("循环012数据树身份漂移")
    source_group_map_path = bound_file(inputs.get("trainSourceGroupMap"), "train来源组映射")
    source_group_map = read_json(source_group_map_path)
    if source_group_map.get("counts") != {"trainImages": 350, "sourceGroups": 124}:
        raise ValueError("train来源组映射计数漂移")
    stage1_weights_path = bound_file(plan["stage1"].get("weights"), "循环011 stage1权重")
    cycle011_plan_path = bound_file(inputs.get("cycle011CleanRebaselinePlan"), "循环011 clean98计划")
    cycle011_plan = read_json(cycle011_plan_path)
    if (
        cycle011_plan.get("decision") != "pre_registered_single_read_only_clean_truth_rebaseline"
        or cycle011_plan.get("sourceExperiment", {}).get("weights", {}).get("sha256") != sha256_file(stage1_weights_path)
    ):
        raise ValueError("stage1权重不是循环011 clean98锁定权重")
    clean_materialization_path = bound_file(inputs.get("clean98Materialization"), "clean98物化报告")
    clean_materializer = load_module(
        "cycle013_clean_materializer", HERE / "materialize-clean-development-evaluation.py"
    )
    clean_materialization = clean_materializer.verify_report(clean_materialization_path)
    clean_counts = clean_materialization.get("counts")
    if not isinstance(clean_counts, dict) or (
        int(clean_counts.get("trainImages", -1)) != 0
        or int(clean_counts.get("evaluationImages", -1)) != 98
        or int(clean_counts.get("evaluationPositiveImages", -1)) != 58
        or int(clean_counts.get("evaluationPositiveMasks", -1)) != 354
        or int(clean_counts.get("evaluationHardNegativeImages", -1)) != 40
        or int(clean_counts.get("testImages", -1)) != 0
    ):
        raise ValueError("clean98物化计数漂移")
    if inputs["clean98Materialization"].get("datasetFilesSha256") != clean_materialization.get("datasetFilesSha256"):
        raise ValueError("clean98文件树身份漂移")
    runtime_path = bound_file(inputs.get("maskReplacementRuntime"), "循环013 mask替换运行时")
    if runtime_path != (HERE / "nail_texture_cycle013_mask_replacement.py").resolve():
        raise ValueError("循环013运行时路径不正确")
    content = dict(plan)
    saved_content_sha = content.pop("contentSha256", None)
    if saved_content_sha != canonical_sha256(content):
        raise ValueError("循环013计划contentSha256漂移")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan = verify_plan(args.plan)
    print(
        json.dumps(
            {
                "ok": True,
                "cycleId": plan["cycleId"],
                "decision": plan["decision"],
                "planSha256": sha256_file(args.plan.resolve()),
                "contentSha256": plan["contentSha256"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
