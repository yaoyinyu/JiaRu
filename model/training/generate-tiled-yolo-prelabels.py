from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate review-only tiled YOLO prelabels for small nails and collage images."
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--annotation-dir", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source-group", required=True)
    parser.add_argument("--conf", type=float, default=0.20)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--max-det-per-tile", type=int, default=12)
    parser.add_argument("--tile-fraction", type=float, default=0.62)
    parser.add_argument("--grid-size", type=int, default=3)
    parser.add_argument("--dedupe-mask-iou", type=float, default=0.45)
    parser.add_argument("--edge-margin", type=int, default=3)
    return parser


def load_rework_names(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row["fileName"] for row in csv.DictReader(handle) if row["status"] == "rework"]


def axis_starts(length: int, tile_length: int, grid_size: int) -> list[int]:
    if tile_length >= length:
        return [0]
    return sorted({round(index * (length - tile_length) / max(1, grid_size - 1)) for index in range(grid_size)})


def build_tiles(width: int, height: int, fraction: float, grid_size: int) -> list[tuple[int, int, int, int]]:
    tile_width = min(width, max(64, round(width * fraction)))
    tile_height = min(height, max(64, round(height * fraction)))
    return [
        (x, y, x + tile_width, y + tile_height)
        for y in axis_starts(height, tile_height, grid_size)
        for x in axis_starts(width, tile_width, grid_size)
    ]


def polygon_area(points: list[dict[str, float]]) -> float:
    contour = np.asarray([[point["x"], point["y"]] for point in points], dtype=np.float32)
    return float(abs(cv2.contourArea(contour)))


def polygon_iou(first: list[dict[str, float]], second: list[dict[str, float]]) -> float:
    first_points = np.asarray([[round(point["x"]), round(point["y"])] for point in first], dtype=np.int32)
    second_points = np.asarray([[round(point["x"]), round(point["y"])] for point in second], dtype=np.int32)
    all_points = np.concatenate([first_points, second_points])
    x1, y1 = np.maximum(all_points.min(axis=0) - 1, 0)
    x2, y2 = all_points.max(axis=0) + 2
    if x2 <= x1 or y2 <= y1:
        return 0.0
    offset = np.asarray([x1, y1], dtype=np.int32)
    shape = (int(y2 - y1), int(x2 - x1))
    first_mask = np.zeros(shape, dtype=np.uint8)
    second_mask = np.zeros(shape, dtype=np.uint8)
    cv2.fillPoly(first_mask, [first_points - offset], 1)
    cv2.fillPoly(second_mask, [second_points - offset], 1)
    intersection = int(np.logical_and(first_mask, second_mask).sum())
    union = int(np.logical_or(first_mask, second_mask).sum())
    return intersection / union if union else 0.0


def touches_internal_tile_edge(
    polygon: np.ndarray,
    tile: tuple[int, int, int, int],
    image_size: tuple[int, int],
    margin: int,
) -> bool:
    x1, y1, x2, y2 = tile
    width, height = image_size
    local_width = x2 - x1
    local_height = y2 - y1
    minimum = polygon.min(axis=0)
    maximum = polygon.max(axis=0)
    return (
        (x1 > 0 and minimum[0] <= margin)
        or (y1 > 0 and minimum[1] <= margin)
        or (x2 < width and maximum[0] >= local_width - 1 - margin)
        or (y2 < height and maximum[1] >= local_height - 1 - margin)
    )


def dedupe(candidates: list[dict], threshold: float) -> list[dict]:
    accepted: list[dict] = []
    for candidate in sorted(candidates, key=lambda item: item["attributes"]["confidence"], reverse=True):
        if any(polygon_iou(candidate["polygon"], current["polygon"]) >= threshold for current in accepted):
            continue
        candidate["id"] = f"n{len(accepted) + 1}"
        accepted.append(candidate)
    return accepted


def draw_overlay(image: Image.Image, annotations: list[dict], output: Path) -> None:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay, "RGBA")
    for index, annotation in enumerate(annotations, start=1):
        points = [(point["x"], point["y"]) for point in annotation["polygon"]]
        draw.polygon(points, fill=(0, 220, 90, 80), outline=(0, 190, 70, 255), width=3)
        draw.text(points[0], str(index), fill=(255, 30, 30, 255), stroke_width=2, stroke_fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output, quality=92)


