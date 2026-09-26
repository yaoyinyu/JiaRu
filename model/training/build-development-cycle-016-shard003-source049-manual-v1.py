#!/usr/bin/env python3
"""Build replayable source-49 nail candidates on an isolated original image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


REPAIRS = {
    3: {
        "points": [(485, 594), (505, 591), (525, 598), (545, 608), (568, 620),
                   (590, 631), (618, 660), (645, 691), (671, 723), (698, 756),
                   (722, 791), (742, 825), (751, 850), (745, 861), (745, 873),
                   (738, 880), (726, 882), (711, 876), (693, 865), (668, 851),
                   (648, 828), (625, 801), (601, 775), (578, 749), (554, 724),
                   (531, 698), (510, 672), (492, 647), (479, 625), (476, 607)],
        "positive": [(500, 625), (570, 700), (720, 835)],
        "negative": [(465, 590), (550, 585), (765, 850)],
    },
    4: {
        "points": [(248, 746), (266, 739), (288, 742), (314, 751), (345, 765),
                   (376, 780), (407, 795), (437, 807), (465, 815), (490, 820),
                   (507, 826), (516, 835), (512, 847), (500, 854), (486, 854),
                   (464, 848), (438, 842), (409, 833), (380, 824), (351, 811),
                   (323, 797), (296, 784), (271, 771), (252, 757), (243, 750)],
        "positive": [(270, 755), (380, 802), (500, 834)],
        "negative": [(240, 715), (350, 740), (530, 825)],
    },
    5: {
        "points": [(495, 776), (508, 768), (524, 769), (543, 779), (567, 796),
                   (592, 815), (620, 838), (647, 862), (675, 889), (705, 917),
                   (734, 947), (754, 974), (763, 991), (760, 1004), (749, 1011),
                   (735, 1008), (715, 997), (693, 980), (668, 959), (640, 934),
                   (612, 908), (585, 883), (558, 856), (533, 832), (510, 808),
                   (491, 786)],
        "positive": [(520, 790), (620, 870), (740, 990)],
        "negative": [(480, 735), (550, 765), (770, 970)],
    },
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


def old_polygons(path: Path, width: int, height: int) -> list[list[tuple[float, float]]]:
    polygons = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = [float(value) for value in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2 or len(values) < 7:
            raise ValueError("old polygon structure drift")
        polygons.append([(values[i] * width, values[i + 1] * height)
                         for i in range(1, len(values), 2)])
    return polygons


def build(native_path: Path, progress_path: Path, output: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual"
            or native["counts"] != {"sourceImages": 3, "oldLabelNails": 14,
                                    "visualApprovals": 0}
            or progress["decision"] != "shard003_progress_v8_reconciled_training_still_prohibited"):
        raise ValueError("upstream decision drift")
    for document in (native, progress):
        for item in document["inputs"].values():
            checked(item)
    source = next(row for row in native["sources"] if row["ordinal"] == 49)
    previous = next(row for row in progress["sources"] if row["ordinal"] == 49)
    if (previous["currentDecision"] != "mask_rework"
            or previous["trainingUse"] != "prohibited"
            or source["sourceImage"] != previous["sourceImage"]
            or source["sourceGroup"] != previous["sourceGroup"]
            or len(source["historicalCanonicalTruths"]) != 1):
        raise ValueError("source identity, canonical count or prior role drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    if source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"]:
        raise ValueError("isolated source not byte identical")
    with Image.open(checked(source["isolatedImage"])) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != source["imageSize"]:
        raise ValueError("source size drift")
    polygons = old_polygons(checked(source["sourceLabel"]), width, height)
    if len(polygons) != 5:
        raise ValueError("old nail count drift")
    for index, item in REPAIRS.items():
        polygons[index - 1] = [(float(x), float(y)) for x, y in item["points"]]
    shapes = [Polygon(points) for points in polygons]
    if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError("invalid nail polygon")
    overlaps = [(i + 1, j + 1) for i in range(5) for j in range(i + 1, 5)
                if shapes[i].intersection(shapes[j]).area > 0]
    if overlaps:
        raise ValueError(f"same-image nail overlap: {overlaps}")
    qa = []
    for index, item in REPAIRS.items():
        shape = shapes[index - 1]
        hits = sum(shape.covers(Point(point)) for point in item["positive"])
        misses = sum(shape.covers(Point(point)) for point in item["negative"])
        if hits != len(item["positive"]) or misses:
            raise ValueError(f"source49 nail{index} QA disagree: {hits}/{misses}")
        qa.append({"nailIndex": index, "positivePoints": [list(p) for p in item["positive"]],
                   "negativePoints": [list(p) for p in item["negative"]],
                   "positiveHits": hits, "negativeHits": misses})
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    annotation = {
        "version": "shard003-source049-historical-correction-candidate/v1",
        "decision": "candidate_only_pending_full_original_pixel_visual_and_role_gates",
        "trainingUse": "prohibited",
        "image": {"fileName": source["sourceFileName"], "width": width, "height": height,
                  "sourceGroup": source["sourceGroup"],
                  "imageSha256": source["sourceImage"]["sha256"]},
        "annotations": [
            {"id": f"n{index}", "label": "nail_texture",
             "polygon": [{"x": x, "y": y} for x, y in points],
             "method": "manual_original_resolution" if index in REPAIRS else "retained_old"}
            for index, points in enumerate(polygons, 1)],
    }
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
        nails.append({
            "truthIndex": index,
            "method": annotation["annotations"][index - 1]["method"],
            "polygonArea": round(shape.area, 3), "cropBox": box,
            "raw3x": write_image_exact(raw.resize(size, Image.Resampling.NEAREST),
                                      output / "crops" / f"{prefix}-raw-3x.png"),
            "outline3x": write_image_exact(outline.resize(size, Image.Resampling.NEAREST),
                                          output / "crops" / f"{prefix}-outline-3x.png"),
            "visualDecision": "pending_original_resolution_review",
        })
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source049_five_nail_candidate_v1_geometry_pass_visual_pending",
        "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                   "priorProgress": bind(progress_path)},
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
    current = build(Path(saved["inputs"]["nativeReview"]["path"]),
                    Path(saved["inputs"]["priorProgress"]["path"]), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source049_candidate_v1", "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.native_review, args.prior_progress, args.output_dir, args.report)):
            parser.error("all input and output arguments required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.prior_progress.resolve(),
                       args.output_dir.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
