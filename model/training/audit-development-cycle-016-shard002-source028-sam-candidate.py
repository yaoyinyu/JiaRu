#!/usr/bin/env python3
"""Audit source28's isolated SAM candidate and freeze native review crops."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Point, Polygon


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build(prompts_path: Path, sam_path: Path, crop_dir: Path,
          model_path: Path, *, verify: bool) -> dict:
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    sam = json.loads(sam_path.read_text(encoding="utf-8"))
    if (prompts["decision"] != "source028_sam_candidates_only" or
            prompts["trainingUse"] != "prohibited" or len(prompts["images"]) != 1 or
            not sam["ok"] or sam["decision"] != "sam_candidate_only_not_training_truth" or
            sam["trainingUse"] != "prohibited" or sam["promptCount"] != 5 or
            sam["completedCount"] != 1 or sam["errors"] or len(sam["outputs"]) != 1):
        raise ValueError("prompt/SAM candidate contract mismatch")
    for binding in prompts["inputs"].values():
        checked(binding)
    item, output = prompts["images"][0], sam["outputs"][0]
    if output["fileName"] != item["fileName"] or output["sourceGroup"] != item["sourceGroup"]:
        raise ValueError("source identity mismatch")
    source_path = Path(prompts["inputs"]["isolatedImage"]["path"])
    if sha(source_path) != item["sourceImageSha256"]:
        raise ValueError("isolated copy drift")
    annotation_path, overlay_path = Path(output["annotationPath"]), Path(output["overlayPath"])
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    if (annotation["decision"] != "candidate_only_not_training_truth" or
            annotation["trainingUse"] != "prohibited" or
            annotation["image"]["fileName"] != item["fileName"] or
            annotation["image"]["sourceGroup"] != item["sourceGroup"] or
            len(annotation["annotations"]) != 5 or output["polygonCount"] != 5):
        raise ValueError("annotation identity/role mismatch")
    with Image.open(source_path) as image_file, Image.open(overlay_path) as overlay_file:
        image, overlay = image_file.convert("RGB"), overlay_file.convert("RGB")
    width, height = image.size
    if image.size != overlay.size or (width, height) != (1080, 1352):
        raise ValueError("image/overlay dimensions mismatch")
    crop_dir.mkdir(parents=True, exist_ok=True)
    shapes, rows = [], []
    for index, nail in enumerate(annotation["annotations"], start=1):
        if nail["id"] != f"n{index}":
            raise ValueError("nail index mismatch")
        points = [(float(p["x"]), float(p["y"])) for p in nail["polygon"]]
        if len(points) < 4 or any(not (0 <= x < width and 0 <= y < height) for x, y in points):
            raise ValueError("polygon outside image")
        shape = Polygon(points)
        if not shape.is_valid or shape.area <= 16:
            raise ValueError("invalid polygon")
        shapes.append(shape)
        x1, y1, x2, y2 = shape.bounds
        box = (max(0, int(x1) - 45), max(0, int(y1) - 45),
               min(width, int(x2) + 46), min(height, int(y2) + 46))
        paths = []
        for suffix, source_image in (("source-native", image), ("candidate-native", overlay)):
            path = crop_dir / f"source028-nail-{index:02d}-{suffix}.png"
            data = png_bytes(source_image.crop(box))
            if verify:
                if not path.is_file() or sha(path) != hashlib.sha256(data).hexdigest():
                    raise ValueError(f"review crop drift: {path}")
            else:
                if path.exists():
                    raise FileExistsError(path)
                path.write_bytes(data)
            paths.append(bind(path))
        positive = item["positivePoints"][index - 1]
        negative = item["negativePoints"][index - 1]
        rows.append({"truthIndex": index, "polygonAreaPixels": round(shape.area, 3),
                     "cropBox": box, "positivePointsInside": all(
                         shape.covers(Point(x * width, y * height)) for x, y in positive),
                     "negativePointsOutside": all(
                         not shape.covers(Point(x * width, y * height)) for x, y in negative),
                     "sourceNative": paths[0], "candidateNative": paths[1],
                     "visualDecision": "pending_original_resolution_review"})
    overlap_pairs = sum(shapes[i].intersection(shapes[j]).area > 1e-10
                        for i in range(5) for j in range(i + 1, 5))
    return {"schemaVersion": 1, "ok": True,
            "decision": "source028_sam_candidate_geometry_review_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "prompts": bind(prompts_path),
                       "samReport": bind(sam_path), "modelWeights": bind(model_path),
                       "sourceCopy": bind(source_path), "annotation": bind(annotation_path),
                       "fullOverlay": bind(overlay_path)},
            "counts": {"sources": 1, "nails": 5, "legalPolygons": 5,
                       "overlapPairs": overlap_pairs,
                       "positivePointRowsInside": sum(row["positivePointsInside"] for row in rows),
                       "negativePointRowsOutside": sum(row["negativePointsOutside"] for row in rows),
                       "visualApproved": 0, "trainingApproved": 0},
            "sourceFileName": item["fileName"], "sourceGroup": item["sourceGroup"],
            "nails": rows, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path)
    parser.add_argument("--sam-report", type=Path)
    parser.add_argument("--crop-dir", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["prompts"]["path"]),
                        Path(inputs["samReport"]["path"]),
                        Path(old["nails"][0]["sourceNative"]["path"]).parent,
                        Path(inputs["modelWeights"]["path"]), verify=True)
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.prompts, args.sam_report, args.crop_dir, args.model, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prompts.resolve(), args.sam_report.resolve(), args.crop_dir.resolve(),
                   args.model.resolve(), verify=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
