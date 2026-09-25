#!/usr/bin/env python3
"""One directed SAM candidate pass for three failed complete-nail polygons."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


# Pixel points were selected on original-resolution source images and 3x untinted crops.
PROMPTS = {
    25: [
        (5, [584, 321, 683, 480],
         [[605, 350], [628, 397], [654, 443]],
         [[580, 350], [579, 421], [671, 489]]),
    ],
    27: [
        (1, [397, 480, 492, 626],
         [[447, 510], [441, 560], [425, 602]],
         [[392, 505], [495, 550], [423, 632]]),
        (5, [211, 383, 372, 454],
         [[245, 409], [297, 418], [340, 427]],
         [[299, 382], [254, 461], [380, 426]]),
    ],
}


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


def build(old_outline_path: Path, preflight_path: Path) -> dict:
    outline, preflight = map(load, (old_outline_path, preflight_path))
    if (outline["decision"] !=
            "source025027_old_polygon_original_resolution_review_pending" or
            outline["trainingUse"] != "prohibited" or
            preflight["counts"]["historicalCanonicalRecords"] != 1 or
            [r["ordinal"] for r in outline["sources"]] != [25, 27]):
        raise ValueError("old outline/preflight contract mismatch")
    images = []
    for old in outline["sources"]:
        ordinal = old["ordinal"]
        row = next(item for item in preflight["sources"] if item["ordinal"] == ordinal)
        if (old["sourceImage"] != row["sourceImage"] or
                old["sourceLabel"] != row["sourceLabel"] or
                old["sourceGroup"] != row["sourceGroup"] or
                old["isolatedImage"] != row["isolatedSourceImage"] or
                row["historicalCanonicalCount"] != 0 or
                row["trainingUse"] != "prohibited"):
            raise ValueError(f"source {ordinal} frozen identity/role mismatch")
        for key in ("sourceImage", "sourceLabel", "isolatedImage", "fullOutline"):
            checked(old[key])
        width, height = old["dimensions"]
        boxes, positives, negatives, truth_indices = [], [], [], []
        for truth_index, box, plus, minus in PROMPTS[ordinal]:
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError(f"source {ordinal} nail {truth_index} box invalid")
            if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
                raise ValueError(f"source {ordinal} nail {truth_index} point invalid")
            if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
                raise ValueError(f"source {ordinal} nail {truth_index} positive outside box")
            truth_indices.append(truth_index)
            boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
            positives.append([[x / width, y / height] for x, y in plus])
            negatives.append([[x / width, y / height] for x, y in minus])
        images.append({"sourceOrdinal": ordinal,
                       "fileName": old["sourceFileName"],
                       "sourceGroup": old["sourceGroup"],
                       "sourceImageSha256": old["sourceImage"]["sha256"],
                       "promptTruthIndices": truth_indices,
                       "boxes": boxes, "positivePoints": positives,
                       "negativePoints": negatives,
                       "promptModes": ["box-center"] * len(boxes)})
    return {"schemaVersion": 1,
            "decision": "source025027_one_directed_sam_pass_candidate_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "oldOutline": bind(old_outline_path),
                       "batchPreflight": bind(preflight_path)},
            "images": images}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for item in old["inputs"].values():
            checked(item)
        current = build(Path(old["inputs"]["oldOutline"]["path"]),
                        Path(old["inputs"]["batchPreflight"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.old_outline, args.preflight, args.output)):
        parser.error("--old-outline, --preflight and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.old_outline.resolve(), args.preflight.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