def main() -> None:
    args = build_parser().parse_args()
    if not 0.25 <= args.tile_fraction <= 1:
        raise ValueError("tile-fraction must be between 0.25 and 1")
    if args.grid_size < 1:
        raise ValueError("grid-size must be at least 1")

    image_dir = Path(args.image_dir).resolve()
    annotation_dir = Path(args.annotation_dir).resolve()
    overlay_dir = Path(args.overlay_dir).resolve()
    report_path = Path(args.report).resolve()
    annotation_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(Path(args.model).resolve()))

    items = []
    errors = []
    total_candidates = 0
    total_edge_rejections = 0
    for file_name in load_rework_names(Path(args.review_csv).resolve()):
        image_path = image_dir / file_name
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
            width, height = image.size
            tiles = build_tiles(width, height, args.tile_fraction, args.grid_size)
            crops = [np.asarray(image.crop(tile)) for tile in tiles]
            results = model.predict(
                source=crops,
                conf=args.conf,
                iou=args.iou,
                imgsz=args.imgsz,
                device=args.device,
                max_det=args.max_det_per_tile,
                retina_masks=True,
                verbose=False,
            )
            candidates = []
            edge_rejections = 0
            for tile_index, (tile, result) in enumerate(zip(tiles, results, strict=True)):
                confidences = result.boxes.conf.cpu().tolist() if result.boxes is not None else []
                polygons = result.masks.xy if result.masks is not None else []
                for polygon, score in zip(polygons, confidences, strict=True):
                    local = np.asarray(polygon)
                    if len(local) < 4 or touches_internal_tile_edge(
                        local, tile, (width, height), args.edge_margin
                    ):
                        edge_rejections += 1
                        continue
                    translated = local + np.asarray([tile[0], tile[1]])
                    points = [{"x": float(x), "y": float(y)} for x, y in translated]
                    if polygon_area(points) < 16:
                        continue
                    candidates.append(
                        {
                            "id": "pending",
                            "label": "nail_texture",
                            "polygon": points,
                            "attributes": {
                                "fingerHint": "unknown",
                                "shape": "unknown",
                                "quality": 2,
                                "occluded": False,
                                "artificialTip": False,
                                "annotationMethod": "yolo-overlapping-tiles-v1",
                                "confidence": round(float(score), 6),
                                "tileIndex": tile_index,
                                "reviewRequired": True,
                            },
                        }
                    )
            annotations = dedupe(candidates, args.dedupe_mask_iou)
            document = {
                "version": "nail-texture-dataset/v1",
                "decision": "candidate_only_not_training_truth",
                "image": {
                    "id": Path(file_name).stem,
                    "fileName": file_name,
                    "width": width,
                    "height": height,
                    "sourceGroup": args.source_group,
                    "negative": False,
                },
                "annotations": annotations,
            }
            annotation_path = annotation_dir / f"{Path(file_name).stem}.json"
            annotation_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            overlay_path = overlay_dir / f"{Path(file_name).stem}-tiled-overlay.jpg"
            draw_overlay(image, annotations, overlay_path)
            total_candidates += len(annotations)
            total_edge_rejections += edge_rejections
            items.append(
                {
                    "fileName": file_name,
                    "tileCount": len(tiles),
                    "rawCandidateCount": len(candidates),
                    "edgeRejectionCount": edge_rejections,
                    "candidateCount": len(annotations),
                    "annotationPath": str(annotation_path),
                    "overlayPath": str(overlay_path),
                }
            )
        except Exception as error:
            errors.append({"fileName": file_name, "message": str(error)})

    report = {
        "version": "nail-texture-tiled-yolo-prelabel/v1",
        "ok": not errors,
        "decision": "candidate_only_not_training_truth",
        "model": str(Path(args.model).resolve()),
        "settings": {
            "conf": args.conf,
            "iou": args.iou,
            "imgsz": args.imgsz,
            "tileFraction": args.tile_fraction,
            "gridSize": args.grid_size,
            "dedupeMaskIou": args.dedupe_mask_iou,
            "edgeMargin": args.edge_margin,
        },
        "imageCount": len(items),
        "imagesWithCandidates": sum(item["candidateCount"] > 0 for item in items),
        "imagesWithoutCandidates": sum(item["candidateCount"] == 0 for item in items),
        "totalCandidates": total_candidates,
        "totalEdgeRejections": total_edge_rejections,
        "errors": errors,
        "items": items,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: report[key] for key in (
                "ok", "imageCount", "imagesWithCandidates", "imagesWithoutCandidates",
                "totalCandidates", "totalEdgeRejections"
            )},
            ensure_ascii=True,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
