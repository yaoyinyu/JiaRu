#!/usr/bin/env python3
"""独立重放candidate55真实候选条件化ROI数据的来源、边界与文件树。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


APPROVED_DECISION = "approved_candidate55_proposal_conditioned_roi_training_input"


def load_module(name: str, file_name: str):
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载审计依赖：{file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = load_module("candidate53_materializer_for_candidate55_audit", "materialize-candidate53-single-nail-roi-dataset.py")
CANDIDATE53_AUDITOR = load_module("candidate53_auditor_for_candidate55", "audit-candidate53-single-nail-roi-dataset.py")
PARENT_AUDITOR = load_module("candidate_input_auditor_for_candidate55", "audit-candidate-training-input.py")


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


def read_sources(root: Path) -> dict[str, dict[str, str]]:
    with (root / "metadata" / "sources-isolation.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {str(row["fileName"]): {key: str(value or "") for key, value in row.items()} for row in rows}


def proposal_mask(points: list[list[float]], width: int, height: int) -> np.ndarray:
    pixels = np.asarray(points, dtype=np.float32)
    if pixels.ndim != 2 or pixels.shape[0] < 3 or pixels.shape[1] != 2:
        raise ValueError("候选polygon非法")
    pixels[:, 0] = np.clip(pixels[:, 0], 0, width - 1)
    pixels[:, 1] = np.clip(pixels[:, 1], 0, height - 1)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(pixels).astype(np.int32)], 1)
    if int(mask.sum()) == 0:
        raise ValueError("候选polygon栅格化为空")
    return mask


def build_report(materialization_path: Path) -> dict[str, Any]:
    materialization = read_json(materialization_path)
    if materialization.get("decision") != "candidate55_proposal_conditioned_roi_materialized_pending_independent_audit":
        raise ValueError("candidate55物化报告状态不正确")
    root = materialization_path.parent.resolve()
    if Path(materialization.get("outputDir", "")).resolve() != root:
        raise ValueError("物化报告未绑定当前数据目录")
    lineage_path = Path(materialization["lineage"]["path"]).resolve()
    lineage = read_json(lineage_path)
    if sha256_file(lineage_path) != materialization["lineage"]["sha256"]:
        raise ValueError("candidate55 lineage哈希漂移")
    records = lineage.get("records")
    if not isinstance(records, list) or canonical_sha256(records) != lineage.get("recordsSha256"):
        raise ValueError("candidate55 lineage记录哈希错误")
    if lineage.get("rolePolicy") != {"proposalConditionedTrainFromTrainOnly": True, "baseValCopiedUnchanged": True, "testUsed": False, "holdoutUsed": False}:
        raise ValueError("candidate55角色隔离策略错误")
    inputs = lineage["inputs"]
    plan_path = Path(inputs["plan"]).resolve()
    evidence_path = Path(inputs["runtimeEvidence"]).resolve()
    base_root = Path(inputs["baseDataset"]).resolve()
    base_audit_path = Path(inputs["baseAudit"]).resolve()
    parent_root = Path(inputs["parentDataset"]).resolve()
    parent_audit_path = Path(inputs["parentAudit"]).resolve()
    weights_path = Path(inputs["stage1Weights"]).resolve()
    for path, key in (
        (plan_path, "planSha256"), (evidence_path, "runtimeEvidenceSha256"),
        (base_audit_path, "baseAuditSha256"), (parent_audit_path, "parentAuditSha256"),
        (weights_path, "stage1WeightsSha256"),
    ):
        if not path.is_file() or sha256_file(path) != inputs[key]:
            raise ValueError(f"candidate55绑定输入漂移：{path}")
    plan = read_json(plan_path)
    if plan.get("candidate") != "candidate55" or plan.get("entryGate", {}).get("decision") != "closed_with_runtime_semantics_mismatch_confirmed":
        raise ValueError("candidate55计划未锁定入口差异")
    if sha256_file(evidence_path) != plan["entryGate"]["evidenceSha256"]:
        raise ValueError("运行时入口报告未与计划一致")
    if sha256_file(weights_path) != plan["stage1"]["weightsSha256"]:
        raise ValueError("stage1权重未与计划一致")
    base_replay = CANDIDATE53_AUDITOR.verify_approved_report(base_audit_path, base_root / "dataset.yaml")
    parent_replay = PARENT_AUDITOR.verify_approved_report(parent_audit_path, parent_root / "dataset.yaml")
    if base_replay.get("decision") != "approved_candidate53_single_nail_roi_training_input":
        raise ValueError("candidate53基础ROI深重放失败")
    if parent_replay.get("decision") != "approved_candidate_training_input":
        raise ValueError("candidate52父输入深重放失败")

    base_materialization = read_json(Path(base_replay["inputs"]["materializationReport"]["path"]))
    base_file_count = 0
    for item in base_materialization["datasetFiles"]:
        relative = str(item["path"])
        if not (relative.startswith("images/") or relative.startswith("labels/")):
            continue
        base_path = base_root / relative
        copied_path = root / relative
        expected = str(item["sha256"])
        if sha256_file(base_path) != expected or sha256_file(copied_path) != expected:
            raise ValueError(f"candidate53基础文件未逐字节复制：{relative}")
        base_file_count += 1
    if list((root / "images" / "test").glob("*")) or list((root / "labels" / "test").glob("*")):
        raise ValueError("candidate55数据意外包含test文件")

    sources = read_sources(parent_root)
    seen_ids: set[str] = set()
    seen_outputs: set[str] = set()
    source_groups: set[str] = set()
    selected_truths: set[tuple[str, int]] = set()
    for index, item in enumerate(records, 1):
        item_id = str(item.get("id", ""))
        if not item_id or item_id in seen_ids or item.get("split") != "train" or item.get("kind") != "proposal-conditioned-positive":
            raise ValueError(f"candidate55第{index}条记录身份/角色非法")
        seen_ids.add(item_id)
        if item.get("labelSource") != "authoritative-parent-hard-polygon":
            raise ValueError(f"candidate55标签不是权威硬polygon：{item_id}")
        output_image = root / str(item["outputImage"])
        output_label = root / str(item["outputLabel"])
        if str(item["outputImage"]) in seen_outputs or str(item["outputLabel"]) in seen_outputs:
            raise ValueError("candidate55输出路径重复")
        seen_outputs.update((str(item["outputImage"]), str(item["outputLabel"])))
        if "/train/" not in f"/{str(item['outputImage']).replace(chr(92), '/')}":
            raise ValueError("candidate55新裁片未进入train")
        if sha256_file(output_image) != item["outputImageSha256"] or sha256_file(output_label) != item["outputLabelSha256"]:
            raise ValueError(f"candidate55输出哈希漂移：{item_id}")
        parent_image = Path(item["parentImage"]).resolve()
        parent_label = Path(item["parentLabel"]).resolve()
        if parent_image.parent.resolve() != (parent_root / "images" / "train").resolve():
            raise ValueError(f"candidate55父图不是train：{item_id}")
        if parent_label.parent.resolve() != (parent_root / "labels" / "train").resolve():
            raise ValueError(f"candidate55父标签不是train：{item_id}")
        if sha256_file(parent_image) != item["parentImageSha256"] or sha256_file(parent_label) != item["parentLabelSha256"]:
            raise ValueError(f"candidate55父证据哈希漂移：{item_id}")
        role = sources.get(parent_image.name)
        if role is None or role.get("split") != "train" or role.get("role") == "hard-negative" or role.get("sourceGroup") != item.get("sourceGroup"):
            raise ValueError(f"candidate55父角色/来源组错误：{item_id}")
        source_groups.add(str(item["sourceGroup"]))
        polygon_index = int(item["parentPolygonIndex"])
        identity = (parent_image.name, polygon_index)
        if identity in selected_truths:
            raise ValueError(f"同一真值产生多个candidate55裁片：{identity}")
        selected_truths.add(identity)
        polygons = HELPERS.parse_polygons(parent_label)
        if not 1 <= polygon_index <= len(polygons):
            raise ValueError(f"candidate55父polygon索引非法：{item_id}")
        with Image.open(parent_image) as encoded:
            width, height = ImageOps.exif_transpose(encoded).size
        truth_masks, truth_boxes = HELPERS.truth_masks_and_boxes(polygons, width, height)
        predicted_mask = proposal_mask(item["proposalPolygonPixels"], width, height)
        proposal_box = tuple(float(value) for value in item["proposalBox"])
        mask_ious = [HELPERS.mask_iou(predicted_mask, truth) for truth in truth_masks]
        box_ious = [HELPERS.box_iou(proposal_box, truth_box) for truth_box in truth_boxes]
        associations = [i for i, (miou, biou) in enumerate(zip(mask_ious, box_ious, strict=True)) if miou >= 0.10 or biou >= 0.10]
        if associations != [polygon_index - 1]:
            raise ValueError(f"candidate55候选不是唯一关联真值：{item_id}")
        if abs(mask_ious[polygon_index - 1] - float(item["proposalMaskIou"])) > 1e-8 or abs(box_ious[polygon_index - 1] - float(item["proposalBoxIou"])) > 1e-8:
            raise ValueError(f"candidate55候选IoU记录不可重放：{item_id}")
        crop_box = tuple(int(value) for value in item["cropBox"])
        expected_crop = HELPERS.proposal_crop_box(proposal_box, width, height, float(plan["stage1"]["cropContextRatio"]))
        if expected_crop != crop_box:
            raise ValueError(f"candidate55裁片框不可重放：{item_id}")
        expected_polygon = HELPERS.transformed_polygon(polygons[polygon_index - 1], width, height, crop_box)
        expected_text = HELPERS.format_polygon(expected_polygon)
        if output_label.read_text(encoding="utf-8") != expected_text:
            raise ValueError(f"candidate55输出标签不是映射后的权威polygon：{item_id}")
        fields = expected_text.split()
        values = [float(value) for value in fields[1:]]
        if any(not math.isfinite(value) or value <= 0 or value >= 1 for value in values):
            raise ValueError(f"candidate55输出polygon触边：{item_id}")

    counts = lineage["counts"]
    if len(records) != int(counts["proposalConditionedPositiveRois"]):
        raise ValueError("candidate55新增裁片计数不一致")
    if int(counts["uniqueAssociatedProposals"]) != len(records) + int(counts["duplicateProposalsSuppressed"]):
        raise ValueError("candidate55唯一关联候选、最终产物与去重计数未闭合")
    base_counts = base_replay["counts"]
    expected_final = {
        "trainPositiveRois": int(base_counts["trainPositiveRois"]) + len(records),
        "trainNegativeRois": int(base_counts["trainNegativeRois"]),
        "valPositiveRois": int(base_counts["valPositiveRois"]),
        "valNegativeRois": int(base_counts["valNegativeRois"]),
        "testImages": 0,
    }
    if any(int(counts[key]) != value for key, value in expected_final.items()):
        raise ValueError("candidate55最终计数未与基础数据和新增裁片闭合")
    current_files = HELPERS.inventory(root, {materialization_path.resolve()})
    if current_files != materialization["datasetFiles"] or canonical_sha256(current_files) != materialization["datasetFilesSha256"]:
        raise ValueError("candidate55物化文件树漂移")
    parent_val_groups = {
        str(row.get("sourceGroup", ""))
        for row in sources.values()
        if row.get("split") == "val"
    }
    train_val_overlap = source_groups & parent_val_groups
    if train_val_overlap:
        raise ValueError("candidate55新增train裁片与val来源组交叠")
    return {
        "schemaVersion": 1, "ok": True, "status": "PASS", "decision": APPROVED_DECISION,
        "candidateTrainingEligible": True, "trainingUse": "approved-for-candidate55-training-only",
        "inputs": {
            "materializationReport": {"path": str(materialization_path), "sha256": sha256_file(materialization_path)},
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "runtimeEvidence": {"path": str(evidence_path), "sha256": sha256_file(evidence_path)},
            "baseCandidate53Audit": {"path": str(base_audit_path), "sha256": sha256_file(base_audit_path)},
            "parentCandidate52Audit": {"path": str(parent_audit_path), "sha256": sha256_file(parent_audit_path)},
            "stage1Weights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "outputDir": str(root), "datasetYaml": str(root / "dataset.yaml"),
        "counts": {
            **{key: int(value) for key, value in expected_final.items()},
            "trainImages": expected_final["trainPositiveRois"] + expected_final["trainNegativeRois"],
            "trainPositiveImages": expected_final["trainPositiveRois"],
            "hardNegativeImages": expected_final["trainNegativeRois"],
            "validationImages": expected_final["valPositiveRois"] + expected_final["valNegativeRois"],
            "positiveMasks": expected_final["trainPositiveRois"],
            "validationMasks": expected_final["valPositiveRois"],
            "orphanFiles": 0, "proposalConditionedPositiveRois": len(records),
        },
        "sourceGroups": {"proposalConditionedTrain": len(source_groups), "trainValOverlap": len(train_val_overlap)},
        "baseFilesVerified": base_file_count, "recordsSha256": lineage["recordsSha256"],
        "datasetFilesSha256": materialization["datasetFilesSha256"],
        "allRolesSha256": canonical_sha256({
            "proposalConditionedTrainSourceGroups": sorted(source_groups),
            "parentValSourceGroups": sorted(parent_val_groups),
            "recordsSha256": lineage["recordsSha256"],
        }),
        "invariants": {
            "baseCandidate53DatasetCopiedByteForByte": True,
            "allNewRoisDeriveFromTrainOnly": True,
            "oneBestProposalPerTruth": True,
            "everyProposalUniquelyAssociatesExactlyOneTruth": True,
            "everyOutputLabelReplaysFromAuthoritativeHardPolygon": True,
            "allNewPolygonsRemainInsideCrop": True,
            "squareLetterboxRuntimeContractBound": True,
            "testAndHoldoutUnused": True,
        },
        "errors": [],
    }


def verify_approved_report(report_path: Path, dataset_yaml: Path | None = None) -> dict[str, Any]:
    existing = read_json(report_path)
    if existing.get("decision") != APPROVED_DECISION:
        raise ValueError("待重放报告不是candidate55批准报告")
    replay = build_report(Path(existing["inputs"]["materializationReport"]["path"]).resolve())
    if replay != existing:
        raise ValueError("candidate55批准报告与独立重放不一致")
    if dataset_yaml is not None and Path(replay["datasetYaml"]).resolve() != dataset_yaml.resolve():
        raise ValueError("candidate55批准报告未绑定指定dataset.yaml")
    return replay


def main() -> None:
    parser = argparse.ArgumentParser(description="审计candidate55真实候选条件化ROI数据")
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
