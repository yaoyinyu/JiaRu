#!/usr/bin/env python3
"""Bind the original-resolution occlusion stop-loss decision for source 30."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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


def build(preflight_path: Path, old_path: Path, sam_review_path: Path,
          visual_path: Path, progress_path: Path) -> dict:
    preflight, old, sam_review, visual, progress = map(
        load, (preflight_path, old_path, sam_review_path, visual_path, progress_path))
    if (preflight["counts"]["historicalCanonicalRecords"] != 1
            or old["decision"] !=
            "source030040_old_polygon_original_resolution_review_pending"
            or sam_review["decision"] !=
            "source030040_sam_geometry_pass_visual_review_pending"
            or visual["decision"] != "source030_rework_source040_quality_exclude"
            or progress["schemaVersion"] != 12 or not progress["ok"]
            or progress["counts"]["sourceImages"] != 20
            or progress["counts"]["oldLabelNails"] != 104
            or progress["counts"]["sourceGroups"] != 8):
        raise ValueError("source30 frozen evidence contract mismatch")
    for report in (preflight, old, sam_review, visual, progress):
        for item in report["inputs"].values():
            checked(item)
    if (old["inputs"]["batchPreflight"]["sha256"] != sha(preflight_path)
            or sam_review["inputs"]["oldOutline"]["sha256"] != sha(old_path)
            or visual["inputs"]["oldOutline"]["sha256"] != sha(old_path)
            or visual["inputs"]["samVisualReview"]["sha256"] != sha(sam_review_path)
            or progress["inputs"]["source030040VisualAudit"]["sha256"] != sha(visual_path)):
        raise ValueError("source30 evidence chain mismatch")
    batch = next(row for row in preflight["sources"] if row["ordinal"] == 30)
    prior = next(row for row in old["sources"] if row["ordinal"] == 30)
    sam = next(row for row in sam_review["sources"] if row["ordinal"] == 30)
    row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == 30)
    group_rows = [item for item in progress["sourceDispositions"]
                  if item["sourceGroup"] == batch["sourceGroup"]]
    if (batch["historicalCanonicalCount"] != 0
            or batch["sameGroupVisualPassOrdinals"] != [28, 29]
            or [item["ordinal"] for item in group_rows] != [28, 29, 30]
            or any(not item["everyNailVisualApproval"] for item in group_rows[:2])
            or not (batch["sourceImage"] == prior["sourceImage"] == row["sourceImage"])
            or not (batch["sourceLabel"] == prior["sourceLabel"] == row["sourceLabel"])
            or not (batch["isolatedSourceImage"] == prior["isolatedImage"] == sam["isolatedImage"])
            or not (batch["sourceGroup"] == prior["sourceGroup"] == row["sourceGroup"])
            or row["decision"] != "confirmed_label_rework"
            or row["everyNailVisualApproval"]
            or row["trainingUse"] != "prohibited"
            or visual["source30"]["sourceImage"] != batch["sourceImage"]
            or visual["source30"]["maskVisualApproval"]):
        raise ValueError("source30 identity, role or group gain mismatch")
    old_nail = next(item for item in prior["crops"] if item["nailIndex"] == 3)
    sam_nail = next(item for item in sam["nails"] if item["truthIndex"] == 3)
    if (old_nail["cropBoxPixels"] != [386, 737, 624, 975]
            or sam_nail["positiveHits"] != sam_nail["positiveCount"]
            or sam_nail["negativeHits"] != 0
            or sam_nail["polygonArea"] <= 1):
        raise ValueError("source30 nail3 crop or prompt drift")
    evidence = {"fullOriginal": batch["isolatedSourceImage"],
                "oldFullOutline": prior["fullOutline"],
                "oldNail3Source3x": old_nail["source"],
                "oldNail3Outline3x": old_nail["old-outline"],
                "samFullOutline": sam["fullOutline"],
                "samNail3Source3x": sam_nail["source"],
                "samNail3Outline3x": sam_nail["outline"]}
    for item in evidence.values():
        checked(item)
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source030_occluded_nail_surface_quality_exclude_next_train",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "batchPreflight": bind(preflight_path),
                   "oldOutline": bind(old_path),
                   "samVisualReview": bind(sam_review_path),
                   "priorVisualDecision": bind(visual_path),
                   "priorProgressV12": bind(progress_path)},
        "sourceOrdinal": 30,
        "sourceFileName": batch["sourceFileName"],
        "sourceGroup": batch["sourceGroup"],
        "sourceImage": batch["sourceImage"],
        "oldLabel": batch["sourceLabel"],
        "reviewedNailIndex": 3,
        "frozenOldMaskNails": 5,
        "sameGroupVisualPassOrdinals": [28, 29],
        "evidenceImages": evidence,
        "visualFinding": (
            "The large three-dimensional bow occludes the proximal nail surface; "
            "the hidden plate boundary is not recoverable at original resolution. "
            "Both old and one directed SAM contours incorporate decorative wings "
            "outside the identifiable plate. Manual drawing would infer unseen pixels."
        ),
        "manualBoundaryFeasible": False,
        "fullImageMaskVisualApproval": False,
        "scope": "next_train_candidate_and_derivatives_only_historical_snapshot_unchanged",
        "watermarkShortcutAbsenceProven": False,
        "newTrainingApprovedSources": 0,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("preflight", "old", "sam-review", "visual", "progress", "output",
                 "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for item in previous["inputs"].values():
            checked(item)
        for item in previous["evidenceImages"].values():
            checked(item)
        current = build(*(Path(previous["inputs"][key]["path"]) for key in
                          ("batchPreflight", "oldOutline", "samVisualReview",
                           "priorVisualDecision", "priorProgressV12")))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.preflight, args.old, args.sam_review, args.visual,
                args.progress, args.output)):
        parser.error("all inputs/outputs required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(*(path.resolve() for path in
                     (args.preflight, args.old, args.sam_review, args.visual, args.progress)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
