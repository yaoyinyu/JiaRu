#!/usr/bin/env python3
"""Bind source32 SAM topology and five original-pixel review crops."""

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


def build(prompts_path: Path, sam_path: Path, geometry_path: Path,
          output_dir: Path) -> dict:
    prompts, sam, geometry = map(load, (prompts_path, sam_path, geometry_path))
    if (prompts["decision"] != "source032_one_directed_sam_retry_candidate_only" or
            prompts["trainingUse"] != "prohibited" or
            sam["decision"] != "sam_candidate_only_not_training_truth" or
            sam["trainingUse"] != "prohibited" or
            not sam["ok"] or sam["completedCount"] != 1 or
            sam["errors"] != []):
        raise ValueError("source32 SAM input contract mismatch")
    if (sam["outputs"][0]["polygonCount"] != 5 or
            geometry["decision"] != "candidate_only_not_training_truth" or
            len(geometry["rows"]) != 5 or
            any(row["status"] != "pass" for row in geometry["rows"])):
        raise ValueError("source32 SAM geometry mismatch")
    item = prompts["images"][0]
    output = sam["outputs"][0]
    if (item["fileName"] != output["fileName"] or
            item["sourceGroup"] != output["sourceGroup"] or
            len(item["boxes"]) != 5):
        raise ValueError("source32 SAM image identity mismatch")
    source_path = Path(prompts["inputs"]["isolatedImage"]["path"])
    checked(prompts["inputs"]["isolatedImage"])
    annotation_path = Path(output["annotationPath"])
    annotation = load(annotation_path)
    if (annotation["image"]["fileName"] != item["fileName"] or
            annotation["image"]["sourceGroup"] != item["sourceGroup"] or
            annotation["trainingUse"] != "prohibited" or
            len(annotation["annotations"]) != 5):
        raise ValueError("source32 SAM annotation identity mismatch")
    polygons = [Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
                for nail in annotation["annotations"]]
    legal = sum(poly.is_valid and poly.area > 1 for poly in polygons)
    overlaps = sum(polygons[i].intersection(polygons[j]).area > 0
                   for i in range(5) for j in range(i + 1, 5))
    if legal != 5 or overlaps:
        raise ValueError("source32 SAM topology/overlap failure")
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as opened:
        source = opened.convert("RGB")
    width, height = source.size
    if (width, height) != (1080, 1440):
        raise ValueError("source32 dimensions drift")
    overlay = source.copy()
    draw = ImageDraw.Draw(overlay)
    for index, nail in enumerate(annotation["annotations"], start=1):
        points = [(p["x"], p["y"]) for p in nail["polygon"]]
        draw.line(points + points[:1], fill=(255, 0, 0), width=2)
        draw.text(points[0], str(index), fill=(255, 255, 0))
    crops = []
    for index, box in enumerate(item["boxes"], start=1):
        x1 = max(0, int(box[0] * width) - 36)
        y1 = max(0, int(box[1] * height) - 36)
        x2 = min(width, int(box[2] * width) + 36)
        y2 = min(height, int(box[3] * height) + 36)
        pixel_box = (x1, y1, x2, y2)
        pair = {}
        for name, image in (("source", source), ("overlay", overlay)):
            path = output_dir / f"nail-{index:02d}-{name}-2x.png"
            expected = image.crop(pixel_box).resize(
                ((x2 - x1) * 2, (y2 - y1) * 2), Image.Resampling.NEAREST)
            if not path.exists():
                expected.save(path)
            with Image.open(path) as actual:
                if actual.size != expected.size or actual.convert("RGB").tobytes() != expected.tobytes():
                    raise ValueError(f"review crop drift: {path}")
            pair[name] = bind(path)
        crops.append({"nailIndex": index, "cropBoxPixels": list(pixel_box), **pair})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_directed_retry_geometry_pass_original_resolution_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "prompts": bind(prompts_path),
                       "samReport": bind(sam_path), "geometry": bind(geometry_path),
                       "sourceImage": bind(source_path),
                       "annotation": bind(annotation_path),
                       "fullOverlay": bind(Path(output["overlayPath"]))},
            "counts": {"sourceImages": 1, "polygons": 5,
                       "legalPolygons": legal, "overlapPairs": overlaps,
                       "visualApproved": 0, "trainingApproved": 0},
            "crops": crops, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path)
    parser.add_argument("--sam-report", type=Path)
    parser.add_argument("--geometry", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            checked(item)
        for crop in prior["crops"]:
            checked(crop["source"])
            checked(crop["overlay"])
        current = build(Path(prior["inputs"]["prompts"]["path"]),
                        Path(prior["inputs"]["samReport"]["path"]),
                        Path(prior["inputs"]["geometry"]["path"]),
                        Path(prior["crops"][0]["source"]["path"]).parent)
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prompts, args.sam_report, args.geometry, args.output_dir, args.report)):
        parser.error("all inputs and outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.prompts.resolve(), args.sam_report.resolve(),
                   args.geometry.resolve(), args.output_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
