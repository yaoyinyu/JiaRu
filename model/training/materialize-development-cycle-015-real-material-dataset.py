#!/usr/bin/env python3
"""在锁定开发数据集（cycle012 v1）上只追加循环015的11张真实素材图52 mask，并生成可重放物化报告。

单变量短训实验专用（预注册偏差：148图门未达，用户明确指示"继续优化模型，提升模型质量"）。
基础 = 2026_9_10_cycle012_development_dataset_v1（datasetFilesSha256 34fe0a85…41edf）。
新增真值来源 = development-evaluation-truth-index-v5.json 中 11 条 cycle015_real_* 唯一真值。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

REAL_PREFIX = "cycle015_real"
EXPECTED_REAL_IMAGES = 11
EXPECTED_REAL_MASKS = 52
FOLD_NAME = "cycle015-real-material-positive"
DATASET_VERSION_OLD = "development-cycle-012-targeted-positive/v1"
DATASET_VERSION_NEW = "development-cycle-015-real-material/v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def inventory_tree(root: Path) -> tuple[list[dict[str, str]], str]:
    items = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    return items, canonical_sha256(items)


def label_text(annotation: dict[str, Any]) -> str:
    image = annotation.get("image") or {}
    width, height = image.get("width"), image.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError("annotation图片尺寸无效")
    lines: list[str] = []
    for item in annotation.get("annotations") or []:
        points = item.get("polygon") if isinstance(item, dict) else None
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError("annotation缺少polygon")
        values = ["0"]
        for point in points:
            x, y = float(point["x"]), float(point["y"])
            values.extend((f"{x / width:.8f}", f"{y / height:.8f}"))
        lines.append(" ".join(values))
    return "\n".join(lines) + "\n"


def load_real_truths(truth_path: Path) -> list[dict[str, Any]]:
    truth = read_object(truth_path, "循环015开发评估唯一真值索引v5")
    if (
        truth.get("ok") is not True
        or truth.get("decision") != "approved_unique_development_evaluation_truth_index"
        or truth.get("summary", {}).get("conflictingImageCount") != 0
    ):
        raise ValueError("循环015真值索引未通过唯一性批准门")
    truths = [item for item in truth.get("canonicalTruths") or [] if str(item.get("fileName", "")).startswith(REAL_PREFIX)]
    if len(truths) != EXPECTED_REAL_IMAGES:
        raise ValueError(f"真实素材条目数不符：期望{EXPECTED_REAL_IMAGES}，实际{len(truths)}")
    resolved: list[dict[str, Any]] = []
    for entry in truths:
        report = read_object(Path(entry["reportPath"]).resolve(), f"逐图真值报告{entry['fileName']}")
        if report.get("ok") is not True or report.get("decision") != "approved_as_development_evaluation_truth_candidate_pending_dataset_materialization":
            raise ValueError(f"逐图报告未批准：{entry['fileName']}")
        if sha256_file(Path(entry["reportPath"])) != entry.get("reportSha256"):
            raise ValueError(f"逐图报告哈希漂移：{entry['fileName']}")
        item = report.get("item") or {}
        inputs = report.get("inputs") or {}
        image_path = Path(inputs["image"]["path"]).resolve()
        annotation_path = Path(inputs["annotation"]["path"]).resolve()
        if not image_path.is_file() or not annotation_path.is_file():
            raise ValueError(f"真值文件缺失：{entry['fileName']}")
        if sha256_file(image_path) != entry.get("imageSha256") or item.get("sha256") != entry.get("imageSha256"):
            raise ValueError(f"图像哈希漂移：{entry['fileName']}")
        if sha256_file(annotation_path) != inputs["annotation"]["sha256"]:
            raise ValueError(f"标注哈希漂移：{entry['fileName']}")
        annotation = read_object(annotation_path, f"标注{entry['fileName']}")
        mask_count = len(annotation.get("annotations") or [])
        if mask_count != entry.get("completeMaskCount") or item.get("completeMaskCount") != entry.get("completeMaskCount"):
            raise ValueError(f"mask数不一致：{entry['fileName']}")
        if item.get("invalidPolygonCount") != 0 or item.get("overlapPairCount") != 0:
            raise ValueError(f"多边形拓扑或交叠未清零：{entry['fileName']}")
        resolved.append({
            "fileName": entry["fileName"],
            "imageSha256": entry["imageSha256"],
            "sourceGroup": entry["sourceGroup"],
            "maskCount": mask_count,
            "imagePath": str(image_path),
            "annotationPath": str(annotation_path),
            "reportPath": str(Path(entry["reportPath"]).resolve()),
        })
    total = sum(item["maskCount"] for item in resolved)
    if total != EXPECTED_REAL_MASKS:
        raise ValueError(f"真实素材mask总数不符：期望{EXPECTED_REAL_MASKS}，实际{total}")
    if len({item["imageSha256"] for item in resolved}) != EXPECTED_REAL_IMAGES or len({item["sourceGroup"] for item in resolved}) != EXPECTED_REAL_IMAGES:
        raise ValueError("循环015真实素材身份不唯一")
    return resolved


def build_report(base_path: Path, truth_path: Path, output_dir: Path, *, materialize: bool) -> dict[str, Any]:
    base = read_object(base_path, "基础物化报告(cycle012)")
    if (
        base.get("ok") is not True
        or base.get("decision") != "development_cycle_012_dataset_materialized_for_single_short_experiment"
        or base.get("trainingUse") != "development-experiment-only"
    ):
        raise ValueError("基础开发数据集未获实验物化批准")
    base_root = Path(str(base.get("outputDir") or "")).resolve()
    if not base_root.is_dir():
        raise ValueError("基础开发数据集目录不存在")
    base_inventory, base_inventory_sha = inventory_tree(base_root)
    if base_inventory_sha != base.get("datasetFilesSha256") or len(base_inventory) != base.get("datasetFileCount"):
        raise ValueError("基础开发数据集文件树漂移")
    base_records = base.get("records")
    if not isinstance(base_records, list):
        raise ValueError("基础记录缺失")
    base_names = {str(item.get("fileName", "")).casefold() for item in base_records}
    base_hashes = {str(item.get("imageSha256", "")) for item in base_records}
    base_groups = {str(item.get("sourceGroup", "")) for item in base_records}
    truths = load_real_truths(truth_path)
    new_names = [item["fileName"] for item in truths]
    if any(name.casefold() in base_names for name in new_names):
        raise ValueError("循环015新增文件名与基础数据集交叠")
    if {item["imageSha256"] for item in truths} & base_hashes:
        raise ValueError("循环015新增图像哈希与基础数据集交叠")
    if {item["sourceGroup"] for item in truths} & base_groups:
        raise ValueError("循环015新增来源组与基础数据集交叠")
    for item in truths:
        if sha256_file(Path(item["imagePath"])) != item["imageSha256"] or sha256_file(Path(item["annotationPath"])) != read_object(Path(item["reportPath"]), "r").get("inputs", {}).get("annotation", {}).get("sha256"):
            raise ValueError(f"新增真值哈希漂移：{item['fileName']}")

    if not materialize:
        if not output_dir.is_dir():
            raise ValueError("待验证物化目录不存在")
        inventory, inventory_sha = inventory_tree(output_dir)
        report_records = base_records + [
            {
                "fileName": item["fileName"], "role": "train-positive", "sourceGroup": item["sourceGroup"],
                "fold": FOLD_NAME, "developmentSplit": "train", "maskCount": item["maskCount"],
                "image": f"images/train/{item['fileName']}", "imageSha256": sha256_file(Path(item["imagePath"])),
                "label": f"labels/train/{Path(item['fileName']).stem}.txt",
                "labelSha256": sha256_file(output_dir / "labels" / "train" / f"{Path(item['fileName']).stem}.txt"),
            }
            for item in truths
        ]
    else:
        if output_dir.exists():
            raise ValueError(f"输出目录已存在，禁止覆盖：{output_dir}")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = output_dir.parent / f".{output_dir.name}.staging-{os.getpid()}"
        if staging.exists():
            raise ValueError(f"临时目录已存在：{staging}")
        try:
            shutil.copytree(base_root, staging)
            report_records = list(base_records)
            for item in truths:
                name = item["fileName"]
                image_source = Path(item["imagePath"])
                annotation_source = Path(item["annotationPath"])
                image_target = staging / "images" / "train" / name
                label_target = staging / "labels" / "train" / f"{Path(name).stem}.txt"
                if image_target.exists() or label_target.exists():
                    raise ValueError(f"新增目标已存在：{name}")
                shutil.copy2(image_source, image_target)
                annotation = read_object(annotation_source, f"新增标注{name}")
                label_target.write_text(label_text(annotation), encoding="utf-8")
                report_records.append({
                    "fileName": name, "role": "train-positive", "sourceGroup": item["sourceGroup"],
                    "fold": FOLD_NAME, "developmentSplit": "train", "maskCount": item["maskCount"],
                    "image": f"images/train/{name}", "imageSha256": sha256_file(image_target),
                    "label": f"labels/train/{label_target.name}", "labelSha256": sha256_file(label_target),
                })
            dataset_yaml = staging / "dataset.yaml"
            text = dataset_yaml.read_text(encoding="utf-8")
            if DATASET_VERSION_OLD not in text:
                raise ValueError("dataset.yaml 版本锚点缺失")
            dataset_yaml.write_text(text.replace(DATASET_VERSION_OLD, DATASET_VERSION_NEW), encoding="utf-8")
            inventory, inventory_sha = inventory_tree(staging)
            os.replace(staging, output_dir)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    report_records.sort(key=lambda item: (str(item["developmentSplit"]), str(item["role"]), str(item["fileName"])))
    base_counts = base["counts"]
    counts = dict(base_counts)
    counts["trainImages"] = int(base_counts["trainImages"]) + EXPECTED_REAL_IMAGES
    counts["trainPositiveImages"] = int(base_counts["trainPositiveImages"]) + EXPECTED_REAL_IMAGES
    counts["trainPositiveMasks"] = int(base_counts["trainPositiveMasks"]) + EXPECTED_REAL_MASKS
    counts["sourceGroupOverlap"] = 0
    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": "development_cycle_015_real_material_dataset_materialized_for_single_short_experiment",
        "trainingUse": "development-experiment-only",
        "candidateTrainingEligible": False,
        "formalCalibrationTestOrHoldoutEligible": False,
        "inputs": {
            "baseMaterialization": binding(base_path),
            "realMaterialTruthIndexV5": binding(truth_path),
            "gateDeviationPreRegistered": {
                "old": "clean148数据集门（≥148图）方可启动短训",
                "new": "+11真实素材图/+52 mask在cycle012基础数据集上单变量短训",
                "why": "用户明确指示继续优化模型提升质量并加速推进；148门未达，仅作诊断性单变量实验，不作正式候选/发布依据",
                "evidence": "development-evaluation-truth-index-v5.json (54图/317mask, sha256 5bb70b56…2eed)；geometry-audit-v6 pass:52/suspect:0",
            },
        },
        "outputDir": str(output_dir),
        "datasetYaml": binding(output_dir / "dataset.yaml"),
        "counts": counts,
        "addedCounts": {"trainPositiveImages": EXPECTED_REAL_IMAGES, "trainPositiveMasks": EXPECTED_REAL_MASKS, "sourceGroups": EXPECTED_REAL_IMAGES},
        "datasetFilesSha256": inventory_sha,
        "datasetFileCount": len(inventory),
        "recordsSha256": canonical_sha256(report_records),
        "records": report_records,
        "invariants": {
            "baseDatasetReplayedBeforeCopy": True,
            "baseEvaluationBytesPreserved": True,
            "onlyCycle015RealTruthAddedToTrain": True,
            "sourceGroupOverlap": 0,
            "testImages": 0,
            "formalDataRolesUnchanged": True,
            "singleShortExperimentOnly": True,
        },
        "errors": [],
    }


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告输出已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def verify_report(report_path: Path) -> dict[str, Any]:
    """重放并返回循环015真实素材物化报告，供训练入口绑定同一文件树身份。"""

    report_path = report_path.resolve()
    existing = read_object(report_path, "待重放报告")
    inputs = existing.get("inputs") or {}
    replay = build_report(
        Path(inputs["baseMaterialization"]["path"]).resolve(),
        Path(inputs["realMaterialTruthIndexV5"]["path"]).resolve(),
        Path(existing["outputDir"]).resolve(),
        materialize=False,
    )
    if replay != existing:
        raise ValueError("物化报告与当前磁盘重放结果不一致")
    return replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-materialization")
    parser.add_argument("--real-truth-index")
    parser.add_argument("--output-dir")
    parser.add_argument("--report")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        verify_report(report_path)
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0
    required = [args.base_materialization, args.real_truth_index, args.output_dir, args.report]
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    report = build_report(
        Path(args.base_materialization).resolve(),
        Path(args.real_truth_index).resolve(),
        Path(args.output_dir).resolve(),
        materialize=True,
    )
    report_path = Path(args.report).resolve()
    write_atomic(report_path, report)
    print(json.dumps({"ok": True, "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
