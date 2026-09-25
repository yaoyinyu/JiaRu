#!/usr/bin/env python3
"""Freeze one original-pixel SAM candidate pass for source32's five complete nails."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


PROMPTS = [
    ([355, 655, 452, 935], [[405, 688], [403, 788], [411, 891]],
     [[350, 700], [458, 794], [435, 945]]),
    ([435, 680, 563, 989], [[529, 718], [511, 828], [473, 942]],
     [[428, 720], [570, 840], [436, 970]]),
    ([535, 782, 680, 1060], [[647, 825], [623, 934], [570, 1023]],
     [[526, 817], [690, 940], [528, 1045]]),
    ([626, 922, 846, 1048], [[801, 968], [740, 990], [680, 1003]],
     [[620, 926], [847, 1030], [755, 1053]]),
    ([218, 880, 457, 1005], [[259, 916], [343, 949], [425, 977]],
     [[213, 882], [360, 902], [455, 1007]]),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(preflight_path: Path, canonical_path: Path) -> dict:
    preflight, canonical = load(preflight_path), load(canonical_path)
    row = next(item for item in preflight["sources"] if item["ordinal"] == 32)
    if (preflight["counts"]["sourceImages"] != 5 or
            preflight["counts"]["oldLabelNails"] != 25 or
            row["oldMaskQuality"] != "confirmed_label_rework" or
            row["historicalCanonicalCount"] != 1 or
            canonical["decision"] != "historical_approved_truth_is_same_defective_cycle012_polygon" or
            canonical["sourceOrdinal"] != 32 or
            canonical["sourceFileName"] != row["sourceFileName"] or
            canonical["sourceGroup"] != row["sourceGroup"] or
            canonical["sourceImageSha256"] != row["sourceImage"]["sha256"] or
            canonical["counts"]["polygons"] != 5 or
            row["trainingUse"] != "prohibited"):
        raise ValueError("source32 identity/quality mismatch")
    for key in ("sourceImage", "sourceLabel", "isolatedSourceImage"):
        checked(row[key])
    copy_path = Path(row["isolatedSourceImage"]["path"])
    with Image.open(copy_path) as image:
        width, height = image.size
    if (width, height) != (1080, 1440):
        raise ValueError("source32 image dimensions drift")
    boxes, positives, negatives = [], [], []
    for index, (box, plus, minus) in enumerate(PROMPTS, start=1):
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(f"nail {index} box invalid")
        if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
            raise ValueError(f"nail {index} point outside image")
        if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
            raise ValueError(f"nail {index} positive point outside box")
        boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
        positives.append([[x / width, y / height] for x, y in plus])
        negatives.append([[x / width, y / height] for x, y in minus])
    return {"schemaVersion": 1, "decision": "source032_one_sam_candidate_pass_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "batchPreflight": bind(preflight_path),
                       "canonicalIdentity": bind(canonical_path),
                       "isolatedImage": bind(copy_path)},
            "images": [{"fileName": row["sourceFileName"],
                        "sourceGroup": row["sourceGroup"],
                        "sourceImageSha256": row["sourceImage"]["sha256"],
                        "boxes": boxes, "positivePoints": positives,
                        "negativePoints": negatives,
                        "promptModes": ["box-center"] * 5}]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for item in old["inputs"].values():
            checked(item)
        current = build(Path(old["inputs"]["batchPreflight"]["path"]),
                        Path(old["inputs"]["canonicalIdentity"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.preflight, args.canonical, args.output)):
        parser.error("--preflight, --canonical and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.preflight.resolve(), args.canonical.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
