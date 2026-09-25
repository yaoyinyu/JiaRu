#!/usr/bin/env python3
"""Render source32 hybrid candidate as untinted original-resolution outlines."""

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
    with Image.open(path) as prior:
        if prior.size != image.size or prior.convert("RGB").tobytes() != image.tobytes():
            raise ValueError(f"hybrid outline drift: {path}")
    return bind(path)


def build(shard_path: Path, source_path: Path, candidate_path: Path,
          build_report_path: Path, output_dir: Path) -> dict:
    shard, candidate, report = map(load, (shard_path, candidate_path, build_report_path))
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == 32)
    if (source["sourceFileName"] != candidate["image"]["fileName"] or
            source["sourceGroup"] != candidate["image"]["sourceGroup"] or
            candidate["trainingUse"] != "prohibited" or
            report["decision"] != "candidate_only_not_training_or_test_truth" or
            report["polygonCount"] != 5 or report["pairwiseOverlapCount"] != 0 or
            len(candidate["annotations"]) != 5 or
            sha(source_path) != source["sourceImage"]["sha256"]):
        raise ValueError("source32 hybrid identity/quality mismatch")
    with Image.open(source_path) as opened:
        image = opened.convert("RGB")
    if image.size != (1080, 1440):
        raise ValueError("source32 dimensions drift")
    polygons = [[(point["x"], point["y"]) for point in nail["polygon"]]
                for nail in candidate["annotations"]]
    shapes = [Polygon(points) for points in polygons]
    legal = sum(shape.is_valid and shape.area > 1 for shape in shapes)
    overlaps = sum(shapes[i].intersection(shapes[j]).area > 0
                   for i in range(5) for j in range(i + 1, 5))
    if legal != 5 or overlaps:
        raise ValueError("source32 hybrid topology failure")
    outlined = image.copy()
    pen = ImageDraw.Draw(outlined)
    for index, points in enumerate(polygons, start=1):
        pen.line(points + points[:1], fill=(255, 0, 0), width=2)
        pen.text(points[0], str(index), fill=(255, 255, 0))
    output_dir.mkdir(parents=True, exist_ok=True)
    full = save_exact(outlined, output_dir / "full-old-style-outline.png")
    crops = []
    for nail in source["nails"]:
        index = nail["truthIndex"]
        x1, y1, x2, y2 = nail["cropBox"]
        box = (x1, y1, x2, y2)
        pair = {}
        for name, canvas in (("source", image), ("outline", outlined)):
            crop = canvas.crop(box).resize(((x2 - x1) * 3, (y2 - y1) * 3),
                                           Image.Resampling.NEAREST)
            pair[name] = save_exact(crop, output_dir / f"nail-{index:02d}-{name}-3x.png")
        crops.append({"nailIndex": index, "cropBoxPixels": list(box), **pair})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_hybrid_outline_visual_review_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "shardReport": bind(shard_path),
                       "isolatedImage": bind(source_path),
                       "hybridAnnotation": bind(candidate_path),
                       "hybridBuildReport": bind(build_report_path)},
            "fullOutline": full, "crops": crops,
            "counts": {"polygons": 5, "legalPolygons": legal,
                       "overlapPairs": overlaps, "visualApproved": 0,
                       "newTrainingApprovedSources": 0},
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--isolated-image", type=Path)
    parser.add_argument("--annotation", type=Path)
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            checked(item)
        checked(prior["fullOutline"])
        for crop in prior["crops"]:
            checked(crop["source"])
            checked(crop["outline"])
        inputs = prior["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["isolatedImage"]["path"]),
                        Path(inputs["hybridAnnotation"]["path"]),
                        Path(inputs["hybridBuildReport"]["path"]),
                        Path(prior["fullOutline"]["path"]).parent)
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.shard, args.isolated_image, args.annotation,
                args.build_report, args.output_dir, args.report)):
        parser.error("all inputs and outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.shard.resolve(), args.isolated_image.resolve(),
                   args.annotation.resolve(), args.build_report.resolve(),
                   args.output_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
