#!/usr/bin/env python3
"""Bind original-pixel source-48 quality stoploss without changing history."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound evidence drift: {path}")
    return path


def build(native_path: Path, preflight_path: Path, progress_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    for document in (native, preflight, progress):
        role = document.get("trainingUse", document.get("scope", {}).get("trainingUse"))
        if not document.get("ok") or role != "prohibited":
            raise ValueError("upstream decision or training role drift")
        for item in document["inputs"].values():
            checked(item)
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            native["counts"] != {"sourceImages": 1, "oldLabelNails": 5, "visualApprovals": 0} or
            [row["ordinal"] for row in native["sources"]] != [48] or
            preflight["decision"] != "four_remaining_reworks_identity_verified_source045_first" or
            progress["decision"] != "shard003_progress_v4_reconciled_training_still_prohibited" or
            progress["counts"]["sourceImages"] != 20 or
            progress["counts"]["oldLabelNails"] != 105):
        raise ValueError("upstream report mismatch")
    source = native["sources"][0]
    prior = next(row for row in progress["sources"] if row["ordinal"] == 48)
    preflight_row = next(row for row in preflight["sources"] if row["ordinal"] == 48)
    passed_group = next(row for row in progress["sources"] if row["ordinal"] == 47)
    if (source["sourceImage"] != prior["sourceImage"] or
            source["sourceImage"] != preflight_row["sourceImage"] or
            source["sourceLabel"] != preflight_row["sourceLabel"] or
            source["sourceGroup"] != prior["sourceGroup"] or
            source["sourceGroup"] != passed_group["sourceGroup"] or
            passed_group["currentDecision"] != "mask_visual_pass_role_pending" or
            source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"] or
            source["historicalCanonicalTruths"] != [] or
            prior["currentDecision"] != "mask_rework" or
            prior["trainingUse"] != "prohibited" or len(source["nails"]) != 5):
        raise ValueError("source 48 identity, role, or same-group comparison drift")
    for key in ("sourceImage", "sourceLabel", "isolatedImage"):
        checked(source[key])
    for nail in source["nails"]:
        checked(nail["raw3x"])
        checked(nail["oldOutline3x"])
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "exclude_source048_next_train_unconfirmable_side_thumb_boundary",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "nativeReview": bind(native_path), "preflight": bind(preflight_path),
                   "priorProgress": bind(progress_path)},
        "source": {
            "ordinal": 48, "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"],
            "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"],
            "isolatedImage": source["isolatedImage"],
            "hardFailure": {
                "nailIndex": 5,
                "reason": "thumb_side_view_proximal_nail_skin_boundary_not_confirmable",
                "raw3x": source["nails"][4]["raw3x"],
                "oldOutline3x": source["nails"][4]["oldOutline3x"],
            },
            "otherObservedOldMaskDefects": [
                "nail_2_old_polygon_jagged_and_includes_finger_skin",
                "nail_1_and_3_old_polygons_have_protrusions",
            ],
            "sourceMarker": "bottom_right_xiaohongshu_text_and_logo",
            "sameGroupMaskVisualPassSource": 47,
            "historicalCanonicalTruthCount": 0,
            "oldLabelNailsPreserved": 5,
            "decision": "source_quality_excluded_next_train_only",
            "trainingUse": "prohibited",
        },
        "counts": {"sourceImagesExcludedNextTrain": 1,
                   "oldNailsPreservedInHistoricalSnapshot": 5,
                   "newTrainingApproved": 0},
        "historicalSnapshotChanged": False,
        "protectedRolesChanged": False,
        "sourceImageOrLabelChanged": False,
        "limitations": "Original-pixel source rejection is a visual judgment; source 47 remains mask-visual-pass but source-marker and role gates are still open.",
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(*(Path(saved["inputs"][key]["path"]) for key in
                          ("nativeReview", "preflight", "priorProgress")))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_source048_quality_stoploss",
                  "counts": saved["counts"]}
    else:
        if not all((args.native_review, args.preflight, args.prior_progress, args.report)):
            parser.error("--native-review, --preflight, --prior-progress, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.preflight.resolve(),
                       args.prior_progress.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
