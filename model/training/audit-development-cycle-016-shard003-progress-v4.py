#!/usr/bin/env python3
"""Reconcile frozen shard-003 denominator after source-54/55 quality stoploss."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {
    "source_quality_excluded": {"sourceImages": 7, "oldLabelNails": 41},
    "mask_visual_pass_role_pending": {"sourceImages": 3, "oldLabelNails": 15},
    "mask_rework": {"sourceImages": 1, "oldLabelNails": 5},
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


def build(prior_path: Path, stoploss_path: Path) -> dict:
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    stoploss = json.loads(stoploss_path.read_text(encoding="utf-8"))
    if (prior["decision"] != "shard003_progress_v3_reconciled_training_still_prohibited" or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 105 or
            prior["counts"]["sourceGroups"] != 10 or
            stoploss["decision"] != "exclude_sources054055_next_train_unconfirmable_side_nail_boundaries" or
            stoploss["counts"] != {"sourceImagesExcludedNextTrain": 2,
                                   "oldNailsPreservedInHistoricalSnapshot": 9,
                                   "sourceGroups": 1, "newTrainingApproved": 0}):
        raise ValueError("prior audit/quality state drift")
    for item in prior["inputs"].values():
        checked(item)
    for item in stoploss["inputs"].values():
        checked(item)
    for focus in stoploss["sources"]:
        previous = next(row for row in prior["sources"] if row["ordinal"] == focus["ordinal"])
        if (focus["ordinal"] not in (54, 55) or previous["currentDecision"] != "mask_rework" or
                previous["oldLabelNails"] != focus["oldLabelNailsPreserved"] or
                focus["sourceImage"]["sha256"] != previous["sourceImage"]["sha256"] or
                focus["sourceGroup"] != previous["sourceGroup"] or
                focus["trainingUse"] != "prohibited"):
            raise ValueError("source 54/55 identity or role drift")
    rows = []
    for previous_row in prior["sources"]:
        row = dict(previous_row)
        if row["ordinal"] in (54, 55):
            row["currentDecision"] = "source_quality_excluded"
            row["qualityEvidence"] = bind(stoploss_path)
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
        "decision": "shard003_progress_v4_reconciled_training_still_prohibited",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "priorProgress": bind(prior_path), "source054055Stoploss": bind(stoploss_path)},
        "counts": {"sourceImages": 20, "oldLabelNails": 105, "sourceGroups": 10,
                   "statusCounts": counts, "newTrainingApprovedSources": 0},
        "sources": rows,
        "historicalSnapshotChanged": False, "protectedRolesChanged": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--source054055-stoploss", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["priorProgress"]["path"]),
                        Path(saved["inputs"]["source054055Stoploss"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_shard003_progress_v4",
                  "counts": saved["counts"]}
    else:
        if not args.prior_progress or not args.source054055_stoploss or not args.report:
            parser.error("--prior-progress, --source054055-stoploss, and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.prior_progress.resolve(), args.source054055_stoploss.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
