#!/usr/bin/env python3
"""Repair explicitly reviewed polygon topology defects without changing dataset use.

The manifest must name every invalid polygon and every overlap to resolve. The
tool records all area changes and emits full-image plus per-nail zoom evidence.
Outputs remain reviewed candidates and never become training or release truth
without the separate original-resolution review decision.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Repair reviewed annotation topology.")
    result.add_argument("--manifest", required=True)
    result.add_argument("--core-image-dir", required=True)
    result.add_argument("--stress-image-dir", required=True)
    result.add_argument("--core-annotations", required=True)
    result.add_argument("--stress-annotations", required=True)
    result.add_argument("--output-annotations", required=True)
    result.add_argument("--overlay-dir", required=True)
    result.add_argument("--crop-dir", required=True)
    result.add_argument("--report", required=True)
    return result


def select_polygon(shape: Any, maximum_discard_ratio: float, label: str) -> tuple[Polygon, float]:
    if shape.is_empty:
        raise ValueError(f"{label} repair produced an empty geometry")
    if shape.geom_type == "Polygon":
        return shape, 0.0
    if shape.geom_type != "MultiPolygon":
        raise ValueError(f"{label} repair produced unsupported {shape.geom_type}")
    parts = sorted(shape.geoms, key=lambda part: part.area, reverse=True)
    kept = parts[0]
    discarded = sum(part.area for part in parts[1:])
    total = kept.area + discarded
    ratio = discarded / total if total else 1.0
    if ratio > maximum_discard_ratio:
        raise ValueError(
            f"{label} discarded area ratio {ratio:.6f} exceeds {maximum_discard_ratio:.6f}"
        )
    return kept, discarded


def points(shape: Polygon) -> list[dict[str, float]]:
    return [
        {"x": round(float(x), 4), "y": round(float(y), 4)}
        for x, y in list(shape.exterior.coords)[:-1]
    ]


def draw_overlay(image_path: Path, shapes: list[Polygon], output_path: Path) -> None:
    with Image.open(image_path) as source:
        overlay = source.convert("RGB")
    draw = ImageDraw.Draw(overlay, "RGBA")
    for index, shape in enumerate(shapes, start=1):
        coords = list(shape.exterior.coords)[:-1]
        draw.polygon(coords, fill=(0, 220, 90, 80), outline=(0, 190, 70, 255), width=3)
        draw.text(coords[0], str(index), fill=(255, 30, 30, 255), stroke_width=2, stroke_fill="white")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, quality=94)


def write_crops(
    image_path: Path,
    overlay_path: Path,
    shapes: list[Polygon],
    crop_dir: Path,
) -> list[dict[str, str]]:
    crop_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        original = source.convert("RGB")
    with Image.open(overlay_path) as source:
        overlay = source.convert("RGB")
    outputs = []
    for index, shape in enumerate(shapes, start=1):
        min_x, min_y, max_x, max_y = shape.bounds
        padding = 24
        bounds = (
            max(0, int(min_x) - padding),
            max(0, int(min_y) - padding),
            min(original.width, int(max_x) + padding + 1),
            min(original.height, int(max_y) + padding + 1),
        )
        source_crop = original.crop(bounds)
        overlay_crop = overlay.crop(bounds)
        size = (source_crop.width * 2, source_crop.height * 2)
        source_crop = source_crop.resize(size, Image.Resampling.LANCZOS)
        overlay_crop = overlay_crop.resize(size, Image.Resampling.LANCZOS)
        stem = Path(image_path).stem
        source_output = crop_dir / f"{stem}-source-n{index}-2x.png"
        overlay_output = crop_dir / f"{stem}-topology-overlay-n{index}-2x.png"
        source_crop.save(source_output)
        overlay_crop.save(overlay_output)
        outputs.append({"source": str(source_output.resolve()), "overlay": str(overlay_output.resolve())})
    return outputs


def safe_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError(f"file is missing or escapes its root: {name}")
    return path


def process_item(
    item: dict[str, Any],
    roots: dict[str, tuple[Path, Path]],
    output_dir: Path,
    overlay_dir: Path,
    crop_dir: Path,
) -> dict[str, Any]:
    lane = str(item["lane"])
    if lane not in roots:
        raise ValueError(f"unsupported lane: {lane}")
    file_name = str(item["fileName"])
    image_root, annotation_root = roots[lane]
    image_path = safe_file(image_root, file_name)
    annotation_path = safe_file(annotation_root, f"{Path(file_name).stem}.json")
    document = json.loads(annotation_path.read_text(encoding="utf-8"))
    with Image.open(image_path) as image:
        size = image.size
        image.verify()
    metadata = document.get("image", {})
    if metadata.get("fileName") != file_name:
        raise ValueError("annotation fileName mismatch")
    if (int(metadata.get("width", 0)), int(metadata.get("height", 0))) != size:
        raise ValueError("annotation dimensions mismatch")

    annotations = deepcopy(document.get("annotations", []))
    shapes = [
        Polygon([(float(point["x"]), float(point["y"])) for point in annotation["polygon"]])
        for annotation in annotations
    ]
    maximum_discard_ratio = float(item.get("maximumDiscardedAreaRatio", 0.02))
    repairs = []
    requested_topology = {int(index) for index in item.get("repairTopologyIndices", [])}
    actual_invalid = {index for index, shape in enumerate(shapes, start=1) if not shape.is_valid}
    if requested_topology != actual_invalid:
        raise ValueError(
            f"invalid polygon set mismatch: requested={sorted(requested_topology)} actual={sorted(actual_invalid)}"
        )
    for index in sorted(requested_topology):
        before = shapes[index - 1]
        repaired, discarded = select_polygon(
            before.buffer(0), maximum_discard_ratio, f"nail {index} topology"
        )
        if not repaired.is_valid or repaired.area <= 1:
            raise ValueError(f"nail {index} topology repair is invalid")
        shapes[index - 1] = repaired
        repairs.append(
            {
                "type": "invalid-topology",
                "nailIndex": index,
                "beforeArea": round(before.area, 4),
                "afterArea": round(repaired.area, 4),
                "discardedComponentArea": round(discarded, 4),
            }
        )

    requested_pairs = set()
    for repair in item.get("overlapRepairs", []):
        background_index = int(repair["backgroundIndex"])
        foreground_index = int(repair["foregroundIndex"])
        pair = tuple(sorted((background_index, foreground_index)))
        if pair in requested_pairs:
            raise ValueError(f"duplicate overlap repair for nails {pair[0]} and {pair[1]}")
        requested_pairs.add(pair)
        background = shapes[background_index - 1]
        foreground = shapes[foreground_index - 1]
        overlap_before = background.intersection(foreground).area
        maximum_overlap = float(repair["maximumOverlapPixels"])
        if overlap_before <= 0 or overlap_before > maximum_overlap:
            raise ValueError(
                f"nails {background_index} and {foreground_index} overlap {overlap_before:.4f} "
                f"outside (0, {maximum_overlap:.4f}]"
            )
        margin = float(repair.get("marginPixels", 0.25))
        changed, discarded = select_polygon(
            background.difference(foreground.buffer(margin, join_style=2)),
            maximum_discard_ratio,
            f"nails {background_index}/{foreground_index} overlap",
        )
        area_loss_ratio = (background.area - changed.area) / background.area
        maximum_area_loss_ratio = float(repair.get("maximumAreaLossRatio", 0.25))
        if area_loss_ratio > maximum_area_loss_ratio:
            raise ValueError(
                f"nail {background_index} overlap repair loses {area_loss_ratio:.6f}, "
                f"above {maximum_area_loss_ratio:.6f}"
            )
        shapes[background_index - 1] = changed
        repairs.append(
            {
                "type": "foreground-occlusion-boundary",
                "backgroundIndex": background_index,
                "foregroundIndex": foreground_index,
                "overlapBefore": round(overlap_before, 4),
                "areaLossRatio": round(area_loss_ratio, 6),
                "discardedComponentArea": round(discarded, 4),
                "marginPixels": margin,
            }
        )

    unresolved = []
    for first_index, first in enumerate(shapes):
        if not first.is_valid or first.area <= 1:
            unresolved.append(f"nail {first_index + 1} invalid after repair")
        for second_index in range(first_index + 1, len(shapes)):
            overlap = first.intersection(shapes[second_index]).area
            if overlap > 0:
                unresolved.append(
                    f"nails {first_index + 1}/{second_index + 1} overlap {overlap:.4f} after repair"
                )
    if unresolved:
        raise ValueError("; ".join(unresolved))

    for index, shape in enumerate(shapes):
        annotations[index]["polygon"] = points(shape)
        annotations[index].setdefault("attributes", {})["topologyRepair"] = (
            "reviewed-explicit-topology-repair" if any(
                repair.get("nailIndex") == index + 1
                or repair.get("backgroundIndex") == index + 1
                for repair in repairs
            ) else "unchanged-reviewed-polygon"
        )
    output_document = deepcopy(document)
    output_document["annotations"] = annotations
    output_path = output_dir / f"{Path(file_name).stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overlay_path = overlay_dir / f"{Path(file_name).stem}-topology-reviewed-overlay.png"
    draw_overlay(image_path, shapes, overlay_path)
    crops = write_crops(image_path, overlay_path, shapes, crop_dir)
    return {
        "lane": lane,
        "fileName": file_name,
        "sourceGroup": metadata.get("sourceGroup"),
        "annotationPath": str(output_path.resolve()),
        "overlayPath": str(overlay_path.resolve()),
        "polygonCount": len(shapes),
        "repairs": repairs,
        "pairwiseOverlapCount": 0,
        "zoomPaths": crops,
    }


def main() -> None:
    args = parser().parse_args()
    manifest = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    roots = {
        "core": (Path(args.core_image_dir).resolve(), Path(args.core_annotations).resolve()),
        "stress": (Path(args.stress_image_dir).resolve(), Path(args.stress_annotations).resolve()),
    }
    output_dir = Path(args.output_annotations).resolve()
    overlay_dir = Path(args.overlay_dir).resolve()
    crop_dir = Path(args.crop_dir).resolve()
    outputs = []
    errors = []
    for item in manifest.get("images", []):
        try:
            outputs.append(process_item(item, roots, output_dir, overlay_dir, crop_dir))
        except Exception as error:
            errors.append(f"{item.get('fileName', '<missing-fileName>')}: {error}")
    report = {
        "ok": not errors and len(outputs) == len(manifest.get("images", [])),
        "method": "reviewed-explicit-annotation-topology-repair",
        "decision": "candidate_only_not_training_or_test_truth",
        "imageCount": len(manifest.get("images", [])),
        "completedCount": len(outputs),
        "polygonCount": sum(output["polygonCount"] for output in outputs),
        "repairCount": sum(len(output["repairs"]) for output in outputs),
        "outputs": outputs,
        "errors": errors,
    }
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
