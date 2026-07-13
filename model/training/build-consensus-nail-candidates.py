from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build review-only nail candidates that agree across two inference resolutions."
    )
    parser.add_argument("--primary-annotations", required=True)
    parser.add_argument("--secondary-annotations", required=True)
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--output-annotations", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--minimum-iou", type=float, default=0.55)
    parser.add_argument("--minimum-primary-confidence", type=float, default=0.35)
    parser.add_argument("--maximum-image-area-ratio", type=float, default=0.15)
    return parser


def polygon_points(annotation: dict) -> np.ndarray:
    return np.asarray(
        [[round(point["x"]), round(point["y"])] for point in annotation["polygon"]],
        dtype=np.int32,
    )


def polygon_area(annotation: dict) -> float:
    return float(abs(cv2.contourArea(polygon_points(annotation))))


def polygon_iou(first: dict, second: dict) -> float:
    first_points = polygon_points(first)
    second_points = polygon_points(second)
    all_points = np.concatenate([first_points, second_points])
    x1, y1 = np.maximum(all_points.min(axis=0) - 1, 0)
    x2, y2 = all_points.max(axis=0) + 2
    width = int(x2 - x1)
    height = int(y2 - y1)
    if width <= 0 or height <= 0:
        return 0.0
    first_mask = np.zeros((height, width), dtype=np.uint8)
    second_mask = np.zeros((height, width), dtype=np.uint8)
    offset = np.asarray([x1, y1], dtype=np.int32)
    cv2.fillPoly(first_mask, [first_points - offset], 1)
    cv2.fillPoly(second_mask, [second_points - offset], 1)
    intersection = int(np.logical_and(first_mask, second_mask).sum())
    union = int(np.logical_or(first_mask, second_mask).sum())
    return intersection / union if union else 0.0


def confidence(annotation: dict) -> float:
    return float(annotation.get("attributes", {}).get("confidence", 0.0))


def match_annotations(
    primary: list[dict],
    secondary: list[dict],
    minimum_iou: float,
) -> list[tuple[int, int, float]]:
    ranked = sorted(
        (
            (primary_index, secondary_index, polygon_iou(primary_item, secondary_item))
            for primary_index, primary_item in enumerate(primary)
            for secondary_index, secondary_item in enumerate(secondary)
        ),
        key=lambda item: item[2],
        reverse=True,
    )
    primary_used: set[int] = set()
    secondary_used: set[int] = set()
    matches = []
    for primary_index, secondary_index, iou in ranked:
        if iou < minimum_iou:
            break
        if primary_index in primary_used or secondary_index in secondary_used:
            continue
        primary_used.add(primary_index)
        secondary_used.add(secondary_index)
        matches.append((primary_index, secondary_index, iou))
    return matches


def load_rework_names(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row["fileName"] for row in csv.DictReader(handle) if row["status"] == "rework"]


def draw_overlay(image_path: Path, annotations: list[dict], output_path: Path) -> None:
    with Image.open(image_path) as source:
        overlay = source.convert("RGB")
    draw = ImageDraw.Draw(overlay, "RGBA")
    for index, annotation in enumerate(annotations, start=1):
        points = [(point["x"], point["y"]) for point in annotation["polygon"]]
        draw.polygon(points, fill=(0, 220, 90, 80), outline=(0, 190, 70, 255), width=3)
        draw.text(points[0], str(index), fill=(255, 30, 30, 255), stroke_width=2, stroke_fill="white")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, quality=92)


