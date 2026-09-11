#!/usr/bin/env python3
"""循环013 可达性判决（零推理"候选天花板"）与判定分辨率（Wilson 置信区间）。

本脚本是**只读分析**：不训练、不推理、不消费受保护评估集、不修改任何既有产物，
只读取已冻结的 clean98（循环011 唯一一次只读复评）证据，回答两个问题：

1. ``ceiling``：把 clean98 上被漏掉的 21 枚真值逐枚判定为
   "同图接受候选集中存在可附着候选（stage2 理论上可修复）"或"无任何可附着候选
   （逐甲 mask 替换按构造不可修复）"，并以"已存在的匹配固定、其余候选可被替换为
   其附着真值的完美 mask"为假设，重放权威匹配/去重/杂散口径，得到双轴天花板：
   - 漏甲轴：漏甲实例、漏甲图、实例召回、完整 mask 比例的最好情况；
   - 杂散轴：duplicates×1.0 + invalidPredictionMasks×1.5 + falsePositives×2.0 的最好情况。
   同时给出"stage2 成功率"敏感性曲线，用于区分"理论可达"与"实际可行"。

2. ``wilson``：用 Wilson 95% 区间量化判定分辨率，回答"相对门 漏甲图≤10（基线 13，
   n=58）是否落在噪声内"，并给出要让该门可判别所需的最小样本量。

权威口径完全复用既有实现（不得另行发明）：
- ``QUALITY`` = ``build-positive-recognition-quality-report.py``（``parse_label``、
  ``polygon_iou``、``match_instances``，``MATCH_IOU = 0.50``、``COMPLETE_MASK_IOU = 0.75``）；
- ``LEGACY`` = ``build-development-instance-quality-report.py``（``suppress_product_duplicates``，
  maskIoU≥0.60 或 containment≥0.85、boxIoU≥0.55、每图至多 10 个候选）；
- ``MATERIALIZATION`` = ``materialize-clean-development-evaluation.py``（``verify_report``）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
LEGACY_QUALITY_SOURCE = HERE / "build-development-instance-quality-report.py"
MATERIALIZATION_SOURCE = HERE / "materialize-clean-development-evaluation.py"
AUTHORITATIVE_GENERATOR = HERE / "build-development-clean-rebaseline-report.py"

SCORE_THRESHOLD = 0.25
COMPLETE_MASK_IOU = 0.75
DUPLICATE_IOU = 0.10
SPURIOUS_WEIGHTS = {"duplicates": 1.0, "invalidPredictionMasks": 1.5, "falsePositives": 2.0}
EVALUATION_IMAGES = 98
POSITIVE_IMAGES = 58
HARD_NEGATIVE_IMAGES = 40
TRUTH_TOTAL = 354
DEFAULT_EPSILON_SWEEP = (0.0, 0.01, 0.05, 0.10, 0.30)
DEFAULT_SUCCESS_RATES = (0.25, 0.5, 0.75, 1.0)
HEADLINE_EPSILON = 0.05
NEAR_PERFECT_CONVERSION_SHARE = 0.90
Z_95 = 1.959963984540054
Z_POWER_80 = 0.8416212335729143
DEVELOPMENT_FLOOR = {
    "minimumInstanceRecall": 0.90,
    "minimumCompleteMaskRatio": 0.85,
    "maximumMissingImageRate": 0.10,
    "maximumWeightedSpuriousRate": 0.02,
}
FROZEN_IMAGE_FIELDS = (
    "role",
    "truthCount",
    "predictionCount",
    "matchedCount",
    "completeMaskCount",
    "missingCount",
    "missingTruthIndices",
    "duplicateCount",
    "falsePositiveCount",
    "invalidPredictionMaskCount",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LEGACY = load_module("jiaru_legacy_development_quality", LEGACY_QUALITY_SOURCE)
QUALITY = LEGACY.QUALITY
MATERIALIZATION = load_module("jiaru_clean_development_materialization", MATERIALIZATION_SOURCE)


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
        raise ValueError(f"JSON 根必须是对象：{path}")
    return value


def require_file(value: str, label: str) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"{label} 缺失：{path}")
    return path


def bound_input(value: str, label: str) -> tuple[Path, dict[str, str]]:
    path = require_file(value, label)
    return path, {"label": label, "path": path.as_posix(), "sha256": sha256_file(path)}


def parse_float_list(raw: str, *, allow_zero: bool, upper: float | None = None) -> tuple[float, ...]:
    values: list[float] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        number = float(chunk)
        if number < 0 or (not allow_zero and number <= 0):
            raise ValueError(f"数值不合法：{chunk}")
        if upper is not None and number > upper:
            raise ValueError(f"数值超出上限 {upper}：{chunk}")
        values.append(number)
    if not values:
        raise ValueError("列表不能为空")
    return tuple(sorted(set(values)))


# --------------------------------------------------------------------------------------
# 接受候选集重建（与 build-development-clean-rebaseline-report.py 的 build() 逐行同口径）
# --------------------------------------------------------------------------------------


def load_evaluation_inputs(
    materialization_path: Path, artifact_path: Path
) -> tuple[Path, dict[str, dict[str, Any]], dict[str, Path | None]]:
    materialization = MATERIALIZATION.verify_report(materialization_path)
    dataset_root = Path(str(materialization["outputDir"])).resolve()
    records = materialization.get("records", [])
    if not isinstance(records, list):
        raise ValueError("物化报告缺少 records")
    by_stem = {Path(str(row["fileName"])).stem: row for row in records}
    if len(by_stem) != EVALUATION_IMAGES:
        raise ValueError(f"评估记录应为 {EVALUATION_IMAGES} 图，实得 {len(by_stem)}")

    artifact = read_json(artifact_path)
    prediction_records = artifact.get("prediction_records")
    if not isinstance(prediction_records, list) or canonical_sha256(
        prediction_records
    ) != artifact.get("prediction_records_sha256"):
        raise ValueError("预测记录缺失或哈希漂移")
    artifact_root = Path(str(artifact.get("artifacts_dir", ""))).resolve()
    predictions: dict[str, Path | None] = {}
    for row in prediction_records:
        stem = str(row.get("stem", ""))
        if stem in predictions:
            raise ValueError(f"预测 stem 重复：{stem}")
        relative = row.get("path")
        if relative is None:
            if row.get("sha256") is not None or int(row.get("prediction_count", -1)) != 0:
                raise ValueError(f"零预测记录无效：{stem}")
            predictions[stem] = None
            continue
        path = (artifact_root / str(relative)).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError as error:
            raise ValueError(f"预测路径越界：{stem}") from error
        require_file(str(path), "预测标签")
        if sha256_file(path) != str(row.get("sha256", "")):
            raise ValueError(f"预测标签哈希漂移：{stem}")
        predictions[stem] = path
    if set(predictions) != set(by_stem):
        raise ValueError("预测没有逐图覆盖评估集")
    return dataset_root, by_stem, predictions


def reconstruct(
    dataset_root: Path, by_stem: dict[str, dict[str, Any]], predictions: dict[str, Path | None]
) -> dict[str, Any]:
    """按权威口径重建逐图逐实例结果，并保留内部几何用于天花板模拟。"""
    image_rows: list[dict[str, Any]] = []
    internal: dict[str, dict[str, Any]] = {}
    totals = {
        "truth": 0,
        "predictions": 0,
        "matched": 0,
        "completeMasks": 0,
        "missing": 0,
        "duplicates": 0,
        "falsePositives": 0,
        "invalidPredictionMasks": 0,
    }
    for stem in sorted(by_stem):
        record = by_stem[stem]
        truth = QUALITY.parse_label(
            dataset_root / str(record["label"]), prediction=False, threshold=SCORE_THRESHOLD
        )
        prediction_path = predictions[stem]
        raw = (
            QUALITY.parse_label(prediction_path, prediction=True, threshold=SCORE_THRESHOLD)
            if prediction_path
            else []
        )
        predicted = LEGACY.suppress_product_duplicates(raw)
        matches, missing, unmatched = QUALITY.match_instances(truth, predicted)
        matched_details = [
            {
                "truthIndex": truth_index + 1,
                "predictionIndex": prediction_index + 1,
                "iou": round(iou, 6),
                "complete": iou >= COMPLETE_MASK_IOU,
            }
            for truth_index, prediction_index, iou in sorted(matches)
        ]
        unmatched_details: list[dict[str, Any]] = []
        duplicates = 0
        false_positives = 0
        for prediction_index in unmatched:
            best_iou = max(
                (QUALITY.polygon_iou(item[0], predicted[prediction_index][0]) for item in truth),
                default=0.0,
            )
            category = "duplicate" if best_iou >= DUPLICATE_IOU else "false-positive"
            duplicates += int(category == "duplicate")
            false_positives += int(category == "false-positive")
            unmatched_details.append(
                {
                    "predictionIndex": prediction_index + 1,
                    "category": category,
                    "bestTruthIou": round(best_iou, 6),
                    "originallyValid": bool(predicted[prediction_index][2]),
                }
            )
        complete = sum(item["complete"] for item in matched_details)
        invalid = sum(not item[2] for item in predicted)
        positive = record.get("role") == "train-positive"
        image_rows.append(
            {
                "stem": stem,
                "role": record.get("role"),
                "sourceGroup": record.get("sourceGroup"),
                "truthCount": len(truth),
                "predictionCount": len(predicted),
                "matchedCount": len(matches),
                "completeMaskCount": complete,
                "missingCount": len(missing),
                "missingTruthIndices": [index + 1 for index in sorted(missing)],
                "duplicateCount": duplicates,
                "falsePositiveCount": false_positives,
                "invalidPredictionMaskCount": invalid,
                "matchedInstances": matched_details,
                "unmatchedPredictions": unmatched_details,
                "allVisibleNailsRecognized": positive and not missing,
                "directlyExtractable": positive
                and not missing
                and duplicates == 0
                and false_positives == 0
                and invalid == 0
                and complete == len(truth),
            }
        )
        internal[stem] = {
            "role": record.get("role"),
            "truth": truth,
            "predicted": predicted,
            "matches": matches,
            "missing": list(missing),
            "unmatched": list(unmatched),
        }
        totals["truth"] += len(truth)
        totals["predictions"] += len(predicted)
        totals["matched"] += len(matches)
        totals["completeMasks"] += complete
        totals["missing"] += len(missing)
        totals["duplicates"] += duplicates
        totals["falsePositives"] += false_positives
        totals["invalidPredictionMasks"] += invalid

    positives = [row for row in image_rows if row["role"] == "train-positive"]
    negatives = [row for row in image_rows if row["role"] == "hard-negative"]
    missing_images = sum(row["missingCount"] > 0 for row in positives)
    direct_images = sum(row["directlyExtractable"] for row in positives)
    weighted = (
        SPURIOUS_WEIGHTS["duplicates"] * totals["duplicates"]
        + SPURIOUS_WEIGHTS["invalidPredictionMasks"] * totals["invalidPredictionMasks"]
        + SPURIOUS_WEIGHTS["falsePositives"] * totals["falsePositives"]
    )
    summary = {
        "evaluationImages": len(image_rows),
        "positiveImages": len(positives),
        "hardNegativeImages": len(negatives),
        **totals,
        "missingImages": missing_images,
        "directlyExtractableImages": direct_images,
        "hardNegativeFalsePositiveImages": sum(row["predictionCount"] > 0 for row in negatives),
        "instanceRecall": round(totals["matched"] / totals["truth"], 8) if totals["truth"] else 0.0,
        "completeMaskRatio": round(totals["completeMasks"] / totals["truth"], 8)
        if totals["truth"]
        else 0.0,
        "missingImageRate": round(missing_images / len(positives), 8) if positives else 0.0,
        "weightedSpuriousRate": round(weighted / totals["truth"], 8) if totals["truth"] else 0.0,
        "directlyExtractableRate": round(direct_images / len(positives), 8) if positives else 0.0,
        "weightedSpuriousNumerator": weighted,
    }
    return {"images": image_rows, "totals": totals, "summary": summary, "internal": internal}


def check_fidelity(
    reconstructed: dict[str, Any], frozen: dict[str, Any]
) -> dict[str, Any]:
    """把重建结果与冻结质量报告逐图逐实例比对；任何不一致都阻止给出天花板结论。"""
    mismatches: list[dict[str, Any]] = []
    frozen_images = frozen.get("images")
    if not isinstance(frozen_images, list):
        return {
            "ok": False,
            "checks": 0,
            "mismatchCount": 1,
            "mismatches": [{"scope": "report", "detail": "缺少 images"}],
        }
    frozen_by_stem = {str(row.get("stem")): row for row in frozen_images}
    checks = 0
    for row in reconstructed["images"]:
        stem = row["stem"]
        expected = frozen_by_stem.get(stem)
        if expected is None:
            mismatches.append({"scope": "image", "stem": stem, "detail": "冻结报告缺少该图"})
            continue
        for field in FROZEN_IMAGE_FIELDS:
            checks += 1
            if row.get(field) != expected.get(field):
                mismatches.append(
                    {
                        "scope": "image",
                        "stem": stem,
                        "field": field,
                        "expected": expected.get(field),
                        "actual": row.get(field),
                    }
                )
        checks += 1
        expected_pairs = sorted(
            (item["truthIndex"], item["predictionIndex"]) for item in expected.get("matchedInstances", [])
        )
        actual_pairs = sorted(
            (item["truthIndex"], item["predictionIndex"]) for item in row["matchedInstances"]
        )
        if expected_pairs != actual_pairs:
            mismatches.append(
                {
                    "scope": "image",
                    "stem": stem,
                    "field": "matchedInstancePairs",
                    "expected": expected_pairs,
                    "actual": actual_pairs,
                }
            )
        checks += 1
        expected_categories = sorted(
            (item["predictionIndex"], item["category"])
            for item in expected.get("unmatchedPredictions", [])
        )
        actual_categories = sorted(
            (item["predictionIndex"], item["category"]) for item in row["unmatchedPredictions"]
        )
        if expected_categories != actual_categories:
            mismatches.append(
                {
                    "scope": "image",
                    "stem": stem,
                    "field": "unmatchedCategories",
                    "expected": expected_categories,
                    "actual": actual_categories,
                }
            )
    frozen_summary = frozen.get("summary", {})
    for field in (
        "instanceRecall",
        "completeMaskRatio",
        "missingImageRate",
        "weightedSpuriousRate",
        "directlyExtractableRate",
        "matched",
        "completeMasks",
        "missing",
        "missingImages",
        "duplicates",
        "falsePositives",
        "invalidPredictionMasks",
        "truth",
        "predictions",
    ):
        checks += 1
        if reconstructed["summary"].get(field) != frozen_summary.get(field):
            mismatches.append(
                {
                    "scope": "summary",
                    "field": field,
                    "expected": frozen_summary.get(field),
                    "actual": reconstructed["summary"].get(field),
                }
            )
    return {"ok": not mismatches, "checks": checks, "mismatches": mismatches[:40], "mismatchCount": len(mismatches)}


# --------------------------------------------------------------------------------------
# 理想化 stage2 模拟
# --------------------------------------------------------------------------------------


def attachment_pairs(truth, predicted, unmatched_indices, missing_indices) -> list[tuple[float, int, int]]:
    pairs: list[tuple[float, int, int]] = []
    for prediction_index in unmatched_indices:
        for truth_index in missing_indices:
            iou = QUALITY.polygon_iou(truth[truth_index][0], predicted[prediction_index][0])
            if iou > 0.0:
                pairs.append((iou, prediction_index, truth_index))
    pairs.sort(key=lambda row: (-row[0], row[1], row[2]))
    return pairs


def maximum_bipartite_matching(
    pairs: list[tuple[float, int, int]]
) -> list[tuple[float, int, int]]:
    """Kuhn 增广路求最大基数匹配：一个候选最多救一枚真值，一枚真值最多被一个候选救。

    贪心（按 IoU 降序放置）只保证极大匹配，会在候选与真值存在竞争时低估天花板；
    可达性判决取理论上限，必须用最大基数匹配，并在同基数解中优先高 IoU 边。
    """
    adjacency: dict[int, list[int]] = {}
    weight: dict[tuple[int, int], float] = {}
    for iou, prediction_index, truth_index in pairs:
        adjacency.setdefault(prediction_index, [])
        if truth_index not in adjacency[prediction_index]:
            adjacency[prediction_index].append(truth_index)
        best = weight.get((prediction_index, truth_index))
        if best is None or iou > best:
            weight[(prediction_index, truth_index)] = iou
    for prediction_index in adjacency:
        adjacency[prediction_index].sort(
            key=lambda truth_index: (-weight[(prediction_index, truth_index)], truth_index)
        )
    match_of_truth: dict[int, int] = {}

    def augment(prediction_index: int, visited: set[int]) -> bool:
        for truth_index in adjacency[prediction_index]:
            if truth_index in visited:
                continue
            visited.add(truth_index)
            occupant = match_of_truth.get(truth_index)
            if occupant is None or augment(occupant, visited):
                match_of_truth[truth_index] = prediction_index
                return True
        return False

    for prediction_index in sorted(adjacency):
        augment(prediction_index, set())
    matched = [
        (weight[(prediction_index, truth_index)], prediction_index, truth_index)
        for truth_index, prediction_index in match_of_truth.items()
    ]
    matched.sort(key=lambda row: (-row[0], row[1], row[2]))
    return matched


def evaluate_replaced(
    stem: str, entry: dict[str, Any], rescued: list[tuple[int, int]]
) -> dict[str, Any]:
    """把 rescued 候选的 mask 替换为其附着真值的完美 mask，重放权威匹配与杂散口径。"""
    truth = entry["truth"]
    predicted = entry["predicted"]
    snapped = list(predicted)
    for prediction_index, truth_index in rescued:
        snapped[prediction_index] = (truth[truth_index][0], predicted[prediction_index][1], True)
    matches, missing, unmatched = QUALITY.match_instances(truth, snapped)
    complete = sum(1 for _, _, iou in matches if iou >= COMPLETE_MASK_IOU)
    duplicates = 0
    false_positives = 0
    for prediction_index in unmatched:
        best_iou = max(
            (QUALITY.polygon_iou(item[0], snapped[prediction_index][0]) for item in truth), default=0.0
        )
        if best_iou >= DUPLICATE_IOU:
            duplicates += 1
        else:
            false_positives += 1
    return {
        "stem": stem,
        "role": entry["role"],
        "matched": len(matches),
        "completeMasks": complete,
        "missing": len(missing),
        "duplicates": duplicates,
        "falsePositives": false_positives,
        "invalidPredictionMasks": sum(not item[2] for item in snapped),
        "truthCount": len(truth),
    }


def simulate(reconstructed: dict[str, Any], epsilon: float, success_rate: float) -> dict[str, Any]:
    """在给定附着阈值 ε 与 stage2 成功率下计算双轴天花板。"""
    totals = {
        "matched": 0,
        "completeMasks": 0,
        "missing": 0,
        "duplicates": 0,
        "falsePositives": 0,
        "invalidPredictionMasks": 0,
        "truth": 0,
    }
    missing_images = 0
    positive_images = 0
    rescued_instances = 0
    rescued_images = 0
    eligible_candidates = 0
    unattached_missing = 0
    per_image: list[dict[str, Any]] = []
    for stem in sorted(reconstructed["internal"]):
        entry = reconstructed["internal"][stem]
        if entry["role"] != "train-positive":
            continue
        positive_images += 1
        truth = entry["truth"]
        predicted = entry["predicted"]
        missing_indices = list(entry["missing"])
        unmatched_indices = list(entry["unmatched"])
        pairs = attachment_pairs(truth, predicted, unmatched_indices, missing_indices)
        eligible = [(iou, ci, ti) for iou, ci, ti in pairs if iou >= epsilon]
        eligible_candidates += len(eligible)
        # 理论上限：最大基数匹配（已按 IoU 降序），一个候选/一枚真值至多被用一次。
        matching = maximum_bipartite_matching(eligible)
        budget = int(math.ceil(success_rate * len(matching))) if matching else 0
        rescued: list[tuple[int, int]] = [(ci, ti) for _, ci, ti in matching[:budget]]
        rescued_truths = {ti for _, ti in rescued}
        unattached_missing += len(missing_indices) - len(rescued_truths)
        rescued_instances += len(rescued)
        if missing_indices and len(rescued_truths) == len(missing_indices):
            rescued_images += 1
        outcome = evaluate_replaced(stem, entry, rescued)
        totals["matched"] += outcome["matched"]
        totals["completeMasks"] += outcome["completeMasks"]
        totals["missing"] += outcome["missing"]
        totals["duplicates"] += outcome["duplicates"]
        totals["falsePositives"] += outcome["falsePositives"]
        totals["invalidPredictionMasks"] += outcome["invalidPredictionMasks"]
        totals["truth"] += outcome["truthCount"]
        missing_images += int(outcome["missing"] > 0)
        per_image.append(
            {
                "stem": stem,
                "missingBefore": len(missing_indices),
                "missingAfter": outcome["missing"],
                "rescued": len(rescued),
            }
        )
    weighted = (
        SPURIOUS_WEIGHTS["duplicates"] * totals["duplicates"]
        + SPURIOUS_WEIGHTS["invalidPredictionMasks"] * totals["invalidPredictionMasks"]
        + SPURIOUS_WEIGHTS["falsePositives"] * totals["falsePositives"]
    )
    baseline = reconstructed["summary"]
    summary = {
        **totals,
        "missingImages": missing_images,
        "positiveImages": positive_images,
        "instanceRecall": round(totals["matched"] / totals["truth"], 8) if totals["truth"] else 0.0,
        "completeMaskRatio": round(totals["completeMasks"] / totals["truth"], 8)
        if totals["truth"]
        else 0.0,
        "missingImageRate": round(missing_images / positive_images, 8) if positive_images else 0.0,
        "weightedSpuriousRate": round(weighted / totals["truth"], 8) if totals["truth"] else 0.0,
        "weightedSpuriousNumerator": weighted,
    }
    needs_conversion = baseline["weightedSpuriousNumerator"] - weighted
    return {
        "epsilon": epsilon,
        "stage2SuccessRate": success_rate,
        "rescuedInstances": rescued_instances,
        "rescuedImages": rescued_images,
        "eligibleCandidates": eligible_candidates,
        "missingTruthsWithoutAttachableCandidate": unattached_missing,
        "weightedSpuriousReduction": round(needs_conversion, 6),
        "summary": summary,
        "perImage": per_image,
    }


def verdict_for(ceiling_summary: dict[str, Any]) -> dict[str, Any]:
    missing_ok = ceiling_summary["missingImages"] <= DEVELOPMENT_FLOOR["maximumMissingImageRate"] * ceiling_summary["positiveImages"]
    spurious_ok = ceiling_summary["weightedSpuriousRate"] <= DEVELOPMENT_FLOOR["maximumWeightedSpuriousRate"]
    complete_ok = ceiling_summary["completeMaskRatio"] >= DEVELOPMENT_FLOOR["minimumCompleteMaskRatio"]
    recall_ok = ceiling_summary["instanceRecall"] >= DEVELOPMENT_FLOOR["minimumInstanceRecall"]
    if missing_ok and spurious_ok:
        decision = "reachable"
    elif missing_ok or spurious_ok:
        decision = "reachable_on_single_axis_only"
    else:
        decision = "unreachable_by_mask_replacement_stage2"
    return {
        "decision": decision,
        "missingImageAxis": missing_ok,
        "spuriousAxis": spurious_ok,
        "completeMaskAxis": complete_ok,
        "instanceRecallAxis": recall_ok,
        "maximumMissingImagesAllowed": int(DEVELOPMENT_FLOOR["maximumMissingImageRate"] * ceiling_summary["positiveImages"]),
    }


# --------------------------------------------------------------------------------------
# 余量判据：理论可达 ≠ 实际可行
# --------------------------------------------------------------------------------------


def verify_floor(plan: dict[str, Any]) -> dict[str, Any]:
    """比对计划声明的开发信号门限与脚本内置门限；不一致则拒绝分析。"""
    declared = plan.get("formalFloorForDevelopmentSignalOnly")
    if not isinstance(declared, dict):
        raise ValueError("计划缺少 formalFloorForDevelopmentSignalOnly，无法确认门限口径")
    for key, value in DEVELOPMENT_FLOOR.items():
        if declared.get(key) != value:
            raise ValueError(
                f"计划门限与脚本内置不一致：{key} 计划={declared.get(key)!r} 脚本={value!r}"
            )
    if declared.get("everyEvaluationImageAccountedFor") is not True:
        raise ValueError("计划未要求逐图闭环（everyEvaluationImageAccountedFor）")
    return declared


def build_margin(reconstructed: dict[str, Any], headline: dict[str, Any] | None) -> dict[str, Any]:
    """量化"杂散轴要达到门限需要多少未匹配候选被转正"。

    ``spuriousAxisReachable`` 只说明**理论上**最好的 mask 替换能压到门限之下；
    ``requiredShareOfAchievableDrop`` 说明为此要吃掉多少可达余量，
    ``requiresNearPerfectStage2`` 在需要"几乎全部可转正候选都成功"时给出警示。
    """
    baseline_numerator = reconstructed["summary"]["weightedSpuriousNumerator"]
    unmatched_candidates = reconstructed["summary"]["predictions"] - reconstructed["summary"]["matched"]
    ceiling_numerator = (
        headline["summary"]["weightedSpuriousNumerator"] if headline else baseline_numerator
    )
    target_numerator = DEVELOPMENT_FLOOR["maximumWeightedSpuriousRate"] * TRUTH_TOTAL
    required_drop = max(0.0, baseline_numerator - target_numerator)
    achievable_drop = max(0.0, baseline_numerator - ceiling_numerator)
    spurious_axis_reachable = achievable_drop >= required_drop
    required_share = round(required_drop / achievable_drop, 6) if achievable_drop > 0 else None
    requires_near_perfect = bool(
        spurious_axis_reachable
        and required_share is not None
        and required_share >= NEAR_PERFECT_CONVERSION_SHARE
    )
    return {
        "missingTruthsWithoutAttachableCandidate": (
            headline["missingTruthsWithoutAttachableCandidate"] if headline else None
        ),
        "unmatchedCandidatesAtBaseline": unmatched_candidates,
        "weightedSpuriousNumeratorBaseline": baseline_numerator,
        "weightedSpuriousNumeratorCeiling": ceiling_numerator,
        "weightedSpuriousNumeratorTarget": round(target_numerator, 6),
        "requiredNumeratorDrop": round(required_drop, 6),
        "achievableNumeratorDrop": round(achievable_drop, 6),
        "spuriousAxisReachable": spurious_axis_reachable,
        "requiredShareOfAchievableDrop": required_share,
        "requiresNearPerfectStage2": requires_near_perfect,
    }


# --------------------------------------------------------------------------------------
# Wilson 判定分辨率
# --------------------------------------------------------------------------------------


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n 必须为正")
    if not 0 <= k <= n:
        raise ValueError("k 必须落在 [0, n]")
    proportion = k / n
    denominator = 1.0 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, center - half), min(1.0, center + half))


def min_detectable_difference(p1: float, n1: int, p2: float, n2: int, z: float = Z_95) -> float:
    standard_error = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return z * standard_error


def required_group_size(p1: float, p2: float, alpha_z: float = Z_95, power_z: float = Z_POWER_80) -> int:
    if p1 == p2:
        return 0
    pooled = (p1 + p2) / 2
    numerator = (
        alpha_z * math.sqrt(2 * pooled * (1 - pooled))
        + power_z * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    return int(math.ceil(numerator / ((p1 - p2) ** 2)))


def build_resolution(reconstructed: dict[str, Any]) -> dict[str, Any]:
    summary = reconstructed["summary"]
    intervals: list[dict[str, Any]] = []
    specs = [
        ("instanceRecall", summary["matched"], summary["truth"]),
        ("completeMaskRatio", summary["completeMasks"], summary["truth"]),
        ("missingImageRate", summary["missingImages"], summary["positiveImages"]),
        ("weightedSpuriousRate", summary["weightedSpuriousNumerator"], summary["truth"]),
    ]
    for name, k, n in specs:
        low, high = wilson_interval(int(k), int(n))
        intervals.append(
            {
                "metric": name,
                "k": int(k),
                "n": int(n),
                "point": round(k / n, 8),
                "low": round(low, 8),
                "high": round(high, 8),
                "halfWidth": round((high - low) / 2, 8),
            }
        )
    baseline_missing_rate = summary["missingImages"] / summary["positiveImages"]
    low, high = wilson_interval(int(summary["missingImages"]), int(summary["positiveImages"]))
    relative_gate_k = 10
    relative_gate_rate = relative_gate_k / summary["positiveImages"]
    absolute_gate_k = int(DEVELOPMENT_FLOOR["maximumMissingImageRate"] * summary["positiveImages"])
    resolvability = {
        "baselineMissingImages": int(summary["missingImages"]),
        "baselineMissingImageRate": round(baseline_missing_rate, 8),
        "wilsonLow": round(low, 8),
        "wilsonHigh": round(high, 8),
        "relativeGateImages": relative_gate_k,
        "relativeGateRate": round(relative_gate_rate, 8),
        "absoluteGateImages": absolute_gate_k,
        "absoluteGateRate": DEVELOPMENT_FLOOR["maximumMissingImageRate"],
        "relativeGateInsideBaselineInterval": bool(low <= relative_gate_rate <= high),
        "absoluteGateInsideBaselineInterval": bool(
            low <= DEVELOPMENT_FLOOR["maximumMissingImageRate"] <= high
        ),
        "minDetectableDifferenceAtSameN": round(
            min_detectable_difference(
                baseline_missing_rate, summary["positiveImages"], relative_gate_rate, summary["positiveImages"]
            ),
            8,
        ),
    }
    samples = [
        {
            "comparison": "missingImageRate 0.2241 vs 0.1724",
            "requiredImagesPerGroup": required_group_size(baseline_missing_rate, relative_gate_rate),
        },
        {
            "comparison": "missingImageRate 0.1724 vs 0.1000",
            "requiredImagesPerGroup": required_group_size(relative_gate_rate, DEVELOPMENT_FLOOR["maximumMissingImageRate"]),
        },
        {
            "comparison": "weightedSpuriousRate 0.0960 vs 0.0200",
            "requiredImagesPerGroup": required_group_size(
                summary["weightedSpuriousRate"], DEVELOPMENT_FLOOR["maximumWeightedSpuriousRate"]
            ),
        },
    ]
    holdout = []
    for name, rate in (
        ("instanceRecall", DEVELOPMENT_FLOOR["minimumInstanceRecall"]),
        ("completeMaskRatio", DEVELOPMENT_FLOOR["minimumCompleteMaskRatio"]),
        ("missingImageRate", DEVELOPMENT_FLOOR["maximumMissingImageRate"]),
        ("weightedSpuriousRate", DEVELOPMENT_FLOOR["maximumWeightedSpuriousRate"]),
    ):
        estimate = int(round(rate * 100))
        low, high = wilson_interval(estimate, 100)
        holdout.append(
            {
                "metric": name,
                "assumedK": estimate,
                "n": 100,
                "low": round(low, 8),
                "high": round(high, 8),
                "halfWidth": round((high - low) / 2, 8),
            }
        )
    return {"intervals": intervals, "relativeGateResolvability": resolvability, "requiredSampleSizes": samples, "holdoutN100": holdout}


def determinism_check(quality_report: Path) -> dict[str, Any]:
    """重放权威报告生成器的 --verify-report，确认推理侧输出可逐字节复现。"""
    if not AUTHORITATIVE_GENERATOR.is_file():
        return {"ran": False, "reason": f"生成器缺失：{AUTHORITATIVE_GENERATOR}"}
    completed = subprocess.run(
        [sys.executable, str(AUTHORITATIVE_GENERATOR), "--verify-report", str(quality_report)],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    payload: dict[str, Any] = {
        "ran": True,
        "command": [str(AUTHORITATIVE_GENERATOR), "--verify-report", quality_report.name],
        "returncode": completed.returncode,
        "stdoutTail": completed.stdout.strip().splitlines()[-3:] if completed.stdout.strip() else [],
        "stderrTail": completed.stderr.strip().splitlines()[-3:] if completed.stderr.strip() else [],
    }
    return payload


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", required=True, help="循环011 clean98 预注册计划 JSON")
    parser.add_argument("--materialization-report", required=True)
    parser.add_argument("--artifact-index", required=True)
    parser.add_argument("--quality-report", required=True)
    parser.add_argument("--error-profile")
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify-report", action="store_true")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="循环013 零推理候选天花板与 Wilson 判定分辨率分析")
    sub = value.add_subparsers(dest="command", required=True)
    ceiling = sub.add_parser("ceiling", help="候选天花板与可达性判决")
    add_common(ceiling)
    ceiling.add_argument("--epsilon-sweep", default=",".join(str(item) for item in DEFAULT_EPSILON_SWEEP))
    ceiling.add_argument(
        "--stage2-success-rates", default=",".join(str(item) for item in DEFAULT_SUCCESS_RATES)
    )
    wilson = sub.add_parser("wilson", help="Wilson 判定分辨率")
    add_common(wilson)
    wilson.add_argument("--determinism-check", action="store_true")
    return value


def write_report(path: Path, payload: dict[str, Any]) -> None:
    body = dict(payload)
    body.pop("contentSha256", None)
    payload["contentSha256"] = canonical_sha256(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_content_sha256(payload: dict[str, Any]) -> bool:
    recorded = payload.get("contentSha256")
    body = dict(payload)
    body.pop("contentSha256", None)
    return recorded == canonical_sha256(body)


def first_difference(left: Any, right: Any, path: str = "$") -> str | None:
    if type(left) is not type(right):
        return f"{path}: 类型不一致"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: 字段不一致"
        for key in sorted(left):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: 长度不一致"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            difference = first_difference(a, b, f"{path}[{index}]")
            if difference:
                return difference
        return None
    return None if left == right else f"{path}: 值不一致"


def replay_bound_inputs(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("报告缺少绑定输入")
    paths: dict[str, Path] = {}
    for label in ("plan", "materializationReport", "artifactIndex", "qualityReport"):
        binding = inputs.get(label)
        if not isinstance(binding, dict) or binding.get("label") != label:
            raise ValueError(f"绑定输入字段无效：{label}")
        path = require_file(str(binding.get("path", "")), label)
        if path.as_posix() != binding.get("path") or sha256_file(path) != binding.get("sha256"):
            raise ValueError(f"绑定输入哈希漂移：{label}")
        paths[label] = path
    error_binding = inputs.get("errorProfile")
    if error_binding is not None:
        if not isinstance(error_binding, dict) or error_binding.get("label") != "errorProfile":
            raise ValueError("errorProfile绑定无效")
        error_path = require_file(str(error_binding.get("path", "")), "errorProfile")
        if error_path.as_posix() != error_binding.get("path") or sha256_file(error_path) != error_binding.get("sha256"):
            raise ValueError("errorProfile绑定哈希漂移")
    plan = read_json(paths["plan"])
    declared_floor = verify_floor(plan)
    dataset_root, by_stem, predictions = load_evaluation_inputs(
        paths["materializationReport"], paths["artifactIndex"]
    )
    reconstructed = reconstruct(dataset_root, by_stem, predictions)
    frozen = read_json(paths["qualityReport"])
    fidelity = check_fidelity(reconstructed, frozen)
    if not fidelity["ok"]:
        raise ValueError(
            f"接受候选集重建保真门失败：mismatchCount={fidelity['mismatchCount']}"
        )
    return plan, declared_floor, reconstructed


def verify_ceiling_payload(payload: dict[str, Any]) -> None:
    plan, declared_floor, reconstructed = replay_bound_inputs(payload)
    epsilons = tuple(float(row["epsilon"]) for row in payload.get("epsilonSweep", []))
    success_rates = tuple(
        sorted({float(row["stage2SuccessRate"]) for row in payload.get("successRateSensitivity", [])})
    )
    if epsilons != DEFAULT_EPSILON_SWEEP or success_rates != DEFAULT_SUCCESS_RATES:
        raise ValueError("天花板报告的epsilon或成功率网格偏离冻结默认值")
    if float(payload.get("headlineEpsilon", -1)) != HEADLINE_EPSILON:
        raise ValueError("天花板报告headlineEpsilon漂移")
    sweep = []
    for epsilon in epsilons:
        run = simulate(reconstructed, epsilon, 1.0)
        sweep.append({**run, "verdict": verdict_for(run["summary"])})
    sensitivity = []
    for epsilon in epsilons:
        for rate in success_rates:
            run = simulate(reconstructed, epsilon, rate)
            sensitivity.append(
                {
                    "epsilon": epsilon,
                    "stage2SuccessRate": rate,
                    "rescuedInstances": run["rescuedInstances"],
                    "rescuedImages": run["rescuedImages"],
                    "missingImages": run["summary"]["missingImages"],
                    "weightedSpuriousRate": run["summary"]["weightedSpuriousRate"],
                    "completeMaskRatio": run["summary"]["completeMaskRatio"],
                    "decision": verdict_for(run["summary"])["decision"],
                }
            )
    headline = next((row for row in sweep if row["epsilon"] == float(payload["headlineEpsilon"])), None)
    if headline is None:
        raise ValueError("headlineEpsilon未出现在epsilonSweep")
    stable = {
        "schemaVersion": 1,
        "analysisKind": "development_cycle_013_candidate_ceiling_zero_inference",
        "readOnly": True,
        "decision": headline["verdict"]["decision"],
        "headlineEpsilon": float(payload["headlineEpsilon"]),
        "inputs": payload["inputs"],
        "planContract": {
            "cycleId": plan.get("cycleId"),
            "onlyVariable": (plan.get("hypothesis") or {}).get("onlyVariable"),
            "formalFloorForDevelopmentSignalOnly": declared_floor,
        },
        "developmentFloor": DEVELOPMENT_FLOOR,
        "reconstructionFidelity": {
            "ok": True,
            "checks": check_fidelity(reconstructed, read_json(Path(payload["inputs"]["qualityReport"]["path"])))["checks"],
            "mismatchCount": 0,
        },
        "baseline": reconstructed["summary"],
        "epsilonSweep": sweep,
        "successRateSensitivity": sensitivity,
        "verdict": headline["verdict"],
        "margin": build_margin(reconstructed, headline),
        "assumptions": [
            "可附着候选的 mask 被替换为其附着真值的完美 mask（IoU=1.0，必然 complete）",
            "stage2 不产生新候选、不删除候选；产品去重规则与每图候选上限 10 不变",
            "真值分母 354 与正图分母 58 不变；困难负样本图不做任何替换",
            "IoU 一律沿用既有实现的归一化坐标口径（与历史匹配/报告完全一致）",
        ],
    }
    actual = {key: payload.get(key) for key in stable}
    difference = first_difference(actual, stable)
    if difference:
        raise ValueError(f"天花板报告深重放不一致：{difference}")


def verify_wilson_payload(payload: dict[str, Any]) -> None:
    _, _, reconstructed = replay_bound_inputs(payload)
    fidelity = check_fidelity(
        reconstructed, read_json(Path(payload["inputs"]["qualityReport"]["path"]))
    )
    resolution = build_resolution(reconstructed)
    stable = {
        "schemaVersion": 1,
        "analysisKind": "development_cycle_013_decision_resolution_wilson",
        "readOnly": True,
        "inputs": payload["inputs"],
        "reconstructionFidelity": {
            "ok": True,
            "checks": fidelity["checks"],
            "mismatchCount": 0,
        },
        "baseline": reconstructed["summary"],
        **resolution,
        "interpretation": [
            "若相对门（漏甲图数）落在基线的 Wilson 区间内，则该相对信号不可判别，不能作为分支关闭/保留的依据。",
            "单轮判定分辨率由分母与基线比例共同决定；分母不足时应改用绝对门与噪声内的方向性结论。",
            "推理侧在同一权重同一输入下确定性，不确定性主要来自训练随机性，不能靠重复推理估计。",
        ],
    }
    actual = {key: payload.get(key) for key in stable}
    difference = first_difference(actual, stable)
    if difference:
        raise ValueError(f"Wilson报告深重放不一致：{difference}")
    recorded_determinism = payload.get("determinismCheck")
    if isinstance(recorded_determinism, dict) and recorded_determinism.get("ran") is True:
        current = determinism_check(Path(payload["inputs"]["qualityReport"]["path"]))
        if current.get("returncode") != 0:
            raise ValueError("权威clean98质量报告当前已不能深重放")


def verify_report(path: Path) -> int:
    payload = read_json(path)
    if not verify_content_sha256(payload):
        print("报告内容哈希不一致", file=sys.stderr)
        return 1
    try:
        kind = payload.get("analysisKind")
        if kind == "development_cycle_013_candidate_ceiling_zero_inference":
            verify_ceiling_payload(payload)
        elif kind == "development_cycle_013_decision_resolution_wilson":
            verify_wilson_payload(payload)
        else:
            raise ValueError(f"不支持深重放的报告类型：{kind}")
    except Exception as error:
        print(f"报告深重放失败：{error}", file=sys.stderr)
        return 1
    print(
        f"报告深重放通过：{path} decision={payload.get('decision')} "
        f"contentSha256={payload.get('contentSha256')}"
    )
    return 0


def collect_channels(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    channels: dict[str, dict[str, str]] = {}
    for label, raw in (
        ("plan", args.plan),
        ("materializationReport", args.materialization_report),
        ("artifactIndex", args.artifact_index),
        ("qualityReport", args.quality_report),
        ("errorProfile", args.error_profile),
    ):
        if not raw:
            continue
        _, binding = bound_input(raw, label)
        channels[label] = binding
    return channels


def cmd_ceiling(args: argparse.Namespace) -> int:
    if args.verify_report:
        return verify_report(Path(args.output).resolve())
    channels = collect_channels(args)
    plan = read_json(Path(args.plan).resolve())
    declared_floor = verify_floor(plan)
    dataset_root, by_stem, predictions = load_evaluation_inputs(
        Path(args.materialization_report).resolve(), Path(args.artifact_index).resolve()
    )
    reconstructed = reconstruct(dataset_root, by_stem, predictions)
    frozen = read_json(Path(args.quality_report).resolve())
    fidelity = check_fidelity(reconstructed, frozen)
    if not fidelity["ok"]:
        payload = {
            "schemaVersion": 1,
            "analysisKind": "development_cycle_013_candidate_ceiling_zero_inference",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "readOnly": True,
            "decision": "reconstruction_mismatch",
            "inputs": channels,
            "reconstructionFidelity": fidelity,
            "baseline": reconstructed["summary"],
            "note": "接受候选集重建与冻结质量报告不一致，未产出任何天花板结论。",
        }
        write_report(Path(args.output).resolve(), payload)
        print("重建与冻结报告不一致，已以 reconstruction_mismatch 结项。", file=sys.stderr)
        return 1
    epsilons = parse_float_list(args.epsilon_sweep, allow_zero=True)
    success_rates = parse_float_list(args.stage2_success_rates, allow_zero=False, upper=1.0)
    sweep: list[dict[str, Any]] = []
    for epsilon in epsilons:
        full = simulate(reconstructed, epsilon, 1.0)
        sweep.append({**full, "verdict": verdict_for(full["summary"])})
    sensitivity: list[dict[str, Any]] = []
    for epsilon in epsilons:
        for rate in success_rates:
            run = simulate(reconstructed, epsilon, rate)
            sensitivity.append(
                {
                    "epsilon": epsilon,
                    "stage2SuccessRate": rate,
                    "rescuedInstances": run["rescuedInstances"],
                    "rescuedImages": run["rescuedImages"],
                    "missingImages": run["summary"]["missingImages"],
                    "weightedSpuriousRate": run["summary"]["weightedSpuriousRate"],
                    "completeMaskRatio": run["summary"]["completeMaskRatio"],
                    "decision": verdict_for(run["summary"])["decision"],
                }
            )
    headline = next((row for row in sweep if row["epsilon"] == HEADLINE_EPSILON), sweep[0] if sweep else None)
    verdict = headline["verdict"] if headline else {"decision": "no_sweep"}
    margin = build_margin(reconstructed, headline)
    payload = {
        "schemaVersion": 1,
        "analysisKind": "development_cycle_013_candidate_ceiling_zero_inference",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "readOnly": True,
        "decision": verdict["decision"],
        "headlineEpsilon": HEADLINE_EPSILON,
        "inputs": channels,
        "planContract": {
            "cycleId": plan.get("cycleId"),
            "onlyVariable": (plan.get("hypothesis") or {}).get("onlyVariable"),
            "formalFloorForDevelopmentSignalOnly": declared_floor,
        },
        "developmentFloor": DEVELOPMENT_FLOOR,
        "reconstructionFidelity": {
            "ok": fidelity["ok"],
            "checks": fidelity["checks"],
            "mismatchCount": fidelity["mismatchCount"],
        },
        "baseline": reconstructed["summary"],
        "epsilonSweep": sweep,
        "successRateSensitivity": sensitivity,
        "verdict": verdict,
        "margin": margin,
        "assumptions": [
            "可附着候选的 mask 被替换为其附着真值的完美 mask（IoU=1.0，必然 complete）",
            "stage2 不产生新候选、不删除候选；产品去重规则与每图候选上限 10 不变",
            "真值分母 354 与正图分母 58 不变；困难负样本图不做任何替换",
            "IoU 一律沿用既有实现的归一化坐标口径（与历史匹配/报告完全一致）",
        ],
    }
    write_report(Path(args.output).resolve(), payload)
    print(
        f"decision={payload['decision']} 漏甲图天花板={headline['summary']['missingImages'] if headline else 'n/a'} "
        f"杂散率天花板={headline['summary']['weightedSpuriousRate'] if headline else 'n/a'}"
    )
    return 0


def cmd_wilson(args: argparse.Namespace) -> int:
    if args.verify_report:
        return verify_report(Path(args.output).resolve())
    channels = collect_channels(args)
    plan = read_json(Path(args.plan).resolve())
    verify_floor(plan)
    dataset_root, by_stem, predictions = load_evaluation_inputs(
        Path(args.materialization_report).resolve(), Path(args.artifact_index).resolve()
    )
    reconstructed = reconstruct(dataset_root, by_stem, predictions)
    frozen = read_json(Path(args.quality_report).resolve())
    fidelity = check_fidelity(reconstructed, frozen)
    if not fidelity["ok"]:
        payload = {
            "schemaVersion": 1,
            "analysisKind": "development_cycle_013_decision_resolution_wilson",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "readOnly": True,
            "decision": "reconstruction_mismatch",
            "inputs": channels,
            "reconstructionFidelity": fidelity,
            "baseline": reconstructed["summary"],
            "note": "接受候选集重建与冻结质量报告不一致，未产出任何判定分辨率结论。",
        }
        write_report(Path(args.output).resolve(), payload)
        print("重建与冻结报告不一致，已以 reconstruction_mismatch 结项。", file=sys.stderr)
        return 1
    resolution = build_resolution(reconstructed)
    determinism = determinism_check(Path(args.quality_report).resolve()) if args.determinism_check else {"ran": False}
    payload = {
        "schemaVersion": 1,
        "analysisKind": "development_cycle_013_decision_resolution_wilson",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "readOnly": True,
        "inputs": channels,
        "reconstructionFidelity": {"ok": fidelity["ok"], "checks": fidelity["checks"], "mismatchCount": fidelity["mismatchCount"]},
        "baseline": reconstructed["summary"],
        **resolution,
        "determinismCheck": determinism,
        "interpretation": [
            "若相对门（漏甲图数）落在基线的 Wilson 区间内，则该相对信号不可判别，不能作为分支关闭/保留的依据。",
            "单轮判定分辨率由分母与基线比例共同决定；分母不足时应改用绝对门与噪声内的方向性结论。",
            "推理侧在同一权重同一输入下确定性，不确定性主要来自训练随机性，不能靠重复推理估计。",
        ],
    }
    write_report(Path(args.output).resolve(), payload)
    resolvability = resolution["relativeGateResolvability"]
    print(
        f"相对门可判别={not resolvability['relativeGateInsideBaselineInterval']} "
        f"基线区间=[{resolvability['wilsonLow']}, {resolvability['wilsonHigh']}]"
    )
    return 0


def main() -> int:
    args = parser().parse_args()
    if args.command == "ceiling":
        return cmd_ceiling(args)
    if args.command == "wilson":
        return cmd_wilson(args)
    raise ValueError(f"未知子命令：{args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
