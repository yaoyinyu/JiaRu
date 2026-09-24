#!/usr/bin/env python3
"""Build source-7 watermark variants outside every frozen nail polygon.

The four PNGs are diagnostic inputs, not newly approved train images. Model
invariance must be audited separately and again for any later trained model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bound(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def decode(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode {path}")
    return image


def png_bytes(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encoding failed")
    return data.tobytes()


def build(preflight_path: Path, shard_path: Path, output_dir: Path, *, verify: bool) -> dict:
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    source = next(row for row in shard["sourceImages"] if row["ordinal"] == 7)
    if preflight["watermarkPreflight"]["sourceImage"]["sha256"] != source["sourceImage"]["sha256"]:
        raise ValueError("source-7 image identity drift")
    for key in ("sourceImage", "sourceLabel"):
        if sha256(Path(source[key]["path"])) != source[key]["sha256"]:
            raise ValueError(f"source-7 {key} drift")
    image = decode(Path(source["sourceImage"]["path"]))
    height, width = image.shape[:2]
    if (width, height) != (800, 678):
        raise ValueError("source-7 dimension drift")
    label_lines = Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    if len(label_lines) != 5:
        raise ValueError("source-7 nail count drift")
    nails = np.zeros((height, width), np.uint8)
    for line in label_lines:
        tokens = line.split()
        if tokens[0] != "0" or (len(tokens) - 1) % 2 != 0:
            raise ValueError("unexpected YOLO label")
        points = np.asarray([(round(float(tokens[i]) * width), round(float(tokens[i + 1]) * height))
                             for i in range(1, len(tokens), 2)], np.int32)
        cv2.fillPoly(nails, [points], 255)
    guarded = cv2.dilate(nails, np.ones((9, 9), np.uint8)) > 0
    safe = np.zeros((height, width), bool)
    safe[469:520, 200:530] = True
    safe[469:488, 530:548] = True
    # Rectangles are conservative search windows; rasterized nail exclusion is
    # the final safety mask and removes their narrow intersections at the edges.
    safe &= ~guarded
    # Pale watermark lettering on brown cloth, with a conservative text-colour
    # threshold and a 1 px antialias halo. The safe region also excludes nails.
    b, g, r = cv2.split(image)
    letters = safe & (r > 170) & (g > 153) & (b > 123)
    letters = cv2.dilate(letters.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    letters &= safe & ~guarded
    if not 1000 <= int(letters.sum()) <= 17000:
        raise ValueError("watermark pixel mask out of expected range")
    mask = (letters.astype(np.uint8) * 255)
    removed = cv2.inpaint(image, mask, 4, cv2.INPAINT_TELEA)
    occluded = image.copy()
    cloth_patch = image[525:545, 220:340]
    cloth_color = np.median(cloth_patch.reshape(-1, 3), axis=0).astype(np.uint8)
    occluded[safe] = cloth_color
    blurred = image.copy()
    blur_region = cv2.dilate(mask, np.ones((11, 11), np.uint8)) > 0
    blur_region &= ~guarded
    gaussian = cv2.GaussianBlur(image, (0, 0), 5)
    blurred[blur_region] = gaussian[blur_region]
    moved = removed.copy()
    dy, dx = 91, -75
    ys, xs = np.nonzero(letters)
    target_y, target_x = ys + dy, xs + dx
    if (target_y.max() >= height or target_x.min() < 0
            or np.any(guarded[target_y, target_x]) or np.any(safe[target_y, target_x])):
        raise ValueError("moved watermark touches a nail or source watermark area")
    moved[target_y, target_x] = image[ys, xs]
    variants = {"original": image, "remove": removed, "occlude": occluded,
                "blur": blurred, "move_position": moved}
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, variant in variants.items():
        if name != "original" and np.array_equal(variant, image):
            raise ValueError(f"variant unchanged: {name}")
        if not np.array_equal(variant[nails > 0], image[nails > 0]):
            raise ValueError(f"nail pixels changed: {name}")
        path = output_dir / f"source-007-{name}.png"
        data = png_bytes(variant)
        if verify:
            if not path.is_file() or sha256(path) != hashlib.sha256(data).hexdigest():
                raise ValueError(f"variant drift: {name}")
        else:
            if path.exists():
                raise FileExistsError(path)
            path.write_bytes(data)
        files[name] = bound(path)
    mask_path = output_dir / "source-007-watermark-pixel-mask.png"
    mask_data = png_bytes(mask)
    if verify:
        if not mask_path.is_file() or sha256(mask_path) != hashlib.sha256(mask_data).hexdigest():
            raise ValueError("watermark mask drift")
    else:
        if mask_path.exists():
            raise FileExistsError(mask_path)
        mask_path.write_bytes(mask_data)
    return {"schemaVersion": 1, "ok": True,
            "decision": "four_watermark_variants_built_model_ablation_pending",
            "inputs": {"sourceScript": bound(Path(__file__)), "preflight": bound(preflight_path),
                       "shard": bound(shard_path), "sourceImage": source["sourceImage"],
                       "sourceLabel": source["sourceLabel"]},
            "sourceOrdinal": 7, "sourceGroup": source["sourceGroup"],
            "watermarkType": "pale_horizontal_text_on_cloth",
            "safeRegionsPixels": [[200, 469, 530, 520], [530, 469, 548, 488]],
            "watermarkMaskPixels": int(letters.sum()),
            "nailMaskPixels": int((nails > 0).sum()),
            "nailPixelsChanged": 0, "positionShiftPixels": {"x": dx, "y": dy},
            "watermarkMask": bound(mask_path), "variants": files,
            "modelAblationComplete": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for input_binding in old["inputs"].values():
            if sha256(Path(input_binding["path"])) != input_binding["sha256"]:
                raise ValueError("input drift")
        current = build(Path(old["inputs"]["preflight"]["path"]),
                        Path(old["inputs"]["shard"]["path"]),
                        Path(old["variants"]["original"]["path"]).parent, verify=True)
        ok = current == old
        print(json.dumps({"ok": ok, "decision": current["decision"] if ok else "reconstruction_mismatch",
                          "watermarkMaskPixels": current["watermarkMaskPixels"]}))
        if not ok:
            raise SystemExit(1)
        return
    if not all((args.preflight, args.shard, args.output_dir, args.report)):
        parser.error("--preflight, --shard, --output-dir, --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.preflight.resolve(), args.shard.resolve(), args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "watermarkMaskPixels": report["watermarkMaskPixels"]}))


if __name__ == "__main__":
    main()
