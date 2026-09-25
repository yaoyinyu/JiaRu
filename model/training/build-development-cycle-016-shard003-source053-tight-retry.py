#!/usr/bin/env python3
"""Freeze one final tight SAM retry for source-053 nail 5 after skin leakage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BOX = [118, 345, 280, 501]
POSITIVE = [[151, 373], [197, 419], [236, 459]]
NEGATIVE = [[115, 449], [284, 492], [300, 469]]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound evidence drift: {path}")
    return path


def build(native_path: Path, failed_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    failed = json.loads(failed_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            failed["decision"] != "one_pass_sam_visual_stoploss_three_rejected_one_pending" or
            failed["counts"] != {"sourceImages": 4, "focusCandidates": 4, "geometryPass": 4,
                                 "visualRejected": 3, "visualPending": 1, "trainingApproved": 0}):
        raise ValueError("previous visual stoploss drift")
    for item in native["inputs"].values():
        checked(item)
    for item in failed["inputs"].values():
        checked(item)
    source = next(row for row in native["sources"] if row["ordinal"] == 53)
    failed_row = next(row for row in failed["sources"] if row["ordinal"] == 53)
    if (failed_row["visualDecision"] != "reject_skin_contamination" or
            failed_row["sourceImage"] != source["sourceImage"] or
            failed_row["sourceLabel"] != source["sourceLabel"] or
            failed_row["sourceGroup"] != source["sourceGroup"] or
            failed_row["focusTruthIndex"] != 5):
        raise ValueError("source-053 first-pass identity drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    if sha(Path(source["sourceImage"]["path"])) != sha(Path(source["isolatedImage"]["path"])):
        raise ValueError("isolated image differs from frozen source")
    width, height = source["imageSize"]
    x1, y1, x2, y2 = BOX
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("box invalid")
    if any(not (0 <= x < width and 0 <= y < height) for x, y in POSITIVE + NEGATIVE):
        raise ValueError("point outside source")
    if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in POSITIVE):
        raise ValueError("positive point outside tight box")
    image = {"sourceOrdinal": 53, "fileName": source["sourceFileName"],
             "sourceGroup": source["sourceGroup"],
             "sourceImageSha256": source["sourceImage"]["sha256"],
             "promptTruthIndices": [5],
             "boxes": [[x1 / width, y1 / height, x2 / width, y2 / height]],
             "positivePoints": [[[x / width, y / height] for x, y in POSITIVE]],
             "negativePoints": [[[x / width, y / height] for x, y in NEGATIVE]],
             "promptModes": ["box-center"]}
    return {"schemaVersion": 1, "decision": "source053_nail5_final_tight_sam_retry_candidate_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                       "failedVisual": bind(failed_path)},
            "images": [image]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--failed-visual", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["nativeReview"]["path"]),
                        Path(saved["inputs"]["failedVisual"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": "verified_source053_final_retry_prompt"}))
        return
    if not all((args.native_review, args.failed_visual, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = build(args.native_review.resolve(), args.failed_visual.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": result["decision"]}))


if __name__ == "__main__":
    main()
