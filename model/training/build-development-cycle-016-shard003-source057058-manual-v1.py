#!/usr/bin/env python3
"""Rebuild two local nail boundaries on isolated shard-003 source images."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


# Original-image pixels selected against the untinted full images and 3x crops.
# All other old polygons remain candidates and require independent visual review.
REPAIRS = {
    57: {
        "nailIndex": 5,
        "points": [
            (640, 909), (642, 884), (648, 866), (659, 844), (674, 820),
            (691, 797), (709, 778), (728, 763), (746, 754), (764, 752),
            (782, 758), (797, 768), (807, 781), (813, 795), (813, 811),
            (809, 827), (801, 844), (790, 860), (776, 877), (760, 891),
            (744, 904), (728, 913), (711, 918), (694, 918), (680, 920),
            (665, 920), (650, 917),
        ],
        "positive": [(757, 800), (700, 871), (657, 911)],
        "negative": [(632, 906), (652, 927), (821, 807)],
    },
    58: {
        "nailIndex": 4,
        "points": [
            (875, 1116), (854, 1098), (840, 1093), (820, 1093),
            (800, 1096), (784, 1099), (768, 1106), (752, 1117),
            (731, 1129), (717, 1146), (706, 1152), (703, 1163),
            (651, 1200), (626, 1225), (621, 1245), (637, 1282),
            (649, 1293), (662, 1295), (746, 1270), (775, 1257),
            (845, 1211), (871, 1187), (881, 1166), (882, 1137),
        ],
        "positive": [(790, 1120), (705, 1200), (680, 1260)],
        "negative": [(774, 1088), (748, 1104), (902, 1150)],
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


def build(native_path: Path, progress_path: Path, output: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual"
            or native["counts"] != {"sourceImages": 2, "oldLabelNails": 10,
                                    "visualApprovals": 0}
            or progress["decision"] != "shard003_progress_v6_reconciled_training_still_prohibited"
            or [s["ordinal"] for s in native["sources"]] != [57, 58]):
        raise ValueError("upstream roster or decision drift")
    for document in (native, progress):
        for item in document["inputs"].values():
            checked(item)
    canonical_path = checked(native["inputs"]["canonicalIndex"])
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    sources = []
    for source in native["sources"]:
        ordinal = source["ordinal"]
        repair = REPAIRS[ordinal]
        prior = next(row for row in progress["sources"] if row["ordinal"] == ordinal)
        same_name = [item for item in canonical["canonicalTruths"]
                     if item["fileName"] == source["sourceFileName"]]
        if (prior["currentDecision"] != "mask_rework"
                or prior["trainingUse"] != "prohibited"
                or source["sourceImage"] != prior["sourceImage"]
                or source["sourceGroup"] != prior["sourceGroup"]
                or len(same_name) != 1
                or len(source["historicalCanonicalTruths"]) != 1):
            raise ValueError(f"source {ordinal} identity or prior role drift")
        for key in ("sourceImage", "sourceLabel", "isolatedImage"):
            checked(source[key])
        if source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"]:
            raise ValueError("isolated source not byte identical")
        with Image.open(checked(source["isolatedImage"])) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        if [width, height] != source["imageSize"]:
            raise ValueError("image dimensions drift")
        polygons = old_polygons(checked(source["sourceLabel"]), width, height)
        if len(polygons) != 5:
            raise ValueError("old nail count drift")
        index = repair["nailIndex"] - 1
        polygons[index] = [(float(x), float(y)) for x, y in repair["points"]]
        shapes = [Polygon(points) for points in polygons]
        if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
            raise ValueError("invalid nail polygon")
        overlaps = [(i + 1, j + 1) for i in range(5) for j in range(i + 1, 5)
                    if shapes[i].intersection(shapes[j]).area > 0]
        if overlaps:
            raise ValueError(f"same-image nail overlap: {overlaps}")
        shape = shapes[index]
        positive_hits = sum(shape.covers(Point(p)) for p in repair["positive"])
        negative_hits = sum(shape.covers(Point(p)) for p in repair["negative"])
        if positive_hits != len(repair["positive"]) or negative_hits != 0:
            raise ValueError(f"source {ordinal} manual QA points disagree with polygon")
        annotation = {
            "version": f"shard003-source{ordinal:03d}-historical-correction-candidate/v1",
            "decision": "candidate_only_pending_full_original_pixel_visual_and_role_gates",
            "trainingUse": "prohibited",
            "image": {"fileName": source["sourceFileName"], "width": width,
                      "height": height, "sourceGroup": source["sourceGroup"],
                      "imageSha256": source["sourceImage"]["sha256"]},
            "annotations": [
                {"id": f"n{n}", "label": "nail_texture",
                 "polygon": [{"x": x, "y": y} for x, y in points],
                 "method": "manual_original_resolution" if n - 1 == index else "retained_old"}
                for n, points in enumerate(polygons, 1)
            ],
        }
        annotation_binding = write_json_exact(
            annotation, output / "annotations" / f"{Path(source['sourceFileName']).stem}.json")
        full = image.copy()
        full_draw = ImageDraw.Draw(full)
        nails = []
        for n, nail_shape in enumerate(shapes, 1):
            points = list(nail_shape.exterior.coords)
            full_draw.line(points, fill=(255, 20, 20), width=2)
            full_draw.text(points[0], str(n), fill=(255, 255, 0))
            x1, y1, x2, y2 = nail_shape.bounds
            box = [max(0, int(x1 - 40)), max(0, int(y1 - 40)),
                   min(width, int(x2 + 41)), min(height, int(y2 + 41))]
            raw = image.crop(tuple(box))
            outline = raw.copy()
            ImageDraw.Draw(outline).line([(x - box[0], y - box[1]) for x, y in points],
                                         fill=(255, 20, 20), width=2)
            size = (raw.width * 3, raw.height * 3)
            prefix = f"source-{ordinal:03d}-nail-{n:02d}"
            nails.append({
                "truthIndex": n,
                "method": "manual_original_resolution" if n - 1 == index else "retained_old",
                "polygonArea": round(nail_shape.area, 3), "cropBox": box,
                "raw3x": write_image_exact(raw.resize(size, Image.Resampling.NEAREST),
                                          output / "crops" / f"{prefix}-raw-3x.png"),
                "outline3x": write_image_exact(outline.resize(size, Image.Resampling.NEAREST),
                                              output / "crops" / f"{prefix}-outline-3x.png"),
                "visualDecision": "pending_original_resolution_review",
            })
        sources.append({
            "ordinal": ordinal, "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"], "isolatedImage": source["isolatedImage"],
            "historicalCanonicalTruthCount": 1,
            "candidateAnnotation": annotation_binding,
            "fullOutline": write_image_exact(full, output / f"source-{ordinal:03d}-full-outline.png"),
            "nails": nails,
            "manualQA": {"nailIndex": index + 1,
                         "positivePoints": [list(p) for p in repair["positive"]],
                         "negativePoints": [list(p) for p in repair["negative"]],
                         "positiveHits": positive_hits, "negativeHits": negative_hits},
            "polygonValidCount": 5, "overlapPairs": 0,
            "visualApprovals": 0, "trainingUse": "prohibited",
        })
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source057058_five_nail_candidates_geometry_pass_visual_pending",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "nativeReview": bind(native_path), "priorProgress": bind(progress_path),
                   "canonicalIndex": bind(canonical_path)},
        "sources": sources,
        "counts": {"sourceImages": 2, "nails": 10, "legalPolygons": 10,
                   "overlapPairs": 0, "visualApprovals": 0, "trainingApproved": 0},
        "trainingUse": "prohibited",
    }


def verify(path: Path) -> dict:
    saved = json.loads(path.read_text(encoding="utf-8"))
    for item in saved["inputs"].values():
        checked(item)
    for source in saved["sources"]:
        for key in ("sourceImage", "sourceLabel", "isolatedImage",
                    "candidateAnnotation", "fullOutline"):
            checked(source[key])
        for nail in source["nails"]:
            checked(nail["raw3x"])
            checked(nail["outline3x"])
    output = Path(saved["sources"][0]["candidateAnnotation"]["path"]).parent.parent
    current = build(Path(saved["inputs"]["nativeReview"]["path"]),
                    Path(saved["inputs"]["priorProgress"]["path"]), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source057058_geometry_candidates",
            "counts": saved["counts"]}


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
