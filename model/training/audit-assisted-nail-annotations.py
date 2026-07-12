from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit vision-assisted nail polygons against their human supplied prompt boxes."
    )
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--annotations", action="append", required=True, metavar="NAME=DIR")
    parser.add_argument("--report", required=True)
    parser.add_argument("--csv", required=True)
    return parser


def polygon_area(points: list[dict[str, float]]) -> float:
    return abs(
        sum(
            point["x"] * points[(index + 1) % len(points)]["y"]
            - points[(index + 1) % len(points)]["x"] * point["y"]
            for index, point in enumerate(points)
        )
    ) / 2


def polygon_bounds(points: list[dict[str, float]]) -> tuple[float, float, float, float]:
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def intersection_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )


def bounds_iou(a: list[float], b: list[float]) -> float:
    intersection = intersection_area(tuple(a), tuple(b))
    area_a = max(0.0, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(0.0, (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / max(1.0, area_a + area_b - intersection)


def point_in_polygon(x: float, y: float, points: list[dict[str, float]]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        crosses = (current["y"] > y) != (previous["y"] > y)
        if crosses:
            boundary_x = (previous["x"] - current["x"]) * (y - current["y"]) / (
                previous["y"] - current["y"]
            ) + current["x"]
            if x < boundary_x:
                inside = not inside
        previous = current
    return inside


def inspect_polygon(
    points: list[dict[str, float]], prompt_box: tuple[float, float, float, float]
) -> dict[str, object]:
    bounds = polygon_bounds(points)
    prompt_area = max(1.0, (prompt_box[2] - prompt_box[0]) * (prompt_box[3] - prompt_box[1]))
    bounds_area = max(1.0, (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
    area_ratio = polygon_area(points) / prompt_area
    containment = intersection_area(bounds, prompt_box) / bounds_area
    center_inside = point_in_polygon(
        (prompt_box[0] + prompt_box[2]) / 2,
        (prompt_box[1] + prompt_box[3]) / 2,
        points,
    )
    reasons = []
    if not center_inside:
        reasons.append("prompt_center_outside_polygon")
    if containment < 0.72:
        reasons.append("polygon_extends_beyond_prompt")
    if area_ratio < 0.12:
        reasons.append("polygon_too_small")
    if area_ratio > 1.35:
        reasons.append("polygon_too_large")
    return {
        "status": "pass" if not reasons else "suspect",
        "reasons": reasons,
        "areaRatio": round(area_ratio, 4),
        "boundsContainment": round(containment, 4),
        "centerInside": center_inside,
        "bounds": [round(value, 2) for value in bounds],
    }


def parse_sources(values: list[str]) -> dict[str, Path]:
    sources = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"annotation source must use NAME=DIR: {value}")
        name, directory = value.split("=", 1)
        sources[name] = Path(directory).resolve()
    return sources


def main() -> None:
    args = build_parser().parse_args()
    prompts = json.loads(Path(args.prompts).read_text(encoding="utf-8"))
    sources = parse_sources(args.annotations)
    rows = []
    summary = {name: {"pass": 0, "suspect": 0, "missing": 0} for name in sources}

    for image_item in prompts["images"]:
        file_name = image_item["fileName"]
        stem = Path(file_name).stem
        for source_name, source_dir in sources.items():
            annotation_path = source_dir / f"{stem}.json"
            if not annotation_path.exists():
                summary[source_name]["missing"] += len(image_item["boxes"])
                continue
            document = json.loads(annotation_path.read_text(encoding="utf-8"))
            width = document["image"]["width"]
            height = document["image"]["height"]
            annotations = document["annotations"]
            for index, normalized_box in enumerate(image_item["boxes"]):
                if index >= len(annotations):
                    summary[source_name]["missing"] += 1
                    continue
                box = (
                    normalized_box[0] * width,
                    normalized_box[1] * height,
                    normalized_box[2] * width,
                    normalized_box[3] * height,
                )
                metrics = inspect_polygon(annotations[index]["polygon"], box)
                rows.append(
                    {
                        "fileName": file_name,
                        "nailIndex": index + 1,
                        "source": source_name,
                        **metrics,
                    }
                )

    for row in rows:
        peers = [
            peer
            for peer in rows
            if peer is not row
            and peer["fileName"] == row["fileName"]
            and peer["source"] == row["source"]
        ]
        maximum_overlap = max((bounds_iou(row["bounds"], peer["bounds"]) for peer in peers), default=0.0)
        row["maximumPeerBoundsIou"] = round(maximum_overlap, 4)
        if maximum_overlap > 0.35:
            row["reasons"].append("candidate_overlaps_peer")
            row["status"] = "suspect"

    for source_name in sources:
        source_rows = [row for row in rows if row["source"] == source_name]
        summary[source_name]["pass"] = sum(row["status"] == "pass" for row in source_rows)
        summary[source_name]["suspect"] = sum(row["status"] == "suspect" for row in source_rows)

    report = {
        "version": "nail-texture-assisted-annotation-audit/v1",
        "decision": "candidate_only_not_training_truth",
        "thresholds": {
            "minimumBoundsContainment": 0.72,
            "minimumAreaRatio": 0.12,
            "maximumAreaRatio": 1.35,
            "promptCenterMustBeInside": True,
            "maximumPeerBoundsIou": 0.35,
        },
        "summary": summary,
        "rows": rows,
    }
    report_path = Path(args.report)
    csv_path = Path(args.csv)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "reasons": "|".join(row["reasons"])})


if __name__ == "__main__":
    main()
