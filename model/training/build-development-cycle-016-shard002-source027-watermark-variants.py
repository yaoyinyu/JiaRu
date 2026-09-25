#!/usr/bin/env python3
"""Create four isolated source27 logo variants without changing nail pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


MASK_BOX = (760, 776, 800, 800)
SHIFT = (-160, -630)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def decode(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode {path}")
    return image


def png_bytes(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encoding failed")
    return data.tobytes()


def save_exact(image: Image.Image, path: Path, verify: bool) -> dict:
    if verify:
        if not path.is_file():
            raise ValueError(f"logo review crop missing: {path}")
    else:
        if path.exists():
            raise FileExistsError(path)
        image.save(path)
    with Image.open(path) as previous:
        if previous.size != image.size or previous.convert("RGB").tobytes() != image.tobytes():
            raise ValueError(f"logo review crop drift: {path}")
    return bind(path)


def build(preflight_path: Path, visual_path: Path, output_dir: Path,
          *, verify: bool) -> dict:
    preflight, visual = map(load, (preflight_path, visual_path))
    row = next(item for item in preflight["sources"] if item["ordinal"] == 27)
    result = visual["source27"]
    if (preflight["counts"]["sourceImages"] != 5 or
            row["dimensions"] != [800, 800] or
            row["markType"] != "xiaohongshu_corner_logo" or
            row["markBoxPixels"] != [764, 779, 797, 799] or
            row["trainingUse"] != "prohibited" or
            result["decision"] !=
            "repaired_mask_visual_pass_pending_watermark_and_full_split" or
            result["sourceImage"] != row["sourceImage"] or
            result["sourceGroup"] != row["sourceGroup"] or
            result["visualPassNails"] != 5 or
            result["watermarkShortcutAbsenceProven"] or
            result["trainingUse"] != "prohibited"):
        raise ValueError("source27 watermark input contract mismatch")
    for binding in (row["sourceImage"], row["sourceLabel"],
                    row["isolatedSourceImage"], result["hybridAnnotation"]):
        checked(binding)
    source = decode(Path(row["isolatedSourceImage"]["path"]))
    if source.shape[:2] != (800, 800):
        raise ValueError("source27 dimensions drift")
    annotation = load(Path(result["hybridAnnotation"]["path"]))
    if (annotation["image"]["sourceImageSha256"] != row["sourceImage"]["sha256"] or
            annotation["trainingUse"] != "prohibited" or
            len(annotation["annotations"]) != 5):
        raise ValueError("source27 hybrid annotation mismatch")
    nails = np.zeros(source.shape[:2], np.uint8)
    for nail in annotation["annotations"]:
        points = np.array([(round(p["x"]), round(p["y"]))
                           for p in nail["polygon"]], np.int32)
        cv2.fillPoly(nails, [points], 255)
    guarded = cv2.dilate(nails, np.ones((21, 21), np.uint8)) > 0
    x0, y0, x1, y1 = MASK_BOX
    safe = np.zeros(source.shape[:2], bool)
    safe[y0:y1, x0:x1] = True
    if np.any(safe & guarded):
        raise ValueError("logo removal intersects protected nail margins")
    mask = safe.astype(np.uint8) * 255
    removed = cv2.inpaint(source, mask, 7, cv2.INPAINT_TELEA)
    occluded = source.copy()
    reference = source[145:175, 590:660]
    background = np.median(reference.reshape(-1, 3), axis=0).astype(np.uint8)
    occluded[safe] = background
    blurred = source.copy()
    softened = cv2.GaussianBlur(source, (0, 0), 11)
    blurred[safe] = softened[safe]
    dx, dy = SHIFT
    ys, xs = np.nonzero(safe)
    target_y, target_x = ys + dy, xs + dx
    if (target_x.min() < 0 or target_x.max() >= 800 or
            target_y.min() < 0 or target_y.max() >= 800 or
            np.any(guarded[target_y, target_x]) or
            np.any(safe[target_y, target_x])):
        raise ValueError("moved watermark intersects nail/logo or leaves image")
    moved = removed.copy()
    local_x, local_y = xs - x0, ys - y0
    edge_distance = np.minimum.reduce((local_x, x1 - x0 - 1 - local_x,
                                       local_y, y1 - y0 - 1 - local_y))
    alpha = np.clip((edge_distance.astype(np.float32) - 1) / 3, 0, 1)[:, None]
    residual = source[ys, xs].astype(np.float32) - removed[ys, xs].astype(np.float32)
    moved[target_y, target_x] = np.rint(np.clip(
        removed[target_y, target_x].astype(np.float32) + residual * alpha,
        0, 255)).astype(np.uint8)
    variants = {"original": source, "remove": removed,
                "occlude": occluded, "blur": blurred,
                "move_position": moved}
    if not verify:
        output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    logo_crops = {}
    moved_crops = {}
    logo_box = (746, 762, 800, 800)
    moved_box = (586, 132, 655, 185)
    for name, image in variants.items():
        if name != "original" and np.array_equal(image, source):
            raise ValueError(f"unchanged logo variant: {name}")
        if not np.array_equal(image[nails > 0], source[nails > 0]):
            raise ValueError(f"nail pixels changed in variant: {name}")
        path = output_dir / f"source-027-{name}.png"
        data = png_bytes(image)
        if verify:
            if not path.is_file() or sha(path) != hashlib.sha256(data).hexdigest():
                raise ValueError(f"variant drift: {name}")
        else:
            if path.exists():
                raise FileExistsError(path)
            path.write_bytes(data)
        files[name] = bind(path)
        rgb = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        for label, region, collection in (("logo", logo_box, logo_crops),
                                          ("moved", moved_box, moved_crops)):
            crop = rgb.crop(region).resize(((region[2] - region[0]) * 8,
                                            (region[3] - region[1]) * 8),
                                           Image.Resampling.NEAREST)
            collection[name] = save_exact(
                crop, output_dir / f"source-027-{name}-{label}-8x.png", verify)
    mask_path = output_dir / "source-027-logo-mask.png"
    mask_data = png_bytes(mask)
    if verify:
        if not mask_path.is_file() or sha(mask_path) != hashlib.sha256(mask_data).hexdigest():
            raise ValueError("logo mask drift")
    else:
        if mask_path.exists():
            raise FileExistsError(mask_path)
        mask_path.write_bytes(mask_data)
    return {"schemaVersion": 1, "ok": True,
            "decision": "source027_four_logo_variants_built_visual_and_model_ablation_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "batchPreflight": bind(preflight_path),
                       "source025027VisualAudit": bind(visual_path),
                       "frozenSourceImage": row["sourceImage"],
                       "frozenOldLabel": row["sourceLabel"],
                       "isolatedSourceImage": row["isolatedSourceImage"],
                       "source27HybridAnnotation": result["hybridAnnotation"]},
            "sourceOrdinal": 27, "sourceFileName": row["sourceFileName"],
            "sourceGroup": row["sourceGroup"],
            "logoMaskBoxPixels": list(MASK_BOX),
            "logoMaskPixels": int(safe.sum()),
            "nailMaskPixels": int((nails > 0).sum()),
            "nailPixelsChanged": 0,
            "positionShiftPixels": {"x": dx, "y": dy},
            "logoMask": bind(mask_path), "variants": files,
            "logoCrops": logo_crops, "movedCrops": moved_crops,
            "maskVisualApproval": True,
            "variantVisualApproval": False,
            "modelAblationComplete": False,
            "shortcutAbsenceProven": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--visual-audit", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        checked(previous["logoMask"])
        for key in ("variants", "logoCrops", "movedCrops"):
            for binding in previous[key].values():
                checked(binding)
        current = build(Path(previous["inputs"]["batchPreflight"]["path"]),
                        Path(previous["inputs"]["source025027VisualAudit"]["path"]),
                        Path(previous["variants"]["original"]["path"]).parent,
                        verify=True)
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "nailPixelsChanged": current["nailPixelsChanged"]}))
        return
    if not all((args.preflight, args.visual_audit, args.output_dir, args.report)):
        parser.error("--preflight, --visual-audit, --output-dir, --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.preflight.resolve(), args.visual_audit.resolve(),
                   args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "nailPixelsChanged": report["nailPixelsChanged"]}))


if __name__ == "__main__":
    main()
