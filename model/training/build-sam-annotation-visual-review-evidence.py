from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def polygon_bounds(annotation: dict[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    points = annotation.get("polygon")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("polygon requires at least three points")
    coordinates: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("polygon points must be objects")
        x, y = point.get("x"), point.get("y")
        if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(float(x)):
            raise ValueError("polygon x coordinate is invalid")
        if not isinstance(y, (int, float)) or isinstance(y, bool) or not math.isfinite(float(y)):
            raise ValueError("polygon y coordinate is invalid")
        coordinates.append((float(x), float(y)))
    if any(x < 0 or y < 0 or x >= width or y >= height for x, y in coordinates):
        raise ValueError("polygon escapes the source image")
    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    return int(min(xs)), int(min(ys)), int(max(xs)) + 1, int(max(ys)) + 1


def padded_bounds(
    bounds: tuple[int, int, int, int], width: int, height: int, padding: int
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def save_double_crop(source: Image.Image, bounds: tuple[int, int, int, int], output: Path) -> None:
    crop = source.crop(bounds)
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
    crop.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build hash-bound original-resolution and 2x SAM mask review evidence."
    )
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--sam-report", required=True)
    parser.add_argument("--geometry-audit", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--padding", type=int, default=16)
    args = parser.parse_args()

    prompts_path = Path(args.prompts).resolve()
    sam_report_path = Path(args.sam_report).resolve()
    geometry_path = Path(args.geometry_audit).resolve()
    image_dir = Path(args.image_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.padding < 0:
        raise ValueError("--padding cannot be negative")
    for path, label in (
        (prompts_path, "prompts"),
        (sam_report_path, "SAM report"),
        (geometry_path, "geometry audit"),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"missing {label}: {path}")
    if not image_dir.is_dir():
        raise FileNotFoundError(f"missing image directory: {image_dir}")
    if output_dir.exists():
        raise ValueError(f"output directory must not already exist: {output_dir}")

    prompts = read_json(prompts_path)
    sam_report = read_json(sam_report_path)
    geometry = read_json(geometry_path)
    if prompts.get("decision") != "sam_repair_candidate_only_not_test_truth":
        raise ValueError("review requires candidate-only repair prompts")
    if (
        sam_report.get("ok") is not True
        or sam_report.get("decision") != "sam_candidate_only_not_training_truth"
        or sam_report.get("trainingUse") != "prohibited"
        or sam_report.get("originalResolutionReviewRequired") is not True
        or sam_report.get("errors") != []
    ):
        raise ValueError("review requires a complete candidate-only SAM report")
    if geometry.get("decision") != "candidate_only_not_training_truth":
        raise ValueError("geometry evidence must remain candidate-only")

    prompt_items = {str(item.get("fileName") or ""): item for item in prompts.get("images", [])}
    sam_outputs = {str(item.get("fileName") or ""): item for item in sam_report.get("outputs", [])}
    if not prompt_items or set(prompt_items) != set(sam_outputs):
        raise ValueError("prompts and SAM outputs must cover the same unique images")
    if len(prompt_items) != int(prompts.get("imageCount", -1)) or len(sam_outputs) != int(
        sam_report.get("completedCount", -1)
    ):
        raise ValueError("image summary differs from prompt or SAM output coverage")
    if sum(len(item.get("boxes", [])) for item in prompt_items.values()) != int(
        sam_report.get("promptCount", -1)
    ):
        raise ValueError("prompt count differs from the SAM report")

    geometry_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in geometry.get("rows", []):
        geometry_rows[str(row.get("fileName") or "")].append(row)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    crops_dir = temporary / "crops"
    crops_dir.mkdir()
    items: list[dict[str, Any]] = []
    total_polygons = 0
    try:
        for file_name in sorted(sam_outputs):
            prompt_item = prompt_items[file_name]
            sam_output = sam_outputs[file_name]
            image_path = (image_dir / file_name).resolve()
            annotation_path = Path(str(sam_output.get("annotationPath") or "")).resolve()
            overlay_path = Path(str(sam_output.get("overlayPath") or "")).resolve()
            if image_path.parent != image_dir or not image_path.is_file():
                raise ValueError(f"image is missing or escapes image-dir: {file_name}")
            if not annotation_path.is_file() or not overlay_path.is_file():
                raise ValueError(f"SAM annotation or overlay is missing: {file_name}")
            annotation = read_json(annotation_path)
            if (
                annotation.get("decision") != "candidate_only_not_training_truth"
                or annotation.get("trainingUse") != "prohibited"
                or annotation.get("image", {}).get("fileName") != file_name
                or annotation.get("image", {}).get("sourceGroup") != prompt_item.get("sourceGroup")
                or sam_output.get("sourceGroup") != prompt_item.get("sourceGroup")
            ):
                raise ValueError(f"candidate-only annotation identity mismatch: {file_name}")
            annotations = annotation.get("annotations", [])
            boxes = prompt_item.get("boxes", [])
            rows = sorted(geometry_rows.get(file_name, []), key=lambda row: int(row.get("nailIndex", 0)))
            if (
                len(annotations) != len(boxes)
                or len(annotations) != int(sam_output.get("polygonCount", -1))
                or len(rows) != len(annotations)
                or [int(row.get("nailIndex", 0)) for row in rows] != list(range(1, len(rows) + 1))
            ):
                raise ValueError(f"polygon/prompt/geometry coverage mismatch: {file_name}")

            with Image.open(image_path) as source_image, Image.open(overlay_path) as overlay_image:
                source = source_image.convert("RGB")
                overlay = overlay_image.convert("RGB")
                if source.size != overlay.size:
                    raise ValueError(f"source and overlay dimensions differ: {file_name}")
                width, height = source.size
                if (int(annotation.get("image", {}).get("width", 0)), int(annotation.get("image", {}).get("height", 0))) != (
                    width,
                    height,
                ):
                    raise ValueError(f"annotation dimensions differ from source: {file_name}")
                crop_records: list[dict[str, Any]] = []
                for index, (shape, geometry_row) in enumerate(zip(annotations, rows), start=1):
                    bounds = padded_bounds(polygon_bounds(shape, width, height), width, height, args.padding)
                    source_crop = crops_dir / f"{Path(file_name).stem}-n{index:02d}-source-2x.png"
                    overlay_crop = crops_dir / f"{Path(file_name).stem}-n{index:02d}-overlay-2x.png"
                    save_double_crop(source, bounds, source_crop)
                    save_double_crop(overlay, bounds, overlay_crop)
                    crop_records.append(
                        {
                            "nailIndex": index,
                            "bounds": list(bounds),
                            "geometryStatus": geometry_row.get("status"),
                            "geometryReasons": geometry_row.get("reasons", []),
                            "sourceCrop": str((output_dir / "crops" / source_crop.name)),
                            "sourceCropSha256": sha256_file(source_crop),
                            "overlayCrop": str((output_dir / "crops" / overlay_crop.name)),
                            "overlayCropSha256": sha256_file(overlay_crop),
                        }
                    )
                total_polygons += len(crop_records)
                items.append(
                    {
                        "fileName": file_name,
                        "sourceGroup": prompt_item.get("sourceGroup"),
                        "imagePath": str(image_path),
                        "imageSha256": sha256_file(image_path),
                        "annotationPath": str(annotation_path),
                        "annotationSha256": sha256_file(annotation_path),
                        "overlayPath": str(overlay_path),
                        "overlaySha256": sha256_file(overlay_path),
                        "polygonCount": len(crop_records),
                        "geometrySuspectCount": sum(row.get("status") != "pass" for row in rows),
                        "crops": crop_records,
                    }
                )

        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "sam_visual_review_evidence_ready_not_truth",
            "inputs": {
                "prompts": str(prompts_path),
                "promptsSha256": sha256_file(prompts_path),
                "samReport": str(sam_report_path),
                "samReportSha256": sha256_file(sam_report_path),
                "geometryAudit": str(geometry_path),
                "geometryAuditSha256": sha256_file(geometry_path),
                "imageDir": str(image_dir),
            },
            "policy": {
                "originalResolutionOverlayReviewRequired": True,
                "everyPolygonHasSourceAndOverlay2xCrop": True,
                "evidenceDoesNotGrantTruth": True,
                "trainingUse": "prohibited",
            },
            "summary": {
                "images": len(items),
                "polygons": total_polygons,
                "cropPairs": total_polygons,
                "geometrySuspects": sum(item["geometrySuspectCount"] for item in items),
            },
            "items": items,
            "errors": [],
        }
        report_path = temporary / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"ok": True, **report["summary"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
