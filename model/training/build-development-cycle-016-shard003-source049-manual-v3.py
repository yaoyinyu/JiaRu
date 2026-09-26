#!/usr/bin/env python3
"""Smooth the remaining source-49 v2 cuticle and tip kinks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


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


def helpers():
    path = Path(__file__).with_name("build-development-cycle-016-shard003-source049-manual-v2.py")
    spec = importlib.util.spec_from_file_location("source049_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(v2_path: Path, output: Path) -> dict:
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    if (v2["decision"] != "source049_five_nail_candidate_v2_geometry_pass_visual_pending"
            or v2["counts"] != {"sourceImages": 1, "nails": 5,
                                "legalPolygons": 5, "overlapPairs": 0,
                                "visualApprovals": 0, "trainingApproved": 0}
            or not helpers().verify(v2_path)["ok"]):
        raise ValueError("second candidate drift")
    for item in v2["inputs"].values():
        checked(item)
    source = v2["source"]
    for key in ("sourceImage", "sourceLabel", "isolatedImage", "candidateAnnotation"):
        checked(source[key])
    old_annotation = json.loads(checked(source["candidateAnnotation"]).read_text(encoding="utf-8"))
    annotation = json.loads(json.dumps(old_annotation))
    if (source["ordinal"] != 49 or source["trainingUse"] != "prohibited"
            or source["historicalCanonicalTruthCount"] != 1
            or annotation["trainingUse"] != "prohibited"
            or annotation["image"]["imageSha256"] != source["sourceImage"]["sha256"]):
        raise ValueError("source identity or role drift")
    with Image.open(checked(source["isolatedImage"])) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != [annotation["image"]["width"], annotation["image"]["height"]]:
        raise ValueError("source size drift")
    annotation["version"] = "shard003-source049-historical-correction-candidate/v3"
    nail2 = annotation["annotations"][1]["polygon"]
    nail2[4:7] = [{"x": float(x), "y": float(y)} for x, y in
                  [(646, 468), (661, 486), (676, 505)]]
    nail3 = annotation["annotations"][2]["polygon"]
    nail3[11:19] = [{"x": float(x), "y": float(y)} for x, y in
                    [(748, 844), (748, 856), (744, 867), (735, 875),
                     (722, 877), (710, 872), (694, 863), (675, 852)]]
    for index in (0, 3, 4):
        if annotation["annotations"][index] != old_annotation["annotations"][index]:
            raise ValueError(f"non-target nail changed: {index + 1}")
    shapes = [Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
              for nail in annotation["annotations"]]
    if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError("invalid polygon")
    if any(shapes[i].intersection(shapes[j]).area > 0
           for i in range(5) for j in range(i + 1, 5)):
        raise ValueError("same-image nail overlap")
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "crops").mkdir(exist_ok=True)
    write_json_exact = helpers().write_json_exact
    write_image_exact = helpers().write_image_exact
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
            "decision": "source049_five_nail_candidate_v3_geometry_pass_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "rejectedCandidateV2": bind(v2_path),
                       "previousCandidateAnnotation": source["candidateAnnotation"]},
            "source": {"ordinal": 49, "sourceFileName": source["sourceFileName"],
                       "sourceGroup": source["sourceGroup"],
                       "sourceImage": source["sourceImage"],
                       "sourceLabel": source["sourceLabel"],
                       "isolatedImage": source["isolatedImage"],
                       "historicalCanonicalTruthCount": 1,
                       "candidateAnnotation": annotation_binding,
                       "fullOutline": write_image_exact(full, output / "source-049-full-outline.png"),
                       "nails": nails, "polygonValidCount": 5, "overlapPairs": 0,
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
    current = build(Path(saved["inputs"]["rejectedCandidateV2"]["path"]), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_source049_candidate_v3", "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-v2", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.candidate_v2, args.output_dir, args.report)):
            parser.error("candidate-v2, output-dir and report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.candidate_v2.resolve(), args.output_dir.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
