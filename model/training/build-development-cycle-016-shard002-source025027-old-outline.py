#!/usr/bin/env python3
"""Bind and render the frozen old polygons for shard002 sources 25 and 27."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


ORDINALS = (25, 27)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_exact(image: Image.Image, path: Path) -> dict:
    if not path.exists():
        image.save(path)
    with Image.open(path) as previous:
        if previous.size != image.size or previous.convert("RGB").tobytes() != image.tobytes():
            raise ValueError(f"outline artifact drift: {path}")
    return bind(path)


def build(shard_path: Path, preflight_path: Path, progress_path: Path,
          output_dir: Path) -> dict:
    shard, preflight, progress = map(load, (shard_path, preflight_path, progress_path))
    if (shard["shard"]["shard"] != 2 or
            shard["shard"]["sourceImages"] != 20 or
            preflight["inputs"]["shardReport"]["sha256"] != sha(shard_path) or
            progress["counts"]["sourceImages"] != 20 or
            progress["counts"]["oldLabelNails"] != 104 or
            progress["counts"]["newTrainingApprovedSources"] != 0):
        raise ValueError("frozen shard/preflight/progress mismatch")
    for value in shard["inputs"].values():
        checked(value)
    for value in preflight["inputs"].values():
        checked(value)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for ordinal in ORDINALS:
        source = next(row for row in shard["sourceImages"] if row["ordinal"] == ordinal)
        batch = next(row for row in preflight["sources"] if row["ordinal"] == ordinal)
        state = next(row for row in progress["sourceDispositions"] if row["ordinal"] == ordinal)
        if (state["decision"] != "confirmed_label_rework" or
                state["trainingUse"] != "prohibited" or
                batch["historicalCanonicalCount"] != 0 or
                source["sourceFileName"] != batch["sourceFileName"] != state["sourceFileName"] or
                source["sourceGroup"] != batch["sourceGroup"] != state["sourceGroup"] or
                source["sourceImage"] != batch["sourceImage"] != state["sourceImage"] or
                source["sourceLabel"] != batch["sourceLabel"] != state["sourceLabel"] or
                len(source["nails"]) != 5):
            raise ValueError(f"source {ordinal} frozen identity/role mismatch")
        for key in ("sourceImage", "sourceLabel", "overview"):
            checked(source[key])
        checked(batch["isolatedSourceImage"])
        if batch["isolatedSourceImage"]["sha256"] != source["sourceImage"]["sha256"]:
            raise ValueError(f"source {ordinal} isolated copy mismatch")
        with Image.open(batch["isolatedSourceImage"]["path"]) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        if [width, height] != batch["dimensions"]:
            raise ValueError(f"source {ordinal} dimensions drift")
        polygons = []
        for line in Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines():
            values = [float(value) for value in line.split()]
            if values[0] != 0 or len(values) < 9 or (len(values) - 1) % 2:
                raise ValueError(f"source {ordinal} YOLO polygon format invalid")
            polygons.append(list(zip((x * width for x in values[1::2]),
                                     (y * height for y in values[2::2]), strict=True)))
        if len(polygons) != 5:
            raise ValueError(f"source {ordinal} old polygon count drift")
        shapes = [Polygon(points) for points in polygons]
        legal = sum(shape.is_valid and shape.area > 1 for shape in shapes)
        overlaps = sum(shapes[i].intersection(shapes[j]).area > 0
                       for i in range(5) for j in range(i + 1, 5))
        if legal != 5 or overlaps:
            raise ValueError(f"source {ordinal} old topology/overlap failure")
        outlined = image.copy()
        pen = ImageDraw.Draw(outlined)
        for index, points in enumerate(polygons, start=1):
            pen.line(points + points[:1], fill=(255, 0, 0), width=2)
            pen.text(points[0], str(index), fill=(255, 255, 0))
        full = save_exact(outlined, output_dir / f"source-{ordinal:03d}-old-outline.png")
        crops = []
        for nail in source["nails"]:
            index = nail["truthIndex"]
            x1, y1, x2, y2 = nail["cropBox"]
            box = (x1, y1, x2, y2)
            pair = {}
            for name, canvas in (("source", image), ("old-outline", outlined)):
                crop = canvas.crop(box).resize(((x2 - x1) * 3, (y2 - y1) * 3),
                                               Image.Resampling.NEAREST)
                pair[name] = save_exact(
                    crop, output_dir / f"source-{ordinal:03d}-nail-{index:02d}-{name}-3x.png")
            crops.append({"nailIndex": index, "cropBoxPixels": list(box), **pair})
        sources.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                        "sourceGroup": source["sourceGroup"],
                        "sourceImage": source["sourceImage"],
                        "sourceLabel": source["sourceLabel"],
                        "isolatedImage": batch["isolatedSourceImage"],
                        "logoCrop": batch["logoCrop"],
                        "logoBoxPixels": batch["markBoxPixels"],
                        "dimensions": [width, height], "legalOldPolygons": legal,
                        "oldOverlapPairs": overlaps, "fullOutline": full,
                        "crops": crops, "visualApproved": 0,
                        "trainingUse": "prohibited"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source025027_old_polygon_original_resolution_review_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "shardReport": bind(shard_path),
                       "batchPreflight": bind(preflight_path),
                       "progressV10": bind(progress_path)},
            "sources": sources, "newTrainingApprovedSources": 0,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        for source in old["sources"]:
            for key in ("sourceImage", "sourceLabel", "isolatedImage", "logoCrop", "fullOutline"):
                checked(source[key])
            for crop in source["crops"]:
                checked(crop["source"])
                checked(crop["old-outline"])
        current = build(Path(old["inputs"]["shardReport"]["path"]),
                        Path(old["inputs"]["batchPreflight"]["path"]),
                        Path(old["inputs"]["progressV10"]["path"]),
                        Path(old["sources"][0]["fullOutline"]["path"]).parent)
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.shard, args.preflight, args.progress, args.output_dir, args.report)):
        parser.error("all inputs/outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.shard.resolve(), args.preflight.resolve(), args.progress.resolve(),
                   args.output_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
