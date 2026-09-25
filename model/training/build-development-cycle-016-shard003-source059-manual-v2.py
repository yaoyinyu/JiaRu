#!/usr/bin/env python3
"""Build source-59 correction candidate with manual n1 and n4 boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


# Original 1008x812 pixels. The old n1 polygon started at the gold foil near
# y224, omitting the visible nude nail bed and cuticle above it.
MANUAL_N1 = [
    (482, 185), (493, 184), (505, 188), (515, 195), (521, 204),
    (522, 216), (519, 230), (514, 244), (507, 261), (499, 279),
    (489, 298), (476, 316), (460, 331), (451, 337), (433, 335),
    (421, 326), (417, 310), (421, 289), (431, 263), (441, 241),
    (449, 222), (458, 205), (469, 193),
]
QA = {
    "positive": [(490, 204), (479, 228), (463, 269), (443, 316)],
    "negative": [(440, 183), (535, 208), (522, 282), (402, 308)],
}
MANUAL_N4 = [
    (743, 354), (757, 358), (769, 367), (772, 381), (766, 394),
    (752, 406), (735, 416), (713, 424), (690, 430), (670, 430),
    (649, 428), (628, 421), (611, 414), (599, 405), (597, 396),
    (601, 390), (611, 384), (627, 378), (643, 371), (662, 364),
    (684, 358), (705, 354), (724, 352),
]
QA_N4 = {
    "positive": [(610, 399), (650, 395), (729, 379)],
    "negative": [(625, 362), (660, 348), (600, 374), (650, 442)],
}
MANUAL_INDICES = {1, 4}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
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


def old_polygons(path: Path, width: int, height: int) -> list[list[tuple[float, float]]]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = [float(value) for value in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2 or len(values) < 7:
            raise ValueError("old polygon structure drift")
        result.append([(values[i] * width, values[i + 1] * height)
                       for i in range(1, len(values), 2)])
    return result


def build(native_path: Path, progress_path: Path, first_visual_path: Path,
          output: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    visual = json.loads(first_visual_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            progress["decision"] != "shard003_progress_reconciled_training_still_prohibited" or
            visual["decision"] != "one_pass_sam_visual_stoploss_three_rejected_one_pending"):
        raise ValueError("upstream decision drift")
    row = next(item for item in progress["sources"] if item["ordinal"] == 59)
    if row["currentDecision"] != "mask_rework":
        raise ValueError("source 59 no longer in rework queue")
    source = next(item for item in native["sources"] if item["ordinal"] == 59)
    if (source["historicalCanonicalTruths"] != [] or
            source["sourceImage"]["sha256"] != row["sourceImage"]["sha256"] or
            source["sourceGroup"] != row["sourceGroup"] or
            source["imageSize"] != [1008, 812]):
        raise ValueError("source 59 identity/canonical drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    if source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"]:
        raise ValueError("isolated source not byte identical")
    canonical_path = checked(native["inputs"]["canonicalIndex"])
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    same_name = [item for item in canonical["canonicalTruths"]
                 if item["fileName"] == source["sourceFileName"]]
    if same_name:
        raise ValueError("source 59 has a canonical truth identity")
    with Image.open(checked(source["isolatedImage"])) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != source["imageSize"]:
        raise ValueError("image dimensions drift")
    old = old_polygons(checked(source["sourceLabel"]), width, height)
    if len(old) != 5:
        raise ValueError("old nail count drift")
    polygons = [[(float(x), float(y)) for x, y in MANUAL_N1],
                old[1], old[2],
                [(float(x), float(y)) for x, y in MANUAL_N4], old[4]]
    shapes = [Polygon(points) for points in polygons]
    if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError("invalid nail polygon")
    overlaps = [(i + 1, j + 1) for i in range(5) for j in range(i + 1, 5)
                if shapes[i].intersection(shapes[j]).area > 0]
    if overlaps:
        raise ValueError(f"nail polygon overlap: {overlaps}")
    plus = sum(shapes[0].covers(Point(p)) for p in QA["positive"])
    minus = sum(shapes[0].covers(Point(p)) for p in QA["negative"])
    if plus != len(QA["positive"]) or minus != 0:
        raise ValueError("manual QA points disagree with polygon")
    plus_n4 = sum(shapes[3].covers(Point(p)) for p in QA_N4["positive"])
    minus_n4 = sum(shapes[3].covers(Point(p)) for p in QA_N4["negative"])
    if plus_n4 != len(QA_N4["positive"]) or minus_n4 != 0:
        raise ValueError("nail 4 manual QA points disagree with polygon")
    output.mkdir(parents=True, exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    annotation = {
        "version": "shard003-source059-historical-correction-candidate/v2",
        "decision": "candidate_only_pending_full_original_pixel_visual_and_role_gates",
        "trainingUse": "prohibited",
        "image": {"fileName": source["sourceFileName"], "width": width, "height": height,
                  "sourceGroup": source["sourceGroup"],
                  "imageSha256": source["sourceImage"]["sha256"]},
        "annotations": [
            {"id": f"n{index}", "label": "nail_texture",
             "polygon": [{"x": x, "y": y} for x, y in points],
             "method": "manual_original_resolution" if index in MANUAL_INDICES else "retained_old"}
            for index, points in enumerate(polygons, 1)
        ],
    }
    annotation_path = output / "annotations" / f"{Path(source['sourceFileName']).stem}.json"
    annotation_binding = write_json_exact(annotation, annotation_path)
    full = image.copy()
    draw = ImageDraw.Draw(full)
    nails = []
    for index, shape in enumerate(shapes, 1):
        points = list(shape.exterior.coords)
        draw.line(points, fill=(255, 20, 20), width=2)
        draw.text(points[0], str(index), fill=(255, 255, 0))
        x1, y1, x2, y2 = shape.bounds
        box = [max(0, int(x1 - 40)), max(0, int(y1 - 40)),
               min(width, int(x2 + 41)), min(height, int(y2 + 41))]
        raw = image.crop(tuple(box))
        outline = raw.copy()
        ImageDraw.Draw(outline).line([(x - box[0], y - box[1]) for x, y in points],
                                     fill=(255, 20, 20), width=2)
        size = (raw.width * 3, raw.height * 3)
        prefix = f"source-059-nail-{index:02d}"
        nails.append({
            "truthIndex": index,
            "method": "manual_original_resolution" if index in MANUAL_INDICES else "retained_old",
            "polygonArea": round(shape.area, 3), "cropBox": box,
            "raw3x": write_image_exact(raw.resize(size, Image.Resampling.NEAREST),
                                      output / "crops" / f"{prefix}-raw-3x.png"),
            "outline3x": write_image_exact(outline.resize(size, Image.Resampling.NEAREST),
                                          output / "crops" / f"{prefix}-outline-3x.png"),
            "visualDecision": "pending_original_resolution_review",
        })
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source059_five_nail_candidate_geometry_pass_visual_pending",
        "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                   "priorProgress": bind(progress_path), "firstSamVisual": bind(first_visual_path),
                   "canonicalIndex": bind(canonical_path)},
        "source": {"ordinal": 59, "sourceFileName": source["sourceFileName"],
                   "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                   "sourceLabel": source["sourceLabel"], "isolatedImage": source["isolatedImage"],
                   "historicalCanonicalTruthCount": 0,
                   "candidateAnnotation": annotation_binding,
                   "fullOutline": write_image_exact(full, output / "source-059-full-outline.png"),
                   "nails": nails, "manualQA": [
                       {"nailIndex": 1,
                        "positivePoints": [list(p) for p in QA["positive"]],
                        "negativePoints": [list(p) for p in QA["negative"]],
                        "positiveHits": plus, "negativeHits": minus},
                       {"nailIndex": 4,
                        "positivePoints": [list(p) for p in QA_N4["positive"]],
                        "negativePoints": [list(p) for p in QA_N4["negative"]],
                        "positiveHits": plus_n4, "negativeHits": minus_n4},
                   ],
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
    for key in ("sourceImage", "sourceLabel", "isolatedImage", "candidateAnnotation", "fullOutline"):
        checked(source[key])
    for nail in source["nails"]:
        checked(nail["raw3x"])
        checked(nail["outline3x"])
    output = Path(source["candidateAnnotation"]["path"]).parent.parent
    current = build(*(Path(saved["inputs"][key]["path"]) for key in
                      ("nativeReview", "priorProgress", "firstSamVisual")), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source059_geometry_candidate",
            "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--first-sam-visual", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.native_review, args.prior_progress, args.first_sam_visual,
                    args.output_dir, args.report)):
            parser.error("all inputs and output arguments required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.prior_progress.resolve(),
                       args.first_sam_visual.resolve(), args.output_dir.resolve())
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