def main() -> None:
    args = build_parser().parse_args()
    primary_dir = Path(args.primary_annotations).resolve()
    secondary_dir = Path(args.secondary_annotations).resolve()
    image_dir = Path(args.image_dir).resolve()
    output_dir = Path(args.output_annotations).resolve()
    overlay_dir = Path(args.overlay_dir).resolve()
    report_path = Path(args.report).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    items = []
    errors = []
    total_consensus = 0
    for file_name in load_rework_names(Path(args.review_csv).resolve()):
        stem = Path(file_name).stem
        primary_path = primary_dir / f"{stem}.json"
        secondary_path = secondary_dir / f"{stem}.json"
        try:
            primary_document = json.loads(primary_path.read_text(encoding="utf-8"))
            secondary_document = json.loads(secondary_path.read_text(encoding="utf-8"))
            if primary_document["image"]["fileName"] != secondary_document["image"]["fileName"]:
                raise ValueError("annotation documents refer to different images")
            width = int(primary_document["image"]["width"])
            height = int(primary_document["image"]["height"])
            if (width, height) != (
                int(secondary_document["image"]["width"]),
                int(secondary_document["image"]["height"]),
            ):
                raise ValueError("annotation documents use different image dimensions")

            primary = primary_document.get("annotations", [])
            secondary = secondary_document.get("annotations", [])
            matches = match_annotations(primary, secondary, args.minimum_iou)
            accepted = []
            rejected_matches = []
            for primary_index, secondary_index, iou in matches:
                primary_item = primary[primary_index]
                secondary_item = secondary[secondary_index]
                primary_confidence = confidence(primary_item)
                area_ratio = polygon_area(primary_item) / max(1, width * height)
                reasons = []
                if primary_confidence < args.minimum_primary_confidence:
                    reasons.append("primary_confidence_below_threshold")
                if area_ratio > args.maximum_image_area_ratio:
                    reasons.append("polygon_area_ratio_above_threshold")
                if reasons:
                    rejected_matches.append(
                        {"primaryIndex": primary_index, "secondaryIndex": secondary_index, "reasons": reasons}
                    )
                    continue
                chosen = primary_item if primary_confidence >= confidence(secondary_item) else secondary_item
                copied = json.loads(json.dumps(chosen, ensure_ascii=False))
                copied["id"] = f"n{len(accepted) + 1}"
                copied.setdefault("attributes", {}).update(
                    {
                        "annotationMethod": "cross-resolution-consensus-v1",
                        "reviewRequired": True,
                        "consensusIou": round(iou, 6),
                        "primaryConfidence": round(primary_confidence, 6),
                        "secondaryConfidence": round(confidence(secondary_item), 6),
                    }
                )
                accepted.append(copied)

            output_document = {
                "version": "nail-texture-dataset/v1",
                "decision": "candidate_only_not_training_truth",
                "image": primary_document["image"],
                "annotations": accepted,
            }
            output_path = output_dir / f"{stem}.json"
            output_path.write_text(json.dumps(output_document, ensure_ascii=False, indent=2), encoding="utf-8")
            overlay_path = overlay_dir / f"{stem}-consensus-overlay.jpg"
            draw_overlay(image_dir / file_name, accepted, overlay_path)
            total_consensus += len(accepted)
            items.append(
                {
                    "fileName": file_name,
                    "primaryCount": len(primary),
                    "secondaryCount": len(secondary),
                    "matchedCount": len(matches),
                    "consensusCount": len(accepted),
                    "rejectedMatchedCount": len(rejected_matches),
                    "rejectedMatches": rejected_matches,
                    "annotationPath": str(output_path),
                    "overlayPath": str(overlay_path),
                }
            )
        except Exception as error:
            errors.append({"fileName": file_name, "message": str(error)})

    report = {
        "version": "nail-texture-cross-resolution-consensus/v1",
        "ok": not errors,
        "decision": "candidate_only_not_training_truth",
        "thresholds": {
            "minimumPolygonIou": args.minimum_iou,
            "minimumPrimaryConfidence": args.minimum_primary_confidence,
            "maximumImageAreaRatio": args.maximum_image_area_ratio,
        },
        "imageCount": len(items),
        "imagesWithConsensus": sum(item["consensusCount"] > 0 for item in items),
        "imagesWithoutConsensus": sum(item["consensusCount"] == 0 for item in items),
        "totalConsensusCandidates": total_consensus,
        "errors": errors,
        "items": items,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "imageCount": report["imageCount"],
                "imagesWithConsensus": report["imagesWithConsensus"],
                "imagesWithoutConsensus": report["imagesWithoutConsensus"],
                "totalConsensusCandidates": report["totalConsensusCandidates"],
                "report": str(report_path),
            },
            ensure_ascii=True,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
