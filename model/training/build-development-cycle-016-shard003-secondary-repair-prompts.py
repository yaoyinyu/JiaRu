#!/usr/bin/env python3
"""Freeze one SAM pass for three defects revealed by full-image review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


# Original-image coordinates from bound 3x untinted old-outline crops.
REPAIRS = {
    47: [
        (1, [311, 449, 526, 686],
         [[359, 493], [418, 568], [484, 641]],
         [[296, 540], [532, 557], [422, 693]],
         "旧第1枚右侧边缘出现向非甲面突出的锯齿。"),
        (4, [510, 285, 710, 531],
         [[562, 333], [619, 410], [668, 484]],
         [[505, 384], [718, 405], [630, 539]],
         "旧第4枚右上缘有不随真实甲缘的突刺。"),
    ],
    53: [
        (3, [129, 660, 255, 795],
         [[156, 685], [193, 724], [224, 765]],
         [[121, 718], [262, 733], [207, 803]],
         "旧第3枚透明尖左侧polygon扩入黑色头发，甲根亦锯齿。"),
    ],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound evidence drift: {path}")
    return path


def build(native_path: Path, first_visual_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    visual = json.loads(first_visual_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            visual["decision"] != "one_pass_sam_visual_stoploss_three_rejected_one_pending" or
            visual["counts"]["trainingApproved"] != 0):
        raise ValueError("prior review identity/role drift")
    for source in native["sources"]:
        if source["ordinal"] in REPAIRS:
            for key in ("sourceImage", "sourceLabel", "isolatedImage"):
                checked(source[key])
            for nail in source["nails"]:
                checked(nail["raw3x"])
                checked(nail["oldOutline3x"])
    images = []
    for ordinal, specifications in REPAIRS.items():
        source = next(row for row in native["sources"] if row["ordinal"] == ordinal)
        width, height = source["imageSize"]
        boxes, positives, negatives, indices, reasons = [], [], [], [], []
        for index, box, plus, minus, reason in specifications:
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError("prompt box invalid")
            if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
                raise ValueError("prompt point invalid")
            if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
                raise ValueError("positive point outside box")
            if index < 1 or index > len(source["nails"]):
                raise ValueError("old nail index invalid")
            boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
            positives.append([[x / width, y / height] for x, y in plus])
            negatives.append([[x / width, y / height] for x, y in minus])
            indices.append(index)
            reasons.append(reason)
        images.append({"sourceOrdinal": ordinal, "fileName": source["sourceFileName"],
                       "sourceGroup": source["sourceGroup"],
                       "sourceImageSha256": source["sourceImage"]["sha256"],
                       "promptTruthIndices": indices, "oldVisualDefectReasons": reasons,
                       "boxes": boxes, "positivePoints": positives,
                       "negativePoints": negatives,
                       "promptModes": ["box-center"] * len(indices)})
    return {"schemaVersion": 1,
            "decision": "source047_053_secondary_old_mask_repair_candidate_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                       "firstVisual": bind(first_visual_path)},
            "images": images}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--first-visual", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["nativeReview"]["path"]),
                        Path(saved["inputs"]["firstVisual"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": "verified_secondary_repair_prompts"}))
        return
    if not all((args.native_review, args.first_visual, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = build(args.native_review.resolve(), args.first_visual.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": result["decision"],
                      "prompts": sum(len(row["boxes"]) for row in result["images"])}))


if __name__ == "__main__":
    main()
