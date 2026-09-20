#!/usr/bin/env python3
"""从 cycle012 训练正样本物化 sourceGroup 隔离的逐甲 ROI 数据集。"""

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

import cv2
import numpy as np
from PIL import Image


SCHEMA_VERSION = 1
SPLIT_SALT = "nail-texture-development-cycle-016-roi-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_guards() -> tuple[Any, Any]:
    path = Path(__file__).resolve().with_name("train-yolo-seg.py")
    spec = importlib.util.spec_from_file_location("nail_texture_train_yolo_seg", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载只读图片守卫")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.install_read_only_ultralytics_image_check, module.remove_ultralytics_label_caches


def parse_polygons(path: Path) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.strip().split()
        if not tokens:
            continue
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法标签：{path}:{line_number}")
        result.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float32).reshape(-1, 2))
    return result


def crop_box(polygon: np.ndarray, width: int, height: int, scale: float) -> tuple[int, int, int, int]:
    pixels = polygon * np.asarray([width, height], dtype=np.float32)
    minimum = pixels.min(axis=0)
    maximum = pixels.max(axis=0)
    center = (minimum + maximum) / 2
    side = max(float(maximum[0] - minimum[0]), float(maximum[1] - minimum[1])) * scale
    side = min(max(side, 8.0), float(min(width, height)))
    x1 = int(round(center[0] - side / 2))
    y1 = int(round(center[1] - side / 2))
    x1 = min(max(0, x1), max(0, width - int(round(side))))
    y1 = min(max(0, y1), max(0, height - int(round(side))))
    x2 = min(width, x1 + int(round(side)))
    y2 = min(height, y1 + int(round(side)))
    return x1, y1, x2, y2


def choose_split(source_group: str) -> str:
    value = hashlib.sha256(f"{SPLIT_SALT}:{source_group}".encode("utf-8")).digest()[0]
    return "val" if value < 51 else "train"


def aggregate_files(root: Path) -> tuple[str, int]:
    entries = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.name == "materialization-report.json":
            continue
        entries.append(f"{path.relative_to(root).as_posix()}\t{sha256_file(path)}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest(), len(entries)


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source_report = Path(report["inputs"]["cycle012MaterializationReport"]["path"])
    if sha256_file(source_report) != report["inputs"]["cycle012MaterializationReport"]["sha256"]:
        raise ValueError("cycle012物化报告哈希不匹配")
    output = Path(report["outputDir"])
    aggregate, count = aggregate_files(output)
    if aggregate != report["datasetFilesSha256"] or count != report["datasetFileCount"]:
        raise ValueError("ROI数据集文件聚合哈希不匹配")
    train_groups = set(report["sourceGroups"]["train"])
    val_groups = set(report["sourceGroups"]["val"])
    if train_groups & val_groups:
        raise ValueError("train/val sourceGroup存在交叠")
    return {"ok": True, "decision": "verified", "counts": report["counts"], "datasetFilesSha256": aggregate}


def materialize(source_report_path: Path, output: Path, crop_scale: float, size: int) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output}")
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    source_root = Path(source_report["outputDir"])
    records = [
        row
        for row in source_report["records"]
        if row["developmentSplit"] == "train" and int(row["maskCount"]) > 0
    ]
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    result_records: list[dict[str, Any]] = []
    try:
        for row in records:
            source_group = str(row["sourceGroup"])
            split = choose_split(source_group)
            image_path = source_root / row["image"]
            label_path = source_root / row["label"]
            with Image.open(image_path) as source:
                image = np.asarray(source.convert("RGB"))
            height, width = image.shape[:2]
            source_polygons = parse_polygons(label_path)
            if len(source_polygons) != int(row["maskCount"]):
                raise ValueError(f"maskCount不一致：{row['fileName']}")
            for truth_index, polygon in enumerate(source_polygons, start=1):
                x1, y1, x2, y2 = crop_box(polygon, width, height, crop_scale)
                crop = image[y1:y2, x1:x2]
                polygon_pixels = polygon * np.asarray([width, height], dtype=np.float32)
                polygon_pixels -= np.asarray([x1, y1], dtype=np.float32)
                mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
                cv2.fillPoly(mask, [np.rint(polygon_pixels).astype(np.int32)], 255)
                crop_resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)
                mask_resized = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
                stem = f"{Path(row['fileName']).stem}__nail-{truth_index:02d}"
                image_output = temporary / "images" / split / f"{stem}.jpg"
                mask_output = temporary / "masks" / split / f"{stem}.png"
                image_output.parent.mkdir(parents=True, exist_ok=True)
                mask_output.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(crop_resized).save(image_output, format="JPEG", quality=95, subsampling=0)
                Image.fromarray(mask_resized).save(mask_output, format="PNG", optimize=True)
                result_records.append(
                    {
                        "id": stem,
                        "split": split,
                        "sourceFileName": row["fileName"],
                        "sourceGroup": source_group,
                        "truthIndex": truth_index,
                        "cropBox": [x1, y1, x2, y2],
                        "image": image_output.relative_to(temporary).as_posix(),
                        "mask": mask_output.relative_to(temporary).as_posix(),
                        "imageSha256": sha256_file(image_output),
                        "maskSha256": sha256_file(mask_output),
                    }
                )
        manifest = temporary / "manifest.json"
        manifest.write_text(json.dumps({"schemaVersion": 1, "records": result_records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    train_groups = sorted({row["sourceGroup"] for row in result_records if row["split"] == "train"})
    val_groups = sorted({row["sourceGroup"] for row in result_records if row["split"] == "val"})
    if set(train_groups) & set(val_groups):
        raise ValueError("物化后sourceGroup交叠")
    aggregate, file_count = aggregate_files(output)
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "ok": True,
        "decision": "source_group_isolated_train_only_roi_dataset",
        "scope": {"formalCalibrationTestOrHoldoutEligible": False, "testOrHoldoutRead": False},
        "inputs": {
            "cycle012MaterializationReport": {"path": str(source_report_path), "sha256": sha256_file(source_report_path)},
            "cycle012DatasetFilesSha256": source_report["datasetFilesSha256"],
        },
        "contract": {"cropScale": crop_scale, "size": size, "splitSalt": SPLIT_SALT},
        "outputDir": str(output),
        "counts": {
            "sourceImages": len(records),
            "instances": len(result_records),
            "trainInstances": sum(row["split"] == "train" for row in result_records),
            "valInstances": sum(row["split"] == "val" for row in result_records),
            "trainSourceGroups": len(train_groups),
            "valSourceGroups": len(val_groups),
        },
        "sourceGroups": {"train": train_groups, "val": val_groups, "overlap": []},
        "datasetFilesSha256": aggregate,
        "datasetFileCount": file_count,
        "manifest": {"path": str(output / "manifest.json"), "sha256": sha256_file(output / "manifest.json")},
        "errors": [],
    }
    report_path = output.parent / f"{output.name}-materialization-report.json"
    if report_path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{report_path}")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report")
    parser.add_argument("--output-dir")
    parser.add_argument("--crop-scale", type=float, default=1.6)
    parser.add_argument("--size", type=int, default=384)
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.source_report or not args.output_dir:
        raise ValueError("物化模式需要--source-report与--output-dir")
    source_report = Path(args.source_report).resolve()
    output = Path(args.output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    install_guard, remove_caches = load_guards()
    install_guard()
    source = json.loads(source_report.read_text(encoding="utf-8"))
    source_root = Path(source["outputDir"])
    remove_caches(source_root)
    try:
        report = materialize(source_report, output, args.crop_scale, args.size)
    finally:
        remove_caches(source_root)
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
