#!/usr/bin/env python3
"""Make a versioned local spur repair without altering frozen old labels."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def png_bytes(image: Image.Image) -> bytes:
    data = io.BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def stable_file(path: Path, data: bytes, verify: bool) -> dict:
    if path.exists() or verify:
        if not path.is_file() or sha(path) != hashlib.sha256(data).hexdigest():
            raise ValueError(f"output drift: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return bind(path)


def build(shard_path: Path, progress_path: Path, focus_path: Path,
          spec_path: Path, output_dir: Path, *, verify: bool) -> dict:
    shard, progress, focus, spec = [json.loads(path.read_text(encoding="utf-8"))
                                    for path in (shard_path, progress_path, focus_path, spec_path)]
    if (not progress["ok"] or shard["shard"]["shard"] != 2 or
            spec["sourceOrdinal"] != 23 or spec["trainingUse"] != "prohibited" or
            not spec["watermarkReviewRequired"] or spec["modifiedTruthIndex"] != 5 or
            spec["removeVertexIndices"] != [22, 23, 24] or
            focus["sourceOrdinal"] != 23 or focus["decision"] != "confirmed_label_rework"):
        raise ValueError("frozen review/microrepair contract mismatch")
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == 23)
    row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == 23)
    if (row["decision"] != "confirmed_label_rework" or
            row["sourceImage"] != source["sourceImage"] or
            row["sourceLabel"] != source["sourceLabel"] or
            focus["sourceImage"] != source["sourceImage"] or
            focus["sourceLabel"] != source["sourceLabel"] or len(source["nails"]) != 5):
        raise ValueError("frozen source identity drift")
    source_image = checked(source["sourceImage"])
    source_label = checked(source["sourceLabel"])
    checked(source["overview"])
    for nail in source["nails"]:
        checked(nail["nativeOverlay"])
    copy_path = output_dir / "images" / source["sourceFileName"]
    if not copy_path.exists():
        if verify:
            raise ValueError("isolated copy missing")
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_image, copy_path)
    if sha(copy_path) != source["sourceImage"]["sha256"]:
        raise ValueError("isolated copy drift")
    # Pillow only decodes the isolated copy; the bound dataset remains read-only.
    with Image.open(copy_path) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if [width, height] != spec["expectedDimensions"]:
        raise ValueError("source dimensions drift")
    lines = source_label.read_text(encoding="utf-8").splitlines()
    if len(lines) != 5:
        raise ValueError("old label count drift")
    old_polygons, polygons = [], []
    for index, line in enumerate(lines, start=1):
        values = [float(value) for value in line.split()]
        if values[0] != 0 or len(values) < 9 or len(values) % 2 != 1:
            raise ValueError("old YOLO polygon malformed")
        vertices = [(values[j] * width, values[j + 1] * height)
                    for j in range(1, len(values), 2)]
        old_polygons.append(vertices)
        repaired = [vertex for vertex_index, vertex in enumerate(vertices, start=1)
                    if index != 5 or vertex_index not in spec["removeVertexIndices"]]
        polygons.append(repaired)
    if (len(old_polygons[4]) - len(polygons[4]) != 3 or
            any(old_polygons[index] != polygons[index] for index in range(4))):
        raise ValueError("microrepair changed unrelated vertices")
    shapes = [Polygon(vertices) for vertices in polygons]
    if any(not shape.is_valid or shape.area <= 16 for shape in shapes):
        raise ValueError("repaired polygon invalid")
    overlaps = sum(shapes[i].intersection(shapes[j]).area > 1e-10
                   for i in range(5) for j in range(i + 1, 5))
    if overlaps:
        raise ValueError("repaired polygons overlap")
    x1, y1, x2, y2 = spec["qaBox"]
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("QA box outside image")
    if any(not (x1 <= x <= x2 and y1 <= y <= y2 and shapes[4].covers(Point(x, y)))
           for x, y in spec["qaPositivePoints"]):
        raise ValueError("QA positive point not in repaired nail")
    if any(not (0 <= x < width and 0 <= y < height and
                not shapes[4].covers(Point(x, y)))
           for x, y in spec["qaNegativePoints"]):
        raise ValueError("QA negative point inside repaired nail")
    if not (x1 <= shapes[4].bounds[0] and y1 <= shapes[4].bounds[1] and
            shapes[4].bounds[2] <= x2 and shapes[4].bounds[3] <= y2):
        raise ValueError("QA box does not contain repaired nail")
    annotation = {"version": "nail-texture-dataset/v1",
                  "decision": "candidate_only_not_training_truth", "trainingUse": "prohibited",
                  "originalResolutionReviewRequired": True,
                  "image": {"id": Path(source["sourceFileName"]).stem,
                            "fileName": source["sourceFileName"], "width": width,
                            "height": height, "sourceGroup": source["sourceGroup"],
                            "negative": False},
                  "annotations": [{"id": f"n{index}", "label": "nail_texture",
                                   "polygon": [{"x": round(x, 5), "y": round(y, 5)}
                                               for x, y in vertices]}
                                  for index, vertices in enumerate(polygons, start=1)]}
    annotation_path = output_dir / "annotations" / f"{Path(source['sourceFileName']).stem}.json"
    annotation_binding = stable_file(annotation_path,
                                     (json.dumps(annotation, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                                     verify)
    overlay = image.convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index, vertices in enumerate(polygons, start=1):
        draw.polygon(vertices, fill=(0, 220, 110, 55), outline=(0, 255, 80, 255), width=2)
        draw.text(tuple(vertices[0]), str(index), fill=(255, 255, 255, 255))
    overlay = Image.alpha_composite(overlay, layer).convert("RGB")
    overlay_binding = stable_file(output_dir / "overlays" / f"{Path(source['sourceFileName']).stem}-microrepair.png",
                                  png_bytes(overlay), verify)
    nails = []
    for index, shape in enumerate(shapes, start=1):
        bx1, by1, bx2, by2 = shape.bounds
        crop = [max(0, int(bx1) - 45), max(0, int(by1) - 45),
                min(width, int(bx2) + 46), min(height, int(by2) + 46)]
        path_prefix = output_dir / "native-crops" / f"source023-nail-{index:02d}"
        source_native = stable_file(Path(str(path_prefix) + "-source-native.png"),
                                    png_bytes(image.crop(tuple(crop))), verify)
        candidate_native = stable_file(Path(str(path_prefix) + "-candidate-native.png"),
                                       png_bytes(overlay.crop(tuple(crop))), verify)
        nails.append({"truthIndex": index, "polygonAreaPixels": round(shape.area, 3),
                      "cropBox": crop, "changedFromOld": index == 5,
                      "sourceNative": source_native, "candidateNative": candidate_native,
                      "visualDecision": "pending_original_resolution_review"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source023_spur_microrepair_candidate_visual_pending",
            "trainingUse": "prohibited", "sourceOrdinal": 23,
            "sourceFileName": source["sourceFileName"], "sourceGroup": source["sourceGroup"],
            "inputs": {"sourceScript": bind(Path(__file__)), "shardReport": bind(shard_path),
                       "progressV4": bind(progress_path), "focusedReview": bind(focus_path),
                       "microrepairSpec": bind(spec_path), "sourceImage": bind(source_image),
                       "sourceLabel": bind(source_label), "isolatedImage": bind(copy_path),
                       "sourceOverview": bind(Path(source["overview"]["path"])),
                       "nativeOverlays": [bind(Path(nail["nativeOverlay"]["path"]))
                                          for nail in source["nails"]],
                       "candidateAnnotation": annotation_binding,
                       "candidateOverlay": overlay_binding},
            "counts": {"sourceImages": 1, "nails": 5, "unchangedNails": 4,
                       "changedNails": 1, "removedSpurVertices": 3,
                       "legalPolygons": 5, "overlapPairs": 0,
                       "qaPositivePointsInside": len(spec["qaPositivePoints"]),
                       "qaNegativePointsOutside": len(spec["qaNegativePoints"]),
                       "visualApproved": 0, "trainingApproved": 0},
            "watermarkReviewRequired": True, "nails": nails}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("shard-report", "progress", "focus", "spec", "output-dir", "report", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["progressV4"]["path"]),
                        Path(inputs["focusedReview"]["path"]),
                        Path(inputs["microrepairSpec"]["path"]),
                        Path(inputs["candidateAnnotation"]["path"]).parents[1], verify=True)
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.shard_report, args.progress, args.focus, args.spec, args.output_dir, args.report)):
        parser.error("all source bindings, --output-dir and --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.shard_report.resolve(), args.progress.resolve(), args.focus.resolve(),
                   args.spec.resolve(), args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
