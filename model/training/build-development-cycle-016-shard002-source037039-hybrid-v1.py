#!/usr/bin/env python3
"""Build candidate-only five-nail hybrids for shard002 sources 37/39."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


SAM_TRUTH_INDICES = {37: (4, 5), 39: (4,)}


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


def build(old_path: Path, sam_path: Path, output_dir: Path, *, verify: bool) -> dict:
    old, sam = map(load, (old_path, sam_path))
    if (old["decision"] !=
            "source037039_old_polygon_original_resolution_review_pending"
            or sam["decision"] != "source037039_sam_geometry_pass_visual_review_pending"
            or old["trainingUse"] != "prohibited"
            or sam["trainingUse"] != "prohibited"
            or sam["inputs"]["oldOutline"]["sha256"] != sha(old_path)):
        raise ValueError("hybrid upstream contract mismatch")
    for report in (old, sam):
        for item in report["inputs"].values():
            checked(item)
    sources = []
    for source, candidate in zip(old["sources"], sam["sources"], strict=True):
        ordinal = source["ordinal"]
        if (ordinal not in SAM_TRUTH_INDICES
                or ordinal != candidate["ordinal"]
                or source["sourceFileName"] != candidate["sourceFileName"]
                or source["sourceGroup"] != candidate["sourceGroup"]
                or source["sourceImage"] != candidate["sourceImage"]
                or source["isolatedImage"] != candidate["isolatedImage"]
                or [item["truthIndex"] for item in candidate["nails"]]
                != list(SAM_TRUTH_INDICES[ordinal])):
            raise ValueError(f"source {ordinal} frozen identity/mapping mismatch")
        for item in (source["sourceImage"], source["sourceLabel"],
                     source["isolatedImage"], candidate["samAnnotation"]):
            checked(item)
        with Image.open(source["isolatedImage"]["path"]) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        if [width, height] != source["dimensions"]:
            raise ValueError(f"source {ordinal} dimensions drift")
        sam_annotation = load(Path(candidate["samAnnotation"]["path"]))
        lines = Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
        if len(lines) != 5 or len(sam_annotation["annotations"]) != len(SAM_TRUTH_INDICES[ordinal]):
            raise ValueError(f"source {ordinal} polygon count drift")
        annotations = []
        shapes = []
        for truth_index, line in enumerate(lines, start=1):
            if truth_index in SAM_TRUTH_INDICES[ordinal]:
                prompt_index = SAM_TRUTH_INDICES[ordinal].index(truth_index)
                polygon = sam_annotation["annotations"][prompt_index]["polygon"]
                origin = "directed_sam_candidate"
            else:
                values = [float(value) for value in line.split()]
                if values[0] != 0 or len(values) < 9 or (len(values) - 1) % 2:
                    raise ValueError(f"source {ordinal} old polygon {truth_index} format drift")
                polygon = [{"x": x * width, "y": y * height}
                           for x, y in zip(values[1::2], values[2::2], strict=True)]
                origin = "frozen_old_label_pending_full_image_visual_review"
            shape = Polygon([(point["x"], point["y"]) for point in polygon])
            if not shape.is_valid or shape.area <= 1:
                raise ValueError(f"source {ordinal} nail {truth_index} invalid polygon")
            shapes.append(shape)
            annotations.append({"id": f"n{truth_index}", "label": "nail_texture",
                                "polygon": polygon,
                                "attributes": {"sourceTruthIndex": truth_index,
                                               "polygonOrigin": origin,
                                               "artificialTip": True}})
        overlaps = sum(shapes[i].intersection(shapes[j]).area > 0
                       for i in range(5) for j in range(i + 1, 5))
        if overlaps:
            raise ValueError(f"source {ordinal} hybrid polygon overlap")
        document = {"version": "nail-texture-dataset/v1",
                    "decision": "candidate_only_not_training_truth",
                    "trainingUse": "prohibited",
                    "image": {"fileName": source["sourceFileName"],
                              "sourceGroup": source["sourceGroup"],
                              "sourceImageSha256": source["sourceImage"]["sha256"],
                              "width": width, "height": height},
                    "annotations": annotations}
        target = output_dir / f"source-{ordinal:03d}"
        annotation = write_exact(document, target / "annotation.json", verify)
        outlined = image.copy()
        pen = ImageDraw.Draw(outlined)
        for index, item in enumerate(annotations, start=1):
            points = [(point["x"], point["y"]) for point in item["polygon"]]
            pen.line(points + points[:1], fill=(255, 0, 0), width=2)
            pen.text(points[0], str(index), fill=(255, 255, 0))
        full = save_exact(outlined, target / "full-outline.png", verify)
        crops = []
        for index, shape in enumerate(shapes, start=1):
            left, top, right, bottom = shape.bounds
            x1, y1 = max(0, int(left) - 32), max(0, int(top) - 32)
            x2, y2 = min(width, int(right) + 33), min(height, int(bottom) + 33)
            pair = {}
            for name, canvas in (("source", image), ("outline", outlined)):
                crop = canvas.crop((x1, y1, x2, y2)).resize(
                    ((x2 - x1) * 3, (y2 - y1) * 3), Image.Resampling.NEAREST)
                pair[name] = save_exact(crop, target / f"nail-{index:02d}-{name}-3x.png",
                                        verify)
            crops.append({"truthIndex": index, "cropBoxPixels": [x1, y1, x2, y2],
                          "polygonOrigin": annotations[index - 1]["attributes"]["polygonOrigin"],
                          **pair})
        sources.append({"sourceOrdinal": ordinal, "sourceFileName": source["sourceFileName"],
                        "sourceGroup": source["sourceGroup"],
                        "sourceImage": source["sourceImage"],
                        "oldLabel": source["sourceLabel"],
                        "isolatedImage": source["isolatedImage"],
                        "samAnnotation": candidate["samAnnotation"],
                        "annotation": annotation, "fullOutline": full, "crops": crops,
                        "counts": {"polygons": 5, "legalPolygons": 5,
                                   "overlapPairs": overlaps,
                                   "retainedOldPolygons": 5 - len(SAM_TRUTH_INDICES[ordinal]),
                                   "directedSamPolygons": len(SAM_TRUTH_INDICES[ordinal]),
                                   "visualApproved": 0, "newTrainingApprovedSources": 0},
                        "watermarkShortcutAbsenceProven": False,
                        "trainingUse": "prohibited"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source037039_five_nail_hybrid_candidates_visual_review_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "oldOutline": bind(old_path),
                       "samCandidateAudit": bind(sam_path)},
            "sources": sources, "newTrainingApprovedSources": 0,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--sam-audit", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for item in previous["inputs"].values():
            checked(item)
        for source in previous["sources"]:
            for key in ("sourceImage", "oldLabel", "isolatedImage", "samAnnotation",
                        "annotation", "fullOutline"):
                checked(source[key])
            for crop in source["crops"]:
                checked(crop["source"])
                checked(crop["outline"])
        current = build(Path(previous["inputs"]["oldOutline"]["path"]),
                        Path(previous["inputs"]["samCandidateAudit"]["path"]),
                        Path(previous["sources"][0]["annotation"]["path"]).parent.parent,
                        verify=True)
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.old_outline, args.sam_audit, args.output_dir, args.report)):
        parser.error("all inputs/outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.old_outline.resolve(), args.sam_audit.resolve(),
                   args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
