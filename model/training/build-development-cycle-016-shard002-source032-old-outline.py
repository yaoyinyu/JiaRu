#!/usr/bin/env python3
"""Render source32's frozen YOLO polygons as outlines without mask tint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


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
    with Image.open(path) as current:
        if current.size != image.size or current.convert("RGB").tobytes() != image.tobytes():
            raise ValueError(f"outline artifact drift: {path}")
    return bind(path)


def build(shard_path: Path, canonical_path: Path, isolated_path: Path,
          output_dir: Path) -> dict:
    shard, canonical = load(shard_path), load(canonical_path)
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == 32)
    if (canonical["decision"] != "historical_approved_truth_is_same_defective_cycle012_polygon" or
            canonical["sourceOrdinal"] != 32 or
            canonical["sourceFileName"] != source["sourceFileName"] or
            canonical["sourceGroup"] != source["sourceGroup"] or
            len(source["nails"]) != 5):
        raise ValueError("source32 frozen identity mismatch")
    checked(source["sourceImage"])
    checked(source["sourceLabel"])
    if sha(isolated_path) != source["sourceImage"]["sha256"]:
        raise ValueError("source32 isolated image drift")
    with Image.open(isolated_path) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if (width, height) != (1080, 1440):
        raise ValueError("source32 dimensions drift")
    polygons = []
    for line in Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines():
        values = [float(value) for value in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2:
            raise ValueError("source32 YOLO class/vertex mismatch")
        coords = list(zip((x * width for x in values[1::2]),
                          (y * height for y in values[2::2]), strict=True))
        polygons.append(coords)
    if len(polygons) != 5:
        raise ValueError("source32 label count drift")
    shapes = [Polygon(points) for points in polygons]
    legal = sum(shape.is_valid and shape.area > 1 for shape in shapes)
    overlaps = sum(shapes[i].intersection(shapes[j]).area > 0
                   for i in range(5) for j in range(i + 1, 5))
    if legal != 5 or overlaps:
        raise ValueError("source32 old polygon topology/overlap failure")
    outlined = image.copy()
    pen = ImageDraw.Draw(outlined)
    for index, points in enumerate(polygons, start=1):
        pen.line(points + points[:1], fill=(255, 0, 0), width=2)
        pen.text(points[0], str(index), fill=(255, 255, 0))
    output_dir.mkdir(parents=True, exist_ok=True)
    crops = []
    for nail in source["nails"]:
        index = nail["truthIndex"]
        x1, y1, x2, y2 = nail["cropBox"]
        box = (x1, y1, x2, y2)
        pair = {}
        for name, canvas in (("source", image), ("old-outline", outlined)):
            crop = canvas.crop(box).resize(((x2 - x1) * 3, (y2 - y1) * 3),
                                           Image.Resampling.NEAREST)
            pair[name] = save_exact(crop, output_dir / f"nail-{index:02d}-{name}-3x.png")
        crops.append({"nailIndex": index, "cropBoxPixels": list(box), **pair})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_frozen_old_polygon_original_resolution_reassessment_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "shardReport": bind(shard_path),
                       "canonicalIdentity": bind(canonical_path),
                       "isolatedImage": bind(isolated_path),
                       "oldLabel": source["sourceLabel"]},
            "counts": {"polygons": 5, "legalPolygons": legal,
                       "overlapPairs": overlaps, "visualApproved": 0,
                       "newTrainingApprovedSources": 0},
            "crops": crops, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--isolated-image", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            checked(item)
        for item in prior["crops"]:
            checked(item["source"])
            checked(item["old-outline"])
        inputs = prior["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["canonicalIdentity"]["path"]),
                        Path(inputs["isolatedImage"]["path"]),
                        Path(prior["crops"][0]["source"]["path"]).parent)
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.shard, args.canonical, args.isolated_image,
                args.output_dir, args.report)):
        parser.error("all inputs and outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.shard.resolve(), args.canonical.resolve(),
                   args.isolated_image.resolve(), args.output_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
