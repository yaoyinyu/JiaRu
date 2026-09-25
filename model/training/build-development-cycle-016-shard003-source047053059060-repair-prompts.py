#!/usr/bin/env python3
"""Freeze one directed SAM candidate pass for four incomplete shard-003 masks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


# Original-image pixels, chosen from untinted full images and 3x nearest-neighbor crops.
# The numbers are old label indices, not image order or newly approved truth counts.
PROMPTS = {
    47: (5, [273, 907, 500, 1041],
         [[312, 989], [397, 969], [466, 950]],
         [[265, 935], [445, 1044], [506, 941]]),
    53: (5, [118, 345, 331, 555],
         [[151, 373], [213, 434], [267, 485], [306, 514]],
         [[108, 418], [249, 337], [338, 495]]),
    59: (1, [411, 179, 510, 344],
         [[477, 209], [456, 258], [433, 307]],
         [[396, 279], [520, 217], [484, 350]]),
    60: (5, [544, 693, 700, 846],
         [[569, 812], [620, 762], [664, 721]],
         [[542, 745], [618, 850], [705, 801]]),
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


def build(native_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    if native["decision"] != "isolated_original_resolution_repair_crops_pending_visual":
        raise ValueError("native review state drift")
    for item in native["inputs"].values():
        checked(item)
    if [row["ordinal"] for row in native["sources"]] != list(PROMPTS):
        raise ValueError("source order drift")
    images = []
    for row in native["sources"]:
        ordinal = row["ordinal"]
        truth, box, positive, negative = PROMPTS[ordinal]
        width, height = row["imageSize"]
        for key in ("sourceImage", "sourceLabel", "isolatedImage"):
            checked(row[key])
        if sha(Path(row["sourceImage"]["path"])) != sha(Path(row["isolatedImage"]["path"])):
            raise ValueError("isolated image differs from frozen source")
        for nail in row["nails"]:
            checked(nail["raw3x"])
            checked(nail["oldOutline3x"])
        if truth < 1 or truth > len(row["nails"]):
            raise ValueError("old truth index invalid")
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError("prompt box invalid")
        if any(not (0 <= x < width and 0 <= y < height) for x, y in positive + negative):
            raise ValueError("prompt point out of image")
        if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in positive):
            raise ValueError("positive point out of prompt box")
        images.append({"sourceOrdinal": ordinal, "fileName": row["sourceFileName"],
                       "sourceGroup": row["sourceGroup"],
                       "sourceImageSha256": row["sourceImage"]["sha256"],
                       "promptTruthIndices": [truth],
                       "boxes": [[x1 / width, y1 / height, x2 / width, y2 / height]],
                       "positivePoints": [[[x / width, y / height] for x, y in positive]],
                       "negativePoints": [[[x / width, y / height] for x, y in negative]],
                       "promptModes": ["box-center"]})
    return {"schemaVersion": 1,
            "decision": "source047053059060_one_directed_sam_pass_candidate_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path)},
            "images": images}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["nativeReview"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": "verified_directed_repair_prompts",
                          "prompts": len(current["images"])}))
        return
    if not args.native_review or not args.output:
        parser.error("--native-review and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = build(args.native_review.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": result["decision"],
                      "prompts": len(result["images"])}))


if __name__ == "__main__":
    main()
