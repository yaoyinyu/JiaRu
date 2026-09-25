#!/usr/bin/env python3
"""Bind source-45 original-pixel partial-nail exclusion without rewriting history."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound evidence drift: {path}")
    return path


def build(native_path: Path, preflight_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            native["counts"] != {"sourceImages": 1, "oldLabelNails": 10, "visualApprovals": 0} or
            preflight["decision"] != "four_remaining_reworks_identity_verified_source045_first"):
        raise ValueError("preflight/native decision drift")
    source = native["sources"][0]
    planned = next(row for row in preflight["sources"] if row["ordinal"] == 45)
    if (source["ordinal"] != 45 or len(source["nails"]) != 10 or
            source["sourceImage"]["sha256"] != planned["sourceImage"]["sha256"] or
            source["sourceGroup"] != planned["sourceGroup"] or
            len(source["historicalCanonicalTruths"]) != 1):
        raise ValueError("source 45 identity/canonical drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    if source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"]:
        raise ValueError("isolated source differs")
    for nail in source["nails"]:
        checked(nail["raw3x"])
        checked(nail["oldOutline3x"])
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "exclude_source045_next_train_partial_nail_occlusion",
        "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                   "remainingReworkPreflight": bind(preflight_path)},
        "source": {"ordinal": 45, "sourceFileName": source["sourceFileName"],
                   "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                   "sourceLabel": source["sourceLabel"], "isolatedImage": source["isolatedImage"],
                   "historicalCanonicalTruthCount": 1,
                   "focusNails": [source["nails"][8], source["nails"][9]],
                   "reason": "On the full original and 3x no-fill crops, nail 10 is reduced to a narrow dotted side/tip strip behind a crossing finger; its proximal surface is physically occluded. Nail 9 is also nearly side-on. An invented polygon cannot recover the invisible full nail 10 surface, so the image fails the source-image full-visible-nail gate irrespective of the old ten-label count.",
                   "scope": "next_train_candidate_and_derivatives_only",
                   "trainingUse": "prohibited"},
        "counts": {"sourceImagesExcluded": 1, "oldNailsPreservedInHistoricalSnapshot": 10,
                   "newTrainingApproved": 0},
        "historicalSnapshotChanged": False, "historicalCanonicalRecordChanged": False,
        "protectedRolesChanged": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["nativeReview"]["path"]),
                        Path(saved["inputs"]["remainingReworkPreflight"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_source045_partial_nail_stoploss",
                  "counts": saved["counts"]}
    else:
        if not args.native_review or not args.preflight or not args.report:
            parser.error("--native-review, --preflight, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.preflight.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
