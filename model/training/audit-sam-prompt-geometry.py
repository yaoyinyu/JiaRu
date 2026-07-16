#!/usr/bin/env python3
"""Audit SAM polygon geometry against its reviewed prompts.

This audit only checks prompt/polygon consistency. It cannot decide whether a
nail is missing, partially covered, contaminated, duplicated, cropped, or
otherwise visually unsuitable. Original-resolution review remains mandatory.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon


DEFAULT_THRESHOLDS = {
    "minimumBoundsContainment": 0.72,
    "minimumAreaRatio": 0.12,
    "maximumAreaRatio": 1.35,
    "promptCenterMustBeInside": True,
    "maximumPeerBoundsIou": 0.35,
    "maximumPeerPolygonIntersectionArea": 0.0,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit SAM annotation polygons against reviewed prompts."
    )
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--annotation-dir", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--csv-output", required=True)
    return parser


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def rectangle_area(bounds: tuple[float, float, float, float]) -> float:
    return max(0.0, bounds[2] - bounds[0]) * max(0.0, bounds[3] - bounds[1])


def intersection_area(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    return max(0.0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0.0, min(first[3], second[3]) - max(first[1], second[1])
    )


def bounds_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    overlap = intersection_area(first, second)
    union = rectangle_area(first) + rectangle_area(second) - overlap
    return overlap / union if union > 0 else 0.0


def point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    tolerance: float = 1e-6,
) -> bool:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > tolerance:
        return False
    return (
        min(x1, x2) - tolerance <= px <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= py <= max(y1, y2) + tolerance
    )


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    px, py = point
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        crosses = (y1 > py) != (y2 > py)
        if crosses:
            intersection_x = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < intersection_x:
                inside = not inside
    return inside


def normalized_prompt_box(
    box: list[Any], width: int, height: int
) -> tuple[float, float, float, float]:
    if len(box) != 4:
        raise ValueError(f"prompt box must contain four values: {box}")
    values = tuple(float(value) for value in box)
    if not all(0.0 <= value <= 1.0 for value in values):
        raise ValueError(f"prompt box must be normalized: {box}")
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"prompt box is empty or inverted: {box}")
    return x1 * width, y1 * height, x2 * width, y2 * height


def annotation_points(annotation: dict[str, Any]) -> list[tuple[float, float]]:
    polygon = annotation.get("polygon", [])
    points = [(float(point["x"]), float(point["y"])) for point in polygon]
    if len(points) < 3:
        raise ValueError(f"annotation polygon has fewer than three points: {annotation.get('id')}")
    return points


def maximum_peer_polygon_intersection_area(
    polygons: list[list[tuple[float, float]]], index: int
) -> float:
    polygon = Polygon(polygons[index])
    if not polygon.is_valid:
        return float("inf")
    maximum = 0.0
    for peer_index, peer_points in enumerate(polygons):
        if peer_index == index:
            continue
        peer_polygon = Polygon(peer_points)
        if not peer_polygon.is_valid:
            return float("inf")
        maximum = max(maximum, float(polygon.intersection(peer_polygon).area))
    return maximum


def round_value(value: float) -> float:
    return round(value, 4)


def audit(args: argparse.Namespace) -> dict[str, Any]:
    prompts_path = Path(args.prompts).resolve()
    annotation_dir = Path(args.annotation_dir).resolve()
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))

    rows: list[dict[str, Any]] = []
    summary = {args.source: {"pass": 0, "suspect": 0, "missing": 0}}

    for prompt_image in prompts.get("images", []):
        file_name = prompt_image["fileName"]
        annotation_path = annotation_dir / f"{Path(file_name).stem}.json"
        boxes = prompt_image.get("boxes", [])
        if not annotation_path.exists():
            for index in range(len(boxes)):
                rows.append(
                    {
                        "fileName": file_name,
                        "nailIndex": index + 1,
                        "source": args.source,
                        "status": "missing",
                        "reasons": ["annotation_file_missing"],
                        "areaRatio": None,
                        "boundsContainment": None,
                        "centerInside": None,
                        "bounds": None,
                        "maximumPeerBoundsIou": None,
                        "maximumPeerPolygonIntersectionArea": None,
                    }
                )
                summary[args.source]["missing"] += 1
            continue

        annotation_document = json.loads(annotation_path.read_text(encoding="utf-8"))
        image = annotation_document["image"]
        width = int(image["width"])
        height = int(image["height"])
        annotations = annotation_document.get("annotations", [])
        polygons = [annotation_points(annotation) for annotation in annotations]
        polygon_bounds_list = [polygon_bounds(points) for points in polygons]

        for index, box in enumerate(boxes):
            if index >= len(polygons):
                rows.append(
                    {
                        "fileName": file_name,
                        "nailIndex": index + 1,
                        "source": args.source,
                        "status": "missing",
                        "reasons": ["annotation_polygon_missing"],
                        "areaRatio": None,
                        "boundsContainment": None,
                        "centerInside": None,
                        "bounds": None,
                        "maximumPeerBoundsIou": None,
                        "maximumPeerPolygonIntersectionArea": None,
                    }
                )
                summary[args.source]["missing"] += 1
                continue

            prompt_bounds = normalized_prompt_box(box, width, height)
            points = polygons[index]
            bounds = polygon_bounds_list[index]
            prompt_area = rectangle_area(prompt_bounds)
            bounds_area = rectangle_area(bounds)
            area_ratio = polygon_area(points) / prompt_area if prompt_area > 0 else 0.0
            containment = intersection_area(bounds, prompt_bounds) / bounds_area if bounds_area > 0 else 0.0
            prompt_center = (
                (prompt_bounds[0] + prompt_bounds[2]) / 2.0,
                (prompt_bounds[1] + prompt_bounds[3]) / 2.0,
            )
            center_inside = point_in_polygon(prompt_center, points)
            peer_iou = max(
                (
                    bounds_iou(bounds, peer_bounds)
                    for peer_index, peer_bounds in enumerate(polygon_bounds_list)
                    if peer_index != index
                ),
                default=0.0,
            )
            peer_polygon_intersection_area = maximum_peer_polygon_intersection_area(
                polygons, index
            )

            reasons: list[str] = []
            if area_ratio < DEFAULT_THRESHOLDS["minimumAreaRatio"]:
                reasons.append("area_ratio_below_minimum")
            if area_ratio > DEFAULT_THRESHOLDS["maximumAreaRatio"]:
                reasons.append("area_ratio_above_maximum")
            if containment < DEFAULT_THRESHOLDS["minimumBoundsContainment"]:
                reasons.append("bounds_containment_below_minimum")
            if DEFAULT_THRESHOLDS["promptCenterMustBeInside"] and not center_inside:
                reasons.append("prompt_center_outside_polygon")
            if peer_polygon_intersection_area == float("inf"):
                reasons.append("invalid_polygon_topology")
            elif (
                peer_polygon_intersection_area
                > DEFAULT_THRESHOLDS["maximumPeerPolygonIntersectionArea"]
            ):
                reasons.append("peer_polygon_intersection_area_above_maximum")

            status = "suspect" if reasons else "pass"
            summary[args.source][status] += 1
            rows.append(
                {
                    "fileName": file_name,
                    "nailIndex": index + 1,
                    "source": args.source,
                    "status": status,
                    "reasons": reasons,
                    "areaRatio": round_value(area_ratio),
                    "boundsContainment": round_value(containment),
                    "centerInside": center_inside,
                    "bounds": [round(value, 1) for value in bounds],
                    "maximumPeerBoundsIou": round_value(peer_iou),
                    "maximumPeerPolygonIntersectionArea": (
                        None
                        if peer_polygon_intersection_area == float("inf")
                        else round_value(peer_polygon_intersection_area)
                    ),
                }
            )

        for extra_index in range(len(boxes), len(polygons)):
            rows.append(
                {
                    "fileName": file_name,
                    "nailIndex": extra_index + 1,
                    "source": args.source,
                    "status": "suspect",
                    "reasons": ["annotation_polygon_without_prompt"],
                    "areaRatio": None,
                    "boundsContainment": None,
                    "centerInside": None,
                    "bounds": [round(value, 1) for value in polygon_bounds_list[extra_index]],
                    "maximumPeerBoundsIou": None,
                    "maximumPeerPolygonIntersectionArea": None,
                }
            )
            summary[args.source]["suspect"] += 1

    return {
        "version": "nail-texture-assisted-annotation-audit/v1",
        "decision": "candidate_only_not_training_truth",
        "thresholds": DEFAULT_THRESHOLDS,
        "summary": summary,
        "rows": rows,
    }


def write_outputs(document: dict[str, Any], json_output: Path, csv_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    field_names = [
        "fileName",
        "nailIndex",
        "source",
        "status",
        "reasons",
        "areaRatio",
        "boundsContainment",
        "centerInside",
        "bounds",
        "maximumPeerBoundsIou",
        "maximumPeerPolygonIntersectionArea",
    ]
    with csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in document["rows"]:
            csv_row = dict(row)
            csv_row["reasons"] = ";".join(row["reasons"])
            csv_row["bounds"] = json.dumps(row["bounds"]) if row["bounds"] is not None else ""
            writer.writerow(csv_row)


def main() -> int:
    args = build_parser().parse_args()
    document = audit(args)
    write_outputs(
        document,
        Path(args.json_output).resolve(),
        Path(args.csv_output).resolve(),
    )
    print(json.dumps(document["summary"], ensure_ascii=False, indent=2))
    return 0 if all(counts["missing"] == 0 for counts in document["summary"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
