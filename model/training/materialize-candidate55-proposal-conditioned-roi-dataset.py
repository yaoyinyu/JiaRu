#!/usr/bin/env python3
"""在candidate53 ROI数据之上追加真实stage1候选条件化的train正裁片。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from importlib.util import module_from_spec, spec_from_file_location


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def load_candidate53_helpers():
    path = Path(__file__).with_name("materialize-candidate53-single-nail-roi-dataset.py")
    spec = spec_from_file_location("candidate53_materializer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载candidate53 ROI工具")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = load_candidate53_helpers()


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
    path = root / "metadata" / "sources-isolation.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        name = str(row.get("fileName", ""))
        if not name or name in result:
            raise ValueError("父数据来源表存在空文件名或重复文件名")
        result[name] = {key: str(value or "") for key, value in row.items()}
    return result


def image_map(directory: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            if path.stem in result:
                raise ValueError(f"重复图片stem：{path.stem}")
            result[path.stem] = path
    return result


def proposal_mask(points: list[list[float]], width: int, height: int) -> np.ndarray:
    pixels = np.asarray(points, dtype=np.float32)
    if pixels.ndim != 2 or pixels.shape[0] < 3 or pixels.shape[1] != 2:
        raise ValueError("stage1候选polygon非法")
    pixels[:, 0] = np.clip(pixels[:, 0], 0, width - 1)
    pixels[:, 1] = np.clip(pixels[:, 1], 0, height - 1)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(pixels).astype(np.int32)], 1)
    if int(mask.sum()) == 0:
        raise ValueError("stage1候选polygon栅格化为空")
    return mask


def copy_base_dataset(base_root: Path, temporary: Path) -> None:
    for split in ("train", "val", "test"):
        source_images = base_root / "images" / split
        source_labels = base_root / "labels" / split
        target_images = temporary / "images" / split
        target_labels = temporary / "labels" / split
        target_images.mkdir(parents=True, exist_ok=True)
        target_labels.mkdir(parents=True, exist_ok=True)
        for source_dir, target_dir in ((source_images, target_images), (source_labels, target_labels)):
            for path in sorted(source_dir.iterdir()):
                if path.is_file() and not path.name.endswith(".cache"):
                    shutil.copy2(path, target_dir / path.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建candidate55真实候选条件化ROI数据")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    output_root = Path(args.output_dir).resolve()
    if output_root.exists():
        raise ValueError(f"输出目录必须是全新的：{output_root}")
    plan = read_json(plan_path)
    if plan.get("candidate") != "candidate55" or plan.get("entryGate", {}).get("decision") != "closed_with_runtime_semantics_mismatch_confirmed":
        raise ValueError("candidate55计划或入口门状态不正确")
    dataset = plan["dataset"]
    stage1 = plan["stage1"]
    base_root = Path(dataset["baseCandidate53RoiDataset"]).resolve()
    base_audit_path = Path(dataset["baseCandidate53RoiAudit"]).resolve()
    parent_root = Path(dataset["parentCandidate52Dataset"]).resolve()
    parent_audit_path = Path(dataset["parentCandidate52InputAudit"]).resolve()
    weights = Path(stage1["weights"]).resolve()
    evidence_path = Path(plan["entryGate"]["evidence"]).resolve()
    for path, expected in (
        (base_audit_path, dataset["baseCandidate53RoiAuditSha256"]),
        (parent_audit_path, dataset["parentCandidate52InputAuditSha256"]),
        (weights, stage1["weightsSha256"]),
        (evidence_path, plan["entryGate"]["evidenceSha256"]),
    ):
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"计划绑定输入缺失或哈希漂移：{path}")
    base_audit = read_json(base_audit_path)
    parent_audit = read_json(parent_audit_path)
    if base_audit.get("decision") != "approved_candidate53_single_nail_roi_training_input":
        raise ValueError("candidate53基础ROI审计未批准")
    if Path(base_audit.get("outputDir", "")).resolve() != base_root:
        raise ValueError("candidate53基础ROI审计未绑定指定数据集")
    if parent_audit.get("decision") != "approved_candidate_training_input":
        raise ValueError("candidate52父训练输入审计未批准")
    if Path(parent_audit.get("outputDir", "")).resolve() != parent_root:
        raise ValueError("candidate52父训练输入审计未绑定指定数据集")
    if image_map(parent_root / "images" / "test"):
        raise ValueError("父训练数据不得包含test图片")

    output_size = int(plan["training"]["inputSize"])
    context_ratio = float(stage1["cropContextRatio"])
    sources = read_sources(parent_root)
    base_lineage = read_json(base_root / "metadata" / "candidate53-single-nail-roi-lineage-v1.json")
    excluded_names = {
        str(item["fileName"])
        for item in base_lineage.get("excludedParents", [])
        if item.get("split") == "train"
    }
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f"{output_root.name}-", dir=output_root.parent))
    selected: dict[tuple[str, int], dict[str, Any]] = {}
    counters = {
        "trainParents": 0, "trainTruthMasks": 0, "rawStage1Proposals": 0,
        "uniqueAssociatedProposals": 0, "ambiguousProposalsRejected": 0,
        "unmatchedProposalsIgnored": 0, "invalidOrTruncatedCropsRejected": 0,
        "duplicateProposalsSuppressed": 0,
    }
    try:
        copy_base_dataset(base_root, temporary)
        from ultralytics import YOLO

        model = YOLO(str(weights))
        images = image_map(parent_root / "images" / "train")
        results = model.predict(
            source=str(parent_root / "images" / "train"), imgsz=int(stage1["inputSize"]),
            conf=float(stage1["proposalThreshold"]), iou=0.7,
            max_det=int(stage1["maximumProposalsPerImage"]), device=args.device,
            retina_masks=True, rect=False, stream=True, verbose=False,
        )
        processed: set[Path] = set()
        for result in results:
            image_path = Path(str(result.path)).resolve()
            if image_path.stem not in images or image_path in processed:
                raise ValueError(f"stage1返回未知或重复图片：{image_path}")
            processed.add(image_path)
            label_path = parent_root / "labels" / "train" / f"{image_path.stem}.txt"
            polygons = HELPERS.parse_polygons(label_path)
            role = sources.get(image_path.name)
            if role is None or role.get("split") != "train":
                raise ValueError(f"父图缺少train来源绑定：{image_path.name}")
            if role.get("imageSha256") != sha256_file(image_path):
                raise ValueError(f"父图哈希漂移：{image_path.name}")
            if not polygons or role.get("role") == "hard-negative" or image_path.name in excluded_names:
                continue
            counters["trainParents"] += 1
            counters["trainTruthMasks"] += len(polygons)
            with Image.open(image_path) as encoded:
                source = ImageOps.exif_transpose(encoded).convert("RGB")
            width, height = source.size
            truth_masks, truth_boxes = HELPERS.truth_masks_and_boxes(polygons, width, height)
            if result.boxes is None or result.masks is None:
                continue
            boxes = result.boxes.xyxy.detach().cpu().numpy()
            scores = result.boxes.conf.detach().cpu().numpy()
            outlines = result.masks.xy
            if not (len(boxes) == len(scores) == len(outlines)):
                raise ValueError("stage1候选box/score/polygon数量不一致")
            for proposal_index, (raw_box, score, outline) in enumerate(zip(boxes, scores, outlines, strict=True)):
                counters["rawStage1Proposals"] += 1
                rounded_outline = [[round(float(x), 4), round(float(y), 4)] for x, y in outline]
                try:
                    predicted_mask = proposal_mask(rounded_outline, width, height)
                except ValueError:
                    counters["invalidOrTruncatedCropsRejected"] += 1
                    continue
                proposal_box = tuple(round(float(value), 4) for value in raw_box)
                mask_ious = [HELPERS.mask_iou(predicted_mask, truth) for truth in truth_masks]
                box_ious = [HELPERS.box_iou(proposal_box, truth_box) for truth_box in truth_boxes]
                associations = [
                    index for index, (miou, biou) in enumerate(zip(mask_ious, box_ious, strict=True))
                    if miou >= 0.10 or biou >= 0.10
                ]
                if not associations:
                    counters["unmatchedProposalsIgnored"] += 1
                    continue
                if len(associations) != 1:
                    counters["ambiguousProposalsRejected"] += 1
                    continue
                truth_index = associations[0]
                crop_box = HELPERS.proposal_crop_box(proposal_box, width, height, context_ratio)
                if crop_box is None:
                    counters["invalidOrTruncatedCropsRejected"] += 1
                    continue
                try:
                    transformed = HELPERS.transformed_polygon(polygons[truth_index], width, height, crop_box)
                except ValueError:
                    counters["invalidOrTruncatedCropsRejected"] += 1
                    continue
                counters["uniqueAssociatedProposals"] += 1
                candidate = {
                    "parentImage": str(image_path), "parentImageSha256": role["imageSha256"],
                    "parentLabel": str(label_path), "parentLabelSha256": sha256_file(label_path),
                    "sourceGroup": role["sourceGroup"], "parentPolygonIndex": truth_index + 1,
                    "proposalIndex": proposal_index, "proposalScore": round(float(score), 8),
                    "proposalBox": list(proposal_box), "proposalPolygonPixels": rounded_outline,
                    "proposalMaskIou": round(mask_ious[truth_index], 8),
                    "proposalBoxIou": round(box_ious[truth_index], 8), "cropBox": list(crop_box),
                    "transformedPolygon": transformed, "sourceImage": source,
                }
                key = (image_path.name, truth_index + 1)
                rank = (max(mask_ious[truth_index], box_ious[truth_index]), float(score), -proposal_index)
                previous = selected.get(key)
                if previous is None or rank > previous["rank"]:
                    if previous is not None:
                        counters["duplicateProposalsSuppressed"] += 1
                    candidate["rank"] = rank
                    selected[key] = candidate
                else:
                    counters["duplicateProposalsSuppressed"] += 1
        if processed != {path.resolve() for path in images.values()}:
            raise ValueError("stage1未处理完整train分片")

        records: list[dict[str, Any]] = []
        for ordinal, (key, item) in enumerate(sorted(selected.items()), 1):
            image_path = Path(item["parentImage"])
            with Image.open(image_path) as encoded:
                source = ImageOps.exif_transpose(encoded).convert("RGB")
            output_stem = f"proposal__{ordinal:05d}__{hashlib.sha256(f'{key[0]}:{key[1]}'.encode()).hexdigest()[:12]}"
            output_image = temporary / "images" / "train" / f"{output_stem}.png"
            output_label = temporary / "labels" / "train" / f"{output_stem}.txt"
            HELPERS.save_rgb_crop(source, tuple(item["cropBox"]), output_image, output_size)
            output_label.write_text(HELPERS.format_polygon(item["transformedPolygon"]), encoding="utf-8", newline="\n")
            record = {key: value for key, value in item.items() if key not in {"rank", "transformedPolygon", "sourceImage"}}
            record.update({
                "id": f"train:{output_stem}", "split": "train", "kind": "proposal-conditioned-positive",
                "associationRule": "exactly-one-truth-with-mask-iou-or-box-iou-at-least-0.10",
                "labelSource": "authoritative-parent-hard-polygon",
                "outputImage": output_image.relative_to(temporary).as_posix(),
                "outputImageSha256": sha256_file(output_image),
                "outputLabel": output_label.relative_to(temporary).as_posix(),
                "outputLabelSha256": sha256_file(output_label),
            })
            records.append(record)

        counters["proposalConditionedPositiveRois"] = len(records)
        base_counts = base_audit["counts"]
        final_counts = {
            "trainPositiveRois": int(base_counts["trainPositiveRois"]) + len(records),
            "trainNegativeRois": int(base_counts["trainNegativeRois"]),
            "valPositiveRois": int(base_counts["valPositiveRois"]),
            "valNegativeRois": int(base_counts["valNegativeRois"]),
            "testImages": 0,
        }
        dataset_yaml = temporary / "dataset.yaml"
        dataset_yaml.write_text(
            "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n\n"
            "names:\n  0: nail_texture\n\ntask: segment\nclass_count: 1\nimage_size: 256\n\n"
            "metadata:\n  dataset_version: candidate55-proposal-conditioned-roi/v1\n"
            "  lineage: metadata/candidate55-proposal-conditioned-roi-lineage-v1.json\n",
            encoding="utf-8", newline="\n",
        )
        records.sort(key=lambda row: row["id"])
        lineage_path = temporary / "metadata" / "candidate55-proposal-conditioned-roi-lineage-v1.json"
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        lineage = {
            "schemaVersion": 1, "decision": "candidate55_proposal_conditioned_roi_lineage",
            "inputs": {
                "plan": str(plan_path), "planSha256": sha256_file(plan_path),
                "runtimeEvidence": str(evidence_path), "runtimeEvidenceSha256": sha256_file(evidence_path),
                "baseDataset": str(base_root), "baseAudit": str(base_audit_path),
                "baseAuditSha256": sha256_file(base_audit_path),
                "parentDataset": str(parent_root), "parentAudit": str(parent_audit_path),
                "parentAuditSha256": sha256_file(parent_audit_path),
                "stage1Weights": str(weights), "stage1WeightsSha256": sha256_file(weights),
            },
            "parameters": {
                "proposalInputSize": int(stage1["inputSize"]), "proposalConfidence": float(stage1["proposalThreshold"]),
                "maximumProposalsPerImage": int(stage1["maximumProposalsPerImage"]), "squareLetterbox": True,
                "contextRatio": context_ratio, "outputSize": output_size,
                "associationMaskOrBoxIouInclusive": 0.10, "oneBestProposalPerTruth": True,
            },
            "rolePolicy": {"proposalConditionedTrainFromTrainOnly": True, "baseValCopiedUnchanged": True, "testUsed": False, "holdoutUsed": False},
            "baseCounts": base_counts, "counts": {**counters, **final_counts},
            "recordsSha256": canonical_sha256(records), "records": records,
        }
        lineage_path.write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        report_path = temporary / "candidate55-proposal-conditioned-roi-materialization-v1.json"
        files = HELPERS.inventory(temporary, {report_path.resolve()})
        report = {
            "schemaVersion": 1, "ok": True,
            "decision": "candidate55_proposal_conditioned_roi_materialized_pending_independent_audit",
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
