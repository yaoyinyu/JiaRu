#!/usr/bin/env python3
"""Build source32 corner-logo ablation variants with a clean floor relocation.

Variants are diagnostics only. Neither a visual pass nor a model-shortcut
exclusion decision follows from their construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


MASK_BOX = (1027, 1403, 1079, 1439)
SHIFT = (-130, -120)


def install_read_only_ultralytics_image_check() -> None:
    from ultralytics.data import utils as data_utils

    def check_image_read_only(im_file: str) -> tuple[str, tuple[int, int]]:
        with Image.open(im_file) as image:
            image.verify()
        with Image.open(im_file) as image:
            image.load()
            shape = (int(image.height), int(image.width))
            image_format = str(image.format or "").lower()
        if shape[0] <= 9 or shape[1] <= 9 or image_format not in data_utils.IMG_FORMATS:
            raise AssertionError(f"invalid read-only image: {im_file}")
        return "", shape

    data_utils.check_image = check_image_read_only
    if data_utils.verify_image.__globals__.get("check_image") is not check_image_read_only:
        raise RuntimeError("failed to install read-only image check")


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


def build(preflight_path: Path, output_dir: Path, *, verify: bool) -> dict:
    install_read_only_ultralytics_image_check()
    preflight = load(preflight_path)
    if (preflight.get("decision") !=
            "five_rework_sources_logo_windows_bound_visual_review_pending" or
            preflight["counts"]["sourceImages"] != 5 or
            preflight["counts"]["newTrainingApprovedSources"] != 0 or
            preflight["trainingUse"] != "prohibited"):
        raise ValueError("batch preflight contract mismatch")
    row = next((item for item in preflight["sources"] if item["ordinal"] == 32), None)
    if (row is None or row["dimensions"] != [1080, 1440] or
            row["historicalCanonicalCount"] != 1 or row["sameGroupVisualPassOrdinals"] or
            row["overlappingOldMaskIndices"] or
            row["oldMaskQuality"] != "confirmed_label_rework" or
            row["trainingUse"] != "prohibited"):
        raise ValueError("source32 role/priority mismatch")
    for binding in (row["sourceImage"], row["sourceLabel"],
                    row["isolatedSourceImage"], row["logoCrop"]):
        checked(binding)
    source = decode(Path(row["isolatedSourceImage"]["path"]))
    if source.shape[:2] != (1440, 1080):
        raise ValueError("source32 image dimensions drifted")
    nails = np.zeros(source.shape[:2], np.uint8)
    lines = Path(row["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    if len(lines) != 5:
        raise ValueError("five frozen old labels required")
    for line in lines:
        values = [float(value) for value in line.split()]
        if values[0] != 0 or len(values) < 7 or (len(values) - 1) % 2:
            raise ValueError("old label polygon invalid")
        points = np.array([(round(values[i] * 1080), round(values[i + 1] * 1440))
                           for i in range(1, len(values), 2)], np.int32)
        cv2.fillPoly(nails, [points], 255)
    guarded = cv2.dilate(nails, np.ones((21, 21), np.uint8)) > 0
    x0, y0, x1, y1 = MASK_BOX
    if not (0 <= x0 < x1 <= 1080 and 0 <= y0 < y1 <= 1440):
        raise ValueError("logo mask bounds invalid")
    safe = np.zeros(source.shape[:2], bool)
    safe[y0:y1, x0:x1] = True
    if np.any(safe & guarded):
        raise ValueError("logo removal intersects protected old nail masks")
    mask = safe.astype(np.uint8) * 255
    removed = cv2.inpaint(source, mask, 9, cv2.INPAINT_TELEA)
    occluded = source.copy()
    reference = source[1355:1395, 920:990]
    background = np.median(reference.reshape(-1, 3), axis=0).astype(np.uint8)
    occluded[safe] = background
    blurred = source.copy()
    softened = cv2.GaussianBlur(source, (0, 0), 18)
    blurred[safe] = softened[safe]
    dx, dy = SHIFT
    ys, xs = np.nonzero(safe)
    target_y, target_x = ys + dy, xs + dx
    if (target_x.min() < 0 or target_x.max() >= 1080 or
            target_y.min() < 0 or target_y.max() >= 1440 or
            np.any(guarded[target_y, target_x]) or np.any(safe[target_y, target_x])):
        raise ValueError("moved logo touches nail/source logo or leaves image")
    moved = removed.copy()
    local_x, local_y = xs - x0, ys - y0
    edge_distance = np.minimum.reduce((local_x, x1 - x0 - 1 - local_x,
                                       local_y, y1 - y0 - 1 - local_y))
    alpha = np.clip((edge_distance.astype(np.float32) - 1) / 3, 0, 1)[:, None]
    moved[target_y, target_x] = np.rint(
        source[ys, xs].astype(np.float32) * alpha +
        removed[target_y, target_x].astype(np.float32) * (1 - alpha)
    ).astype(np.uint8)
    variants = {"original": source, "remove": removed, "occlude": occluded,
                "blur": blurred, "move_position": moved}
    if not verify:
        output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, image in variants.items():
        if name != "original" and np.array_equal(image, source):
            raise ValueError(f"unchanged variant: {name}")
        if not np.array_equal(image[nails > 0], source[nails > 0]):
            raise ValueError(f"nail pixels changed: {name}")
        path = output_dir / f"source-032-{name}.png"
        data = png_bytes(image)
        if verify:
            if not path.is_file() or sha(path) != hashlib.sha256(data).hexdigest():
                raise ValueError(f"variant drift: {name}")
        else:
            if path.exists():
                raise FileExistsError(path)
            path.write_bytes(data)
        files[name] = bind(path)
    mask_path = output_dir / "source-032-logo-mask.png"
    mask_bytes = png_bytes(mask)
    if verify:
        if not mask_path.is_file() or sha(mask_path) != hashlib.sha256(mask_bytes).hexdigest():
            raise ValueError("logo mask drift")
    else:
        if mask_path.exists():
            raise FileExistsError(mask_path)
        mask_path.write_bytes(mask_bytes)
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_four_logo_variants_built_visual_and_model_ablation_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "batchPreflight": bind(preflight_path),
                       "frozenSourceImage": row["sourceImage"],
                       "frozenOldLabel": row["sourceLabel"],
                       "isolatedSourceImage": row["isolatedSourceImage"]},
            "sourceOrdinal": 32, "sourceFileName": row["sourceFileName"],
            "sourceGroup": row["sourceGroup"],
            "logoMaskBoxPixels": list(MASK_BOX), "logoMaskPixels": int(safe.sum()),
            "nailMaskPixels": int((nails > 0).sum()), "nailPixelsChanged": 0,
            "positionShiftPixels": {"x": dx, "y": dy},
            "logoMask": bind(mask_path), "variants": files,
            "maskVisualApproval": False, "modelAblationComplete": False,
            "shortcutAbsenceProven": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        current = build(Path(previous["inputs"]["batchPreflight"]["path"]),
                        Path(previous["variants"]["original"]["path"]).parent,
                        verify=True)
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "nailPixelsChanged": current["nailPixelsChanged"]}))
        return
    if not all((args.preflight, args.output_dir, args.report)):
        parser.error("--preflight, --output-dir and --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.preflight.resolve(), args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "nailPixelsChanged": report["nailPixelsChanged"]}))


if __name__ == "__main__":
    main()
