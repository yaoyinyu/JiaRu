#!/usr/bin/env python3
"""Correct source-49 candidate cuticle and distal edges after v1 visual review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


NAIL2 = [(585, 439), (602, 434), (617, 438), (632, 450), (648, 469),
         (662, 472), (676, 501), (690, 533), (704, 567), (718, 603),
         (732, 640), (744, 677), (752, 705), (757, 723), (752, 740),
         (740, 748), (726, 746), (707, 730), (687, 704), (669, 673),
         (648, 638), (628, 601), (609, 564), (590, 526), (574, 487),
         (562, 456), (566, 447)]
NAIL3_TIP = [(744, 855), (741, 866), (733, 874), (721, 875), (710, 869)]
NAIL4_TIP = [(502, 827), (505, 836), (500, 844), (490, 849)]
QA = {
    2: ([(590, 455), (660, 555), (730, 700)],
        [(585, 420), (625, 423), (555, 447)]),
    3: ([(500, 625), (570, 700), (720, 835)],
        [(465, 590), (550, 585), (755, 875)]),
    4: ([(270, 755), (380, 802), (495, 834)],
        [(240, 715), (350, 740), (520, 840)]),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"binding drift: {path}")
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
    if (v1["decision"] != "source049_five_nail_candidate_v1_geometry_pass_visual_pending"
            or v1["counts"] != {"sourceImages": 1, "nails": 5,
                                "legalPolygons": 5, "overlapPairs": 0,
                                "visualApprovals": 0, "trainingApproved": 0}):
        raise ValueError("first candidate state drift")
    for item in v1["inputs"].values():
        checked(item)
    source = v1["source"]
    if (source["ordinal"] != 49 or source["trainingUse"] != "prohibited"
            or source["historicalCanonicalTruthCount"] != 1
            or [n["method"] for n in source["nails"]] != [
                "retained_old", "retained_old", "manual_original_resolution",
                "manual_original_resolution", "manual_original_resolution"]):
        raise ValueError("source49 first candidate drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage", "candidateAnnotation"):
        checked(source[key])
    old_annotation = json.loads(checked(source["candidateAnnotation"]).read_text(encoding="utf-8"))
    annotation = json.loads(json.dumps(old_annotation))
    if (annotation["trainingUse"] != "prohibited"
            or annotation["image"]["imageSha256"] != source["sourceImage"]["sha256"]
            or len(annotation["annotations"]) != 5):
        raise ValueError("candidate annotation identity drift")
    with Image.open(checked(source["isolatedImage"])) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != [annotation["image"]["width"], annotation["image"]["height"]]:
        raise ValueError("source size drift")
    annotation["version"] = "shard003-source049-historical-correction-candidate/v2"
    annotation["annotations"][1]["polygon"] = [{"x": float(x), "y": float(y)}
                                              for x, y in NAIL2]
    annotation["annotations"][1]["method"] = "manual_original_resolution"
    nail3 = annotation["annotations"][2]["polygon"]
    nail3[12:17] = [{"x": float(x), "y": float(y)} for x, y in NAIL3_TIP]
    nail4 = annotation["annotations"][3]["polygon"]
    nail4[10:15] = [{"x": float(x), "y": float(y)} for x, y in NAIL4_TIP]
    if (annotation["annotations"][0] != old_annotation["annotations"][0]
            or annotation["annotations"][4] != old_annotation["annotations"][4]):
        raise ValueError("non-target nail changed")
    shapes = [Polygon([(point["x"], point["y"]) for point in nail["polygon"]])
              for nail in annotation["annotations"]]
    if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError("invalid polygon")
    overlaps = [(i + 1, j + 1) for i in range(5) for j in range(i + 1, 5)
                if shapes[i].intersection(shapes[j]).area > 0]
    if overlaps:
        raise ValueError(f"same-image nail overlap: {overlaps}")
    qa = []
    for index, (positive, negative) in QA.items():
        shape = shapes[index - 1]
        hits = sum(shape.covers(Point(p)) for p in positive)
        misses = sum(shape.covers(Point(p)) for p in negative)
        if hits != len(positive) or misses:
            raise ValueError(f"nail{index} QA disagreement: {hits}/{misses}")
        qa.append({"nailIndex": index, "positivePoints": [list(p) for p in positive],
                   "negativePoints": [list(p) for p in negative],
                   "positiveHits": hits, "negativeHits": misses})
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    annotation_binding = write_json_exact(
        annotation, output / "annotations" / f"{Path(source['sourceFileName']).stem}.json")
    full = image.copy()
    full_draw = ImageDraw.Draw(full)
    nails = []
    for index, shape in enumerate(shapes, 1):
        points = list(shape.exterior.coords)
        full_draw.line(points, fill=(255, 20, 20), width=2)
        full_draw.text(points[0], str(index), fill=(255, 255, 0))
        x1, y1, x2, y2 = shape.bounds
        box = [max(0, int(x1 - 40)), max(0, int(y1 - 40)),
               min(width, int(x2 + 41)), min(height, int(y2 + 41))]
        raw = image.crop(tuple(box))
        outline = raw.copy()
        ImageDraw.Draw(outline).line([(x - box[0], y - box[1]) for x, y in points],
                                     fill=(255, 20, 20), width=2)
        size = (raw.width * 3, raw.height * 3)
        prefix = f"source-049-nail-{index:02d}"
        nails.append({"truthIndex": index,
                      "method": annotation["annotations"][index - 1]["method"],
                      "polygonArea": round(shape.area, 3), "cropBox": box,
                      "raw3x": write_image_exact(raw.resize(size, Image.Resampling.NEAREST),
                                                output / "crops" / f"{prefix}-raw-3x.png"),
                      "outline3x": write_image_exact(outline.resize(size, Image.Resampling.NEAREST),
                                                    output / "crops" / f"{prefix}-outline-3x.png"),
                      "visualDecision": "pending_original_resolution_review"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source049_five_nail_candidate_v2_geometry_pass_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "rejectedCandidateV1": bind(v1_path),
                       "originalCandidateAnnotation": source["candidateAnnotation"]},
            "source": {"ordinal": 49, "sourceFileName": source["sourceFileName"],
                       "sourceGroup": source["sourceGroup"],
                       "sourceImage": source["sourceImage"],
                       "sourceLabel": source["sourceLabel"],
                       "isolatedImage": source["isolatedImage"],
                       "historicalCanonicalTruthCount": 1,
                       "candidateAnnotation": annotation_binding,
                       "fullOutline": write_image_exact(full, output / "source-049-full-outline.png"),
                       "nails": nails, "manualQA": qa,
                       "polygonValidCount": 5, "overlapPairs": 0,
                       "visualApprovals": 0, "trainingUse": "prohibited"},
            "counts": {"sourceImages": 1, "nails": 5, "legalPolygons": 5,
                       "overlapPairs": 0, "visualApprovals": 0, "trainingApproved": 0},
            "trainingUse": "prohibited"}


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
    current = build(Path(saved["inputs"]["rejectedCandidateV1"]["path"]), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source049_candidate_v2", "counts": saved["counts"]}


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
            parser.error("candidate-v1, output-dir and report required")
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
