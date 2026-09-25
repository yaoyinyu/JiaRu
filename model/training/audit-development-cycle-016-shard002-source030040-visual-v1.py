#!/usr/bin/env python3
"""Bind original-resolution visual decisions for shard002 sources 30/40."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(old_path: Path, prompts_path: Path, sam_path: Path,
          geometry_path: Path, review_path: Path) -> dict:
    old, prompts, sam, geometry, review = map(
        load, (old_path, prompts_path, sam_path, geometry_path, review_path))
    if (old["decision"] != "source030040_old_polygon_original_resolution_review_pending"
            or prompts["decision"] != "source030040_one_directed_sam_pass_candidate_only"
            or sam["decision"] != "sam_candidate_only_not_training_truth"
            or not sam["ok"] or sam["completedCount"] != 2
            or sam["promptCount"] != 4 or sam["errors"]
            or geometry["decision"] != "candidate_only_not_training_truth"
            or len(geometry["rows"]) != 4
            or any(row["status"] != "pass" for row in geometry["rows"])
            or review["decision"] != "source030040_sam_geometry_pass_visual_review_pending"
            or [row["ordinal"] for row in old["sources"]] != [30, 40]
            or [row["ordinal"] for row in review["sources"]] != [30, 40]):
        raise ValueError("frozen candidate/geometry contract mismatch")
    for report in (old, prompts, review):
        for binding in report["inputs"].values():
            checked(binding)
    if (prompts["inputs"]["oldOutline"]["sha256"] != sha(old_path)
            or review["inputs"]["prompts"]["sha256"] != sha(prompts_path)
            or review["inputs"]["samReport"]["sha256"] != sha(sam_path)
            or review["inputs"]["samGeometry"]["sha256"] != sha(geometry_path)
            or review["inputs"]["oldOutline"]["sha256"] != sha(old_path)):
        raise ValueError("unbound candidate evidence")
    for row in review["sources"]:
        for binding in row["nails"]:
            checked(binding["source"])
            checked(binding["outline"])
        if ([nail["truthIndex"] for nail in row["nails"]] != [3, 5]
                or row["legalCandidatePolygons"] != 2
                or row["overlapPairs"] != 0 or row["visualApproved"] != 0):
            raise ValueError("candidate nail topology/count drift")
    source30, source40 = old["sources"]
    if (source30["sourceGroup"] !=
            "real-material-2026-07-14-candidate-v1:note-054a61698ceca5c3"
            or source40["sourceGroup"] !=
            "real-material-2026-07-14-candidate-v1:note-20abd951a7db7500"
            or source30["legalOldPolygons"] != 5
            or source40["legalOldPolygons"] != 5
            or source30["oldOverlapPairs"] or source40["oldOverlapPairs"]):
        raise ValueError("frozen source/group/topology drift")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source030_rework_source040_quality_exclude",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "oldOutline": bind(old_path), "prompts": bind(prompts_path),
                   "samReport": bind(sam_path), "samGeometry": bind(geometry_path),
                   "samVisualReview": bind(review_path)},
        "source30": {
            "sourceOrdinal": 30, "sourceFileName": source30["sourceFileName"],
            "sourceGroup": source30["sourceGroup"],
            "sourceImage": source30["sourceImage"],
            "oldLabel": source30["sourceLabel"],
            "decision": "confirmed_label_rework",
            "maskVisualApproval": False,
            "reviewedCandidateNails": [3, 5],
            "candidateNail5": "transparent_tip_covered_better_than_old_polygon_provisional_only",
            "blockingNail3": "flower_decoration_occludes_surface_old_and_sam_contours_include_decoration",
            "nextAction": "original_resolution_manual_boundary_or_source_exclusion",
            "watermarkShortcutAbsenceProven": False,
            "trainingUse": "prohibited",
        },
        "source40": {
            "sourceOrdinal": 40, "sourceFileName": source40["sourceFileName"],
            "sourceGroup": source40["sourceGroup"],
            "sourceImage": source40["sourceImage"],
            "oldLabel": source40["sourceLabel"],
            "decision": "confirmed_source_exclude",
            "maskVisualApproval": False,
            "reviewedCandidateNails": [3, 5],
            "blockingNail5": "low_contrast_proximal_boundary_unconfirmable_old_and_sam_masks_enter_skin",
            "scope": "next_train_candidate_and_derivatives_only_historical_snapshot_unchanged",
            "trainingUse": "prohibited",
        },
        "geometryPassCandidates": 4,
        "fullImageVisualApprovedSources": 0,
        "newTrainingApprovedSources": 0,
        "historicalSnapshotChanged": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("old", "prompts", "sam", "geometry", "review", "output", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        inputs = previous["inputs"]
        current = build(*(Path(inputs[key]["path"]) for key in
                          ("oldOutline", "prompts", "samReport", "samGeometry", "samVisualReview")))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.old, args.prompts, args.sam, args.geometry, args.review, args.output)):
        parser.error("all inputs/outputs required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(*(path.resolve() for path in
                     (args.old, args.prompts, args.sam, args.geometry, args.review)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
