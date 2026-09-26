#!/usr/bin/env python3
"""Smooth source-58 nail-2 cuticle contour on the isolated original pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


NAIL2 = [
    (424, 333), (402, 328), (379, 329), (361, 338), (349, 351),
    (337, 362), (327, 374), (316, 388), (304, 400), (266, 468),
    (241, 531), (238, 564), (250, 581), (295, 611), (308, 614),
    (322, 612), (348, 592), (415, 514), (447, 458), (459, 401),
    (458, 368), (448, 351),
]
POSITIVE = [(385, 349), (344, 391), (283, 537)]
NEGATIVE = [(320, 350), (305, 382), (466, 380)]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def write_json_exact(document: dict, path: Path) -> dict:
    content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    if path.read_text(encoding="utf-8") != content:
        raise ValueError(f"candidate JSON drift: {path}")
    return bind(path)


def write_image_exact(image: Image.Image, path: Path) -> dict:
    if not path.exists():
        image.save(path, format="PNG")
    with Image.open(path) as opened:
        actual = opened.convert("RGB")
    if actual.size != image.size or actual.tobytes() != image.tobytes():
        raise ValueError(f"candidate pixel drift: {path}")
    return bind(path)


def build(v1_path: Path, output: Path) -> dict:
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    if (v1["decision"] != "source057058_five_nail_candidates_geometry_pass_visual_pending"
            or v1["counts"] != {"sourceImages": 2, "nails": 10,
                                "legalPolygons": 10, "overlapPairs": 0,
                                "visualApprovals": 0, "trainingApproved": 0}
            or [row["ordinal"] for row in v1["sources"]] != [57, 58]):
        raise ValueError("first candidate roster or decision drift")
    for item in v1["inputs"].values():
        checked(item)
    for row in v1["sources"]:
        checked(row["candidateAnnotation"])
    source = v1["sources"][1]
    if (source["trainingUse"] != "prohibited"
            or source["historicalCanonicalTruthCount"] != 1
            or [nail["method"] for nail in source["nails"]] != [
                "retained_old", "retained_old", "retained_old",
                "manual_original_resolution", "retained_old"]):
        raise ValueError("source 58 first candidate drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    annotation = json.loads(checked(source["candidateAnnotation"]).read_text(encoding="utf-8"))
    if (annotation["trainingUse"] != "prohibited"
            or annotation["image"]["sourceGroup"] != source["sourceGroup"]
            or annotation["image"]["imageSha256"] != source["sourceImage"]["sha256"]
            or len(annotation["annotations"]) != 5):
        raise ValueError("candidate annotation identity drift")
    with Image.open(checked(source["isolatedImage"])) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != [annotation["image"]["width"], annotation["image"]["height"]]:
        raise ValueError("original image dimensions drift")
    old_nail4 = annotation["annotations"][3]["polygon"]
    annotation["version"] = "shard003-source058-historical-correction-candidate/v2"
    annotation["annotations"][1]["polygon"] = [
        {"x": float(x), "y": float(y)} for x, y in NAIL2]
    annotation["annotations"][1]["method"] = "manual_original_resolution"
    if annotation["annotations"][3]["polygon"] != old_nail4:
        raise ValueError("nail 4 first repair changed")
    shapes = [Polygon([(point["x"], point["y"]) for point in nail["polygon"]])
              for nail in annotation["annotations"]]
    if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError("invalid polygon")
    overlaps = [(i + 1, j + 1) for i in range(5) for j in range(i + 1, 5)
                if shapes[i].intersection(shapes[j]).area > 0]
    if overlaps:
        raise ValueError(f"same-image nail overlap: {overlaps}")
    shape2 = shapes[1]
    positive_hits = sum(shape2.covers(Point(p)) for p in POSITIVE)
    negative_hits = sum(shape2.covers(Point(p)) for p in NEGATIVE)
    if positive_hits != len(POSITIVE) or negative_hits != 0:
        raise ValueError("nail-2 QA points disagree with polygon")
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    annotation_binding = write_json_exact(
        annotation, output / "annotations" / f"{Path(source['sourceFileName']).stem}.json")
    full = image.copy()
    full_draw = ImageDraw.Draw(full)
    nails = []
    for index, nail_shape in enumerate(shapes, 1):
        points = list(nail_shape.exterior.coords)
        full_draw.line(points, fill=(255, 20, 20), width=2)
        full_draw.text(points[0], str(index), fill=(255, 255, 0))
        x1, y1, x2, y2 = nail_shape.bounds
        box = [max(0, int(x1 - 40)), max(0, int(y1 - 40)),
               min(width, int(x2 + 41)), min(height, int(y2 + 41))]
        raw = image.crop(tuple(box))
        outline = raw.copy()
        ImageDraw.Draw(outline).line([(x - box[0], y - box[1]) for x, y in points],
                                     fill=(255, 20, 20), width=2)
        size = (raw.width * 3, raw.height * 3)
        prefix = f"source-058-nail-{index:02d}"
        nails.append({
            "truthIndex": index,
            "method": annotation["annotations"][index - 1]["method"],
            "polygonArea": round(nail_shape.area, 3), "cropBox": box,
            "raw3x": write_image_exact(raw.resize(size, Image.Resampling.NEAREST),
                                      output / "crops" / f"{prefix}-raw-3x.png"),
            "outline3x": write_image_exact(outline.resize(size, Image.Resampling.NEAREST),
                                          output / "crops" / f"{prefix}-outline-3x.png"),
            "visualDecision": "pending_original_resolution_review",
        })
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source058_five_nail_candidate_v2_geometry_pass_visual_pending",
        "inputs": {"sourceScript": bind(Path(__file__)), "candidateV1": bind(v1_path),
                   "originalCandidateAnnotation": source["candidateAnnotation"]},
        "source": {"ordinal": 58, "sourceFileName": source["sourceFileName"],
                   "sourceGroup": source["sourceGroup"],
                   "sourceImage": source["sourceImage"],
                   "sourceLabel": source["sourceLabel"],
                   "isolatedImage": source["isolatedImage"],
                   "historicalCanonicalTruthCount": 1,
                   "candidateAnnotation": annotation_binding,
                   "fullOutline": write_image_exact(full, output / "source-058-full-outline.png"),
                   "nails": nails,
                   "manualQA": {"nailIndex": 2,
                                "positivePoints": [list(p) for p in POSITIVE],
                                "negativePoints": [list(p) for p in NEGATIVE],
                                "positiveHits": positive_hits,
                                "negativeHits": negative_hits},
                   "polygonValidCount": 5, "overlapPairs": 0,
                   "visualApprovals": 0, "trainingUse": "prohibited"},
        "counts": {"sourceImages": 1, "nails": 5, "legalPolygons": 5,
                   "overlapPairs": 0, "visualApprovals": 0, "trainingApproved": 0},
        "trainingUse": "prohibited",
    }


def verify(path: Path) -> dict:
    saved = json.loads(path.read_text(encoding="utf-8"))
    for item in saved["inputs"].values():
        checked(item)
    source = saved["source"]
    for key in ("sourceImage", "sourceLabel", "isolatedImage",
                "candidateAnnotation", "fullOutline"):
        checked(source[key])
    for nail in source["nails"]:
        checked(nail["raw3x"])
        checked(nail["outline3x"])
    output = Path(source["candidateAnnotation"]["path"]).parent.parent
    current = build(Path(saved["inputs"]["candidateV1"]["path"]), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source058_candidate_v2",
            "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-v1", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.candidate_v1, args.output_dir, args.report)):
            parser.error("--candidate-v1, --output-dir and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.candidate_v1.resolve(), args.output_dir.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
