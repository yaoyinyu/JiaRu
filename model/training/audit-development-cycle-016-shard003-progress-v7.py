#!/usr/bin/env python3
"""Reconcile frozen shard-003 denominator after source-57/58 visual decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {
    "source_quality_excluded": {"sourceImages": 9, "oldLabelNails": 51},
    "mask_visual_pass_role_pending": {"sourceImages": 4, "oldLabelNails": 20},
    "mask_rework": {"sourceImages": 0, "oldLabelNails": 0},
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


def build(prior_path: Path, visual_path: Path) -> dict:
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    visual = json.loads(visual_path.read_text(encoding="utf-8"))
    if (prior["decision"] != "shard003_progress_v6_reconciled_training_still_prohibited"
            or prior["counts"]["sourceImages"] != 20
            or prior["counts"]["oldLabelNails"] != 105
            or prior["counts"]["sourceGroups"] != 10
            or visual["decision"] != "source057_quality_stoploss_source058_five_masks_visual_pass_roles_pending"
            or visual["counts"] != {
                "sourceImagesQualityExcludedNextTrain": 1,
                "sourceImagesMaskVisualPassRolePending": 1,
                "maskVisualPassNails": 5, "newTrainingApproved": 0}):
        raise ValueError("prior or visual decision drift")
    for document in (prior, visual):
        for item in document["inputs"].values():
            checked(item)
    rows = []
    for previous in prior["sources"]:
        row = dict(previous)
        ordinal = row["ordinal"]
        if ordinal in (57, 58):
            evidence = visual[f"source{ordinal:03d}"]
            if (row["currentDecision"] != "mask_rework"
                    or row["oldLabelNails"] != 5
                    or row["sourceImage"] != evidence["sourceImage"]
                    or row["sourceGroup"] != evidence["sourceGroup"]
                    or evidence["trainingUse"] != "prohibited"):
                raise ValueError(f"source {ordinal} identity or role drift")
            row["currentDecision"] = (
                "source_quality_excluded" if ordinal == 57
                else "mask_visual_pass_role_pending")
            row["visualEvidence"] = bind(visual_path)
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
        "decision": "shard003_progress_v7_reconciled_training_still_prohibited",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "priorProgress": bind(prior_path),
                   "source057058Visual": bind(visual_path)},
        "counts": {"sourceImages": 20, "oldLabelNails": 105, "sourceGroups": 10,
                   "statusCounts": counts, "newTrainingApprovedSources": 0},
        "sources": rows,
        "historicalSnapshotChanged": False, "protectedRolesChanged": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--source057058-visual", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["priorProgress"]["path"]),
                        Path(saved["inputs"]["source057058Visual"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_shard003_progress_v7",
                  "counts": saved["counts"]}
    else:
        if not all((args.prior_progress, args.source057058_visual, args.report)):
            parser.error("--prior-progress, --source057058-visual, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.prior_progress.resolve(), args.source057058_visual.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
