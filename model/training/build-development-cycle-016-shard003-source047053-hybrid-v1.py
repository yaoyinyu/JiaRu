#!/usr/bin/env python3
"""Rebuild two five-nail historical-truth correction candidates from isolated copies."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


# Source 47 nail 4: the old right-edge zigzag and SAM left-side skin bulge were
# rejected on untinted original pixels. These points follow the visible nail.
MANUAL_47_N4 = [
    (584, 306), (575, 312), (569, 322), (566, 351), (571, 386),
    (579, 408), (580, 424), (585, 429), (590, 443), (600, 453),
    (613, 474), (621, 492), (643, 516), (665, 524), (681, 522),
    (694, 514), (700, 500), (700, 466), (690, 417), (689, 382),
    (681, 351), (669, 326), (652, 310), (640, 302), (628, 298),
    (610, 297),
]
MANUAL_QA = {
    "positive": [(590, 337), (623, 409), (670, 479)],
    "negative": [(551, 370), (712, 398), (640, 540)],
}
SOURCE_METHODS = {
    47: {1: "secondary_sam", 2: "retained_old", 3: "retained_old",
         4: "manual_original_resolution", 5: "first_sam"},
    53: {1: "retained_old", 2: "retained_old", 3: "secondary_sam",
         4: "retained_old", 5: "tight_retry_sam"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def old_polygons(path: Path, width: int, height: int) -> list[list[tuple[float, float]]]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = [float(value) for value in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2:
            raise ValueError("old polygon structure drift")
        result.append([(values[i] * width, values[i + 1] * height)
                       for i in range(1, len(values), 2)])
    return result


def annotation_polygons(binding: dict, expected_count: int,
                        file_name: str, source_group: str) -> list[list[tuple[float, float]]]:
    document = load(checked(binding))
    if (document["image"]["fileName"] != file_name or
            document["image"]["sourceGroup"] != source_group or
            document["trainingUse"] != "prohibited" or
            len(document["annotations"]) != expected_count):
        raise ValueError("SAM annotation identity/count drift")
    return [[(float(point["x"]), float(point["y"])) for point in nail["polygon"]]
            for nail in document["annotations"]]


def save_json_exact(document: dict, path: Path) -> dict:
    content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    if path.read_text(encoding="utf-8") != content:
        raise ValueError(f"candidate annotation drift: {path}")
    return bind(path)


def save_image_exact(image: Image.Image, path: Path) -> dict:
    if not path.exists():
        image.save(path, format="PNG")
    with Image.open(path) as previous:
        actual = previous.convert("RGB")
    if actual.size != image.size or actual.tobytes() != image.tobytes():
        raise ValueError(f"candidate visual artifact drift: {path}")
    return bind(path)


def build(native_path: Path, first_visual_path: Path, secondpass_path: Path,
          first_sam_path: Path, secondary_sam_path: Path, retry_sam_path: Path,
          output: Path) -> dict:
    native, first_visual, secondpass, first_sam, secondary_sam, retry_sam = map(
        load, (native_path, first_visual_path, secondpass_path,
               first_sam_path, secondary_sam_path, retry_sam_path))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            first_visual["decision"] != "one_pass_sam_visual_stoploss_three_rejected_one_pending" or
            secondpass["decision"] != "secondpass_original_resolution_visual_pending" or
            any(doc["decision"] != "sam_candidate_only_not_training_truth" for doc in
                (first_sam, secondary_sam, retry_sam))):
        raise ValueError("source review chain drift")
    if [(row["ordinal"], row["truthIndex"]) for row in secondpass["nails"]] != [
        (47, 1), (47, 4), (53, 3), (53, 5)
    ]:
        raise ValueError("second-pass target order drift")
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    sources = []
    for ordinal in SOURCE_METHODS:
        source = next(row for row in native["sources"] if row["ordinal"] == ordinal)
        for key in ("sourceImage", "sourceLabel", "isolatedImage"):
            checked(source[key])
        if sha(Path(source["sourceImage"]["path"])) != sha(Path(source["isolatedImage"]["path"])):
            raise ValueError("isolated image identity differs")
        with Image.open(checked(source["isolatedImage"])) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        old = old_polygons(Path(source["sourceLabel"]["path"]), width, height)
        if len(old) != 5 or [width, height] != source["imageSize"]:
            raise ValueError("old nail count/dimensions drift")
        first_output = next(row for row in first_sam["outputs"] if row["fileName"] == source["sourceFileName"])
        secondary_output = next(row for row in secondary_sam["outputs"] if row["fileName"] == source["sourceFileName"])
        sam_files = [bind(Path(first_output["annotationPath"])), bind(Path(secondary_output["annotationPath"]))]
        first = annotation_polygons(sam_files[0], 1, source["sourceFileName"], source["sourceGroup"])
        secondary = annotation_polygons(sam_files[1], 2 if ordinal == 47 else 1,
                                        source["sourceFileName"], source["sourceGroup"])
        if ordinal == 53:
            retry_output = retry_sam["outputs"][0]
            if retry_output["fileName"] != source["sourceFileName"]:
                raise ValueError("tight retry source identity drift")
            retry_binding = bind(Path(retry_output["annotationPath"]))
            retry = annotation_polygons(retry_binding, 1, source["sourceFileName"], source["sourceGroup"])
            sam_files.append(retry_binding)
        else:
            retry = []
        polygons: list[list[tuple[float, float]]] = []
        for index, method in SOURCE_METHODS[ordinal].items():
            if method == "retained_old":
                points = old[index - 1]
            elif method == "manual_original_resolution":
                points = [(float(x), float(y)) for x, y in MANUAL_47_N4]
            elif method == "first_sam":
                points = first[0]
            elif method == "secondary_sam":
                points = secondary[0 if ordinal == 47 and index == 1 else 1 if ordinal == 47 else 0]
            elif method == "tight_retry_sam":
                points = retry[0]
            else:
                raise ValueError("unknown candidate polygon method")
            polygons.append(points)
        shapes = [Polygon(points) for points in polygons]
        if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
            raise ValueError(f"source {ordinal} polygon invalid")
        overlaps = [(i + 1, j + 1) for i in range(5) for j in range(i + 1, 5)
                    if shapes[i].intersection(shapes[j]).area > 0]
        if overlaps:
            raise ValueError(f"source {ordinal} polygon intersection: {overlaps}")
        manual_qa = None
        if ordinal == 47:
            manual_shape = shapes[3]
            plus = sum(manual_shape.covers(Point(p)) for p in MANUAL_QA["positive"])
            minus = sum(manual_shape.covers(Point(p)) for p in MANUAL_QA["negative"])
            if plus != 3 or minus != 0:
                raise ValueError("manual original-pixel QA point mismatch")
            manual_qa = {"nailIndex": 4, "positiveHits": plus, "positiveCount": 3,
                         "negativeHits": minus, "negativeCount": 3,
                         "positivePoints": MANUAL_QA["positive"],
                         "negativePoints": MANUAL_QA["negative"]}
        annotation = {"version": "shard003-historical-correction-candidate/v1",
                      "decision": "candidate_only_pending_full_visual_and_role_gates",
                      "trainingUse": "prohibited",
                      "image": {"fileName": source["sourceFileName"],
                                "width": width, "height": height,
                                "sourceGroup": source["sourceGroup"],
                                "imageSha256": source["sourceImage"]["sha256"]},
                      "annotations": [{"id": f"n{index}", "label": "nail_texture",
                                       "polygon": [{"x": x, "y": y} for x, y in points],
                                       "method": SOURCE_METHODS[ordinal][index]}
                                      for index, points in enumerate(polygons, start=1)]}
        annotation_path = output / "annotations" / (Path(source["sourceFileName"]).stem + ".json")
        annotation_binding = save_json_exact(annotation, annotation_path)
        full = image.copy()
        pen = ImageDraw.Draw(full)
        nails = []
        for index, shape in enumerate(shapes, start=1):
            points = list(shape.exterior.coords)
            pen.line(points, fill=(255, 20, 20), width=2)
            pen.text(points[0], str(index), fill=(255, 255, 0))
            x1, y1, x2, y2 = shape.bounds
            box = [max(0, int(x1 - 32)), max(0, int(y1 - 32)),
                   min(width, int(x2 + 33)), min(height, int(y2 + 33))]
            raw = image.crop(tuple(box))
            outline = raw.copy()
            draw = ImageDraw.Draw(outline)
            draw.line([(x - box[0], y - box[1]) for x, y in points],
                      fill=(255, 20, 20), width=2)
            dimensions = (raw.width * 3, raw.height * 3)
            prefix = f"source-{ordinal:03d}-nail-{index:02d}"
            nails.append({"truthIndex": index, "method": SOURCE_METHODS[ordinal][index],
                          "cropBox": box, "polygonArea": round(shape.area, 3),
                          "raw3x": save_image_exact(raw.resize(dimensions, Image.Resampling.NEAREST),
                                                    output / "crops" / f"{prefix}-raw-3x.png"),
                          "outline3x": save_image_exact(outline.resize(dimensions, Image.Resampling.NEAREST),
                                                        output / "crops" / f"{prefix}-outline-3x.png"),
                          "visualDecision": "pending_original_resolution_review"})
        full_binding = save_image_exact(full, output / f"source-{ordinal:03d}-full-outline.png")
        sources.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                        "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                        "sourceLabel": source["sourceLabel"],
                        "isolatedImage": source["isolatedImage"],
                        "samAnnotations": sam_files,
                        "candidateAnnotation": annotation_binding,
                        "fullOutline": full_binding, "nails": nails,
                        "manualQA": manual_qa, "polygonValidCount": 5,
                        "overlapPairs": 0, "visualApprovals": 0,
                        "trainingUse": "prohibited"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source047053_hybrid_candidates_geometry_pass_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                       "firstVisual": bind(first_visual_path), "secondpassNative": bind(secondpass_path),
                       "firstSam": bind(first_sam_path), "secondarySam": bind(secondary_sam_path),
                       "tightRetrySam": bind(retry_sam_path)},
            "counts": {"sourceImages": 2, "nails": 10, "legalPolygons": 10,
                       "overlapPairs": 0, "visualApprovals": 0, "trainingApproved": 0},
            "sources": sources, "trainingUse": "prohibited"}


def verify(report_path: Path) -> dict:
    saved = load(report_path)
    for item in saved["inputs"].values():
        checked(item)
    for source in saved["sources"]:
        for key in ("sourceImage", "sourceLabel", "isolatedImage", "candidateAnnotation", "fullOutline"):
            checked(source[key])
        for item in source["samAnnotations"]:
            checked(item)
        for nail in source["nails"]:
            checked(nail["raw3x"])
            checked(nail["outline3x"])
    output = Path(saved["sources"][0]["candidateAnnotation"]["path"]).parent.parent
    current = build(*(Path(saved["inputs"][key]["path"]) for key in
                      ("nativeReview", "firstVisual", "secondpassNative", "firstSam", "secondarySam", "tightRetrySam")), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source047053_hybrid_candidates",
            "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--first-visual", type=Path)
    parser.add_argument("--secondpass-native", type=Path)
    parser.add_argument("--first-sam", type=Path)
    parser.add_argument("--secondary-sam", type=Path)
    parser.add_argument("--tight-retry-sam", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.native_review, args.first_visual, args.secondpass_native,
                    args.first_sam, args.secondary_sam, args.tight_retry_sam,
                    args.output_dir, args.report)):
            parser.error("all inputs and --output-dir/--report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.first_visual.resolve(),
                       args.secondpass_native.resolve(), args.first_sam.resolve(),
                       args.secondary_sam.resolve(), args.tight_retry_sam.resolve(),
                       args.output_dir.resolve())
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
