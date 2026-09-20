#!/usr/bin/env python3
"""在循环015真实素材v1开发数据集上只追加batch2的10张图38 mask，并生成可重放物化报告。

单变量短训实验专用（用户2026-09-19三条裁决：甲面级过滤、裁断输出通道、免审直接训练）。
基础 = 2026_9_19_cycle015_real_material_development_dataset_v1（datasetFilesSha256 90a1bf08…da88b）。
新增真值来源 = 审核工作区v4 prelabels-filtered-v2（YOLO cycle012 best 预标注，conf≥0.6或白名单 + bbox边距≥8px 过滤）。
偏差声明：batch2 真值为模型预标注多边形（用户明确裁决跳过逐图机器审查直接训练），
与 batch1 的人工逐甲终审真值在证据等级上不同，仅在诊断性开发实验中使用。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_REAL_IMAGES = 10
EXPECTED_REAL_MASKS = 38
FOLD_NAME = "cycle015-real-material-batch2-positive"
DATASET_VERSION_OLD = "development-cycle-015-real-material/v1"
DATASET_VERSION_NEW = "development-cycle-015-real-material-batch2/v1"
FROZEN_IMAGE_DIR = Path(r"E:/AI Project/Codex/JiaRu_image/真实素材/2026_9_19_cycle015_real_material_v2")
WORKSPACE = Path(r"E:/AI Project/Codex/JiaRu_image/审核工作区/2026_9_19_cycle015_real_material_annotation_workspace_v4")
PRELABEL_REPORT = WORKSPACE / "prelabel-report-v2.json"
FILTERED_DIR = WORKSPACE / "prelabels-filtered-v2"
FILTER_LOG_V1 = WORKSPACE / "prelabel-filter-log-v1.json"
FILTER_LOG_V2 = WORKSPACE / "prelabel-filter-log-v2.json"
V1_MODULE_PATH = Path(r"E:/AI Project/Codex/JiaRu/model/training/materialize-development-cycle-015-real-material-dataset.py")


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
            if not (0.0 <= x <= width and 0.0 <= y <= height):
                raise ValueError("polygon坐标越界")
            values.extend((f"{x / width:.8f}", f"{y / height:.8f}"))
        lines.append(" ".join(values))
    return "\n".join(lines) + "\n"


def load_batch2_truths() -> list[dict[str, Any]]:
    report = read_object(PRELABEL_REPORT, "工作区v4预标注报告v2")
    if report.get("ok") is not True or report.get("decision") != "candidate_only_not_training_truth":
        raise ValueError("预标注报告v2状态无效")
    if int(report.get("imageCount") or 0) != EXPECTED_REAL_IMAGES:
        raise ValueError("预标注报告v2图片数不符")
    log_v2 = read_object(FILTER_LOG_V2, "过滤日志v2")
    if int(log_v2.get("masks") or 0) != EXPECTED_REAL_MASKS:
        raise ValueError("过滤日志v2 mask总数不符")
    log_v1 = read_object(FILTER_LOG_V1, "过滤日志v1")
    kept_by_file = {str(item["fileName"]): len(item["kept"]) for item in log_v1.get("items") or []}
    restored = {str(item["fileName"]) for item in log_v2.get("restored") or []}
    truths: list[dict[str, Any]] = []
    for entry in report.get("items") or []:
        name = str(entry["fileName"])
        image_path = FROZEN_IMAGE_DIR / name
        annotation_path = FILTERED_DIR / f"{Path(name).stem}.json"
        if not image_path.is_file() or not annotation_path.is_file():
            raise ValueError(f"真值文件缺失：{name}")
        if sha256_file(image_path) != entry.get("sha256"):
            raise ValueError(f"图像哈希漂移：{name}")
        expected_masks = kept_by_file.get(name, 0) + (1 if name in restored else 0)
        annotation = read_object(annotation_path, f"标注{name}")
        mask_count = len(annotation.get("annotations") or [])
        if mask_count != expected_masks:
            raise ValueError(f"mask数与过滤账目不符：{name} 期望{expected_masks} 实际{mask_count}")
        image_meta = annotation.get("image") or {}
        if image_meta.get("fileName") != name or image_meta.get("sourceGroup") != entry.get("sourceGroup"):
            raise ValueError(f"标注身份不一致：{name}")
        truths.append({
            "fileName": name,
            "imageSha256": entry["sha256"],
            "sourceGroup": entry["sourceGroup"],
            "maskCount": mask_count,
            "imagePath": str(image_path),
            "annotationPath": str(annotation_path),
        })
    if len(truths) != EXPECTED_REAL_IMAGES:
        raise ValueError(f"batch2条目数不符：期望{EXPECTED_REAL_IMAGES}，实际{len(truths)}")
    total = sum(item["maskCount"] for item in truths)
    if total != EXPECTED_REAL_MASKS:
        raise ValueError(f"batch2 mask总数不符：期望{EXPECTED_REAL_MASKS}，实际{total}")
    if len({item["imageSha256"] for item in truths}) != EXPECTED_REAL_IMAGES or len({item["sourceGroup"] for item in truths}) != EXPECTED_REAL_IMAGES:
        raise ValueError("batch2身份不唯一")
    return truths


def load_v1_materializer():
    spec = importlib.util.spec_from_file_location("materialize_development_cycle_015_real_material_dataset_for_training", V1_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load cycle015 v1 real-material materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_report(base_path: Path, output_dir: Path, *, materialize: bool) -> dict[str, Any]:
    base = read_object(base_path, "基础物化报告(cycle015 v1)")
    if (
        base.get("ok") is not True
        or base.get("decision") != "development_cycle_015_real_material_dataset_materialized_for_single_short_experiment"
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
    truths = load_batch2_truths()
    new_names = [item["fileName"] for item in truths]
    if any(name.casefold() in base_names for name in new_names):
        raise ValueError("batch2新增文件名与基础数据集交叠")
    if {item["imageSha256"] for item in truths} & base_hashes:
        raise ValueError("batch2新增图像哈希与基础数据集交叠")
    if {item["sourceGroup"] for item in truths} & base_groups:
        raise ValueError("batch2新增来源组与基础数据集交叠")

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
        "decision": "development_cycle_015_real_material_batch2_dataset_materialized_for_single_short_experiment",
        "trainingUse": "development-experiment-only",
        "candidateTrainingEligible": False,
        "formalCalibrationTestOrHoldoutEligible": False,
        "inputs": {
            "baseMaterialization": binding(base_path),
            "prelabelReportV2": binding(PRELABEL_REPORT),
            "filterLogV1": binding(FILTER_LOG_V1),
            "filterLogV2": binding(FILTER_LOG_V2),
            "frozenImageDir": str(FROZEN_IMAGE_DIR),
            "userRulings2026_09_19": [
                "甲面级过滤：不追求整图无遮挡无失焦，只要图中有完整合适甲面即可使用，遮挡/失焦甲面退出分母",
                "裁断输出通道：受遮挡/失焦影响的素材不整张排除，可用区域按原分辨率裁断输出到 真实素材/美甲图片素材/处理，衍生组与原图共享来源",
                "免审直接训练：本批素材为购入授权美甲素材，用户裁决跳过逐图机器审查直接训练，最终目的是从用户图中提取美甲纹理",
            ],
            "truthProvenanceDeviation": {
                "old": "batch1：SAM多点提示+人工逐甲原分辨率终审+真值唯一索引v5批准",
                "new": "batch2：YOLO(cycle012 best)预标注多边形直接作为训练真值，conf≥0.6或白名单 + bbox边距≥8px过滤，0013 n4(conf 0.575)经原分辨率复核恢复",
                "why": "用户明确指示『算了不每张做机器审查了，直接训练』『不要浪费时间直接进入训练』；诊断性实验可接受证据等级降低",
                "scope": "仅限本次诊断性短训；正式候选/发布真值仍必须走完整审查链",
            },
            "gateDeviationPreRegistered": {
                "old": "clean148数据集门（≥148图）方可启动短训",
                "new": "+10 batch2真实素材图/+38 mask在cycle015 v1数据集上单变量短训（累计真值64/90）",
                "why": "用户指示直接进入训练加速供给验证；仅作诊断性单变量实验，不作正式候选/发布依据",
                "evidence": "prelabel-report-v2.json（10图49候选，哈希绑定）；prelabel-filter-log-v1/v2.json（37+1恢复=38 mask）",
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
            "onlyCycle015Batch2RealTruthAddedToTrain": True,
            "sourceGroupOverlap": 0,
            "testImages": 0,
            "formalDataRolesUnchanged": True,
            "singleShortExperimentOnly": True,
            "prelabelTruthDeviationDocumented": True,
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
    """重放batch2物化报告（含v1基底报告强校验），供训练入口绑定同一文件树身份。"""

    report_path = report_path.resolve()
    existing = read_object(report_path, "待重放报告")
    inputs = existing.get("inputs") or {}
    v1 = load_v1_materializer()
    v1.verify_report(Path(inputs["baseMaterialization"]["path"]).resolve())
    replay = build_report(
        Path(inputs["baseMaterialization"]["path"]).resolve(),
        Path(existing["outputDir"]).resolve(),
        materialize=False,
    )
    if replay != existing:
        raise ValueError("物化报告与当前磁盘重放结果不一致")
    return replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-materialization")
    parser.add_argument("--output-dir")
    parser.add_argument("--report")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        verify_report(report_path)
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0
    required = [args.base_materialization, args.output_dir, args.report]
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    report = build_report(
        Path(args.base_materialization).resolve(),
        Path(args.output_dir).resolve(),
        materialize=True,
    )
    report_path = Path(args.report).resolve()
    write_atomic(report_path, report)
    print(json.dumps({"ok": True, "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
