#!/usr/bin/env python3
"""构建 candidate53 单甲 ROI 训练集，并只从 train/val 角色挖掘候选负例。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TRAIN_VARIANTS = (
    ("base", 0.0, 0.0, 1.0),
    ("shift_x_neg08", -0.08, 0.0, 1.0),
    ("shift_x_pos08", 0.08, 0.0, 1.0),
    ("shift_y_neg08", 0.0, -0.08, 1.0),
    ("shift_y_pos08", 0.0, 0.08, 1.0),
    ("scale_neg08", 0.0, 0.0, 0.92),
    ("scale_pos08", 0.0, 0.0, 1.08),
)
VAL_VARIANTS = (("base", 0.0, 0.0, 1.0),)


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


def read_source_records(root: Path) -> dict[str, dict[str, str]]:
    path = root / "metadata" / "sources-isolation.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records: dict[str, dict[str, str]] = {}
    for row in rows:
        name = str(row.get("fileName", ""))
        if not name or name in records:
            raise ValueError("来源隔离表存在空文件名或重复文件名")
        records[name] = {key: str(value or "") for key, value in row.items()}
    return records


def image_map(directory: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.stem in result:
            raise ValueError(f"同一分片存在重复stem：{path.stem}")
        result[path.stem] = path
    return result


def parse_polygons(path: Path) -> list[list[tuple[float, float]]]:
    polygons: list[list[tuple[float, float]]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw.split()
        if not fields:
            continue
        if len(fields) < 7 or len(fields) % 2 == 0 or int(fields[0]) != 0:
            raise ValueError(f"YOLO polygon格式错误：{path}:{line_number}")
        values = [float(value) for value in fields[1:]]
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in values):
            raise ValueError(f"YOLO polygon坐标越界：{path}:{line_number}")
        points = list(zip(values[0::2], values[1::2], strict=True))
        polygons.append(points)
    return polygons


def polygon_area(points: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
        )
    ) / 2


def format_polygon(points: list[tuple[float, float]]) -> str:
    coordinates = " ".join(f"{value:.8f}" for point in points for value in point)
    return f"0 {coordinates}\n"


def compute_square_crop(
    points: list[tuple[float, float]],
    width: int,
    height: int,
    context_ratio: float,
    shift_x: float,
    shift_y: float,
    scale: float,
) -> tuple[int, int, int, int] | None:
    xs = [x * width for x, _ in points]
    ys = [y * height for _, y in points]
    object_side = max(max(xs) - min(xs), max(ys) - min(ys))
    side = max(16, int(math.ceil(object_side * (1 + 2 * context_ratio) * scale)))
    if side > min(width, height):
        return None
    center_x = (min(xs) + max(xs)) / 2 + shift_x * side
    center_y = (min(ys) + max(ys)) / 2 + shift_y * side
    left = int(round(center_x - side / 2))
    top = int(round(center_y - side / 2))
    left = min(max(left, 0), width - side)
    top = min(max(top, 0), height - side)
    right, bottom = left + side, top + side
    margin = 1.0
    if (
        min(xs) - left < margin
        or min(ys) - top < margin
        or right - max(xs) < margin
        or bottom - max(ys) < margin
    ):
        return None
    return left, top, right, bottom


def transformed_polygon(
    points: list[tuple[float, float]],
    width: int,
    height: int,
    crop_box: tuple[int, int, int, int],
) -> list[tuple[float, float]]:
    left, top, right, bottom = crop_box
    side = right - left
    transformed = [((x * width - left) / side, (y * height - top) / side) for x, y in points]
    if any(value <= 0 or value >= 1 for point in transformed for value in point):
        raise ValueError("变换后的甲面polygon触碰ROI边界")
    if polygon_area(transformed) <= 0:
        raise ValueError("变换后的甲面polygon面积为零")
    return transformed


def save_rgb_crop(
    source: Image.Image,
    crop_box: tuple[int, int, int, int],
    output: Path,
    output_size: int,
    blur_parent_corner: bool = False,
) -> None:
    working = source
    if blur_parent_corner:
        width, height = source.size
        corner = (math.floor(width * 0.88), math.floor(height * 0.88), width, height)
        working = source.copy()
        working.paste(source.crop(corner).filter(ImageFilter.GaussianBlur(radius=8)), corner)
    crop = working.crop(crop_box)
    crop = crop.resize((output_size, output_size), Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output, format="PNG", compress_level=1)


def corner_intersects(
    crop_box: tuple[int, int, int, int], width: int, height: int
) -> bool:
    left, top, right, bottom = crop_box
    return right > width * 0.88 and bottom > height * 0.88 and left < width and top < height


def mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    intersection = int(np.logical_and(left, right).sum())
    union = int(np.logical_or(left, right).sum())
    return intersection / union if union else 0.0


def box_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if intersection == 0:
        return 0.0
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / (left_area + right_area - intersection)


def truth_masks_and_boxes(
    polygons: list[list[tuple[float, float]]], width: int, height: int
) -> tuple[list[np.ndarray], list[tuple[float, float, float, float]]]:
    masks: list[np.ndarray] = []
    boxes: list[tuple[float, float, float, float]] = []
    for points in polygons:
        pixels = np.asarray([(x * width, y * height) for x, y in points], dtype=np.float32)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [np.rint(pixels).astype(np.int32)], 1)
        if int(mask.sum()) == 0:
            raise ValueError("真值polygon栅格化为空")
        masks.append(mask)
        boxes.append((float(pixels[:, 0].min()), float(pixels[:, 1].min()), float(pixels[:, 0].max()), float(pixels[:, 1].max())))
    return masks, boxes


def proposal_crop_box(
    proposal_box: tuple[float, float, float, float], width: int, height: int, context_ratio: float
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = proposal_box
    side = max(16, int(math.ceil(max(x1 - x0, y1 - y0) * (1 + 2 * context_ratio))))
    if side > min(width, height):
        return None
    center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
    left = min(max(int(round(center_x - side / 2)), 0), width - side)
    top = min(max(int(round(center_y - side / 2)), 0), height - side)
    return left, top, left + side, top + side


def inventory(root: Path, excluded: set[Path]) -> list[dict[str, str]]:
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.endswith(".cache") and path.resolve() not in excluded
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="构建candidate53单甲ROI训练/验证数据集")
    parser.add_argument("--input-dataset", required=True)
    parser.add_argument("--input-audit", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    input_root = Path(args.input_dataset).resolve()
    input_audit_path = Path(args.input_audit).resolve()
    plan_path = Path(args.plan).resolve()
    output_root = Path(args.output_dir).resolve()
    if output_root.exists():
        raise ValueError(f"输出目录必须是全新的：{output_root}")
    input_audit = read_json(input_audit_path)
    plan = read_json(plan_path)
    if input_audit.get("decision") != "approved_candidate_training_input":
        raise ValueError("父训练输入审计未批准")
    if Path(str(input_audit.get("outputDir", ""))).resolve() != input_root:
        raise ValueError("父训练输入审计未绑定指定数据集")
    if plan.get("candidate") != "candidate53":
        raise ValueError("计划不是candidate53")
    stage1 = plan["stage1"]
    stage2_dataset = plan["stage2Dataset"]
    weights = Path(str(stage1["weights"])).resolve()
    if sha256_file(weights) != stage1["weightsSha256"]:
        raise ValueError("stage1权重SHA-256不一致")
    truth_index = Path(str(stage2_dataset["sourceTrainingTruthIndex"])).resolve()
    if sha256_file(truth_index) != stage2_dataset["sourceTrainingTruthIndexSha256"]:
        raise ValueError("训练真值索引SHA-256不一致")
    context_ratio = float(plan["runtimeComposition"]["cropContextRatio"])
    output_size = int(plan["stage2"]["inputSize"])
    negative_ratio = float(stage2_dataset["maximumNegativeToPositiveRatio"])
    if not 0 < context_ratio < 1 or output_size < 64 or not 0 <= negative_ratio <= 1:
        raise ValueError("ROI计划参数非法")

    sources = read_source_records(input_root)
    disqualified_parents: dict[str, dict[str, dict[str, Any]]] = {"train": {}, "val": {}}
    for split in ("train", "val"):
        images = image_map(input_root / "images" / split)
        labels = {path.stem: path for path in (input_root / "labels" / split).glob("*.txt")}
        if set(images) != set(labels):
            raise ValueError(f"{split}图片与标签stem不一致")
        for image_path in images.values():
            record = sources.get(image_path.name)
            if record is None or record.get("split") != split:
                raise ValueError(f"来源隔离表未绑定{split}图片：{image_path.name}")
            if record.get("imageSha256") != sha256_file(image_path):
                raise ValueError(f"父图哈希漂移：{image_path.name}")
            label_path = input_root / "labels" / split / f"{image_path.stem}.txt"
            polygons = parse_polygons(label_path)
            if not polygons:
                continue
            with Image.open(image_path) as encoded:
                source = ImageOps.exif_transpose(encoded)
            width, height = source.size
            rejected_indices = [
                index
                for index, points in enumerate(polygons, 1)
                if compute_square_crop(points, width, height, context_ratio, 0.0, 0.0, 1.0) is None
            ]
            if rejected_indices:
                disqualified_parents[split][image_path.name] = {
                    "split": split,
                    "fileName": image_path.name,
                    "imageSha256": record["imageSha256"],
                    "labelSha256": sha256_file(label_path),
                    "sourceGroup": record["sourceGroup"],
                    "polygonCount": len(polygons),
                    "boundaryTouchingPolygonIndices": rejected_indices,
                    "reason": "required_nail_touches_parent_image_boundary_entire_source_excluded_from_stage2",
                }
    if image_map(input_root / "images" / "test"):
        raise ValueError("candidate53输入不得包含test图片")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f"{output_root.name}-", dir=output_root.parent))
    records: list[dict[str, Any]] = []
    positive_counts = {"train": 0, "val": 0}
    negative_candidates: dict[str, list[dict[str, Any]]] = {"train": [], "val": []}
    skipped_perturbations = 0
    try:
        for split in ("train", "val", "test"):
            (temporary / "images" / split).mkdir(parents=True, exist_ok=True)
            (temporary / "labels" / split).mkdir(parents=True, exist_ok=True)
        for split, variants in (("train", TRAIN_VARIANTS), ("val", VAL_VARIANTS)):
            for stem, image_path in image_map(input_root / "images" / split).items():
                label_path = input_root / "labels" / split / f"{stem}.txt"
                polygons = parse_polygons(label_path)
                role = sources[image_path.name]
                if split == "train" and role["role"] == "hard-negative":
                    if polygons:
                        raise ValueError(f"困难负样本包含正标签：{image_path.name}")
                    continue
                if image_path.name in disqualified_parents[split]:
                    continue
                if not polygons:
                    raise ValueError(f"正样本或val图片没有真值：{image_path.name}")
                with Image.open(image_path) as encoded:
                    source = ImageOps.exif_transpose(encoded).convert("RGB")
                width, height = source.size
                for polygon_index, points in enumerate(polygons, 1):
                    base_created = False
                    for variant_name, shift_x, shift_y, scale in variants:
                        crop_box = compute_square_crop(points, width, height, context_ratio, shift_x, shift_y, scale)
                        if crop_box is None:
                            if variant_name == "base":
                                raise ValueError("预扫描后基础ROI仍无法完整包含甲面")
                            skipped_perturbations += 1
                            continue
                        transformed = transformed_polygon(points, width, height, crop_box)
                        output_stem = f"{stem}__n{polygon_index:02d}__{variant_name}"
                        output_image = temporary / "images" / split / f"{output_stem}.png"
                        output_label = temporary / "labels" / split / f"{output_stem}.txt"
                        save_rgb_crop(source, crop_box, output_image, output_size)
                        output_label.write_text(format_polygon(transformed), encoding="utf-8", newline="\n")
                        item = {
                            "id": f"{split}:{output_stem}", "split": split, "kind": "positive",
                            "variant": variant_name, "sourceGroup": role["sourceGroup"],
                            "parentImage": str(image_path), "parentImageSha256": role["imageSha256"],
                            "parentLabel": str(label_path), "parentLabelSha256": sha256_file(label_path),
                            "parentPolygonIndex": polygon_index, "cropBox": list(crop_box),
                            "outputImage": output_image.relative_to(temporary).as_posix(),
                            "outputImageSha256": sha256_file(output_image),
                            "outputLabel": output_label.relative_to(temporary).as_posix(),
                            "outputLabelSha256": sha256_file(output_label),
                        }
                        records.append(item)
                        positive_counts[split] += 1
                        if variant_name == "base":
                            base_created = True
                            if split == "train" and corner_intersects(crop_box, width, height):
                                blur_stem = f"{stem}__n{polygon_index:02d}__base_cornerblur12"
                                blur_image = temporary / "images" / split / f"{blur_stem}.png"
                                blur_label = temporary / "labels" / split / f"{blur_stem}.txt"
                                save_rgb_crop(source, crop_box, blur_image, output_size, blur_parent_corner=True)
                                blur_label.write_text(format_polygon(transformed), encoding="utf-8", newline="\n")
                                records.append({
                                    **item, "id": f"{split}:{blur_stem}", "variant": "base_cornerblur12",
                                    "outputImage": blur_image.relative_to(temporary).as_posix(),
                                    "outputImageSha256": sha256_file(blur_image),
                                    "outputLabel": blur_label.relative_to(temporary).as_posix(),
                                    "outputLabelSha256": sha256_file(blur_label),
                                })
                                positive_counts[split] += 1
                    if not base_created:
                        continue

        from ultralytics import YOLO

        model = YOLO(str(weights))
        for split in ("train", "val"):
            images = image_map(input_root / "images" / split)
            results = model.predict(
                source=str(input_root / "images" / split),
                imgsz=int(stage1["inputSize"]), conf=float(stage1["proposalThreshold"]),
                iou=0.7, max_det=int(stage1["maximumProposalsPerImage"]), device=args.device,
                retina_masks=True, stream=True, verbose=False,
            )
            processed: set[Path] = set()
            for result in results:
                image_path = Path(str(result.path)).resolve()
                if image_path.stem not in images or image_path in processed:
                    raise ValueError(f"stage1返回未知或重复图片：{image_path}")
                processed.add(image_path)
                label_path = input_root / "labels" / split / f"{image_path.stem}.txt"
                polygons = parse_polygons(label_path)
                with Image.open(image_path) as encoded:
                    source = ImageOps.exif_transpose(encoded).convert("RGB")
                width, height = source.size
                truth_masks, truth_boxes = truth_masks_and_boxes(polygons, width, height)
                if result.boxes is None or result.masks is None:
                    continue
                boxes = result.boxes.xyxy.detach().cpu().numpy()
                scores = result.boxes.conf.detach().cpu().numpy()
                masks = result.masks.data.detach().cpu().numpy()
                if not (len(boxes) == len(scores) == len(masks)):
                    raise ValueError("stage1候选box/score/mask数量不一致")
                role = sources[image_path.name]
                if image_path.name in disqualified_parents[split]:
                    continue
                for proposal_index, (raw_box, score, raw_mask) in enumerate(zip(boxes, scores, masks, strict=True)):
                    prediction_mask = cv2.resize(raw_mask, (width, height), interpolation=cv2.INTER_NEAREST) > 0.5
                    proposal_box = tuple(float(value) for value in raw_box)
                    best_mask_iou = max((mask_iou(prediction_mask, truth) for truth in truth_masks), default=0.0)
                    best_box_iou = max((box_iou(proposal_box, truth_box) for truth_box in truth_boxes), default=0.0)
                    if best_mask_iou >= 0.10 or best_box_iou >= 0.10:
                        continue
                    crop_box = proposal_crop_box(proposal_box, width, height, context_ratio)
                    if crop_box is None:
                        continue
                    negative_candidates[split].append({
                        "id": f"{split}:{image_path.stem}:p{proposal_index:03d}", "split": split,
                        "kind": "negative", "variant": "stage1_unmatched", "score": round(float(score), 8),
                        "bestTruthMaskIou": round(best_mask_iou, 8), "bestTruthBoxIou": round(best_box_iou, 8),
                        "sourceGroup": role["sourceGroup"], "parentImage": str(image_path),
                        "parentImageSha256": role["imageSha256"], "parentLabel": str(label_path),
                        "parentLabelSha256": sha256_file(label_path), "cropBox": list(crop_box),
                    })
            if processed != {path.resolve() for path in images.values()}:
                raise ValueError(f"stage1未处理完整{split}分片")

        train_negative_limit = math.floor(int(stage2_dataset["positiveMasks"]) * negative_ratio)
        selected_negatives = {
            "train": sorted(negative_candidates["train"], key=lambda row: (-row["score"], row["id"]))[:train_negative_limit],
            "val": sorted(negative_candidates["val"], key=lambda row: (-row["score"], row["id"])),
        }
        for split, items in selected_negatives.items():
            for ordinal, item in enumerate(items, 1):
                image_path = Path(item["parentImage"])
                with Image.open(image_path) as encoded:
                    source = ImageOps.exif_transpose(encoded).convert("RGB")
                output_stem = f"negative__{ordinal:05d}__{hashlib.sha256(item['id'].encode()).hexdigest()[:12]}"
                output_image = temporary / "images" / split / f"{output_stem}.png"
                output_label = temporary / "labels" / split / f"{output_stem}.txt"
                save_rgb_crop(source, tuple(item["cropBox"]), output_image, output_size)
                output_label.write_text("", encoding="utf-8", newline="\n")
                records.append({
                    **item, "outputImage": output_image.relative_to(temporary).as_posix(),
                    "outputImageSha256": sha256_file(output_image),
                    "outputLabel": output_label.relative_to(temporary).as_posix(),
                    "outputLabelSha256": sha256_file(output_label),
                })

        dataset_yaml = temporary / "dataset.yaml"
        dataset_yaml.write_text(
            "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n\n"
            "names:\n  0: nail_texture\n\ntask: segment\nclass_count: 1\nimage_size: 256\n\n"
            "metadata:\n  dataset_version: candidate53-single-nail-roi/v1\n"
            "  lineage: metadata/candidate53-single-nail-roi-lineage-v1.json\n",
            encoding="utf-8", newline="\n",
        )
        records.sort(key=lambda row: row["id"])
        lineage_path = temporary / "metadata" / "candidate53-single-nail-roi-lineage-v1.json"
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        lineage = {
            "schemaVersion": 1, "decision": "candidate53_single_nail_roi_lineage",
            "inputs": {
                "datasetRoot": str(input_root), "datasetYamlSha256": sha256_file(input_root / "dataset.yaml"),
                "inputAudit": str(input_audit_path), "inputAuditSha256": sha256_file(input_audit_path),
                "plan": str(plan_path), "planSha256": sha256_file(plan_path),
                "stage1Weights": str(weights), "stage1WeightsSha256": sha256_file(weights),
                "trainingTruthIndex": str(truth_index), "trainingTruthIndexSha256": sha256_file(truth_index),
            },
            "parameters": {
                "outputSize": output_size, "contextRatio": context_ratio,
                "trainVariants": [row[0] for row in TRAIN_VARIANTS], "valVariants": [row[0] for row in VAL_VARIANTS],
                "negativeMaskAndBoxIouExclusive": 0.10, "maximumNegativeToUniquePositiveMaskRatio": negative_ratio,
                "proposalInputSize": stage1["inputSize"], "proposalConfidence": stage1["proposalThreshold"],
                "maximumProposalsPerImage": stage1["maximumProposalsPerImage"],
            },
            "counts": {
                "trainPositiveRois": positive_counts["train"], "trainNegativeRois": len(selected_negatives["train"]),
                "valPositiveRois": positive_counts["val"], "valNegativeRois": len(selected_negatives["val"]),
                "rawTrainNegativeCandidates": len(negative_candidates["train"]),
                "rawValNegativeCandidates": len(negative_candidates["val"]),
                "skippedPerturbations": skipped_perturbations,
                "sourceBoundaryRejectedTrainImages": len(disqualified_parents["train"]),
                "sourceBoundaryRejectedTrainMasks": sum(item["polygonCount"] for item in disqualified_parents["train"].values()),
                "sourceBoundaryRejectedValImages": len(disqualified_parents["val"]),
                "sourceBoundaryRejectedValMasks": sum(item["polygonCount"] for item in disqualified_parents["val"].values()),
                "testImages": 0,
            },
            "rolePolicy": {"trainFromTrainOnly": True, "valFromValOnly": True, "testUsed": False, "holdoutUsed": False},
            "excludedParents": sorted(
                [*disqualified_parents["train"].values(), *disqualified_parents["val"].values()],
                key=lambda item: (item["split"], item["fileName"]),
            ),
            "recordsSha256": canonical_sha256(records), "records": records,
        }
        lineage_path.write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        report_path = temporary / "candidate53-single-nail-roi-materialization-v1.json"
        files = inventory(temporary, {report_path.resolve()})
        report = {
            "schemaVersion": 1, "ok": True,
            "decision": "candidate53_single_nail_roi_materialized_pending_independent_audit",
            "outputDir": str(output_root), "datasetYaml": str(output_root / "dataset.yaml"),
            "lineage": {"path": str(output_root / "metadata" / lineage_path.name), "sha256": sha256_file(lineage_path), "recordsSha256": lineage["recordsSha256"]},
            "counts": lineage["counts"], "datasetFilesSha256": canonical_sha256(files), "datasetFiles": files,
            "trainingUse": "prohibited-until-independent-audit", "errors": [],
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"ok": True, "output": str(output_root), "counts": lineage["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
