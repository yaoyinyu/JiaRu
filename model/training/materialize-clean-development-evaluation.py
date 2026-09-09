#!/usr/bin/env python3
"""将终审正图真值与既有开发困难负图冻结为只读开发评估集。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


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


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def inventory_tree(root: Path) -> tuple[list[dict[str, str]], str]:
    records = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    return records, canonical_sha256(records)


def require_bound_file(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError(f"{label}缺失或哈希漂移：{path}")


def parse_mask_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def validate_inputs(
    positive_index_path: Path, legacy_materialization_path: Path
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], set[str], set[str]]:
    positive_index = read_json(positive_index_path)
    if (
        positive_index.get("schemaVersion") != 1
        or positive_index.get("ok") is not True
        or positive_index.get("decision") != "development_positive_truth_v2_final_review_pass"
        or positive_index.get("trainingUse") != "development-experiment-only"
        or positive_index.get("formalCalibrationTestOrHoldoutEligible") is not False
    ):
        raise ValueError("开发正图真值索引合同无效")
    positive_records = positive_index.get("records")
    if not isinstance(positive_records, list) or canonical_sha256(positive_records) != positive_index.get("recordsSha256"):
        raise ValueError("开发正图真值records缺失或哈希漂移")
    counts = positive_index.get("counts")
    if not isinstance(counts, dict) or counts.get("images") != 58 or counts.get("masks") != 354:
        raise ValueError("开发正图真值必须严格为58图/354 mask")

    positive_root = positive_index_path.parent.parent.resolve()
    seen_names: set[str] = set()
    seen_stems: set[str] = set()
    positive_groups: set[str] = set()
    for row in positive_records:
        if not isinstance(row, dict):
            raise ValueError("开发正图记录无效")
        file_name = str(row.get("fileName", ""))
        stem = Path(file_name).stem
        if not file_name or file_name in seen_names or stem in seen_stems:
            raise ValueError(f"开发正图存在空文件名或重复stem：{file_name}")
        seen_names.add(file_name)
        seen_stems.add(stem)
        image = positive_root / "images" / "val" / file_name
        label = positive_root / str(row.get("label", ""))
        if not is_within(label, positive_root):
            raise ValueError(f"开发正图标签路径越界：{file_name}")
        require_bound_file(image, str(row.get("imageSha256", "")), "开发正图")
        require_bound_file(label, str(row.get("labelSha256", "")), "开发正图标签")
        if parse_mask_count(label) != int(row.get("maskCount", -1)):
            raise ValueError(f"开发正图mask计数漂移：{file_name}")
        positive_groups.add(str(row.get("sourceGroup", "")))

    legacy = read_json(legacy_materialization_path)
    legacy_records = legacy.get("records")
    if (
        legacy.get("schemaVersion") != 1
        or legacy.get("ok") is not True
        or legacy.get("status") != "PASS"
        or legacy.get("decision") != "approved_train_internal_development_dataset_materialization"
        or not isinstance(legacy_records, list)
        or canonical_sha256(legacy_records) != legacy.get("recordsSha256")
    ):
        raise ValueError("旧开发物化报告合同无效")
    legacy_root = Path(str(legacy.get("outputDir", ""))).resolve()
    negatives = [
        row for row in legacy_records
        if isinstance(row, dict)
        and row.get("developmentSplit") == "val"
        and row.get("role") == "hard-negative"
    ]
    if len(negatives) != 40 or any(int(row.get("maskCount", -1)) != 0 for row in negatives):
        raise ValueError("旧开发评估困难负图必须严格为40图/0 mask")
    train_records = [
        row for row in legacy_records
        if isinstance(row, dict) and row.get("developmentSplit") == "train"
    ]
    train_groups = {str(row.get("sourceGroup", "")) for row in train_records}
    train_image_hashes = {str(row.get("imageSha256", "")) for row in train_records}
    if positive_groups & train_groups:
        raise ValueError("新开发正图与训练折来源组交叠")

    for row in negatives:
        file_name = str(row.get("fileName", ""))
        stem = Path(file_name).stem
        if file_name in seen_names or stem in seen_stems:
            raise ValueError(f"困难负图与正图文件身份冲突：{file_name}")
        seen_names.add(file_name)
        seen_stems.add(stem)
        image = legacy_root / str(row.get("image", ""))
        label = legacy_root / str(row.get("label", ""))
        if not is_within(image, legacy_root) or not is_within(label, legacy_root):
            raise ValueError(f"困难负图路径越界：{file_name}")
        require_bound_file(image, str(row.get("imageSha256", "")), "困难负图")
        require_bound_file(label, str(row.get("labelSha256", "")), "困难负图标签")
        if label.stat().st_size != 0:
            raise ValueError(f"困难负图标签必须为零字节：{file_name}")
    evaluation_hashes = {str(row["imageSha256"]) for row in positive_records + negatives}
    if evaluation_hashes & train_image_hashes:
        raise ValueError("新开发评估集与训练折图片SHA交叠")
    evaluation_groups = positive_groups | {str(row.get("sourceGroup", "")) for row in negatives}
    if evaluation_groups & train_groups:
        raise ValueError("新开发评估集与训练折来源组交叠")
    return positive_index, legacy, positive_records, negatives, train_groups, train_image_hashes


def build_report(
    positive_index_path: Path,
    legacy_materialization_path: Path,
    output_root: Path,
    report_path: Path,
) -> dict[str, Any]:
    if output_root.exists() or report_path.exists():
        raise ValueError("输出目录和报告必须是尚不存在的新路径")
    positive_index, legacy, positives, negatives, train_groups, train_hashes = validate_inputs(
        positive_index_path, legacy_materialization_path
    )
    positive_root = positive_index_path.parent.parent.resolve()
    legacy_root = Path(str(legacy["outputDir"])).resolve()
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    try:
        (staging / "images" / "val").mkdir(parents=True)
        (staging / "labels" / "val").mkdir(parents=True)
        (staging / "dataset.yaml").write_text(
            "path: .\n"
            "train: images/val\n"
            "val: images/val\n"
            "test: images/val\n\n"
            "names:\n  0: nail_texture\n\n"
            "task: segment\n"
            "class_count: 1\n"
            "image_size: 512\n\n"
            "metadata:\n"
            "  dataset_version: development-clean-evaluation/v1\n"
            "  role: read-only-development-evaluation\n"
            "  formal_calibration_test_or_holdout: false\n",
            encoding="utf-8",
        )
        records: list[dict[str, Any]] = []
        for role, rows, source_root in (
            ("train-positive", positives, positive_root),
            ("hard-negative", negatives, legacy_root),
        ):
            for row in rows:
                file_name = str(row["fileName"])
                if role == "train-positive":
                    image_source = source_root / "images" / "val" / file_name
                    label_source = source_root / str(row["label"])
                else:
                    image_source = source_root / str(row["image"])
                    label_source = source_root / str(row["label"])
                image_relative = Path("images") / "val" / file_name
                label_relative = Path("labels") / "val" / Path(file_name).with_suffix(".txt")
                shutil.copy2(image_source, staging / image_relative)
                shutil.copy2(label_source, staging / label_relative)
                records.append(
                    {
                        "fileName": file_name,
                        "role": role,
                        "sourceGroup": str(row["sourceGroup"]),
                        "developmentSplit": "val",
                        "maskCount": int(row["maskCount"]),
                        "image": image_relative.as_posix(),
                        "imageSha256": sha256_file(staging / image_relative),
                        "label": label_relative.as_posix(),
                        "labelSha256": sha256_file(staging / label_relative),
                    }
                )
        records.sort(key=lambda row: (str(row["fileName"]), str(row["role"])))
        inventory, dataset_sha = inventory_tree(staging)
        counts = {
            "trainImages": 0,
            "trainPositiveImages": 0,
            "trainPositiveMasks": 0,
            "trainHardNegativeImages": 0,
            "evaluationImages": len(records),
            "evaluationPositiveImages": sum(row["role"] == "train-positive" for row in records),
            "evaluationPositiveMasks": sum(row["maskCount"] for row in records if row["role"] == "train-positive"),
            "evaluationHardNegativeImages": sum(row["role"] == "hard-negative" for row in records),
            "testImages": 0,
            "sourceGroupOverlap": 0,
            "imageSha256Overlap": 0,
        }
        if counts["evaluationImages"] != 98 or counts["evaluationPositiveImages"] != 58 or counts["evaluationPositiveMasks"] != 354 or counts["evaluationHardNegativeImages"] != 40:
            raise ValueError(f"新开发评估集计数漂移：{counts}")
        report = {
            "schemaVersion": 2,
            "ok": True,
            "status": "PASS",
            "decision": "approved_read_only_clean_development_evaluation",
            "trainingUse": "prohibited",
            "candidateTrainingEligible": False,
            "formalCalibrationTestOrHoldoutEligible": False,
            "inputs": {
                "positiveTruthIndex": {
                    "path": str(positive_index_path),
                    "sha256": sha256_file(positive_index_path),
                    "recordsSha256": positive_index["recordsSha256"],
                },
                "legacyDevelopmentMaterialization": {
                    "path": str(legacy_materialization_path),
                    "sha256": sha256_file(legacy_materialization_path),
                    "recordsSha256": legacy["recordsSha256"],
                    "negativeRecordsOnly": True,
                },
            },
            "outputDir": str(output_root),
            "datasetYaml": {"path": str(output_root / "dataset.yaml"), "sha256": sha256_file(staging / "dataset.yaml")},
            "counts": counts,
            "sourceGroups": {
                "training": len(train_groups),
                "evaluation": len({row["sourceGroup"] for row in records}),
                "overlap": [],
            },
            "imageSha256": {
                "training": len(train_hashes),
                "evaluation": len({row["imageSha256"] for row in records}),
                "overlap": [],
            },
            "datasetFilesSha256": dataset_sha,
            "datasetFileCount": len(inventory),
            "recordsSha256": canonical_sha256(records),
            "records": records,
            "invariants": {
                "positiveTruthV2Only": True,
                "legacyEvaluationPositivesExcluded": True,
                "legacyHardNegativeSetUnchanged": True,
                "testAndHoldoutRecordsRead": False,
                "sourceGroupMutuallyExclusiveFromTrain": True,
                "imageSha256MutuallyExclusiveFromTrain": True,
                "sourceFilesHashMatchedBeforeAndAfterCopy": True,
                "zeroByteHardNegativeLabelsPreserved": True,
            },
            "errors": [],
        }
        os.replace(staging, output_root)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_report(path: Path) -> dict[str, Any]:
    report = read_json(path)
    if (
        report.get("schemaVersion") != 2
        or report.get("ok") is not True
        or report.get("status") != "PASS"
        or report.get("decision") != "approved_read_only_clean_development_evaluation"
        or report.get("trainingUse") != "prohibited"
        or report.get("candidateTrainingEligible") is not False
        or report.get("formalCalibrationTestOrHoldoutEligible") is not False
        or report.get("errors") != []
    ):
        raise ValueError("新开发评估集报告顶层合同无效")
    inputs = report.get("inputs", {})
    positive_binding = inputs.get("positiveTruthIndex", {})
    legacy_binding = inputs.get("legacyDevelopmentMaterialization", {})
    positive_path = Path(str(positive_binding.get("path", ""))).resolve()
    legacy_path = Path(str(legacy_binding.get("path", ""))).resolve()
    require_bound_file(positive_path, str(positive_binding.get("sha256", "")), "正图真值索引")
    require_bound_file(legacy_path, str(legacy_binding.get("sha256", "")), "旧开发物化报告")
    _, _, positives, negatives, train_groups, train_hashes = validate_inputs(positive_path, legacy_path)
    output_root = Path(str(report.get("outputDir", ""))).resolve()
    if not output_root.is_dir():
        raise ValueError("新开发评估集目录缺失")
    inventory, inventory_sha = inventory_tree(output_root)
    if inventory_sha != report.get("datasetFilesSha256") or len(inventory) != report.get("datasetFileCount"):
        raise ValueError("新开发评估集文件树漂移")
    records = report.get("records")
    if not isinstance(records, list) or canonical_sha256(records) != report.get("recordsSha256"):
        raise ValueError("新开发评估集records漂移")
    expected_names = {str(row["fileName"]) for row in positives + negatives}
    if {str(row.get("fileName", "")) for row in records} != expected_names or len(records) != 98:
        raise ValueError("新开发评估集文件身份覆盖漂移")
    evaluation_groups: set[str] = set()
    evaluation_hashes: set[str] = set()
    for row in records:
        image = output_root / str(row.get("image", ""))
        label = output_root / str(row.get("label", ""))
        if not is_within(image, output_root) or not is_within(label, output_root):
            raise ValueError("新开发评估集记录路径越界")
        require_bound_file(image, str(row.get("imageSha256", "")), "评估图片")
        require_bound_file(label, str(row.get("labelSha256", "")), "评估标签")
        if parse_mask_count(label) != int(row.get("maskCount", -1)):
            raise ValueError(f"评估标签mask计数漂移：{row.get('fileName')}")
        evaluation_groups.add(str(row.get("sourceGroup", "")))
        evaluation_hashes.add(str(row.get("imageSha256", "")))
    if evaluation_groups & train_groups or evaluation_hashes & train_hashes:
        raise ValueError("新开发评估集与训练折隔离漂移")
    counts = report.get("counts", {})
    if counts.get("evaluationImages") != 98 or counts.get("evaluationPositiveImages") != 58 or counts.get("evaluationPositiveMasks") != 354 or counts.get("evaluationHardNegativeImages") != 40:
        raise ValueError("新开发评估集计数合同漂移")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-truth-index", type=Path)
    parser.add_argument("--legacy-materialization-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        if any((args.positive_truth_index, args.legacy_materialization_report, args.output_dir, args.report)):
            parser.error("--verify-report不能与物化参数并用")
        report = verify_report(args.verify_report.resolve())
    else:
        if not all((args.positive_truth_index, args.legacy_materialization_report, args.output_dir, args.report)):
            parser.error("物化参数不完整")
        report = build_report(
            args.positive_truth_index.resolve(),
            args.legacy_materialization_report.resolve(),
            args.output_dir.resolve(),
            args.report.resolve(),
        )
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
