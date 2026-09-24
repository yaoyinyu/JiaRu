#!/usr/bin/env python3
"""Audit isolated SAM repair candidates and create native-resolution review crops.

Geometry and prompt consistency are necessary checks, never visual approval.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def build(prompt_path: Path, sam_path: Path, crop_dir: Path, *, verify: bool) -> dict:
    prompts = json.loads(prompt_path.read_text(encoding="utf-8"))
    sam = json.loads(sam_path.read_text(encoding="utf-8"))
    preflight_binding = prompts["preflight"]
    if sha256(Path(preflight_binding["path"])) != preflight_binding["sha256"]:
        raise ValueError("preflight drift")
    if prompts["trainingUse"] != "prohibited" or sam["trainingUse"] != "prohibited":
        raise ValueError("candidate training role drift")
    if sam["ok"] is not True or sam["promptCount"] != 10 or sam["completedCount"] != 2 or sam["errors"]:
        raise ValueError("SAM run incomplete")
    outputs = {row["fileName"]: row for row in sam["outputs"]}
    if len(outputs) != 2 or len(prompts["images"]) != 2:
        raise ValueError("image count drift")
    crop_dir.mkdir(parents=True, exist_ok=True)
    reviewed = []
    for item in prompts["images"]:
        filename = item["fileName"]
        output = outputs[filename]
        annotation_path = Path(output["annotationPath"])
        overlay_path = Path(output["overlayPath"])
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        image_path = prompt_path.parent / "images" / filename
        if sha256(image_path) != item["sourceImageSha256"]:
            raise ValueError(f"isolated image drift: {filename}")
        if annotation["trainingUse"] != "prohibited" or annotation["image"]["sourceGroup"] != item["sourceGroup"]:
            raise ValueError(f"annotation role/group drift: {filename}")
        nails = annotation["annotations"]
        if len(nails) != 5 or output["polygonCount"] != 5:
            raise ValueError(f"nail count drift: {filename}")
        with Image.open(image_path) as original_file, Image.open(overlay_path) as overlay_file:
            original, overlay = original_file.convert("RGB"), overlay_file.convert("RGB")
        if original.size != overlay.size:
            raise ValueError(f"overlay dimension drift: {filename}")
        width, height = original.size
        shapes = []
        nail_rows = []
        for index, nail in enumerate(nails, start=1):
            if nail["id"] != f"n{index}":
                raise ValueError(f"index drift: {filename} n{index}")
            points = [(float(p["x"]), float(p["y"])) for p in nail["polygon"]]
            if len(points) < 4 or any(not (0 <= x < width and 0 <= y < height) for x, y in points):
                raise ValueError(f"polygon bounds invalid: {filename} n{index}")
            shape = Polygon(points)
            if not shape.is_valid or shape.area <= 16:
                raise ValueError(f"polygon topology invalid: {filename} n{index}")
            shapes.append(shape)
            x1, y1, x2, y2 = shape.bounds
            crop_box = (max(0, int(x1) - 25), max(0, int(y1) - 25),
                        min(width, int(x2) + 26), min(height, int(y2) + 26))
            source_crop, overlay_crop = original.crop(crop_box), overlay.crop(crop_box)
            if source_crop.size != overlay_crop.size:
                raise ValueError("crop size mismatch")
            stem = f"{Path(filename).stem}-n{index:02d}"
            crop_files = []
            for suffix, image in (("source-native", source_crop), ("candidate-native", overlay_crop)):
                path = crop_dir / f"{stem}-{suffix}.png"
                data = png_bytes(image)
                if verify:
                    if not path.is_file() or sha256(path) != hashlib.sha256(data).hexdigest():
                        raise ValueError(f"review crop drift: {path}")
                else:
                    if path.exists():
                        raise FileExistsError(path)
                    path.write_bytes(data)
                crop_files.append(binding(path))
            nail_rows.append({"truthIndex": index, "polygonAreaPixels": round(shape.area, 3),
                              "cropBox": crop_box, "sourceNative": crop_files[0],
                              "candidateNative": crop_files[1], "visualDecision": "pending_original_resolution_review"})
        for first in range(len(shapes)):
            for second in range(first + 1, len(shapes)):
                if shapes[first].intersection(shapes[second]).area > 0:
                    raise ValueError(f"same-image nail overlap: {filename} {first+1}/{second+1}")
        reviewed.append({"fileName": filename, "sourceGroup": item["sourceGroup"],
                         "sourceImage": binding(image_path), "annotation": binding(annotation_path),
                         "overlay": binding(overlay_path), "nails": nail_rows,
                         "trainingUse": "prohibited"})
    return {"schemaVersion": 1, "ok": True, "decision": "geometry_pass_visual_review_pending",
            "inputs": {"sourceScript": binding(Path(__file__)), "prompts": binding(prompt_path), "samReport": binding(sam_path)},
            "counts": {"images": 2, "nails": 10, "legalPolygons": 10,
                       "overlapPairs": 0, "visualApproved": 0, "trainingApproved": 0},
            "images": reviewed, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path)
    parser.add_argument("--sam-report", type=Path)
    parser.add_argument("--crop-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for bound in old["inputs"].values():
            if sha256(Path(bound["path"])) != bound["sha256"]:
                raise ValueError("input drift")
        actual = build(Path(old["inputs"]["prompts"]["path"]),
                       Path(old["inputs"]["samReport"]["path"]),
                       Path(old["images"][0]["nails"][0]["sourceNative"]["path"]).parent,
                       verify=True)
        ok = old == actual
        print(json.dumps({"ok": ok, "decision": actual["decision"] if ok else "reconstruction_mismatch",
                          "counts": actual["counts"]}))
        if not ok:
            raise SystemExit(1)
        return
    if not all((args.prompts, args.sam_report, args.crop_dir, args.output)):
        parser.error("--prompts, --sam-report, --crop-dir and --output are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prompts.resolve(), args.sam_report.resolve(), args.crop_dir.resolve(), verify=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
