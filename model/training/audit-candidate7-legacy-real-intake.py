#!/usr/bin/env python3
"""Audit candidate7 legacy polygons and build hash-bound visual review evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon


COLORS = (
    (236, 72, 153),
    (34, 197, 94),
    (59, 130, 246),
    (249, 115, 22),
    (168, 85, 247),
    (14, 165, 233),
    (234, 179, 8),
    (244, 63, 94),
    (20, 184, 166),
    (99, 102, 241),
    (217, 70, 239),
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def object_array(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Expected object array: {field}")
    return value


def points_from_annotation(annotation: dict[str, Any], field: str) -> list[tuple[float, float]]:
    points = annotation.get("polygon")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError(f"Polygon has fewer than three points: {field}")
    result: list[tuple[float, float]] = []
    for index, point in enumerate(points, start=1):
        if not isinstance(point, dict):
            raise ValueError(f"Invalid polygon point {field}#{index}")
        x = point.get("x")
        y = point.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError(f"Non-numeric polygon point {field}#{index}")
        result.append((float(x), float(y)))
    return result


def render_evidence(
    image: Image.Image,
    polygons: list[list[tuple[float, float]]],
    overlay_path: Path,
    crops_path: Path,
) -> None:
    rgba = image.convert("RGBA")
    fill_layer = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    fill_draw = ImageDraw.Draw(fill_layer)
    outline_draw = ImageDraw.Draw(rgba)
    font = ImageFont.load_default()
    for index, points in enumerate(polygons, start=1):
        color = COLORS[(index - 1) % len(COLORS)]
        fill_draw.polygon(points, fill=(*color, 58))
        outline_draw.line(points + [points[0]], fill=(*color, 255), width=max(2, round(min(image.size) / 350)))
        min_x = min(point[0] for point in points)
        min_y = min(point[1] for point in points)
        label = str(index)
        box = outline_draw.textbbox((min_x, min_y), label, font=font, stroke_width=1)
        outline_draw.rectangle(box, fill=(0, 0, 0, 210))
        outline_draw.text((min_x, min_y), label, fill=(*color, 255), font=font, stroke_width=1, stroke_fill=(0, 0, 0, 255))
    overlay = Image.alpha_composite(rgba, fill_layer).convert("RGB")
    overlay.save(overlay_path, format="PNG", optimize=False)

    tile_width = 520
    tile_height = 420
    label_height = 32
    columns = 2
    rows = (len(polygons) + columns - 1) // columns
    sheet = Image.new("RGB", (tile_width * columns, (tile_height + label_height) * rows), "white")
    sheet_draw = ImageDraw.Draw(sheet)
    for index, points in enumerate(polygons, start=1):
        min_x = max(0, int(min(point[0] for point in points)))
        min_y = max(0, int(min(point[1] for point in points)))
        max_x = min(image.width, int(max(point[0] for point in points)) + 1)
        max_y = min(image.height, int(max(point[1] for point in points)) + 1)
        margin = max(16, round(max(max_x - min_x, max_y - min_y) * 0.55))
        crop_box = (
            max(0, min_x - margin),
            max(0, min_y - margin),
            min(image.width, max_x + margin),
            min(image.height, max_y + margin),
        )
        crop = overlay.crop(crop_box)
        scale = min(tile_width / crop.width, tile_height / crop.height, 2.0)
        resized = crop.resize(
            (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
            Image.Resampling.NEAREST if scale >= 1.0 else Image.Resampling.LANCZOS,
        )
        column = (index - 1) % columns
        row = (index - 1) // columns
        left = column * tile_width + (tile_width - resized.width) // 2
        top = row * (tile_height + label_height) + (tile_height - resized.height) // 2
        sheet.paste(resized, (left, top))
        sheet_draw.text(
            (column * tile_width + 8, row * (tile_height + label_height) + tile_height + 7),
            f"mask {index} | source pixels enlarged at most 2x",
            fill="black",
            font=font,
        )
    sheet.save(crops_path, format="PNG", optimize=False)


def build_report(intake_path: Path, output_root: Path, write_visuals: bool) -> dict[str, Any]:
    intake = load_object(intake_path)
    if intake.get("decision") != "candidate7_legacy_real_rereview_intake_ready":
        raise ValueError("Candidate7 intake is not ready")
    intake_items = object_array(intake.get("items"), "intake.items")
    overlays_dir = output_root / "overlays"
    crops_dir = output_root / "nail-crops-2x"
    if write_visuals:
        if output_root.exists() and any(output_root.iterdir()):
            raise ValueError(f"Refusing to overwrite non-empty output: {output_root}")
        overlays_dir.mkdir(parents=True, exist_ok=True)
        crops_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    totals = {
        "images": 0,
        "legacyPolygons": 0,
        "invalidPolygons": 0,
        "outOfBoundsPolygons": 0,
        "edgeTouchingPolygons": 0,
        "overlapPairs": 0,
        "machineCleanImages": 0,
        "machineReworkImages": 0,
        "legacyNeedsManualFixImages": 0,
    }
    for intake_item in intake_items:
        file_name = str(intake_item.get("fileName") or "")
        image_path = Path(str(intake_item.get("imagePath") or "")).resolve()
        annotation_path = Path(str(intake_item.get("legacyAnnotationPath") or "")).resolve()
        if not image_path.is_file() or not annotation_path.is_file():
            raise ValueError(f"Missing image or annotation: {file_name}")
        if sha256_path(image_path) != intake_item.get("imageSha256"):
            raise ValueError(f"Image hash drift: {file_name}")
        if sha256_path(annotation_path) != intake_item.get("legacyAnnotationSha256"):
            raise ValueError(f"Annotation hash drift: {file_name}")
        annotation = load_object(annotation_path)
        image_meta = annotation.get("image")
        if not isinstance(image_meta, dict) or image_meta.get("fileName") != file_name:
            raise ValueError(f"Annotation image identity mismatch: {file_name}")
        annotations = object_array(annotation.get("annotations"), f"{file_name}.annotations")
        if len(annotations) != intake_item.get("legacyPolygonCount"):
            raise ValueError(f"Annotation count drift: {file_name}")
        with Image.open(image_path) as source:
            source.load()
            image = source.convert("RGB")
        if image.size != (int(intake_item.get("width") or 0), int(intake_item.get("height") or 0)):
            raise ValueError(f"Image dimension drift: {file_name}")

        raw_polygons: list[list[tuple[float, float]]] = []
        shapes: list[Polygon] = []
        polygon_results: list[dict[str, Any]] = []
        for index, entry in enumerate(annotations, start=1):
            points = points_from_annotation(entry, f"{file_name}.annotations[{index}]")
            shape = Polygon(points)
            bounds = shape.bounds
            valid = bool(shape.is_valid and not shape.is_empty and shape.area > 0)
            in_bounds = all(0 <= x < image.width and 0 <= y < image.height for x, y in points)
            edge_touching = bounds[0] <= 0 or bounds[1] <= 0 or bounds[2] >= image.width - 1 or bounds[3] >= image.height - 1
            polygon_results.append(
                {
                    "index": index,
                    "pointCount": len(points),
                    "valid": valid,
                    "inBounds": in_bounds,
                    "edgeTouching": edge_touching,
                    "area": round(float(shape.area), 6),
                    "areaRatio": round(float(shape.area / (image.width * image.height)), 9),
                    "bounds": [round(float(value), 3) for value in bounds],
                }
            )
            raw_polygons.append(points)
            shapes.append(shape)
        overlap_results: list[dict[str, Any]] = []
        for left in range(len(shapes)):
            for right in range(left + 1, len(shapes)):
                if not shapes[left].is_valid or not shapes[right].is_valid:
                    continue
                area = float(shapes[left].intersection(shapes[right]).area)
                if area > 0:
                    overlap_results.append({"left": left + 1, "right": right + 1, "area": round(area, 6)})

        stem = hashlib.sha256(file_name.encode("utf-8")).hexdigest()[:16]
        overlay_path = overlays_dir / f"{stem}.png"
        crops_path = crops_dir / f"{stem}.png"
        if write_visuals:
            render_evidence(image, raw_polygons, overlay_path, crops_path)
        if not overlay_path.is_file() or not crops_path.is_file():
            raise ValueError(f"Visual evidence missing: {file_name}")

        invalid_count = sum(not item["valid"] for item in polygon_results)
        out_of_bounds_count = sum(not item["inBounds"] for item in polygon_results)
        edge_count = sum(bool(item["edgeTouching"]) for item in polygon_results)
        legacy_needs_fix = bool(intake_item.get("legacyNeedsManualFix"))
        machine_clean = invalid_count == 0 and out_of_bounds_count == 0 and edge_count == 0 and not overlap_results
        status = "machine-clean-awaiting-original-resolution-visual-review" if machine_clean else "machine-rework-required"
        totals["images"] += 1
        totals["legacyPolygons"] += len(polygon_results)
        totals["invalidPolygons"] += invalid_count
        totals["outOfBoundsPolygons"] += out_of_bounds_count
        totals["edgeTouchingPolygons"] += edge_count
        totals["overlapPairs"] += len(overlap_results)
        totals["machineCleanImages" if machine_clean else "machineReworkImages"] += 1
        totals["legacyNeedsManualFixImages"] += int(legacy_needs_fix)
        items.append(
            {
                "fileName": file_name,
                "imagePath": str(image_path),
                "imageSha256": intake_item["imageSha256"],
                "annotationPath": str(annotation_path),
                "annotationSha256": intake_item["legacyAnnotationSha256"],
                "sourceGroup": intake_item["sourceGroup"],
                "width": image.width,
                "height": image.height,
                "legacyNeedsManualFix": legacy_needs_fix,
                "machineStatus": status,
                "polygonResults": polygon_results,
                "overlapResults": overlap_results,
                "overlayPath": str(overlay_path),
                "overlaySha256": sha256_path(overlay_path),
                "nailCropSheetPath": str(crops_path),
                "nailCropSheetSha256": sha256_path(crops_path),
                "originalResolutionVisualDecision": "pending",
                "completeMaskDecision": "pending",
                "trainingUse": "prohibited",
            }
        )

    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "machine_audit_ready_for_original_resolution_visual_review",
        "inputs": {
            "intake": str(intake_path),
            "intakeSha256": sha256_path(intake_path),
            "intakeItemsSha256": intake.get("itemsSha256"),
        },
        "policy": {
            "machineGeometryDoesNotApproveSourceQuality": True,
            "machineGeometryDoesNotApproveCompleteMasks": True,
            "originalResolutionImageAndEveryNailCropMustBeReviewed": True,
            "legacyPolygonsAreDiagnosticOnly": True,
            "trainingUse": "prohibited",
        },
        "counts": totals,
        "itemsSha256": canonical_sha256(items),
        "items": items,
        "errors": [],
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake")
    parser.add_argument("--output-dir")
    parser.add_argument("--report")
    parser.add_argument("--verify-report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify_report:
            report_path = Path(args.verify_report).resolve()
            existing = load_object(report_path)
            intake_path = Path(str(existing.get("inputs", {}).get("intake") or "")).resolve()
            current = build_report(intake_path, report_path.parent, False)
            if current != existing:
                raise ValueError("Audit report does not match current replayed evidence")
            print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
            return 0
        if not args.intake or not args.output_dir or not args.report:
            raise ValueError("Generation requires --intake, --output-dir and --report")
        intake_path = Path(args.intake).resolve()
        output_root = Path(args.output_dir).resolve()
        report_path = Path(args.report).resolve()
        if report_path.parent != output_root:
            raise ValueError("Report must be directly inside output-dir")
        report = build_report(intake_path, output_root, True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "decision": report["decision"], "report": str(report_path)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
