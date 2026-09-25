#!/usr/bin/env python3
"""Bind original-pixel rework decisions for frozen shard-003 sources 57/58."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DEFECTS = {
    57: (5, "old_polygon_omits_visible_transparent_distal_tip"),
    58: (4, "old_polygon_has_skinward_spikes_at_proximal_nail_boundary"),
}


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


def build(native_path: Path, progress_path: Path) -> dict:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    for document in (native, progress):
        role = document.get("trainingUse", document.get("scope", {}).get("trainingUse"))
        if not document.get("ok") or role != "prohibited":
            raise ValueError("upstream approval or role drift")
        for item in document["inputs"].values():
            checked(item)
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual"
            or native["counts"] != {"sourceImages": 2, "oldLabelNails": 10,
                                    "visualApprovals": 0}
            or [row["ordinal"] for row in native["sources"]] != [57, 58]
            or progress["decision"] != "shard003_progress_v5_reconciled_training_still_prohibited"
            or progress["counts"]["sourceImages"] != 20
            or progress["counts"]["oldLabelNails"] != 105):
        raise ValueError("frozen roster or denominator drift")
    rows = []
    for source in native["sources"]:
        ordinal = source["ordinal"]
        nail_index, defect = DEFECTS[ordinal]
        prior = next(row for row in progress["sources"] if row["ordinal"] == ordinal)
        if (prior["currentDecision"] != "pending_every_nail_review"
                or prior["trainingUse"] != "prohibited"
                or source["sourceImage"] != prior["sourceImage"]
                or source["sourceGroup"] != prior["sourceGroup"]
                or source["isolatedImage"]["sha256"] != source["sourceImage"]["sha256"]
                or len(source["nails"]) != 5
                or len(source["historicalCanonicalTruths"]) != 1):
            raise ValueError(f"source {ordinal} identity or old role drift")
        for item in (source["sourceImage"], source["sourceLabel"],
                     source["isolatedImage"]):
            checked(item)
        for nail in source["nails"]:
            checked(nail["raw3x"])
            checked(nail["oldOutline3x"])
        focus = source["nails"][nail_index - 1]
        if focus["truthIndex"] != nail_index:
            raise ValueError("nail index drift")
        rows.append({
            "ordinal": ordinal,
            "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"],
            "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"],
            "isolatedImage": source["isolatedImage"],
            "historicalCanonicalTruthCount": 1,
            "oldLabelNailsPreserved": 5,
            "visualFinding": {"nailIndex": nail_index, "reason": defect,
                              "raw3x": focus["raw3x"],
                              "oldOutline3x": focus["oldOutline3x"]},
            "decision": "mask_rework_not_training_approved",
            "trainingUse": "prohibited",
        })
    if rows[0]["sourceGroup"] != rows[1]["sourceGroup"]:
        raise ValueError("shared source group drift")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "sources057058_old_masks_rework_original_pixel_review",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "nativeReview": bind(native_path),
                   "priorProgress": bind(progress_path)},
        "counts": {"sourceImagesRework": 2,
                   "oldNailsPreservedInHistoricalSnapshot": 10,
                   "sourceGroups": 1, "newTrainingApproved": 0},
        "sources": rows,
        "historicalSnapshotChanged": False,
        "historicalCanonicalChanged": False,
        "protectedRolesChanged": False,
        "sourceImageOrLabelChanged": False,
        "limitations": "Original-pixel visual finding is a human judgment; hash replay binds evidence, not a repaired mask or training approval.",
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["nativeReview"]["path"]),
                        Path(saved["inputs"]["priorProgress"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_sources057058_rework",
                  "counts": saved["counts"]}
    else:
        if not all((args.native_review, args.prior_progress, args.report)):
            parser.error("--native-review, --prior-progress, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.prior_progress.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
