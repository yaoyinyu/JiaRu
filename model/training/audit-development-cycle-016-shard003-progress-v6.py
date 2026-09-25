#!/usr/bin/env python3
"""Reconcile frozen shard-003 denominator after source-57/58 visual rework."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {
    "source_quality_excluded": {"sourceImages": 8, "oldLabelNails": 46},
    "mask_visual_pass_role_pending": {"sourceImages": 3, "oldLabelNails": 15},
    "mask_rework": {"sourceImages": 2, "oldLabelNails": 10},
    "pending_every_nail_review": {"sourceImages": 7, "oldLabelNails": 34},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def build(prior_path: Path, rework_path: Path) -> dict:
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    rework = json.loads(rework_path.read_text(encoding="utf-8"))
    if (prior["decision"] != "shard003_progress_v5_reconciled_training_still_prohibited"
            or prior["counts"]["sourceImages"] != 20
            or prior["counts"]["oldLabelNails"] != 105
            or prior["counts"]["sourceGroups"] != 10
            or rework["decision"] != "sources057058_old_masks_rework_original_pixel_review"
            or rework["counts"] != {"sourceImagesRework": 2,
                                   "oldNailsPreservedInHistoricalSnapshot": 10,
                                   "sourceGroups": 1, "newTrainingApproved": 0}):
        raise ValueError("prior audit or rework state drift")
    for document in (prior, rework):
        for item in document["inputs"].values():
            checked(item)
    focus = {row["ordinal"]: row for row in rework["sources"]}
    if set(focus) != {57, 58}:
        raise ValueError("rework roster drift")
    rows = []
    for previous in prior["sources"]:
        row = dict(previous)
        ordinal = row["ordinal"]
        if ordinal in focus:
            evidence = focus[ordinal]
            if (row["currentDecision"] != "pending_every_nail_review"
                    or row["oldLabelNails"] != evidence["oldLabelNailsPreserved"]
                    or row["sourceImage"] != evidence["sourceImage"]
                    or row["sourceGroup"] != evidence["sourceGroup"]
                    or evidence["trainingUse"] != "prohibited"):
                raise ValueError(f"source {ordinal} identity or role drift")
            row["currentDecision"] = "mask_rework"
            row["reworkEvidence"] = bind(rework_path)
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
        "decision": "shard003_progress_v6_reconciled_training_still_prohibited",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "priorProgress": bind(prior_path),
                   "source057058Rework": bind(rework_path)},
        "counts": {"sourceImages": 20, "oldLabelNails": 105, "sourceGroups": 10,
                   "statusCounts": counts, "newTrainingApprovedSources": 0},
        "sources": rows,
        "historicalSnapshotChanged": False, "protectedRolesChanged": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--source057058-rework", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["priorProgress"]["path"]),
                        Path(saved["inputs"]["source057058Rework"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_shard003_progress_v6",
                  "counts": saved["counts"]}
    else:
        if not all((args.prior_progress, args.source057058_rework, args.report)):
            parser.error("--prior-progress, --source057058-rework, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.prior_progress.resolve(), args.source057058_rework.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
