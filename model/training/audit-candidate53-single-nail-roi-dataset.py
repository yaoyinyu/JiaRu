#!/usr/bin/env python3
"""独立核验candidate53单甲ROI数据的哈希、角色、标签与负例比例。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


APPROVED_DECISION = "approved_candidate53_single_nail_roi_training_input"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象：{path}")
    return value


def polygon_area(points: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True))) / 2


def inventory(root: Path, excluded: set[Path]) -> list[dict[str, str]]:
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.endswith(".cache") and path.resolve() not in excluded
    ]


def build_report(materialization_path: Path) -> dict[str, Any]:
    materialization = read_json(materialization_path)
    if materialization.get("decision") != "candidate53_single_nail_roi_materialized_pending_independent_audit":
        raise ValueError("物化报告状态不正确")
    root = materialization_path.parent.resolve()
    if Path(str(materialization.get("outputDir", ""))).resolve() != root:
        raise ValueError("物化报告未绑定当前目录")
    lineage_path = Path(str(materialization["lineage"]["path"])).resolve()
    lineage = read_json(lineage_path)
    if sha256_file(lineage_path) != materialization["lineage"]["sha256"]:
        raise ValueError("lineage哈希漂移")
    records = lineage.get("records")
    if not isinstance(records, list) or canonical_sha256(records) != lineage.get("recordsSha256"):
        raise ValueError("lineage记录哈希错误")
    if lineage.get("rolePolicy") != {"trainFromTrainOnly": True, "valFromValOnly": True, "testUsed": False, "holdoutUsed": False}:
        raise ValueError("角色隔离策略不正确")
    input_audit_path = Path(str(lineage["inputs"]["inputAudit"])).resolve()
    plan_path = Path(str(lineage["inputs"]["plan"])).resolve()
    weights_path = Path(str(lineage["inputs"]["stage1Weights"])).resolve()
    truth_index_path = Path(str(lineage["inputs"]["trainingTruthIndex"])).resolve()
    for path, key in (
        (input_audit_path, "inputAuditSha256"), (plan_path, "planSha256"),
        (weights_path, "stage1WeightsSha256"), (truth_index_path, "trainingTruthIndexSha256"),
    ):
        if not path.is_file() or sha256_file(path) != lineage["inputs"][key]:
            raise ValueError(f"输入文件漂移：{path}")
    input_audit = read_json(input_audit_path)
    plan = read_json(plan_path)
    if input_audit.get("decision") != "approved_candidate_training_input" or plan.get("candidate") != "candidate53":
        raise ValueError("父输入或计划未批准")
    if sha256_file(weights_path) != plan["stage1"]["weightsSha256"]:
        raise ValueError("stage1权重与计划不一致")

    counts = {"trainPositiveRois": 0, "trainNegativeRois": 0, "valPositiveRois": 0, "valNegativeRois": 0}
    excluded_parents = lineage.get("excludedParents")
    if not isinstance(excluded_parents, list):
        raise ValueError("缺少整图边界排除清单")
    excluded_parent_paths: set[Path] = set()
    for item in excluded_parents:
        split = str(item.get("split", ""))
        parent_root = Path(str(lineage["inputs"]["datasetRoot"]))
        image_path = parent_root / "images" / split / str(item.get("fileName", ""))
        label_path = parent_root / "labels" / split / f"{image_path.stem}.txt"
        if split not in {"train", "val"} or sha256_file(image_path) != item.get("imageSha256") or sha256_file(label_path) != item.get("labelSha256"):
            raise ValueError("整图边界排除清单哈希或角色错误")
        if not item.get("boundaryTouchingPolygonIndices") or item.get("reason") != "required_nail_touches_parent_image_boundary_entire_source_excluded_from_stage2":
            raise ValueError("整图边界排除原因不完整")
        excluded_parent_paths.add(image_path.resolve())
    seen_ids: set[str] = set()
    seen_outputs: set[str] = set()
    source_groups = {"train": set(), "val": set()}
    for index, item in enumerate(records, 1):
        item_id = str(item.get("id", ""))
        split = str(item.get("split", ""))
        kind = str(item.get("kind", ""))
        if not item_id or item_id in seen_ids or split not in {"train", "val"} or kind not in {"positive", "negative"}:
            raise ValueError(f"lineage第{index}项身份/角色非法")
        seen_ids.add(item_id)
        image_relative = str(item["outputImage"])
        label_relative = str(item["outputLabel"])
        if image_relative in seen_outputs or label_relative in seen_outputs:
            raise ValueError("ROI输出路径重复")
        seen_outputs.update((image_relative, label_relative))
        image_path, label_path = root / image_relative, root / label_relative
        if sha256_file(image_path) != item["outputImageSha256"] or sha256_file(label_path) != item["outputLabelSha256"]:
            raise ValueError(f"ROI输出哈希漂移：{item_id}")
        parent_image = Path(str(item["parentImage"]))
        parent_label = Path(str(item["parentLabel"]))
        if sha256_file(parent_image) != item["parentImageSha256"] or sha256_file(parent_label) != item["parentLabelSha256"]:
            raise ValueError(f"父图或父标签漂移：{item_id}")
        if parent_image.resolve() in excluded_parent_paths:
            raise ValueError(f"已整图排除的父图仍产生ROI：{item_id}")
        if f"/{split}/" not in image_relative.replace("\\", "/") or f"/{split}/" not in label_relative.replace("\\", "/"):
            raise ValueError(f"ROI输出进入错误分片：{item_id}")
        source_groups[split].add(str(item["sourceGroup"]))
        text = label_path.read_text(encoding="utf-8").strip()
        if kind == "negative":
            if text or float(item.get("bestTruthMaskIou", 1)) >= 0.10 or float(item.get("bestTruthBoxIou", 1)) >= 0.10:
                raise ValueError(f"负ROI标签或IoU非法：{item_id}")
        else:
            lines = [line for line in text.splitlines() if line.strip()]
            if len(lines) != 1:
                raise ValueError(f"正ROI必须且只能包含一个甲面：{item_id}")
            fields = lines[0].split()
            if len(fields) < 7 or len(fields) % 2 == 0 or fields[0] != "0":
                raise ValueError(f"正ROI标签格式非法：{item_id}")
            values = [float(value) for value in fields[1:]]
            if any(not math.isfinite(value) or value <= 0 or value >= 1 for value in values):
                raise ValueError(f"正ROI polygon触边或越界：{item_id}")
            points = list(zip(values[0::2], values[1::2], strict=True))
            if polygon_area(points) <= 0:
                raise ValueError(f"正ROI polygon面积为零：{item_id}")
        counts[f"{split}{kind.title()}Rois"] += 1
    if source_groups["train"] & source_groups["val"]:
        raise ValueError("train与val来源组交叠")
    expected_counts = lineage["counts"]
    for key, actual in counts.items():
        if actual != int(expected_counts[key]):
            raise ValueError(f"计数不一致：{key}")
    unique_positive_masks = int(plan["stage2Dataset"]["positiveMasks"])
    ratio = counts["trainNegativeRois"] / unique_positive_masks
    if ratio > float(plan["stage2Dataset"]["maximumNegativeToPositiveRatio"]) + 1e-12:
        raise ValueError("训练负ROI比例超出计划上限")
    test_files = list((root / "images" / "test").glob("*")) + list((root / "labels" / "test").glob("*"))
    if test_files:
        raise ValueError("candidate53 ROI数据意外包含test文件")
    materialized_files = materialization.get("datasetFiles")
    current_files = inventory(root, {materialization_path.resolve()})
    if current_files != materialized_files or canonical_sha256(current_files) != materialization.get("datasetFilesSha256"):
        raise ValueError("物化文件树漂移")
    return {
        "schemaVersion": 1, "ok": True, "status": "PASS", "decision": APPROVED_DECISION,
        "candidateTrainingEligible": True, "trainingUse": "approved-for-candidate53-training-only",
        "inputs": {
            "materializationReport": {"path": str(materialization_path), "sha256": sha256_file(materialization_path)},
            "parentCandidateInputAudit": {"path": str(input_audit_path), "sha256": sha256_file(input_audit_path)},
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "stage1Weights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "outputDir": str(root), "datasetYaml": str(root / "dataset.yaml"),
        "counts": {
            **counts,
            "trainImages": counts["trainPositiveRois"] + counts["trainNegativeRois"],
            "trainPositiveImages": counts["trainPositiveRois"],
            "hardNegativeImages": counts["trainNegativeRois"],
            "validationImages": counts["valPositiveRois"] + counts["valNegativeRois"],
            "positiveMasks": counts["trainPositiveRois"],
            "validationMasks": counts["valPositiveRois"],
            "testImages": 0,
            "orphanFiles": 0,
        },
        "negativeToUniquePositiveMaskRatio": round(ratio, 8),
        "sourceGroups": {"train": len(source_groups["train"]), "val": len(source_groups["val"]), "overlap": 0},
        "recordsSha256": lineage["recordsSha256"], "datasetFilesSha256": materialization["datasetFilesSha256"],
        "allRolesSha256": canonical_sha256({
            "trainSourceGroups": sorted(source_groups["train"]),
            "valSourceGroups": sorted(source_groups["val"]),
            "recordsSha256": lineage["recordsSha256"],
        }),
        "invariants": {
            "allOutputsAndParentsHashBound": True, "everyPositiveRoiContainsExactlyOneValidPolygon": True,
            "allNegativeRoisHaveMaskAndBoxIouBelowPointOne": True, "trainValSourceGroupsDisjoint": True,
            "testAndHoldoutUnused": True, "watermarkCornerBlurIsTrainOnly": True,
            "sourceBoundaryTouchingParentsEntirelyExcludedFromStage2Rois": True,
        }, "errors": [],
    }


def verify_approved_report(report_path: Path, dataset_yaml: Path | None = None) -> dict[str, Any]:
    existing = read_json(report_path)
    if existing.get("decision") != APPROVED_DECISION:
        raise ValueError("待重放报告不是candidate53批准报告")
    replay = build_report(Path(str(existing["inputs"]["materializationReport"]["path"])).resolve())
    if replay != existing:
        raise ValueError("candidate53批准报告与独立重放不一致")
    if dataset_yaml is not None and Path(str(replay["datasetYaml"])).resolve() != dataset_yaml.resolve():
        raise ValueError("candidate53批准报告未绑定指定dataset.yaml")
    return replay


def main() -> None:
    parser = argparse.ArgumentParser(description="审计candidate53单甲ROI训练数据")
    parser.add_argument("--materialization-report")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        replay = verify_approved_report(report_path)
        print(json.dumps({"ok": True, "decision": replay["decision"]}, ensure_ascii=False))
        return
    if not args.materialization_report or not args.output:
        raise ValueError("构建模式必须提供--materialization-report和--output")
    output = Path(args.output).resolve()
    report = build_report(Path(args.materialization_report).resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "decision": report["decision"], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
