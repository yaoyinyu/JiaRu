#!/usr/bin/env python3
"""以已锁定 candidate57 组合一次性生成受保护 test100 预测制品。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from _training_common import load_dataset_config, write_json


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象：{path}")
    return value


def inventory_tree(root: Path) -> tuple[list[dict[str, str]], str]:
    records = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    return records, canonical_sha256(records)


def load_locked_runtime(lock: dict[str, Any], lock_path: Path):
    implementation = lock.get("implementation", {})
    runtime_path = (lock_path.parents[2] / str(implementation.get("path", ""))).resolve()
    if not runtime_path.is_file() or sha256_file(runtime_path) != implementation.get("sha256"):
        raise ValueError("candidate57锁定的val运行时实现已漂移")
    spec = importlib.util.spec_from_file_location("candidate57_locked_runtime", runtime_path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载candidate57锁定运行时")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_lock(lock_path: Path, dataset_path: Path, snapshot_path: Path, materialization_path: Path) -> tuple[dict[str, Any], Any]:
    lock = read_json(lock_path)
    if (
        lock.get("decision")
        != "candidate57_low_band_margin_gate_val30_locked_ready_for_single_protected_test100_evaluation"
        or lock.get("candidate") != "candidate57-low-band-margin-gate"
        or lock.get("protectedTest100Used") is not False
        or lock.get("releaseState") != "hold_pending_single_protected_test100_evaluation"
    ):
        raise ValueError("candidate57运行时选择锁状态不允许首次test100评估")

    repository_root = lock_path.parents[2]
    for field in ("plan", "implementation", "protectedTestRunner"):
        record = lock[field]
        path = (repository_root / str(record["path"])).resolve()
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"candidate57选择锁输入漂移：{field}")

    for field in ("stage1", "stage2"):
        record = lock[field]
        path = Path(str(record["weights"])).resolve()
        if (
            not path.is_file()
            or path.stat().st_size != int(record["weightsBytes"])
            or sha256_file(path) != record["weightsSha256"]
        ):
            raise ValueError(f"candidate57选择锁权重漂移：{field}")

    val = lock["val30"]
    val_path = Path(str(val["report"])).resolve()
    val_report = read_json(val_path)
    if (
        not val_path.is_file()
        or sha256_file(val_path) != val["reportSha256"]
        or val_report.get("ok") is not True
        or val_report.get("decision") != "candidate57_low_band_margin_gate_val30_pass"
        or int(val_report.get("counts", {}).get("testImagesRead", -1)) != 0
    ):
        raise ValueError("candidate57 val30通过证据无效或已漂移")

    protected = lock.get("protectedTest", {})
    expected = (
        (dataset_path, "datasetYamlSha256"),
        (snapshot_path, "snapshotManifestSha256"),
        (materialization_path, "materializationReportSha256"),
    )
    for path, field in expected:
        if not path.is_file() or sha256_file(path) != protected.get(field):
            raise ValueError(f"candidate57受保护test100输入漂移：{field}")

    composition = lock["runtimeComposition"]
    if composition != {
        "primaryRule": "stage1Score >= 0.40",
        "promotionRule": "0.30 <= stage1Score < 0.40 and stage2Score - stage1Score >= 0.55",
        "selectedPolygon": "stage1Polygon",
        "productDedup": {
            "maskIouThreshold": 0.60,
            "maskContainmentThreshold": 0.85,
            "maskScoreTolerance": 0.12,
            "boxIouThreshold": 0.55,
        },
    }:
        raise ValueError("candidate57锁定组合与实现合同不一致")

    runtime = load_locked_runtime(lock, lock_path)
    if (
        runtime.MASK_IOU_THRESHOLD != 0.60
        or runtime.MASK_CONTAINMENT_THRESHOLD != 0.85
        or runtime.MASK_SCORE_TOLERANCE != 0.12
        or runtime.BOX_IOU_THRESHOLD != 0.55
    ):
        raise ValueError("candidate57锁定去重常量已漂移")
    return lock, runtime


def main() -> None:
    parser = argparse.ArgumentParser(description="执行一次candidate57受保护test100组合评估")
    parser.add_argument("--selection-lock", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--snapshot-manifest", required=True)
    parser.add_argument("--materialization-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    lock_path = Path(args.selection_lock).resolve()
    dataset_path = Path(args.dataset).resolve()
    snapshot_path = Path(args.snapshot_manifest).resolve()
    materialization_path = Path(args.materialization_report).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise ValueError(f"test100输出目录必须全新：{output_dir}")

    lock, runtime = validate_lock(
        lock_path, dataset_path, snapshot_path, materialization_path
    )
    config = load_dataset_config(dataset_path)
    images_dir = (config.dataset_root / config.test).resolve()
    image_paths = sorted(
        path
        for path in images_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    stems = [path.stem for path in image_paths]
    if len(stems) != 100 or len(set(stems)) != 100:
        raise ValueError(f"受保护test100必须精确100个唯一stem，实际{len(stems)}")

    source_inventory_before, source_tree_sha256 = inventory_tree(config.dataset_root)
    stage1 = lock["stage1"]
    stage2 = lock["stage2"]
    from ultralytics import YOLO

    stage1_model = YOLO(str(Path(stage1["weights"]).resolve()))
    stage2_model = YOLO(str(Path(stage2["weights"]).resolve()))
    maximum = int(stage1["maximumProposalsPerImage"])
    context = float(stage2["cropContextRatio"])
    roi_size = int(stage2["inputSize"])
    primary_threshold = float(stage1["acceptanceThreshold"])
    promotion_minimum = float(stage1["promotionBandMinimum"])
    margin_threshold = float(stage2["promotionMarginThreshold"])
    selected_by_stem: dict[str, list[dict[str, Any]]] = {}
    raw_proposals = 0
    promoted_total = 0

    results = stage1_model.predict(
        source=[str(path) for path in image_paths],
        imgsz=int(stage1["inputSize"]),
        conf=float(stage1["proposalThreshold"]),
        iou=0.7,
        max_det=maximum,
        device=args.device,
        retina_masks=True,
        rect=False,
        stream=True,
        verbose=False,
    )
    for image_path, result in zip(image_paths, results, strict=True):
        with Image.open(image_path) as encoded:
            image = ImageOps.exif_transpose(encoded).convert("RGB")
        width, height = image.size
        proposals: list[tuple[int, tuple[int, int, int, int], np.ndarray, float, Any]] = []
        if result.boxes is not None and result.masks is not None:
            boxes = result.boxes.xyxy.detach().cpu().numpy()[:maximum]
            scores = result.boxes.conf.detach().cpu().numpy()[:maximum]
            mask_polygons = result.masks.xy[:maximum]
            if not (len(boxes) == len(scores) == len(mask_polygons)):
                raise ValueError("stage1 box、score与mask数量不一致")
            for index, (raw_box, raw_score, raw_mask_polygon) in enumerate(
                zip(boxes, scores, mask_polygons, strict=True)
            ):
                crop_box = runtime.square_crop(
                    tuple(float(value) for value in raw_box), width, height, context
                )
                stage1_polygon = runtime.polygon_from_image_points(
                    np.asarray(raw_mask_polygon), width, height
                )
                if crop_box is None or stage1_polygon is None:
                    continue
                crop_rgb = np.asarray(
                    image.crop(crop_box).resize(
                        (roi_size, roi_size), Image.Resampling.LANCZOS
                    )
                )
                proposals.append(
                    (
                        index,
                        crop_box,
                        cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR),
                        float(raw_score),
                        stage1_polygon,
                    )
                )
        raw_proposals += len(proposals)
        candidates: list[dict[str, Any]] = []
        if proposals:
            refinements = stage2_model.predict(
                source=[item[2] for item in proposals],
                imgsz=roi_size,
                conf=0.001,
                iou=0.7,
                max_det=1,
                device=args.device,
                retina_masks=True,
                rect=False,
                verbose=False,
            )
            if len(refinements) != len(proposals):
                raise ValueError("stage2结果数与ROI数不一致")
            for (proposal_index, crop_box, _, stage1_score, stage1_polygon), refinement in zip(
                proposals, refinements, strict=True
            ):
                stage2_score = 0.0
                if (
                    refinement.boxes is not None
                    and refinement.masks is not None
                    and len(refinement.boxes) > 0
                    and refinement.masks.xy
                ):
                    polygon = runtime.polygon_from_stage2(
                        np.asarray(refinement.masks.xy[0]),
                        crop_box,
                        roi_size,
                        width,
                        height,
                    )
                    if polygon is not None:
                        stage2_score = float(refinement.boxes.conf[0].detach().cpu())
                promoted = (
                    promotion_minimum <= stage1_score < primary_threshold
                    and stage2_score - stage1_score >= margin_threshold
                )
                if stage1_score < primary_threshold and not promoted:
                    continue
                candidates.append(
                    {
                        "proposalIndex": proposal_index,
                        "polygon": stage1_polygon,
                        "bounds": tuple(float(value) for value in stage1_polygon.bounds),
                        "score": stage1_score,
                        "promoted": promoted,
                    }
                )
        selected = runtime.suppress_duplicates(candidates, maximum)
        promoted_total += sum(bool(item["promoted"]) for item in selected)
        selected_by_stem[image_path.stem] = selected

    if set(selected_by_stem) != set(stems):
        raise ValueError("candidate57没有精确覆盖受保护test100")
    source_inventory_after, source_tree_sha256_after = inventory_tree(config.dataset_root)
    if (
        source_inventory_after != source_inventory_before
        or source_tree_sha256_after != source_tree_sha256
    ):
        raise ValueError("不可变test100数据在推理期间发生漂移")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f"{output_dir.name}-", dir=output_dir.parent)
    )
    try:
        artifacts_dir = temporary / "evaluation-artifacts"
        labels_dir = artifacts_dir / "labels"
        labels_dir.mkdir(parents=True)
        prediction_records: list[dict[str, Any]] = []
        for stem in stems:
            predictions = selected_by_stem[stem]
            lines = []
            for item in predictions:
                coordinates = " ".join(
                    f"{value:.8f}"
                    for point in item["polygon"].exterior.coords[:-1]
                    for value in point
                )
                lines.append(f"0 {coordinates} {item['score']:.8f}")
            label_path = labels_dir / f"{stem}.txt"
            label_path.write_text(
                "\n".join(lines) + ("\n" if lines else ""),
                encoding="utf-8",
                newline="\n",
            )
            prediction_records.append(
                {
                    "stem": stem,
                    "path": label_path.relative_to(artifacts_dir).as_posix(),
                    "sha256": sha256_file(label_path),
                    "prediction_count": len(predictions),
                }
            )
        artifact_paths = sorted(
            path for path in artifacts_dir.rglob("*") if path.is_file()
        )
        file_records = [
            {
                "path": path.relative_to(artifacts_dir).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in artifact_paths
        ]
        artifact_index = {
            "schema_version": 1,
            "split": "test",
            "artifacts_dir": str(output_dir / "evaluation-artifacts"),
            "runtime_selection_lock": str(lock_path),
            "runtime_selection_lock_sha256": sha256_file(lock_path),
            "dataset_yaml": str(dataset_path),
            "dataset_yaml_sha256": sha256_file(dataset_path),
            "source_tree_sha256": source_tree_sha256,
            "files": [record["path"] for record in file_records],
            "file_records": file_records,
            "files_sha256": canonical_sha256(file_records),
            "prediction_records": prediction_records,
            "prediction_records_sha256": canonical_sha256(prediction_records),
            "counts": {
                "total": len(file_records),
                "plots": 0,
                "prediction_labels": len(prediction_records),
                "json": 0,
            },
        }
        index_path = artifacts_dir / "evaluation-artifacts.json"
        write_json(index_path, artifact_index)
        run_report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "candidate57_locked_composition_protected_test100_predictions_materialized_once",
            "trainingUse": "prohibited",
            "candidate": lock["candidate"],
            "selectionLock": str(lock_path),
            "selectionLockSha256": sha256_file(lock_path),
            "inputs": {
                "datasetYaml": str(dataset_path),
                "datasetYamlSha256": sha256_file(dataset_path),
                "snapshotManifest": str(snapshot_path),
                "snapshotManifestSha256": sha256_file(snapshot_path),
                "materializationReport": str(materialization_path),
                "materializationReportSha256": sha256_file(materialization_path),
            },
            "runtime": lock["runtimeComposition"],
            "counts": {
                "images": len(stems),
                "rawStage1Proposals": raw_proposals,
                "selectedPredictions": sum(
                    len(items) for items in selected_by_stem.values()
                ),
                "promotedPredictions": promoted_total,
                "imagesWithNoPredictions": sum(
                    not items for items in selected_by_stem.values()
                ),
                "evaluationCountForLockedCandidate": 1,
            },
            "artifactIndex": str(output_dir / "evaluation-artifacts" / "evaluation-artifacts.json"),
            "releaseState": "hold_pending_positive_recognition_quality_report",
        }
        write_json(temporary / "candidate57-frozen-test100-prediction-run-v1.json", run_report)
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(
        json.dumps(
            {
                "ok": True,
                "decision": run_report["decision"],
                "counts": run_report["counts"],
                "output": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
