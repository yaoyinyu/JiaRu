#!/usr/bin/env python3
"""Bind SAM candidate topology and untinted review crops for sources 37/39."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


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
            raise ValueError(f"SAM review artifact drift: {path}")
    return bind(path)


def build(prompt_path: Path, sam_path: Path, geometry_path: Path,
          old_outline_path: Path, output_dir: Path) -> dict:
    prompts, sam, geometry, old = map(load, (prompt_path, sam_path,
                                             geometry_path, old_outline_path))
    if (prompts["decision"] != "source037039_one_directed_sam_pass_candidate_only" or
            sam["decision"] != "sam_candidate_only_not_training_truth" or
            not sam["ok"] or sam["completedCount"] != 2 or
            sam["promptCount"] != 3 or sam["errors"] or
            geometry["decision"] != "candidate_only_not_training_truth" or
            len(geometry["rows"]) != 3 or
            any(row["status"] != "pass" for row in geometry["rows"]) or
            old["decision"] !=
            "source037039_old_polygon_original_resolution_review_pending"):
        raise ValueError("source037039 SAM input/geometry contract mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for item, output, prior in zip(prompts["images"], sam["outputs"], old["sources"], strict=True):
        ordinal = item["sourceOrdinal"]
        if (ordinal != prior["ordinal"] or
                item["fileName"] != output["fileName"] != prior["sourceFileName"] or
                item["sourceGroup"] != output["sourceGroup"] != prior["sourceGroup"] or
                item["sourceImageSha256"] != prior["sourceImage"]["sha256"] or
                output["polygonCount"] != len(item["promptTruthIndices"])):
            raise ValueError(f"source {ordinal} SAM frozen identity mismatch")
        checked(prior["isolatedImage"])
        annotation_path = Path(output["annotationPath"])
        annotation = load(annotation_path)
        if (annotation["image"]["fileName"] != item["fileName"] or
                annotation["image"]["sourceGroup"] != item["sourceGroup"] or
                annotation["trainingUse"] != "prohibited" or
                len(annotation["annotations"]) != output["polygonCount"]):
            raise ValueError(f"source {ordinal} SAM annotation mismatch")
        with Image.open(prior["isolatedImage"]["path"]) as opened:
            source = opened.convert("RGB")
        width, height = source.size
        if [width, height] != prior["dimensions"]:
            raise ValueError(f"source {ordinal} dimensions drift")
        outlined = source.copy()
        pen = ImageDraw.Draw(outlined)
        nails = []
        polygons = []
        for index, (truth, nail, box, positive, negative) in enumerate(
                zip(item["promptTruthIndices"], annotation["annotations"],
                    item["boxes"], item["positivePoints"],
                    item["negativePoints"], strict=True), start=1):
            points = [(p["x"], p["y"]) for p in nail["polygon"]]
            shape = Polygon(points)
            if not shape.is_valid or shape.area <= 1:
                raise ValueError(f"source {ordinal} prompt {index} invalid polygon")
            polygons.append(shape)
            plus = sum(shape.covers(Point(x * width, y * height)) for x, y in positive)
            minus = sum(shape.covers(Point(x * width, y * height)) for x, y in negative)
            pen.line(points + points[:1], fill=(255, 0, 0), width=2)
            pen.text(points[0], str(truth), fill=(255, 255, 0))
            x1 = max(0, int(box[0] * width) - 36)
            y1 = max(0, int(box[1] * height) - 36)
            x2 = min(width, int(box[2] * width) + 36)
            y2 = min(height, int(box[3] * height) + 36)
            nails.append({"truthIndex": truth, "promptIndex": index,
                          "positiveHits": plus, "positiveCount": len(positive),
                          "negativeHits": minus, "negativeCount": len(negative),
                          "polygonArea": round(shape.area, 3),
                          "cropBoxPixels": [x1, y1, x2, y2]})
        overlaps = sum(polygons[i].intersection(polygons[j]).area > 0
                       for i in range(len(polygons))
                       for j in range(i + 1, len(polygons)))
        if overlaps:
            raise ValueError(f"source {ordinal} SAM polygon overlap")
        full = save_exact(outlined, output_dir / f"source-{ordinal:03d}-sam-outline.png")
        for nail in nails:
            truth = nail["truthIndex"]
            x1, y1, x2, y2 = nail["cropBoxPixels"]
            for name, canvas in (("source", source), ("outline", outlined)):
                crop = canvas.crop((x1, y1, x2, y2)).resize(
                    ((x2 - x1) * 3, (y2 - y1) * 3), Image.Resampling.NEAREST)
                nail[name] = save_exact(
                    crop, output_dir / f"source-{ordinal:03d}-nail-{truth:02d}-{name}-3x.png")
        sources.append({"ordinal": ordinal, "sourceFileName": item["fileName"],
                        "sourceGroup": item["sourceGroup"],
                        "sourceImage": prior["sourceImage"],
                        "isolatedImage": prior["isolatedImage"],
                        "samAnnotation": bind(annotation_path),
                        "samOverlay": bind(Path(output["overlayPath"])),
                        "fullOutline": full, "nails": nails,
                        "legalCandidatePolygons": len(polygons),
                        "overlapPairs": overlaps,
                        "visualApproved": 0, "trainingUse": "prohibited"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source037039_sam_geometry_pass_visual_review_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "prompts": bind(prompt_path), "samReport": bind(sam_path),
                       "samGeometry": bind(geometry_path),
                       "oldOutline": bind(old_outline_path)},
            "sources": sources, "newTrainingApprovedSources": 0,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path)
    parser.add_argument("--sam-report", type=Path)
    parser.add_argument("--geometry", type=Path)
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for item in old["inputs"].values():
            checked(item)
        for source in old["sources"]:
            for key in ("sourceImage", "isolatedImage", "samAnnotation", "samOverlay", "fullOutline"):
                checked(source[key])
            for nail in source["nails"]:
                checked(nail["source"])
                checked(nail["outline"])
        current = build(Path(old["inputs"]["prompts"]["path"]),
                        Path(old["inputs"]["samReport"]["path"]),
                        Path(old["inputs"]["samGeometry"]["path"]),
                        Path(old["inputs"]["oldOutline"]["path"]),
                        Path(old["sources"][0]["fullOutline"]["path"]).parent)
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.prompts, args.sam_report, args.geometry, args.old_outline,
                args.output_dir, args.report)):
        parser.error("all inputs/outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.prompts.resolve(), args.sam_report.resolve(),
                   args.geometry.resolve(), args.old_outline.resolve(),
                   args.output_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
