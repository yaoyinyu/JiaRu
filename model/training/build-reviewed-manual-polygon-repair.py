#!/usr/bin/env python3
"""Build audited hybrid/manual nail polygon candidates for original-resolution review.

The manifest can retain known-good polygons from an earlier annotation document
and replace only failed nails with reviewer-drawn polygons. Output remains a
review candidate; this tool never promotes annotations to training or test truth.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and validate reviewed hybrid/manual nail polygon candidates."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--output-annotations", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--crop-dir")
    parser.add_argument("--prompts-output")
    parser.add_argument("--report", required=True)
    return parser


def resolve_input_path(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def normalize_points(raw: Any, width: int, height: int) -> list[dict[str, float]]:
    if not isinstance(raw, list) or len(raw) < 3:
        raise ValueError("manual polygon must contain at least three points")
    points: list[dict[str, float]] = []
    for item in raw:
        if not isinstance(item, dict) or "x" not in item or "y" not in item:
            raise ValueError("manual polygon points must contain x and y")
        x = float(item["x"])
        y = float(item["y"])
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"polygon point is outside the image: ({x}, {y})")
        points.append({"x": int(x) if x.is_integer() else x, "y": int(y) if y.is_integer() else y})
    return points


def validate_polygons(annotations: list[dict[str, Any]]) -> list[Polygon]:
    shapes: list[Polygon] = []
    for index, annotation in enumerate(annotations, start=1):
        shape = Polygon([(point["x"], point["y"]) for point in annotation["polygon"]])
        if not shape.is_valid:
            raise ValueError(f"nail {index} polygon is invalid")
        if shape.area <= 1:
            raise ValueError(f"nail {index} polygon area is empty")
        shapes.append(shape)
    for first_index, first in enumerate(shapes):
        for second_index in range(first_index + 1, len(shapes)):
            overlap = first.intersection(shapes[second_index]).area
            if overlap > 0:
                raise ValueError(
                    f"nails {first_index + 1} and {second_index + 1} overlap by {overlap:.4f} pixels"
                )
    return shapes


def draw_overlay(image_path: Path, annotations: list[dict[str, Any]], output_path: Path) -> None:
    with Image.open(image_path) as source:
        overlay = source.convert("RGB")
    draw = ImageDraw.Draw(overlay, "RGBA")
    for index, annotation in enumerate(annotations, start=1):
        points = [(point["x"], point["y"]) for point in annotation["polygon"]]
        draw.polygon(points, fill=(0, 220, 90, 80), outline=(0, 190, 70, 255), width=3)
        draw.text(points[0], str(index), fill=(255, 30, 30, 255), stroke_width=2, stroke_fill="white")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, quality=94)


def write_zoom_crops(
    image_path: Path,
    overlay_path: Path,
    annotations: list[dict[str, Any]],
    crop_dir: Path | None,
) -> list[dict[str, str]]:
    if crop_dir is None:
        return []
    crop_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        original = source.convert("RGB")
    with Image.open(overlay_path) as source:
        overlay = source.convert("RGB")
    outputs: list[dict[str, str]] = []
    for index, annotation in enumerate(annotations, start=1):
        xs = [float(point["x"]) for point in annotation["polygon"]]
        ys = [float(point["y"]) for point in annotation["polygon"]]
        padding = 24
        bounds = (
            max(0, int(min(xs)) - padding),
            max(0, int(min(ys)) - padding),
            min(overlay.width, int(max(xs)) + padding + 1),
            min(overlay.height, int(max(ys)) + padding + 1),
        )
        overlay_crop = overlay.crop(bounds)
        original_crop = original.crop(bounds)
        size = (overlay_crop.width * 2, overlay_crop.height * 2)
        overlay_crop = overlay_crop.resize(size, Image.Resampling.LANCZOS)
        original_crop = original_crop.resize(size, Image.Resampling.LANCZOS)
        overlay_output = crop_dir / f"{overlay_path.stem}-n{index}-2x.png"
        source_output = crop_dir / f"{Path(image_path).stem}-source-n{index}-2x.png"
        overlay_crop.save(overlay_output)
        original_crop.save(source_output)
        outputs.append(
            {
                "source": str(source_output.resolve()),
                "overlay": str(overlay_output.resolve()),
            }
        )
    return outputs


def build_item(
    item: dict[str, Any],
    manifest_path: Path,
    image_dir: Path,
    output_dir: Path,
    overlay_dir: Path,
    crop_dir: Path | None,
) -> dict[str, Any]:
    file_name = str(item["fileName"])
    image_path = (image_dir / file_name).resolve()
    if not image_path.is_file() or image_path.parent != image_dir:
        raise ValueError(f"image is missing or escapes image-dir: {file_name}")
    with Image.open(image_path) as image:
        width, height = image.size

    source_path = resolve_input_path(str(item["sourceAnnotationPath"]), manifest_path)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_image = source.get("image", {})
    if source_image.get("fileName") != file_name:
        raise ValueError("source annotation fileName mismatch")
    if (int(source_image.get("width", 0)), int(source_image.get("height", 0))) != (width, height):
        raise ValueError("source annotation dimensions mismatch")
    source_group = str(item.get("sourceGroup") or source_image.get("sourceGroup") or "")
    if not source_group or source_group != source_image.get("sourceGroup"):
        raise ValueError("sourceGroup mismatch or missing")

    annotations: list[dict[str, Any]] = []
    retained_count = 0
    manual_count = 0
    source_annotations = source.get("annotations", [])
    for index, nail in enumerate(item.get("nails", []), start=1):
        has_source = "sourceIndex" in nail
        has_manual = "polygon" in nail
        if has_source == has_manual:
            raise ValueError(f"nail {index} must define exactly one of sourceIndex or polygon")
        if has_source:
            source_index = int(nail["sourceIndex"])
            if source_index < 1 or source_index > len(source_annotations):
                raise ValueError(f"nail {index} sourceIndex is out of range")
            annotation = deepcopy(source_annotations[source_index - 1])
            annotation["polygon"] = normalize_points(annotation.get("polygon"), width, height)
            annotation.setdefault("attributes", {})["repairDisposition"] = "retained-reviewed-source-polygon"
            retained_count += 1
        else:
            annotation = {
                "label": "nail_texture",
                "polygon": normalize_points(nail["polygon"], width, height),
                "attributes": {
                    "fingerHint": "unknown",
                    "shape": "unknown",
                    "quality": 4,
                    "occluded": False,
                    "artificialTip": True,
                    "annotationMethod": "codex-original-resolution-manual",
                    "repairDisposition": "manual-replacement-after-sam-failure",
                },
            }
            annotation["attributes"].update(nail.get("attributes", {}))
            manual_count += 1
        annotation["id"] = f"n{index}"
        annotation["label"] = "nail_texture"
        annotations.append(annotation)

    if not annotations:
        raise ValueError("item does not contain any nails")
    shapes = validate_polygons(annotations)
    document = {
        "version": "nail-texture-dataset/v1",
        "image": {
            "id": Path(file_name).stem,
            "fileName": file_name,
            "width": width,
            "height": height,
            "sourceGroup": source_group,
            "negative": False,
        },
        "annotations": annotations,
    }
    output_path = output_dir / f"{Path(file_name).stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overlay_path = overlay_dir / f"{Path(file_name).stem}-manual-reviewed-overlay.png"
    draw_overlay(image_path, annotations, overlay_path)
    zoom_paths = write_zoom_crops(image_path, overlay_path, annotations, crop_dir)
    geometry_boxes = [
        [
            round(shape.bounds[0] / width, 6),
            round(shape.bounds[1] / height, 6),
            round(shape.bounds[2] / width, 6),
            round(shape.bounds[3] / height, 6),
        ]
        for shape in shapes
    ]
    return {
        "fileName": file_name,
        "sourceGroup": source_group,
        "annotationPath": str(output_path.resolve()),
        "overlayPath": str(overlay_path.resolve()),
        "polygonCount": len(annotations),
        "retainedPolygonCount": retained_count,
        "manualPolygonCount": manual_count,
        "validPolygonCount": len(shapes),
        "pairwiseOverlapCount": 0,
        "zoomPaths": zoom_paths,
        "geometryBoxes": geometry_boxes,
    }


def main() -> None:
    args = build_parser().parse_args()
    manifest_path = Path(args.manifest).resolve()
    image_dir = Path(args.image_dir).resolve()
    output_dir = Path(args.output_annotations).resolve()
    overlay_dir = Path(args.overlay_dir).resolve()
    crop_dir = Path(args.crop_dir).resolve() if args.crop_dir else None
    prompts_path = Path(args.prompts_output).resolve() if args.prompts_output else None
    report_path = Path(args.report).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in manifest.get("images", []):
        try:
            outputs.append(build_item(item, manifest_path, image_dir, output_dir, overlay_dir, crop_dir))
        except Exception as error:  # Persist a complete batch diagnostic instead of hiding later failures.
            errors.append(f"{item.get('fileName', '<missing-fileName>')}: {error}")

    if prompts_path is not None:
        prompts = {
            "schemaVersion": 1,
            "source": "reviewed-hybrid-original-resolution-manual-polygon-bounds",
            "decision": "candidate_only_not_training_or_test_truth",
            "imageCount": len(outputs),
            "promptCount": sum(item["polygonCount"] for item in outputs),
            "images": [
                {
                    "fileName": item["fileName"],
                    "sourceGroup": item["sourceGroup"],
                    "boxes": item["geometryBoxes"],
                    "promptModes": ["box"] * item["polygonCount"],
                    "reviewReason": "audit_reviewed_polygons_against_their_true_original_resolution_bounds",
                }
                for item in outputs
            ],
        }
        prompts_path.parent.mkdir(parents=True, exist_ok=True)
        prompts_path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "ok": not errors and len(outputs) == len(manifest.get("images", [])),
        "method": "reviewed-hybrid-original-resolution-manual-polygon-repair",
        "decision": "candidate_only_not_training_or_test_truth",
        "imageCount": len(manifest.get("images", [])),
        "completedCount": len(outputs),
        "polygonCount": sum(item["polygonCount"] for item in outputs),
        "retainedPolygonCount": sum(item["retainedPolygonCount"] for item in outputs),
        "manualPolygonCount": sum(item["manualPolygonCount"] for item in outputs),
        "pairwiseOverlapCount": 0 if outputs else None,
        "geometryPromptsPath": str(prompts_path) if prompts_path is not None else None,
        "outputs": outputs,
        "errors": errors,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
