#!/usr/bin/env python3
"""Freeze one directed SAM pass for three old-mask skin intrusions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


# Original-image pixel coordinates chosen from untinted 3x source/old-outline crops.
PROMPTS = {
    37: [
        (4, [174, 922, 311, 1038],
         [[198, 1006], [232, 974], [284, 944]],
         [[200, 1045], [247, 1042], [314, 1012]]),
        (5, [360, 320, 427, 405],
         [[384, 341], [390, 365], [395, 383]],
         [[390, 415], [431, 381], [355, 390]]),
    ],
    39: [
        (4, [192, 750, 371, 896],
         [[218, 790], [266, 818], [328, 864]],
         [[163, 758], [186, 787], [369, 815]]),
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


def build(outline_path: Path) -> dict:
    outline = load(outline_path)
    if (outline["decision"] !=
            "source037039_old_polygon_original_resolution_review_pending"
            or outline["trainingUse"] != "prohibited"
            or [row["ordinal"] for row in outline["sources"]] != [37, 39]):
        raise ValueError("old-outline candidate contract mismatch")
    for item in outline["inputs"].values():
        checked(item)
    images = []
    for source in outline["sources"]:
        ordinal = source["ordinal"]
        if source["visualApproved"] or source["oldOverlapPairs"]:
            raise ValueError(f"source {ordinal} old topology/role drift")
        for key in ("sourceImage", "sourceLabel", "isolatedImage", "fullOutline"):
            checked(source[key])
        width, height = source["dimensions"]
        boxes, positives, negatives, truths = [], [], [], []
        for truth, box, plus, minus in PROMPTS[ordinal]:
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError(f"source {ordinal} nail {truth} box invalid")
            if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
                raise ValueError(f"source {ordinal} nail {truth} point invalid")
            if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
                raise ValueError(f"source {ordinal} nail {truth} positive outside box")
            truths.append(truth)
            boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
            positives.append([[x / width, y / height] for x, y in plus])
            negatives.append([[x / width, y / height] for x, y in minus])
        images.append({"sourceOrdinal": ordinal,
                       "fileName": source["sourceFileName"],
                       "sourceGroup": source["sourceGroup"],
                       "sourceImageSha256": source["sourceImage"]["sha256"],
                       "promptTruthIndices": truths,
                       "boxes": boxes, "positivePoints": positives,
                       "negativePoints": negatives,
                       "promptModes": ["box-center"] * len(boxes)})
    return {"schemaVersion": 1,
            "decision": "source037039_one_directed_sam_pass_candidate_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "oldOutline": bind(outline_path)},
            "images": images}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for item in old["inputs"].values():
            checked(item)
        current = build(Path(old["inputs"]["oldOutline"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.old_outline, args.output)):
        parser.error("--old-outline and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.old_outline.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
