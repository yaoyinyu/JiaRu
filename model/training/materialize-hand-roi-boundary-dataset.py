#!/usr/bin/env python3
"""Materialize deterministic train-only hand ROI views from approved YOLO polygons."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


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
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def parse_label(path: Path) -> list[tuple[int, list[tuple[float, float]]]]:
    polygons: list[tuple[int, list[tuple[float, float]]]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        tokens = raw.split()
        if not tokens:
            continue
        if len(tokens) < 7 or len(tokens) % 2 == 0:
            raise ValueError(f"invalid YOLO polygon at {path}:{line_number}")
        class_id = int(tokens[0])
        coordinates = [float(value) for value in tokens[1:]]
        points = list(zip(coordinates[0::2], coordinates[1::2], strict=True))
        if class_id != 0 or any(not math.isfinite(v) or v < 0 or v > 1 for point in points for v in point):
            raise ValueError(f"invalid class or normalized coordinate at {path}:{line_number}")
        polygons.append((class_id, points))
    return polygons


def image_by_stem(directory: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.stem in result:
            raise ValueError(f"duplicate image stem: {path.stem}")
        result[path.stem] = path
    return result


def copy_tree_files(source: Path, destination: Path) -> None:
    for artifact in sorted(source.rglob("*")):
        if not artifact.is_file() or artifact.name.endswith(".cache"):
            continue
        relative = artifact.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, target)


def format_label(polygons: list[tuple[int, list[tuple[float, float]]]]) -> str:
    lines = []
    for class_id, points in polygons:
        coordinates = " ".join(f"{value:.8f}" for point in points for value in point)
        lines.append(f"{class_id} {coordinates}")
    return "\n".join(lines) + "\n"


def build_roi(
    image_path: Path,
    label_path: Path,
    output_image: Path,
    output_label: Path,
    padding_ratio: float,
    maximum_crop_area_ratio: float,
    minimum_polygon_margin: int,
) -> dict[str, Any] | None:
    polygons = parse_label(label_path)
    if not polygons:
        return None
    with Image.open(image_path) as encoded:
        source = ImageOps.exif_transpose(encoded).convert("RGB")
    width, height = source.size
    pixel_polygons = [
        [(x * width, y * height) for x, y in points] for _, points in polygons
    ]
    xs = [x for polygon in pixel_polygons for x, _ in polygon]
    ys = [y for polygon in pixel_polygons for _, y in polygon]
    union_width = max(xs) - min(xs)
    union_height = max(ys) - min(ys)
    pad_x = max(minimum_polygon_margin, math.ceil(union_width * padding_ratio))
    pad_y = max(minimum_polygon_margin, math.ceil(union_height * padding_ratio))
    left = max(0, math.floor(min(xs) - pad_x))
    top = max(0, math.floor(min(ys) - pad_y))
    right = min(width, math.ceil(max(xs) + pad_x))
    bottom = min(height, math.ceil(max(ys) + pad_y))
    crop_width, crop_height = right - left, bottom - top
    area_ratio = (crop_width * crop_height) / (width * height)
    if area_ratio > maximum_crop_area_ratio:
        return None
    margins = (
        min(xs) - left,
        min(ys) - top,
        right - max(xs),
        bottom - max(ys),
    )
    if min(margins) < minimum_polygon_margin:
        return None
    transformed: list[tuple[int, list[tuple[float, float]]]] = []
    for (class_id, _), pixel_points in zip(polygons, pixel_polygons, strict=True):
        normalized = [
            ((x - left) / crop_width, (y - top) / crop_height)
            for x, y in pixel_points
        ]
        if any(value <= 0 or value >= 1 for point in normalized for value in point):
            raise ValueError(f"ROI polygon touches or escapes crop: {image_path.name}")
        transformed.append((class_id, normalized))

    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_label.parent.mkdir(parents=True, exist_ok=True)
    source.crop((left, top, right, bottom)).save(
        output_image, format="PNG", compress_level=1
    )
    output_label.write_text(format_label(transformed), encoding="utf-8", newline="\n")
    return {
        "parentImage": str(image_path),
        "parentImageSha256": sha256_file(image_path),
        "parentLabel": str(label_path),
        "parentLabelSha256": sha256_file(label_path),
        "outputImage": output_image.name,
        "outputImageSha256": sha256_file(output_image),
        "outputLabel": output_label.name,
        "outputLabelSha256": sha256_file(output_label),
        "parentSize": {"width": width, "height": height},
        "cropBox": [left, top, right, bottom],
        "cropSize": {"width": crop_width, "height": crop_height},
        "cropAreaRatio": round(area_ratio, 8),
        "pixelScaleGain": round(math.sqrt(1 / area_ratio), 8),
        "polygonCount": len(polygons),
        "minimumPolygonMarginPixels": round(min(margins), 4),
    }


def dataset_inventory(root: Path, excluded: set[Path]) -> list[dict[str, str]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create hash-bound train-only all-nails ROI views without clipping polygons."
    )
    parser.add_argument("--input-dataset", required=True)
    parser.add_argument("--input-audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--padding-ratio", type=float, default=0.20)
    parser.add_argument("--maximum-crop-area-ratio", type=float, default=0.85)
    parser.add_argument("--minimum-polygon-margin", type=int, default=2)
    parser.add_argument(
        "--selection-modulus",
        type=int,
        default=1,
        help="Keep only parents whose image SHA-256 modulo this value equals --selection-remainder.",
    )
    parser.add_argument("--selection-remainder", type=int, default=0)
    args = parser.parse_args()
    if not 0 < args.padding_ratio <= 1:
        raise ValueError("--padding-ratio must be in (0, 1]")
    if not 0 < args.maximum_crop_area_ratio < 1:
        raise ValueError("--maximum-crop-area-ratio must be in (0, 1)")
    if args.minimum_polygon_margin < 1:
        raise ValueError("--minimum-polygon-margin must be positive")
    if args.selection_modulus < 1:
        raise ValueError("--selection-modulus must be positive")
    if not 0 <= args.selection_remainder < args.selection_modulus:
        raise ValueError("--selection-remainder must be in [0, selection-modulus)")

    input_root = Path(args.input_dataset).resolve()
    input_audit_path = Path(args.input_audit).resolve()
    output_root = Path(args.output_dir).resolve()
    if output_root.exists():
        raise ValueError(f"output directory already exists: {output_root}")
    audit = read_json(input_audit_path)
    if audit.get("decision") != "approved_candidate_training_input":
        raise ValueError("input audit is not an approved candidate-training report")
    if Path(str(audit.get("outputDir", ""))).resolve() != input_root:
        raise ValueError("input audit does not bind the requested dataset root")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f"{output_root.name}-", dir=output_root.parent))
    try:
        copy_tree_files(input_root, temporary)
        dataset_yaml = temporary / "dataset.yaml"
        yaml_text = dataset_yaml.read_text(encoding="utf-8")
        yaml_text = yaml_text.replace(
            "dataset_version: canonical-candidate-training-dataset/v1",
            "dataset_version: canonical-hand-roi-candidate-training-dataset/v1\n"
            "  augmentation: train-only-all-nails-roi-v1",
        )
        dataset_yaml.write_text(yaml_text, encoding="utf-8", newline="\n")
        train_images = image_by_stem(input_root / "images" / "train")
        lineage: list[dict[str, Any]] = []
        skipped = 0
        selection_skipped = 0
        geometry_skipped = 0
        for stem, image_path in train_images.items():
            label_path = input_root / "labels" / "train" / f"{stem}.txt"
            if not label_path.is_file():
                raise ValueError(f"missing train label: {label_path}")
            parent_image_sha256 = sha256_file(image_path)
            if int(parent_image_sha256, 16) % args.selection_modulus != args.selection_remainder:
                skipped += 1
                selection_skipped += 1
                continue
            output_stem = f"{stem}__handroi_v1"
            record = build_roi(
                image_path,
                label_path,
                temporary / "images" / "train" / f"{output_stem}.png",
                temporary / "labels" / "train" / f"{output_stem}.txt",
                args.padding_ratio,
                args.maximum_crop_area_ratio,
                args.minimum_polygon_margin,
            )
            if record is None:
                skipped += 1
                geometry_skipped += 1
                continue
            record["parentStem"] = stem
            record["outputStem"] = output_stem
            lineage.append(record)

        lineage_path = temporary / "metadata" / "hand-roi-lineage-v1.json"
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        lineage_document = {
            "schemaVersion": 1,
            "decision": "train_only_all_nails_roi_lineage",
            "policy": {
                "allParentPolygonsPreservedExactlyOnce": True,
                "partialPolygonsProhibited": True,
                "validationAugmentationProhibited": True,
                "testAugmentationProhibited": True,
                "modelOutputUsed": False,
            },
            "parameters": {
                "paddingRatio": args.padding_ratio,
                "maximumCropAreaRatio": args.maximum_crop_area_ratio,
                "minimumPolygonMarginPixels": args.minimum_polygon_margin,
                "selectionModulus": args.selection_modulus,
                "selectionRemainder": args.selection_remainder,
                "selectionIdentity": "parent-image-sha256",
            },
            "counts": {"created": len(lineage), "skipped": skipped},
            "itemsSha256": canonical_sha256(lineage),
            "items": lineage,
        }
        lineage_path.write_text(
            json.dumps(lineage_document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        report_path = temporary / "candidate30-hand-roi-materialization-v1.json"
        inventory = dataset_inventory(temporary, {report_path.resolve()})
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "candidate_hand_roi_dataset_materialized_pending_independent_audit",
            "inputs": {
                "datasetRoot": str(input_root),
                "datasetYamlSha256": sha256_file(input_root / "dataset.yaml"),
                "candidateInputAudit": str(input_audit_path),
                "candidateInputAuditSha256": sha256_file(input_audit_path),
                "parentDatasetFilesSha256": audit.get("datasetFilesSha256"),
            },
            "outputDir": str(output_root),
            "datasetYaml": str(output_root / "dataset.yaml"),
            "lineage": {
                "path": str(output_root / "metadata" / lineage_path.name),
                "sha256": sha256_file(lineage_path),
                "itemsSha256": lineage_document["itemsSha256"],
            },
            "counts": {
                "parentTrainImages": len(train_images),
                "createdRoiImages": len(lineage),
                "skippedTrainImages": skipped,
                "selectionSkippedTrainImages": selection_skipped,
                "geometrySkippedTrainImages": geometry_skipped,
                "outputTrainImages": len(train_images) + len(lineage),
                "validationImages": len(image_by_stem(input_root / "images" / "val")),
                "testImages": len(image_by_stem(input_root / "images" / "test")),
            },
            "datasetFilesSha256": canonical_sha256(inventory),
            "datasetFiles": inventory,
            "trainingUse": "prohibited-until-independent-audit",
            "errors": [],
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"output": str(output_root), "created": len(lineage), "skipped": skipped}))


if __name__ == "__main__":
    main()
