#!/usr/bin/env python3
"""在锁定开发数据集上只追加循环012的13图65 mask，并生成可重放物化报告。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


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


def build_report(base_path: Path, truth_path: Path, output_dir: Path, *, materialize: bool) -> dict[str, Any]:
    base = read_object(base_path, "基础物化报告")
    truth = read_object(truth_path, "循环012正样本真值审计")
    if (
        base.get("ok") is not True
        or base.get("decision") != "approved_train_internal_development_dataset_materialization"
        or base.get("trainingUse") != "development-experiment-only"
    ):
        raise ValueError("基础开发数据集未获实验物化批准")
    if (
        truth.get("ok") is not True
        or truth.get("decision") != "development_cycle_012_positive_truth_ready_for_materialization"
        or truth.get("trainingUse") != "prohibited-until-materialization-audit"
        or truth.get("counts") != {"images": 13, "sourceGroups": 13, "masks": 65, "invalidPolygons": 0, "pairwiseOverlaps": 0}
    ):
        raise ValueError("循环012正样本真值未通过物化前门")
    base_root = Path(str(base.get("outputDir") or "")).resolve()
    if not base_root.is_dir():
        raise ValueError("基础开发数据集目录不存在")
    base_inventory, base_inventory_sha = inventory_tree(base_root)
    if base_inventory_sha != base.get("datasetFilesSha256") or len(base_inventory) != base.get("datasetFileCount"):
        raise ValueError("基础开发数据集文件树漂移")
    base_records = base.get("records")
    truths = truth.get("canonicalTruths")
    if not isinstance(base_records, list) or not isinstance(truths, list) or len(truths) != 13:
        raise ValueError("基础记录或新增真值缺失")
    base_names = {str(item.get("fileName", "")).casefold() for item in base_records}
    base_hashes = {str(item.get("imageSha256", "")) for item in base_records}
    base_groups = {str(item.get("sourceGroup", "")) for item in base_records}
    new_names = [str(item.get("fileName") or "") for item in truths]
    new_hashes = [str(item.get("imageSha256") or "") for item in truths]
    new_groups = [str(item.get("sourceGroup") or "") for item in truths]
    if len(set(name.casefold() for name in new_names)) != 13 or len(set(new_hashes)) != 13 or len(set(new_groups)) != 13:
        raise ValueError("循环012新增身份不唯一")
    if any(name.casefold() in base_names for name in new_names) or set(new_hashes) & base_hashes or set(new_groups) & base_groups:
        raise ValueError("循环012新增项与基础数据集身份交叠")
    for item in truths:
        image_path = Path(str(item.get("imagePath") or "")).resolve()
        annotation_path = Path(str(item.get("annotationPath") or "")).resolve()
        if sha256_file(image_path) != item.get("imageSha256") or sha256_file(annotation_path) != item.get("annotationSha256"):
            raise ValueError(f"新增真值哈希漂移：{item.get('fileName')}")

    if not materialize:
        if not output_dir.is_dir():
            raise ValueError("待验证物化目录不存在")
        inventory, inventory_sha = inventory_tree(output_dir)
        report_records = base_records + [
            {
                "fileName": item["fileName"], "role": "train-positive", "sourceGroup": item["sourceGroup"],
                "fold": "cycle012-targeted-positive", "developmentSplit": "train", "maskCount": item["maskCount"],
                "image": f"images/train/{item['fileName']}", "imageSha256": item["imageSha256"],
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
                    "fold": "cycle012-targeted-positive", "developmentSplit": "train", "maskCount": item["maskCount"],
                    "image": f"images/train/{name}", "imageSha256": sha256_file(image_target),
                    "label": f"labels/train/{label_target.name}", "labelSha256": sha256_file(label_target),
                })
            dataset_yaml = staging / "dataset.yaml"
            text = dataset_yaml.read_text(encoding="utf-8").replace(
                "dataset_version: train-source-group-development/v1",
                "dataset_version: development-cycle-012-targeted-positive/v1",
            )
            dataset_yaml.write_text(text, encoding="utf-8")
            inventory, inventory_sha = inventory_tree(staging)
            os.replace(staging, output_dir)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    report_records.sort(key=lambda item: (str(item["developmentSplit"]), str(item["role"]), str(item["fileName"])))
    base_counts = base["counts"]
    counts = dict(base_counts)
    counts["trainImages"] = int(base_counts["trainImages"]) + 13
    counts["trainPositiveImages"] = int(base_counts["trainPositiveImages"]) + 13
    counts["trainPositiveMasks"] = int(base_counts["trainPositiveMasks"]) + 65
    counts["sourceGroupOverlap"] = 0
    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": "development_cycle_012_dataset_materialized_for_single_short_experiment",
        "trainingUse": "development-experiment-only",
        "candidateTrainingEligible": False,
        "formalCalibrationTestOrHoldoutEligible": False,
        "inputs": {"baseMaterialization": binding(base_path), "positiveTruthAudit": binding(truth_path)},
        "outputDir": str(output_dir),
        "datasetYaml": binding(output_dir / "dataset.yaml"),
        "counts": counts,
        "addedCounts": {"trainPositiveImages": 13, "trainPositiveMasks": 65, "sourceGroups": 13},
        "datasetFilesSha256": inventory_sha,
        "datasetFileCount": len(inventory),
        "recordsSha256": canonical_sha256(report_records),
        "records": report_records,
        "invariants": {
            "baseDatasetReplayedBeforeCopy": True,
            "baseEvaluationBytesPreserved": True,
            "onlyCycle012TruthAddedToTrain": True,
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
    """重放并返回循环012物化报告，供训练入口绑定同一文件树身份。"""

    report_path = report_path.resolve()
    existing = read_object(report_path, "待重放报告")
    inputs = existing.get("inputs") or {}
    replay = build_report(
        Path(inputs["baseMaterialization"]["path"]).resolve(),
        Path(inputs["positiveTruthAudit"]["path"]).resolve(),
        Path(existing["outputDir"]).resolve(),
        materialize=False,
    )
    if replay != existing:
        raise ValueError("物化报告与当前磁盘重放结果不一致")
    return replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-materialization")
    parser.add_argument("--positive-truth-audit")
    parser.add_argument("--output-dir")
    parser.add_argument("--report")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        verify_report(report_path)
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0
    required = [args.base_materialization, args.positive_truth_audit, args.output_dir, args.report]
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    report = build_report(
        Path(args.base_materialization).resolve(),
        Path(args.positive_truth_audit).resolve(),
        Path(args.output_dir).resolve(),
        materialize=True,
    )
    report_path = Path(args.report).resolve()
    write_atomic(report_path, report)
    print(json.dumps({"ok": True, "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
