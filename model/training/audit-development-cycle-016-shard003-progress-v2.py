#!/usr/bin/env python3
"""Reconcile frozen shard-003 denominator after source-59 visual repair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {
    "source_quality_excluded": {"sourceImages": 4, "oldLabelNails": 22},
    "mask_visual_pass_role_pending": {"sourceImages": 3, "oldLabelNails": 15},
    "mask_rework": {"sourceImages": 4, "oldLabelNails": 24},
    "pending_every_nail_review": {"sourceImages": 9, "oldLabelNails": 44},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def build(prior_path: Path, visual_path: Path) -> dict:
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    visual = json.loads(visual_path.read_text(encoding="utf-8"))
    if (prior["decision"] != "shard003_progress_reconciled_training_still_prohibited" or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 105 or
            prior["counts"]["sourceGroups"] != 10 or
            visual["decision"] != "source059_five_complete_masks_visual_pass_training_prohibited" or
            visual["counts"] != {"sourceImages": 1, "nails": 5,
                                 "maskVisualPassImages": 1, "maskVisualPassNails": 5,
                                 "trainingApproved": 0}):
        raise ValueError("prior audit/visual state drift")
    for item in prior["inputs"].values():
        checked(item)
    for item in visual["inputs"].values():
        checked(item)
    previous = next(row for row in prior["sources"] if row["ordinal"] == 59)
    focus = visual["source"]
    if (previous["currentDecision"] != "mask_rework" or
            previous["oldLabelNails"] != 5 or
            focus["ordinal"] != 59 or
            focus["sourceImage"]["sha256"] != previous["sourceImage"]["sha256"] or
            focus["sourceGroup"] != previous["sourceGroup"] or
            focus["trainingUse"] != "prohibited"):
        raise ValueError("source 59 identity or role drift")
    checked(focus["candidateAnnotation"])
    rows = []
    for previous_row in prior["sources"]:
        row = dict(previous_row)
        if row["ordinal"] == 59:
            row["currentDecision"] = "mask_visual_pass_role_pending"
            row["visualEvidence"] = bind(visual_path)
            row["correctedAnnotation"] = focus["candidateAnnotation"]
            row["visibleSourceMarkerDecision"] = focus["visibleSourceMarkerDecision"]
        rows.append(row)
    if [row["ordinal"] for row in rows] != list(range(41, 61)):
        raise ValueError("source roster drift")
    counts = {}
    for role in EXPECTED:
        subset = [row for row in rows if row["currentDecision"] == role]
        counts[role] = {"sourceImages": len(subset),
                        "oldLabelNails": sum(row["oldLabelNails"] for row in subset)}
    if counts != EXPECTED or sum(row["oldLabelNails"] for row in rows) != 105:
        raise ValueError("nonconserving shard denominator")
    if len({row["sourceGroup"] for row in rows}) != 10:
        raise ValueError("source group count drift")
    if any(row["trainingUse"] != "prohibited" for row in rows):
        raise ValueError("premature training approval")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "shard003_progress_v2_reconciled_training_still_prohibited",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "priorProgress": bind(prior_path), "source059Visual": bind(visual_path)},
        "counts": {"sourceImages": 20, "oldLabelNails": 105, "sourceGroups": 10,
                   "statusCounts": counts, "newTrainingApprovedSources": 0},
        "sources": rows,
        "historicalSnapshotChanged": False, "protectedRolesChanged": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--source059-visual", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["priorProgress"]["path"]),
                        Path(saved["inputs"]["source059Visual"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_shard003_progress_v2",
                  "counts": saved["counts"]}
    else:
        if not args.prior_progress or not args.source059_visual or not args.report:
            parser.error("--prior-progress, --source059-visual, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.prior_progress.resolve(), args.source059_visual.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
