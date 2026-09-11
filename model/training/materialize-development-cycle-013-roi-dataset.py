#!/usr/bin/env python3
"""从循环012的train角色和冻结stage1候选物化循环013单甲ROI数据集。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


HERE = Path(__file__).resolve().parent
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN = load_module("cycle013_plan_verifier_for_materializer", HERE / "verify-development-cycle-013-plan.py")
CYCLE012 = load_module("cycle012_materializer_for_cycle013", HERE / "materialize-development-cycle-012-dataset.py")
LEGACY = load_module("candidate53_helpers_for_cycle013", HERE / "materialize-candidate53-single-nail-roi-dataset.py")
RUNTIME = load_module("cycle013_mask_runtime_for_materializer", HERE / "nail_texture_cycle013_mask_replacement.py")


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


def select_validation_groups(groups: set[str], count: int, seed: int) -> set[str]:
    if count <= 0 or count >= len(groups):
        raise ValueError("内部验证来源组数量必须大于0且小于正样本来源组总数")
    ranked = sorted(groups, key=lambda group: (hashlib.sha256(f"{seed}:{group}".encode()).hexdigest(), group))
    return set(ranked[:count])


def proposal_crop_variant(
    box: tuple[float, float, float, float],
    width: int,
    height: int,
    context_ratio: float,
    shift_x_ratio: float,
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box
    side = max(16, int(math.ceil(max(x1 - x0, y1 - y0) * (1 + 2 * context_ratio))))
    if side > width or side > height:
        return None
    center_x = (x0 + x1) / 2 + shift_x_ratio * side
    center_y = (y0 + y1) / 2
    left = min(max(int(round(center_x - side / 2)), 0), width - side)
    top = min(max(int(round(center_y - side / 2)), 0), height - side)
    return left, top, left + side, top + side


def transformed_truth(
    truth: list[tuple[float, float]],
    width: int,
    height: int,
    crop: tuple[int, int, int, int],
) -> list[tuple[float, float]] | None:
    left, top, right, bottom = crop
    crop_width, crop_height = right - left, bottom - top
    points = [((x * width - left) / crop_width, (y * height - top) / crop_height) for x, y in truth]
    if any(value <= 0 or value >= 1 for point in points for value in point):
        return None
    if LEGACY.polygon_area(points) <= 0:
        return None
    return points


def proposal_mask(points: Any, width: int, height: int) -> np.ndarray | None:
    array = np.asarray(points, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] < 3 or array.shape[1] != 2 or not np.isfinite(array).all():
        return None
    array[:, 0] = np.clip(array[:, 0], 0, width - 1)
    array[:, 1] = np.clip(array[:, 1], 0, height - 1)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(array).astype(np.int32)], 1)
    return mask if int(mask.sum()) else None


def associate_proposals(
    boxes: np.ndarray,
    scores: np.ndarray,
    mask_polygons: list[Any],
    truths: list[list[tuple[float, float]]],
    width: int,
    height: int,
) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    truth_masks, truth_boxes = LEGACY.truth_masks_and_boxes(truths, width, height)
    eligible: list[dict[str, Any]] = []
    ambiguous = 0
    for proposal_index, (raw_box, raw_score, raw_polygon) in enumerate(
        zip(boxes, scores, mask_polygons, strict=True)
    ):
        mask = proposal_mask(raw_polygon, width, height)
        if mask is None:
            continue
        box = tuple(float(value) for value in raw_box)
        mask_ious = [LEGACY.mask_iou(mask, truth_mask) for truth_mask in truth_masks]
        box_ious = [LEGACY.box_iou(box, truth_box) for truth_box in truth_boxes]
        associations = [
            index
            for index, (mask_iou, box_iou) in enumerate(zip(mask_ious, box_ious, strict=True))
            if mask_iou >= 0.10 or box_iou >= 0.10
        ]
        if len(associations) != 1:
            ambiguous += len(associations) > 1
            continue
        truth_index = associations[0]
        eligible.append(
            {
                "proposalIndex": proposal_index,
                "truthIndex": truth_index,
                "box": box,
                "score": float(raw_score),
                "maskPolygonPixels": [[float(x), float(y)] for x, y in np.asarray(raw_polygon)],
                "maskIou": float(mask_ious[truth_index]),
                "boxIou": float(box_ious[truth_index]),
            }
        )
    selected: dict[int, dict[str, Any]] = {}
    for item in sorted(
        eligible,
        key=lambda row: (
            -max(float(row["maskIou"]), float(row["boxIou"])),
            -float(row["score"]),
            int(row["proposalIndex"]),
        ),
    ):
        selected.setdefault(int(item["truthIndex"]), item)
    return selected, {
        "eligibleProposals": len(eligible),
        "ambiguousProposals": ambiguous,
        "duplicateTruthProposalsSuppressed": len(eligible) - len(selected),
    }


def save_crop(source: Image.Image, crop: tuple[int, int, int, int], size: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    source.crop(crop).resize((size, size), Image.Resampling.LANCZOS).save(output, format="PNG", compress_level=1)


def inventory(root: Path) -> list[dict[str, str]]:
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.endswith(".cache")
    ]


def validate_inputs(plan_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    plan = PLAN.verify_plan(plan_path)
    materialization_path = Path(plan["inputs"]["cycle012Materialization"]["path"])
    materialization = CYCLE012.verify_report(materialization_path)
    dataset_root = Path(str(materialization["outputDir"])).resolve()
    source_map_path = Path(plan["inputs"]["trainSourceGroupMap"]["path"])
    source_map = read_json(source_map_path)
    rows = source_map.get("images")
    if not isinstance(rows, list):
        raise ValueError("train来源组映射缺少images")
    expected = {
        str(row["fileName"]): row
        for row in materialization["records"]
        if row.get("developmentSplit") == "train"
    }
    mapped = {str(row.get("fileName", "")): row for row in rows}
    if set(mapped) != set(expected):
        raise ValueError("train来源组映射未精确覆盖循环012 train")
    for name, item in expected.items():
        if mapped[name].get("sourceGroup") != item.get("sourceGroup") or mapped[name].get("role") != item.get("role"):
            raise ValueError(f"train来源组映射漂移：{name}")
    return plan, materialization, source_map, dataset_root


def build_dataset(plan_path: Path, output_root: Path, device: str) -> dict[str, Any]:
    plan, materialization, source_map, dataset_root = validate_inputs(plan_path)
    if output_root.exists():
        raise ValueError(f"输出目录必须全新：{output_root}")
    positive_records = [
        row
        for row in materialization["records"]
        if row.get("developmentSplit") == "train" and row.get("role") == "train-positive"
    ]
    if len(positive_records) != 290 or sum(int(row["maskCount"]) for row in positive_records) != 1731:
        raise ValueError("循环013父train正样本计数漂移")
    positive_groups = {str(row["sourceGroup"]) for row in positive_records}
    data_contract = plan["stage2TrainingData"]
    validation_groups = select_validation_groups(
        positive_groups, int(data_contract["validationSourceGroups"]), int(data_contract["splitSeed"])
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    records: list[dict[str, Any]] = []
    counters = {
        "parentImages": 0,
        "parentTruths": 0,
        "eligibleProposals": 0,
        "ambiguousProposals": 0,
        "duplicateTruthProposalsSuppressed": 0,
        "uniqueAssociatedTruths": 0,
        "unassociatedTruths": 0,
        "cropRejectedTruths": 0,
        "trainPositiveRois": 0,
        "valPositiveRois": 0,
    }
    try:
        from ultralytics import YOLO

        model = YOLO(str(Path(plan["stage1"]["weights"]["path"])))
        images = [(dataset_root / str(row["image"])).resolve() for row in positive_records]
        results = model.predict(
            source=[str(path) for path in images],
            imgsz=int(plan["stage1"]["inputSize"]),
            conf=float(plan["stage1"]["scoreThreshold"]),
            iou=0.7,
            max_det=int(plan["stage1"]["maximumCandidatesPerImage"]),
            device=device,
            retina_masks=True,
            rect=False,
            stream=True,
            verbose=False,
        )
        by_name = {str(row["fileName"]): row for row in positive_records}
        seen_parents: set[str] = set()
        variants = {"base": 0.0, "shift_x_neg06": -0.06, "shift_x_pos06": 0.06}
        for result in results:
            image_path = Path(str(result.path)).resolve()
            parent = by_name.get(image_path.name)
            if parent is None or image_path.name in seen_parents:
                raise ValueError(f"stage1结果父图身份异常：{image_path.name}")
            seen_parents.add(image_path.name)
            label_path = dataset_root / str(parent["label"])
            if sha256_file(image_path) != parent["imageSha256"] or sha256_file(label_path) != parent["labelSha256"]:
                raise ValueError(f"循环012父图或标签哈希漂移：{image_path.name}")
            truths = LEGACY.parse_polygons(label_path)
            with Image.open(image_path) as encoded:
                source = ImageOps.exif_transpose(encoded).convert("RGB")
            width, height = source.size
            boxes = result.boxes.xyxy.detach().cpu().numpy() if result.boxes is not None else np.empty((0, 4))
            scores = result.boxes.conf.detach().cpu().numpy() if result.boxes is not None else np.empty((0,))
            masks = list(result.masks.xy) if result.masks is not None else []
            if not (len(boxes) == len(scores) == len(masks)):
                raise ValueError(f"stage1 box/score/mask数量不一致：{image_path.name}")
            selected, local = associate_proposals(boxes, scores, masks, truths, width, height)
            counters["parentImages"] += 1
            counters["parentTruths"] += len(truths)
            for key in local:
                counters[key] += local[key]
            split = "val" if parent["sourceGroup"] in validation_groups else "train"
            variant_names = ["base"] if split == "val" else list(data_contract["trainVariants"])
            for truth_index, proposal in sorted(selected.items()):
                created = 0
                for variant_name in variant_names:
                    crop = proposal_crop_variant(
                        proposal["box"], width, height, float(plan["stage2"]["cropContextRatio"]), variants[variant_name]
                    )
                    if crop is None:
                        continue
                    mapped_truth = transformed_truth(truths[truth_index], width, height, crop)
                    if mapped_truth is None:
                        continue
                    output_stem = f"{image_path.stem}__n{truth_index + 1:02d}__{variant_name}"
                    relative_image = Path("images") / split / f"{output_stem}.png"
                    relative_label = Path("labels") / split / f"{output_stem}.txt"
                    save_crop(source, crop, int(plan["stage2"]["inputSize"]), temporary / relative_image)
                    (temporary / relative_label).parent.mkdir(parents=True, exist_ok=True)
                    (temporary / relative_label).write_text(LEGACY.format_polygon(mapped_truth), encoding="utf-8")
                    records.append(
                        {
                            "id": f"{split}:{output_stem}",
                            "split": split,
                            "variant": variant_name,
                            "sourceGroup": parent["sourceGroup"],
                            "parentFileName": image_path.name,
                            "parentImage": str(image_path),
                            "parentImageSha256": parent["imageSha256"],
                            "parentLabel": str(label_path.resolve()),
                            "parentLabelSha256": parent["labelSha256"],
                            "parentTruthIndex": truth_index + 1,
                            "proposalIndex": int(proposal["proposalIndex"]),
                            "proposalScore": float(proposal["score"]),
                            "proposalBox": list(proposal["box"]),
                            "proposalMaskPolygonPixels": proposal["maskPolygonPixels"],
                            "proposalMaskIou": float(proposal["maskIou"]),
                            "proposalBoxIou": float(proposal["boxIou"]),
                            "cropBox": list(crop),
                            "outputImage": relative_image.as_posix(),
                            "outputLabel": relative_label.as_posix(),
                        }
                    )
                    created += 1
                if created:
                    counters["uniqueAssociatedTruths"] += 1
                    counters[f"{split}PositiveRois"] += created
                else:
                    counters["cropRejectedTruths"] += 1
            counters["unassociatedTruths"] += len(truths) - len(selected)
        if seen_parents != set(by_name):
            raise ValueError("stage1没有精确覆盖全部train正样本父图")
        if counters["uniqueAssociatedTruths"] < int(data_contract["minimumUniqueAssociatedTruths"]):
            raise ValueError("唯一关联真值数量未达到预注册门")
        if counters["valPositiveRois"] < 100 or counters["trainPositiveRois"] < 1000:
            raise ValueError("循环013内部train/val ROI数量不足")
        for split in ("train", "val", "test"):
            (temporary / "images" / split).mkdir(parents=True, exist_ok=True)
            (temporary / "labels" / split).mkdir(parents=True, exist_ok=True)
        dataset_yaml = temporary / "dataset.yaml"
        dataset_yaml.write_text(
            f"path: {temporary.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: nail_texture\n",
            encoding="utf-8",
        )
        lineage = {
            "schemaVersion": 1,
            "decision": "development_cycle_013_proposal_conditioned_roi_lineage",
            "rolePolicy": {
                "parentsFromCycle012TrainOnly": True,
                "sourceGroupAtomicInternalSplit": True,
                "clean98UsedForTraining": False,
                "formalVal30Test100OrHoldoutUsed": False,
            },
            "inputs": {
                "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
                "cycle012Materialization": plan["inputs"]["cycle012Materialization"],
                "trainSourceGroupMap": plan["inputs"]["trainSourceGroupMap"],
                "stage1Weights": plan["stage1"]["weights"],
            },
            "validationSourceGroups": sorted(validation_groups),
            "counts": counters,
            "recordsSha256": canonical_sha256(records),
            "records": records,
        }
        lineage_path = temporary / "metadata" / "cycle013-roi-lineage-v1.json"
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        lineage_path.write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        dataset_files = inventory(temporary)
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "development_cycle_013_roi_dataset_materialized_pending_independent_audit",
            "trainingIntent": "pre-registered-development-experiment",
            "formalCandidateEligible": False,
            "outputDir": str(output_root),
            "datasetYaml": "dataset.yaml",
            "inputs": lineage["inputs"],
            "rolePolicy": lineage["rolePolicy"],
            "validationSourceGroups": sorted(validation_groups),
            "counts": counters,
            "recordsSha256": lineage["recordsSha256"],
            "datasetFileCount": len(dataset_files),
            "datasetFilesSha256": canonical_sha256(dataset_files),
            "datasetFiles": dataset_files,
            "errors": [],
        }
        os.replace(temporary, output_root)
        return report
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_report(report_path: Path) -> dict[str, Any]:
    report = read_json(report_path.resolve())
    if report.get("decision") != "development_cycle_013_roi_dataset_materialized_pending_independent_audit":
        raise ValueError("循环013物化报告状态无效")
    root = Path(str(report.get("outputDir", ""))).resolve()
    plan_path = Path(str(report.get("inputs", {}).get("plan", {}).get("path", ""))).resolve()
    if not root.is_dir() or not plan_path.is_file() or sha256_file(plan_path) != report["inputs"]["plan"]["sha256"]:
        raise ValueError("循环013输出目录或计划绑定漂移")
    plan, materialization, _, dataset_root = validate_inputs(plan_path)
    if report.get("rolePolicy") != {
        "parentsFromCycle012TrainOnly": True,
        "sourceGroupAtomicInternalSplit": True,
        "clean98UsedForTraining": False,
        "formalVal30Test100OrHoldoutUsed": False,
    }:
        raise ValueError("循环013物化角色策略漂移")
    lineage_path = root / "metadata" / "cycle013-roi-lineage-v1.json"
    lineage = read_json(lineage_path)
    records = lineage.get("records")
    if not isinstance(records, list) or canonical_sha256(records) != report.get("recordsSha256"):
        raise ValueError("循环013lineage记录漂移")
    split_groups = {"train": set(), "val": set()}
    for index, item in enumerate(records, 1):
        split = str(item.get("split", ""))
        if split not in split_groups:
            raise ValueError(f"循环013记录角色非法：{index}")
        split_groups[split].add(str(item.get("sourceGroup", "")))
        parent_image = Path(str(item["parentImage"])).resolve()
        parent_label = Path(str(item["parentLabel"])).resolve()
        if parent_image.parent != (dataset_root / "images" / "train").resolve() or parent_label.parent != (dataset_root / "labels" / "train").resolve():
            raise ValueError(f"循环013记录读取了非train父角色：{index}")
        if sha256_file(parent_image) != item["parentImageSha256"] or sha256_file(parent_label) != item["parentLabelSha256"]:
            raise ValueError(f"循环013父证据漂移：{index}")
        truths = LEGACY.parse_polygons(parent_label)
        truth_index = int(item["parentTruthIndex"]) - 1
        if not 0 <= truth_index < len(truths):
            raise ValueError(f"循环013真值序号非法：{index}")
        with Image.open(parent_image) as encoded:
            source = ImageOps.exif_transpose(encoded).convert("RGB")
        crop = tuple(int(value) for value in item["cropBox"])
        expected_truth = transformed_truth(truths[truth_index], source.width, source.height, crop)
        if expected_truth is None:
            raise ValueError(f"循环013映射真值无效：{index}")
        label_path = root / str(item["outputLabel"])
        image_path = root / str(item["outputImage"])
        if label_path.read_text(encoding="utf-8") != LEGACY.format_polygon(expected_truth):
            raise ValueError(f"循环013ROI标签不是父真值映射：{index}")
        expected_pixels = np.asarray(source.crop(crop).resize((384, 384), Image.Resampling.LANCZOS))
        with Image.open(image_path) as encoded:
            actual_pixels = np.asarray(encoded.convert("RGB"))
        if not np.array_equal(expected_pixels, actual_pixels):
            raise ValueError(f"循环013ROI图片不可从父图重放：{index}")
    if split_groups["train"] & split_groups["val"]:
        raise ValueError("循环013内部train/val来源组交叠")
    current_files = inventory(root)
    if current_files != report.get("datasetFiles") or canonical_sha256(current_files) != report.get("datasetFilesSha256"):
        raise ValueError("循环013物化文件树漂移")
    if list((root / "images" / "test").iterdir()) or list((root / "labels" / "test").iterdir()):
        raise ValueError("循环013数据意外包含test")
    return report


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告输出已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--device", default="0")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        verified = verify_report(args.verify_report)
        print(json.dumps({"ok": True, "decision": verified["decision"], "datasetFilesSha256": verified["datasetFilesSha256"]}, ensure_ascii=True))
        return 0
    if args.plan is None:
        parser.error("缺少--plan")
    plan, materialization, source_map, dataset_root = validate_inputs(args.plan.resolve())
    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "decision": "cycle013_roi_materialization_dry_run",
            "planSha256": sha256_file(args.plan.resolve()),
            "parentDataset": str(dataset_root),
            "parentCounts": materialization["counts"],
            "sourceMapCounts": source_map["counts"],
            "stage1WeightsSha256": plan["stage1"]["weights"]["sha256"],
            "formalVal30Test100OrHoldoutUsed": False,
        }, ensure_ascii=True))
        return 0
    if args.output_dir is None or args.report is None:
        parser.error("真实物化缺少--output-dir或--report")
    report = build_dataset(args.plan.resolve(), args.output_dir.resolve(), args.device)
    write_atomic(args.report.resolve(), report)
    print(json.dumps({"ok": True, "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
