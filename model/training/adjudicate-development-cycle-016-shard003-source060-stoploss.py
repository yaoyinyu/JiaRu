#!/usr/bin/env python3
"""Bind source-60 quality stoploss to original pixels; preserve old evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def build(native_path: Path, first_visual_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    first = json.loads(first_visual_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            first["decision"] != "one_pass_sam_visual_stoploss_three_rejected_one_pending"):
        raise ValueError("upstream review decision drift")
    source = next(row for row in native["sources"] if row["ordinal"] == 60)
    if len(source["nails"]) != 5 or source["imageSize"] != [1080, 940]:
        raise ValueError("source-60 image or nail count drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    if source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"]:
        raise ValueError("isolated image mismatch")
    for nail in source["nails"]:
        checked(nail["raw3x"])
        checked(nail["oldOutline3x"])
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "exclude_source060_from_next_train_candidate_due_to_unrecoverable_occlusion",
        "inputs": {
            "sourceScript": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__))},
            "nativeReview": {"path": str(native_path.resolve()), "sha256": sha(native_path)},
            "firstVisual": {"path": str(first_visual_path.resolve()), "sha256": sha(first_visual_path)},
        },
        "source": {"ordinal": 60, "sourceFileName": source["sourceFileName"],
                   "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                   "sourceLabel": source["sourceLabel"], "isolatedImage": source["isolatedImage"],
                   "focusNails": [source["nails"][0], source["nails"][4]],
                   "reason": "Opaque large gemstone crosses the central nail surface of nail 1, hiding the underlying boundary; a polygon covering it would label non-nail decoration and a polygon omitting it cannot recover the hidden full surface. Nail 5 old polygon also omits its visible nude proximal bed. One SAM pass mixed non-nail regions, so further mask prompting cannot restore information occluded in the source.",
                   "scope": "next_train_candidate_and_derivatives_only",
                   "trainingUse": "prohibited"},
        "counts": {"sourceImagesExcluded": 1, "oldNailsPreservedInHistoricalSnapshot": 5,
                   "newTrainingApproved": 0},
        "historicalSnapshotChanged": False,
        "protectedRolesChanged": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--first-visual", type=Path)
    parser.add_argument("--report", type=Path)
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
        result = {"ok": True, "decision": "verified_source060_quality_stoploss",
                  "counts": saved["counts"]}
    else:
        if not args.native_review or not args.first_visual or not args.report:
            parser.error("--native-review, --first-visual and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.first_visual.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
