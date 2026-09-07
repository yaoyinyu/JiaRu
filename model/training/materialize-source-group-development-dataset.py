#!/usr/bin/env python3
"""把已批准的 sourceGroup 开发折物化为只供短程实验使用的YOLO数据集。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def load_fold_builder() -> ModuleType:
    path = Path(__file__).with_name("build-source-group-development-folds.py")
    spec = importlib.util.spec_from_file_location("source_group_fold_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"不能加载开发折构建器：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FOLD_BUILDER = load_fold_builder()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}必须是JSON对象")
    return value


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def inventory_tree(root: Path) -> tuple[list[dict[str, str]], str]:
    records = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    return records, canonical_sha256(records)


def atomic_write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告输出已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_plan_and_sources(
    plan_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[dict[str, Any]]]:
    plan = FOLD_BUILDER.verify_plan(plan_path)
    materialization_binding = plan["inputs"]["materializationReport"]
    materialization_path = Path(materialization_binding["path"]).resolve()
    materialization = read_json(materialization_path, "源训练物化报告")
    if sha256_file(materialization_path) != materialization_binding["sha256"]:
        raise ValueError("源训练物化报告哈希漂移")
    source_root = Path(materialization["outputDir"]).resolve()
    if not source_root.is_dir():
        raise ValueError(f"源训练数据集不存在：{source_root}")
    source_records = materialization.get("records")
    if not isinstance(source_records, list):
        raise ValueError("源训练物化报告缺少records")
    by_name = {str(item.get("fileName", "")): item for item in source_records}
    if len(by_name) != len(source_records):
        raise ValueError("源训练物化报告文件名不唯一")

    prepared: list[dict[str, Any]] = []
    stems: set[str] = set()
    for number, item in enumerate(plan["records"], start=1):
        file_name = str(item["fileName"])
        source_record = by_name.get(file_name)
        if source_record is None:
            raise ValueError(f"开发折记录未出现在源物化报告：{file_name}")
        if any(
            source_record.get(key) != item.get(key)
            for key in ("role", "sourceGroup", "imageSha256", "maskCount")
        ):
            raise ValueError(f"开发折记录与源物化报告身份不一致：{file_name}")
        suffix = Path(file_name).suffix.lower()
        if suffix not in IMAGE_SUFFIXES or Path(file_name).name != file_name:
            raise ValueError(f"开发折图片文件名无效：{file_name}")
        stem = Path(file_name).stem
        if stem.casefold() in stems:
            raise ValueError(f"开发折存在重复文件stem：{stem}")
        stems.add(stem.casefold())
        image = source_root / "images" / "train" / file_name
        label = source_root / "labels" / "train" / f"{stem}.txt"
        expected_image_sha = str(source_record.get("materializedImageSha256", ""))
        expected_label_sha = str(source_record.get("materializedLabelSha256", ""))
        if not image.is_file() or sha256_file(image) != expected_image_sha:
            raise ValueError(f"源训练图片缺失或漂移：{image}")
        if not label.is_file() or sha256_file(label) != expected_label_sha:
            raise ValueError(f"源训练标签缺失或漂移：{label}")
        if expected_image_sha != item["imageSha256"]:
            raise ValueError(f"开发折图片哈希与物化文件不一致：{file_name}")
        if item["role"] == "hard-negative" and label.stat().st_size != 0:
            raise ValueError(f"困难负样本标签必须是零字节：{file_name}")
        prepared.append(
            {
                **item,
                "sourceImage": str(image),
                "sourceImageSha256": expected_image_sha,
                "sourceLabel": str(label),
                "sourceLabelSha256": expected_label_sha,
                "developmentSplit": "val" if item["developmentRole"] == "evaluation" else "train",
            }
        )
    return plan, materialization, source_root, prepared


def apply_training_hard_negative_selection(
    prepared: list[dict[str, Any]], selection_path: Path | None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if selection_path is None:
        return prepared, None
    selection = read_json(selection_path, "训练困难负样本选择计划")
    groups = selection.get("trainingHardNegativeSourceGroups")
    if selection.get("schemaVersion") != 1 or not isinstance(groups, list):
        raise ValueError("训练困难负样本选择计划合同无效")
    normalized_groups = sorted({str(value) for value in groups})
    if len(normalized_groups) != len(groups) or not normalized_groups:
        raise ValueError("训练困难负样本来源组必须非空且不重复")
    available_groups = {
        item["sourceGroup"]
        for item in prepared
        if item["developmentSplit"] == "train" and item["role"] == "hard-negative"
    }
    unknown_groups = sorted(set(normalized_groups) - available_groups)
    if unknown_groups:
        raise ValueError(f"选择计划包含未知训练困难负样本来源组：{unknown_groups}")
    selected = [
        item
        for item in prepared
        if not (
            item["developmentSplit"] == "train"
            and item["role"] == "hard-negative"
            and item["sourceGroup"] not in normalized_groups
        )
    ]
    selected_count = sum(
        item["developmentSplit"] == "train" and item["role"] == "hard-negative"
        for item in selected
    )
    if selected_count != selection.get("expectedTrainingHardNegativeImages"):
        raise ValueError("训练困难负样本选择后的图片数与计划不一致")
    return selected, {
        "path": str(selection_path),
        "sha256": sha256_file(selection_path),
        "trainingHardNegativeSourceGroups": normalized_groups,
        "expectedTrainingHardNegativeImages": selected_count,
    }


def apply_training_positive_resampling(
    prepared: list[dict[str, Any]], selection_path: Path | None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if selection_path is None:
        return prepared, None
    selection = read_json(selection_path, "训练困难正样本重采样计划")
    groups = selection.get("selectedSourceGroups")
    repeat_factor = selection.get("repeatFactor")
    if (
        selection.get("schemaVersion") != 1
        or selection.get("decision")
        != "approved_train_internal_positive_resampling_selection"
        or selection.get("trainingUse") != "development-experiment-only"
        or not isinstance(groups, list)
        or repeat_factor != 2
    ):
        raise ValueError("训练困难正样本重采样计划合同无效")
    normalized_groups = sorted({str(value) for value in groups})
    if len(normalized_groups) != len(groups) or not normalized_groups:
        raise ValueError("训练困难正样本重采样来源组必须非空且不重复")
    training_positives = [
        item
        for item in prepared
        if item["developmentSplit"] == "train" and item["role"] == "train-positive"
    ]
    if len(training_positives) != selection.get("expectedBaseTrainingPositiveImages"):
        raise ValueError("训练正样本基数与重采样计划不一致")
    available_groups = {item["sourceGroup"] for item in training_positives}
    unknown_groups = sorted(set(normalized_groups) - available_groups)
    if unknown_groups:
        raise ValueError(f"重采样计划包含未知训练正样本来源组：{unknown_groups}")
    selected_items = [
        item for item in training_positives if item["sourceGroup"] in normalized_groups
    ]
    if len(selected_items) != selection.get("expectedSelectedUniqueImages"):
        raise ValueError("训练困难正样本选择数量与计划不一致")
    existing_names = {item["fileName"].casefold() for item in prepared}
    replicas: list[dict[str, Any]] = []
    for item in selected_items:
        source_name = item["fileName"]
        replica_name = f"resample01__{source_name}"
        if replica_name.casefold() in existing_names:
            raise ValueError(f"重采样文件名冲突：{replica_name}")
        existing_names.add(replica_name.casefold())
        replicas.append(
            {
                **item,
                "fileName": replica_name,
                "sourceFileName": source_name,
                "resampleIndex": 1,
                "isResampledCopy": True,
            }
        )
    if len(replicas) != selection.get("expectedResampledPositiveCopies"):
        raise ValueError("训练困难正样本副本数量与计划不一致")
    return prepared + replicas, {
        "path": str(selection_path),
        "sha256": sha256_file(selection_path),
        "selectedSourceGroups": normalized_groups,
        "expectedBaseTrainingPositiveImages": len(training_positives),
        "expectedSelectedUniqueImages": len(selected_items),
        "repeatFactor": repeat_factor,
        "expectedResampledPositiveCopies": len(replicas),
    }


def build_report(
    plan_path: Path,
    output_root: Path,
    report_path: Path,
    training_hard_negative_selection: Path | None = None,
    training_positive_resampling_selection: Path | None = None,
) -> dict[str, Any]:
    plan, source_materialization, source_root, prepared = validate_plan_and_sources(plan_path)
    prepared, selection_binding = apply_training_hard_negative_selection(
        prepared, training_hard_negative_selection
    )
    prepared, positive_resampling_binding = apply_training_positive_resampling(
        prepared, training_positive_resampling_selection
    )
    if output_root.exists():
        raise ValueError(f"开发数据集输出已存在，禁止覆盖：{output_root}")
    if report_path.exists():
        raise ValueError(f"开发数据集报告已存在，禁止覆盖：{report_path}")
    if is_within(output_root, source_root) or is_within(report_path, source_root):
        raise ValueError("开发输出不得写入冻结源训练数据集")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.tmp-", dir=output_root.parent))
    records: list[dict[str, Any]] = []
    try:
        for kind in ("images", "labels"):
            for split in ("train", "val", "test"):
                (staging / kind / split).mkdir(parents=True, exist_ok=True)
        for item in prepared:
            split = item["developmentSplit"]
            file_name = item["fileName"]
            stem = Path(file_name).stem
            target_image = staging / "images" / split / file_name
            target_label = staging / "labels" / split / f"{stem}.txt"
            shutil.copy2(item["sourceImage"], target_image)
            shutil.copy2(item["sourceLabel"], target_label)
            image_sha = sha256_file(target_image)
            label_sha = sha256_file(target_label)
            if image_sha != item["sourceImageSha256"] or label_sha != item["sourceLabelSha256"]:
                raise ValueError(f"开发数据集复制后哈希不一致：{file_name}")
            records.append(
                {
                    "fileName": file_name,
                    "role": item["role"],
                    "sourceGroup": item["sourceGroup"],
                    "fold": item["fold"],
                    "developmentSplit": split,
                    "maskCount": item["maskCount"],
                    "image": f"images/{split}/{file_name}",
                    "imageSha256": image_sha,
                    "label": f"labels/{split}/{stem}.txt",
                    "labelSha256": label_sha,
                    **(
                        {
                            "sourceFileName": item["sourceFileName"],
                            "resampleIndex": item["resampleIndex"],
                            "isResampledCopy": True,
                        }
                        if item.get("isResampledCopy") is True
                        else {}
                    ),
                }
            )
        dataset_yaml = (
            "path: .\n"
            "train: images/train\n"
            "val: images/val\n"
            "test: images/test\n\n"
            "names:\n"
            "  0: nail_texture\n\n"
            "task: segment\n"
            "class_count: 1\n"
            "image_size: 512\n\n"
            "metadata:\n"
            "  dataset_version: train-source-group-development/v1\n"
            "  role: development-experiment-only\n"
            "  formal_calibration_test_or_holdout: false\n"
        )
        (staging / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
        records.sort(key=lambda item: (item["developmentSplit"], item["role"], item["fileName"]))
        inventory, dataset_files_sha = inventory_tree(staging)
        source_groups = {
            split: {item["sourceGroup"] for item in records if item["developmentSplit"] == split}
            for split in ("train", "val")
        }
        if source_groups["train"] & source_groups["val"]:
            raise ValueError("开发训练与评估split发生sourceGroup交叠")
        counts = {
            "trainImages": sum(item["developmentSplit"] == "train" for item in records),
            "trainPositiveImages": sum(item["developmentSplit"] == "train" and item["role"] == "train-positive" for item in records),
            "trainPositiveMasks": sum(item["maskCount"] for item in records if item["developmentSplit"] == "train"),
            "trainHardNegativeImages": sum(item["developmentSplit"] == "train" and item["role"] == "hard-negative" for item in records),
            "evaluationImages": sum(item["developmentSplit"] == "val" for item in records),
            "evaluationPositiveImages": sum(item["developmentSplit"] == "val" and item["role"] == "train-positive" for item in records),
            "evaluationPositiveMasks": sum(item["maskCount"] for item in records if item["developmentSplit"] == "val"),
            "evaluationHardNegativeImages": sum(item["developmentSplit"] == "val" and item["role"] == "hard-negative" for item in records),
            "testImages": 0,
            "sourceGroupOverlap": 0,
        }
        resampled_positive_copies = sum(
            item.get("isResampledCopy") is True for item in records
        )
        unique_train_positive_images = sum(
            item["developmentSplit"] == "train"
            and item["role"] == "train-positive"
            and item.get("isResampledCopy") is not True
            for item in records
        )
        unique_train_positive_masks = sum(
            item["maskCount"]
            for item in records
            if item["developmentSplit"] == "train"
            and item["role"] == "train-positive"
            and item.get("isResampledCopy") is not True
        )
        if positive_resampling_binding is not None:
            counts.update(
                {
                    "trainUniquePositiveImages": unique_train_positive_images,
                    "trainResampledPositiveCopies": resampled_positive_copies,
                    "trainUniquePositiveMasks": unique_train_positive_masks,
                    "trainEffectivePositiveMasks": counts["trainPositiveMasks"],
                }
            )
        expected_counts = {
            "trainImages": unique_train_positive_images
            + resampled_positive_copies
            + counts["trainHardNegativeImages"],
            "trainPositiveImages": unique_train_positive_images
            + resampled_positive_copies,
            "trainPositiveMasks": unique_train_positive_masks
            + sum(
                item["maskCount"]
                for item in records
                if item.get("isResampledCopy") is True
            ),
            "trainHardNegativeImages": counts["trainHardNegativeImages"],
            "evaluationImages": sum(
                item["developmentSplit"] == "val" for item in records
            ),
            "evaluationPositiveImages": sum(
                item["developmentSplit"] == "val"
                and item["role"] == "train-positive"
                for item in records
            ),
            "evaluationPositiveMasks": sum(
                item["maskCount"]
                for item in records
                if item["developmentSplit"] == "val"
            ),
            "evaluationHardNegativeImages": sum(
                item["developmentSplit"] == "val"
                and item["role"] == "hard-negative"
                for item in records
            ),
            "testImages": 0,
            "sourceGroupOverlap": 0,
        }
        if positive_resampling_binding is not None:
            expected_counts.update(
                {
                    "trainUniquePositiveImages": unique_train_positive_images,
                    "trainResampledPositiveCopies": resampled_positive_copies,
                    "trainUniquePositiveMasks": unique_train_positive_masks,
                    "trainEffectivePositiveMasks": expected_counts["trainPositiveMasks"],
                }
            )
        if counts != expected_counts:
            raise ValueError(f"开发数据集计数不等于固定折计划：{counts}")
        if (
            unique_train_positive_images < 263
            or unique_train_positive_masks < 1581
            or counts["evaluationPositiveImages"] < 65
            or counts["evaluationPositiveMasks"] < 400
            or counts["evaluationHardNegativeImages"] != 40
        ):
            raise ValueError(f"开发数据集低于冻结开发基线：{counts}")
        if selection_binding is None and counts["trainHardNegativeImages"] != 120:
            raise ValueError("未指定消融选择计划时必须保留全部120张训练困难负样本")
        report = {
            "schemaVersion": 1,
            "ok": True,
            "status": "PASS",
            "decision": "approved_train_internal_development_dataset_materialization",
            "trainingUse": "development-experiment-only",
            "candidateTrainingEligible": False,
            "formalCalibrationTestOrHoldoutEligible": False,
            "inputs": {
                "developmentFoldPlan": {
                    "path": str(plan_path),
                    "sha256": sha256_file(plan_path),
                    "contentSha256": plan["contentSha256"],
                },
                "sourceMaterializationReport": {
                    "path": plan["inputs"]["materializationReport"]["path"],
                    "sha256": plan["inputs"]["materializationReport"]["sha256"],
                    "recordsSha256": source_materialization["recordsSha256"],
                    "datasetFilesSha256": source_materialization["datasetFilesSha256"],
                },
                "trainingHardNegativeSelection": selection_binding,
                "trainingPositiveResamplingSelection": positive_resampling_binding,
            },
            "outputDir": str(output_root),
            "datasetYaml": {
                "path": str(output_root / "dataset.yaml"),
                "sha256": sha256_file(staging / "dataset.yaml"),
            },
            "counts": counts,
            "sourceGroups": {
                "train": len(source_groups["train"]),
                "evaluation": len(source_groups["val"]),
                "overlap": [],
            },
            "datasetFilesSha256": dataset_files_sha,
            "datasetFileCount": len(inventory),
            "recordsSha256": canonical_sha256(records),
            "records": records,
            "invariants": {
                "onlyOriginalTrainRolesUsed": True,
                "oldValidationRecordsExcluded": True,
                "testAndHoldoutRecordsExcluded": True,
                "sourceGroupAtomicAndMutuallyExclusive": True,
                "sourceFilesHashMatchedBeforeAndAfterCopy": True,
                "zeroByteHardNegativeLabelsPreserved": True,
                "positiveResamplingSourceGroupAtomic": positive_resampling_binding
                is not None,
            },
            "errors": [],
        }
        os.replace(staging, output_root)
        atomic_write_new(report_path, report)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_report(path: Path) -> dict[str, Any]:
    report = read_json(path, "开发数据集物化报告")
    if (
        report.get("schemaVersion") != 1
        or report.get("ok") is not True
        or report.get("status") != "PASS"
        or report.get("decision")
        != "approved_train_internal_development_dataset_materialization"
        or report.get("trainingUse") != "development-experiment-only"
        or report.get("candidateTrainingEligible") is not False
        or report.get("formalCalibrationTestOrHoldoutEligible") is not False
        or report.get("errors") not in (None, [])
    ):
        raise ValueError("开发数据集物化报告顶层合同无效")
    plan_binding = report.get("inputs", {}).get("developmentFoldPlan")
    if not isinstance(plan_binding, dict):
        raise ValueError("开发数据集物化报告未绑定开发折计划")
    plan_path = Path(str(plan_binding.get("path", ""))).resolve()
    if sha256_file(plan_path) != plan_binding.get("sha256"):
        raise ValueError("开发折计划文件哈希漂移")
    plan, _, source_root, prepared = validate_plan_and_sources(plan_path)
    if plan["contentSha256"] != plan_binding.get("contentSha256"):
        raise ValueError("开发折计划内容身份漂移")
    output_root = Path(str(report.get("outputDir", ""))).resolve()
    if not output_root.is_dir() or is_within(output_root, source_root):
        raise ValueError("开发数据集输出目录缺失或污染冻结源数据集")
    inventory, inventory_sha = inventory_tree(output_root)
    if inventory_sha != report.get("datasetFilesSha256") or len(inventory) != report.get("datasetFileCount"):
        raise ValueError("开发数据集文件树发生漂移")
    records = report.get("records")
    if not isinstance(records, list) or canonical_sha256(records) != report.get("recordsSha256"):
        raise ValueError("开发数据集records缺失或哈希漂移")
    selection_binding = report.get("inputs", {}).get("trainingHardNegativeSelection")
    if selection_binding is not None:
        if not isinstance(selection_binding, dict):
            raise ValueError("训练困难负样本选择绑定无效")
        selection_path = Path(str(selection_binding.get("path", ""))).resolve()
        if sha256_file(selection_path) != selection_binding.get("sha256"):
            raise ValueError("训练困难负样本选择计划哈希漂移")
        prepared, replayed_binding = apply_training_hard_negative_selection(
            prepared, selection_path
        )
        if replayed_binding != selection_binding:
            raise ValueError("训练困难负样本选择绑定无法重放")
    positive_resampling_binding = report.get("inputs", {}).get(
        "trainingPositiveResamplingSelection"
    )
    if positive_resampling_binding is not None:
        if not isinstance(positive_resampling_binding, dict):
            raise ValueError("训练困难正样本重采样绑定无效")
        selection_path = Path(str(positive_resampling_binding.get("path", ""))).resolve()
        if sha256_file(selection_path) != positive_resampling_binding.get("sha256"):
            raise ValueError("训练困难正样本重采样计划哈希漂移")
        prepared, replayed_binding = apply_training_positive_resampling(
            prepared, selection_path
        )
        if replayed_binding != positive_resampling_binding:
            raise ValueError("训练困难正样本重采样绑定无法重放")
    if len(records) != len(prepared):
        raise ValueError("开发数据集记录数与开发折计划不一致")
    prepared_by_name = {item["fileName"]: item for item in prepared}
    groups_by_split = {"train": set(), "val": set()}
    for item in records:
        file_name = str(item.get("fileName", ""))
        planned = prepared_by_name.get(file_name)
        if planned is None:
            raise ValueError(f"开发数据集存在计划外记录：{file_name}")
        split = str(item.get("developmentSplit", ""))
        expected_split = planned["developmentSplit"]
        if split != expected_split or split not in groups_by_split:
            raise ValueError(f"开发数据集split不匹配：{file_name}")
        image = output_root / str(item.get("image", ""))
        label = output_root / str(item.get("label", ""))
        if not is_within(image, output_root) or not is_within(label, output_root):
            raise ValueError("开发数据集记录路径越界")
        if sha256_file(image) != item.get("imageSha256") or sha256_file(label) != item.get("labelSha256"):
            raise ValueError(f"开发数据集文件哈希漂移：{file_name}")
        groups_by_split[split].add(item["sourceGroup"])
    if groups_by_split["train"] & groups_by_split["val"]:
        raise ValueError("开发数据集训练与评估来源组交叠")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-fold-plan", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--training-hard-negative-selection", type=Path)
    parser.add_argument("--training-positive-resampling-selection", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report is not None:
        if any(value is not None for value in (args.development_fold_plan, args.output_dir, args.report, args.training_hard_negative_selection, args.training_positive_resampling_selection)):
            raise ValueError("--verify-report不能与物化参数并用")
        report = verify_report(args.verify_report.resolve())
        print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
        return 0
    if any(value is None for value in (args.development_fold_plan, args.output_dir, args.report)):
        raise ValueError("物化必须提供开发折计划、输出目录和报告路径")
    report = build_report(
        args.development_fold_plan.resolve(),
        args.output_dir.resolve(),
        args.report.resolve(),
        args.training_hard_negative_selection.resolve()
        if args.training_hard_negative_selection is not None
        else None,
        args.training_positive_resampling_selection.resolve()
        if args.training_positive_resampling_selection is not None
        else None,
    )
    verify_report(args.report.resolve())
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
