#!/usr/bin/env python3
"""Combine reviewed old polygons with directed SAM candidates for source27."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon, box


SAM_TRUTH_INDICES = (1, 5)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_exact(document: dict, path: Path, verify: bool) -> dict:
    data = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if verify:
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"hybrid annotation drift: {path}")
    else:
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return bind(path)


def save_exact(image: Image.Image, path: Path, verify: bool) -> dict:
    if verify:
        if not path.is_file():
            raise ValueError(f"missing review crop: {path}")
    else:
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    with Image.open(path) as previous:
        if previous.size != image.size or previous.convert("RGB").tobytes() != image.tobytes():
            raise ValueError(f"hybrid review crop drift: {path}")
    return bind(path)


def build(old_outline_path: Path, sam_audit_path: Path, preflight_path: Path,
          output_dir: Path, *, verify: bool) -> dict:
    old, sam, preflight = map(load, (old_outline_path, sam_audit_path, preflight_path))
    if (old["decision"] !=
            "source025027_old_polygon_original_resolution_review_pending" or
            sam["decision"] != "source025027_sam_geometry_pass_visual_review_pending" or
            sam["trainingUse"] != "prohibited" or
            preflight["trainingUse"] != "prohibited"):
        raise ValueError("source27 hybrid upstream contract mismatch")
    source = next(row for row in old["sources"] if row["ordinal"] == 27)
    candidate = next(row for row in sam["sources"] if row["ordinal"] == 27)
    batch = next(row for row in preflight["sources"] if row["ordinal"] == 27)
    if (source["sourceFileName"] != candidate["sourceFileName"] != batch["sourceFileName"] or
            source["sourceGroup"] != candidate["sourceGroup"] != batch["sourceGroup"] or
            source["sourceImage"] != candidate["sourceImage"] != batch["sourceImage"] or
            source["isolatedImage"] != candidate["isolatedImage"] != batch["isolatedSourceImage"] or
            [item["truthIndex"] for item in candidate["nails"]] != list(SAM_TRUTH_INDICES) or
            source["dimensions"] != [800, 800] or
            batch["historicalCanonicalCount"] != 0):
        raise ValueError("source27 frozen identity/mapping mismatch")
    for binding in (source["sourceImage"], source["sourceLabel"],
                    source["isolatedImage"], candidate["samAnnotation"]):
        checked(binding)
    with Image.open(source["isolatedImage"]["path"]) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != source["dimensions"]:
        raise ValueError("source27 dimensions drift")
    sam_annotation = load(Path(candidate["samAnnotation"]["path"]))
    lines = Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    if len(lines) != 5 or len(sam_annotation["annotations"]) != 2:
        raise ValueError("source27 polygon count drift")
    annotations = []
    shapes = []
    for truth_index, line in enumerate(lines, start=1):
        if truth_index in SAM_TRUTH_INDICES:
            prompt_index = SAM_TRUTH_INDICES.index(truth_index)
            polygon = sam_annotation["annotations"][prompt_index]["polygon"]
            origin = "directed_sam_candidate"
        else:
            values = [float(value) for value in line.split()]
            if values[0] != 0 or len(values) < 9 or (len(values) - 1) % 2:
                raise ValueError(f"old polygon {truth_index} format drift")
            polygon = [{"x": x * width, "y": y * height}
                       for x, y in zip(values[1::2], values[2::2], strict=True)]
            origin = "frozen_old_label_visual_review_pending"
        shape = Polygon([(p["x"], p["y"]) for p in polygon])
        if not shape.is_valid or shape.area <= 1:
            raise ValueError(f"source27 nail {truth_index} invalid polygon")
        shapes.append(shape)
        annotations.append({"id": f"n{truth_index}", "label": "nail_texture",
                            "polygon": polygon,
                            "attributes": {"sourceTruthIndex": truth_index,
                                           "polygonOrigin": origin,
                                           "artificialTip": True}})
    overlaps = sum(shapes[i].intersection(shapes[j]).area > 0
                   for i in range(5) for j in range(i + 1, 5))
    if overlaps:
        raise ValueError("source27 hybrid polygons overlap")
    mark = box(*batch["markBoxPixels"])
    logo_overlaps = sum(shape.intersection(mark).area > 0 for shape in shapes)
    if logo_overlaps:
        raise ValueError("source27 hybrid polygon overlaps watermark")
    document = {"version": "nail-texture-dataset/v1",
                "decision": "candidate_only_not_training_truth",
                "trainingUse": "prohibited",
                "image": {"fileName": source["sourceFileName"],
                          "sourceGroup": source["sourceGroup"],
                          "sourceImageSha256": source["sourceImage"]["sha256"],
                          "width": width, "height": height},
                "annotations": annotations}
    annotation = write_exact(document, output_dir / "annotation.json", verify)
    outlined = image.copy()
    pen = ImageDraw.Draw(outlined)
    for index, item in enumerate(annotations, start=1):
        points = [(p["x"], p["y"]) for p in item["polygon"]]
        pen.line(points + points[:1], fill=(255, 0, 0), width=2)
        pen.text(points[0], str(index), fill=(255, 255, 0))
    full = save_exact(outlined, output_dir / "full-outline.png", verify)
    crops = []
    for index, shape in enumerate(shapes, start=1):
        left, top, right, bottom = shape.bounds
        x1, y1 = max(0, int(left) - 32), max(0, int(top) - 32)
        x2, y2 = min(width, int(right) + 33), min(height, int(bottom) + 33)
        pair = {}
        for name, canvas in (("source", image), ("outline", outlined)):
            crop = canvas.crop((x1, y1, x2, y2)).resize(
                ((x2 - x1) * 3, (y2 - y1) * 3), Image.Resampling.NEAREST)
            pair[name] = save_exact(
                crop, output_dir / f"nail-{index:02d}-{name}-3x.png", verify)
        crops.append({"truthIndex": index, "cropBoxPixels": [x1, y1, x2, y2],
                      "polygonOrigin": annotations[index - 1]["attributes"]["polygonOrigin"],
                      **pair})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source027_five_nail_hybrid_candidate_visual_review_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "oldOutline": bind(old_outline_path),
                       "samCandidateAudit": bind(sam_audit_path),
                       "batchPreflight": bind(preflight_path),
                       "sourceImage": source["sourceImage"],
                       "oldLabel": source["sourceLabel"],
                       "samAnnotation": candidate["samAnnotation"]},
            "annotation": annotation, "fullOutline": full, "crops": crops,
            "sourceOrdinal": 27, "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"],
            "counts": {"polygons": 5, "legalPolygons": 5,
                       "overlapPairs": overlaps, "logoOverlapPairs": logo_overlaps,
                       "retainedOldPolygons": 3, "directedSamPolygons": 2,
                       "visualApproved": 0, "newTrainingApprovedSources": 0},
            "watermarkShortcutAbsenceProven": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--sam-audit", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for item in previous["inputs"].values():
            checked(item)
        checked(previous["annotation"])
        checked(previous["fullOutline"])
        for crop in previous["crops"]:
            checked(crop["source"])
            checked(crop["outline"])
        current = build(Path(previous["inputs"]["oldOutline"]["path"]),
                        Path(previous["inputs"]["samCandidateAudit"]["path"]),
                        Path(previous["inputs"]["batchPreflight"]["path"]),
                        Path(previous["annotation"]["path"]).parent,
                        verify=True)
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.old_outline, args.sam_audit, args.preflight,
                args.output_dir, args.report)):
        parser.error("all inputs/outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.old_outline.resolve(), args.sam_audit.resolve(),
                   args.preflight.resolve(), args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
