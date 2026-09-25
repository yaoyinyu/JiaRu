#!/usr/bin/env python3
"""Bind five-nail visual decisions and watermark locations for sources 37/39."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon, box


MARKS = {
    37: {
        "inspectionCrops": (
            ("sleeve-band", (75, 1120, 1030, 1245)),
            ("corner", (1000, 1385, 1080, 1440)),
        ),
        "instances": (
            ("feiyu_repeated_text", (110, 1160, 175, 1230)),
            ("feiyu_repeated_text", (310, 1160, 375, 1230)),
            ("feiyu_repeated_text", (520, 1160, 585, 1230)),
            ("feiyu_repeated_text", (720, 1160, 785, 1230)),
            ("feiyu_repeated_text", (920, 1160, 990, 1230)),
            ("xiaohongshu_corner_logo", (1033, 1410, 1080, 1440)),
        ),
    },
    39: {
        "inspectionCrops": (("author-handle", (760, 810, 1040, 935)),),
        "instances": (("white_author_handle_and_heart_icon", (795, 845, 1015, 920)),),
    },
}


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


def save_exact(image: Image.Image, path: Path, verify: bool) -> dict:
    if verify:
        if not path.is_file():
            raise ValueError(f"missing mark inspection crop: {path}")
    elif not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    with Image.open(path) as previous:
        if previous.size != image.size or previous.convert("RGB").tobytes() != image.tobytes():
            raise ValueError(f"mark inspection crop drift: {path}")
    return bind(path)


def build(old_path: Path, sam_path: Path, hybrid_path: Path,
          progress_path: Path, output_dir: Path, *, verify: bool) -> dict:
    old, sam, hybrid, progress = map(load, (old_path, sam_path, hybrid_path, progress_path))
    if (old["decision"] !=
            "source037039_old_polygon_original_resolution_review_pending"
            or sam["decision"] != "source037039_sam_geometry_pass_visual_review_pending"
            or hybrid["decision"] !=
            "source037039_five_nail_hybrid_candidates_visual_review_pending"
            or progress["schemaVersion"] != 13 or not progress["ok"]
            or hybrid["inputs"]["oldOutline"]["sha256"] != sha(old_path)
            or hybrid["inputs"]["samCandidateAudit"]["sha256"] != sha(sam_path)
            or progress["counts"]["sourceImages"] != 20
            or progress["counts"]["oldLabelNails"] != 104
            or progress["counts"]["sourceGroups"] != 8
            or progress["counts"]["newTrainingApprovedSources"] != 0):
        raise ValueError("visual audit upstream contract mismatch")
    for report in (old, sam, hybrid, progress):
        for item in report["inputs"].values():
            checked(item)
    sources = []
    for prior, candidate in zip(old["sources"], hybrid["sources"], strict=True):
        ordinal = prior["ordinal"]
        row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == ordinal)
        if (ordinal not in MARKS
                or candidate["sourceOrdinal"] != ordinal
                or not (candidate["sourceImage"] == prior["sourceImage"] == row["sourceImage"])
                or not (candidate["oldLabel"] == prior["sourceLabel"] == row["sourceLabel"])
                or not (candidate["sourceGroup"] == prior["sourceGroup"] == row["sourceGroup"])
                or candidate["isolatedImage"] != prior["isolatedImage"]
                or row["decision"] != "watermark_review_required"
                or row["everyNailVisualApproval"]
                or row["trainingUse"] != "prohibited"
                or candidate["counts"]["polygons"] != 5
                or candidate["counts"]["legalPolygons"] != 5
                or candidate["counts"]["overlapPairs"] != 0
                or candidate["counts"]["visualApproved"] != 0):
            raise ValueError(f"source {ordinal} frozen identity/quality mismatch")
        for key in ("sourceImage", "oldLabel", "isolatedImage", "samAnnotation",
                    "annotation", "fullOutline"):
            checked(candidate[key])
        for crop in candidate["crops"]:
            checked(crop["source"])
            checked(crop["outline"])
        if [crop["truthIndex"] for crop in candidate["crops"]] != [1, 2, 3, 4, 5]:
            raise ValueError(f"source {ordinal} crop denominator drift")
        with Image.open(candidate["isolatedImage"]["path"]) as opened:
            image = opened.convert("RGB")
        annotation = load(Path(candidate["annotation"]["path"]))
        if (annotation["image"]["fileName"] != candidate["sourceFileName"]
                or annotation["image"]["sourceGroup"] != candidate["sourceGroup"]
                or len(annotation["annotations"]) != 5
                or annotation["trainingUse"] != "prohibited"):
            raise ValueError(f"source {ordinal} annotation identity drift")
        shapes = [Polygon([(point["x"], point["y"]) for point in item["polygon"]])
                  for item in annotation["annotations"]]
        if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
            raise ValueError(f"source {ordinal} hybrid topology drift")
        if any(shapes[i].intersection(shapes[j]).area > 0
               for i in range(5) for j in range(i + 1, 5)):
            raise ValueError(f"source {ordinal} hybrid overlap drift")
        mark_config = MARKS[ordinal]
        inspection_crops = []
        for name, pixels in mark_config["inspectionCrops"]:
            x1, y1, x2, y2 = pixels
            if not (0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height):
                raise ValueError(f"source {ordinal} mark crop outside image")
            artifact = save_exact(image.crop(pixels), output_dir / f"source-{ordinal:03d}-{name}.png",
                                  verify)
            inspection_crops.append({"name": name, "boxPixels": list(pixels),
                                     "artifact": artifact})
        marks = []
        for name, pixels in mark_config["instances"]:
            region = box(*pixels)
            overlaps = sum(shape.intersection(region).area > 0 for shape in shapes)
            if overlaps:
                raise ValueError(f"source {ordinal} watermark overlaps candidate nail mask")
            marks.append({"type": name, "boxPixels": list(pixels),
                          "candidateMaskOverlapPairs": overlaps})
        sources.append({
            "sourceOrdinal": ordinal,
            "sourceFileName": candidate["sourceFileName"],
            "sourceGroup": candidate["sourceGroup"],
            "sourceImage": candidate["sourceImage"],
            "oldLabel": candidate["oldLabel"],
            "isolatedImage": candidate["isolatedImage"],
            "hybridAnnotation": candidate["annotation"],
            "hybridFullOutline": candidate["fullOutline"],
            "nailCrops": candidate["crops"],
            "markInspectionCrops": inspection_crops,
            "markInstances": marks,
            "visualPassNails": 5,
            "maskVisualApproval": True,
            "decision": "repaired_mask_visual_pass_pending_watermark_and_full_split",
            "watermarkAblationComplete": False,
            "watermarkShortcutAbsenceProven": False,
            "trainingUse": "prohibited",
        })
    return {"schemaVersion": 1, "ok": True,
            "decision": "source037039_ten_masks_visual_pass_watermark_and_split_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "oldOutline": bind(old_path),
                       "samCandidateAudit": bind(sam_path),
                       "hybridCandidates": bind(hybrid_path),
                       "priorProgressV13": bind(progress_path)},
            "sources": sources, "visualPassNails": 10,
            "newTrainingApprovedSources": 0,
            "historicalSnapshotChanged": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--sam-audit", type=Path)
    parser.add_argument("--hybrid", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for item in previous["inputs"].values():
            checked(item)
        for source in previous["sources"]:
            for key in ("sourceImage", "oldLabel", "isolatedImage", "hybridAnnotation",
                        "hybridFullOutline"):
                checked(source[key])
            for crop in source["nailCrops"]:
                checked(crop["source"])
                checked(crop["outline"])
            for crop in source["markInspectionCrops"]:
                checked(crop["artifact"])
        current = build(Path(previous["inputs"]["oldOutline"]["path"]),
                        Path(previous["inputs"]["samCandidateAudit"]["path"]),
                        Path(previous["inputs"]["hybridCandidates"]["path"]),
                        Path(previous["inputs"]["priorProgressV13"]["path"]),
                        Path(previous["sources"][0]["markInspectionCrops"][0]["artifact"]["path"]).parent,
                        verify=True)
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.old_outline, args.sam_audit, args.hybrid, args.progress,
                args.output_dir, args.report)):
        parser.error("all inputs/outputs required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.old_outline.resolve(), args.sam_audit.resolve(),
                   args.hybrid.resolve(), args.progress.resolve(),
                   args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
