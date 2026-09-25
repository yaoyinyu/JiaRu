#!/usr/bin/env python3
"""Reconcile shard-003 source roles after original-pixel repairs and stoploss."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {"source_quality_excluded": [41, 44, 51, 60],
            "mask_visual_pass_role_pending": [47, 53],
            "mask_rework": [45, 48, 54, 55, 59],
            "pending_every_nail_review": [42, 43, 46, 49, 50, 52, 56, 57, 58]}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound report drift: {path}")
    return path


def build(triage_path: Path, quality_path: Path, visual_path: Path,
          stoploss_path: Path) -> dict:
    triage, quality, visual, stoploss = [json.loads(path.read_text(encoding="utf-8"))
                                          for path in (triage_path, quality_path, visual_path, stoploss_path)]
    if (triage["counts"]["reviewedOriginalSourceOverviews"] != 20 or
            triage["counts"]["oldLabelNailsBound"] != 105 or
            quality["decision"] != "shard003_three_sources_quality_exclude_next_train_candidate" or
            visual["decision"] != "two_source_masks_visual_pass_training_still_prohibited" or
            stoploss["decision"] != "exclude_source060_from_next_train_candidate_due_to_unrecoverable_occlusion"):
        raise ValueError("upstream decision/count drift")
    if sorted(row["ordinal"] for row in visual["sources"]) != [47, 53]:
        raise ValueError("mask visual source drift")
    if stoploss["source"]["ordinal"] != 60:
        raise ValueError("stoploss source drift")
    for key in ("hybridReport", "sourceScript"):
        checked(visual["inputs"][key])
    for key in ("nativeReview", "firstVisual", "sourceScript"):
        checked(stoploss["inputs"][key])
    if quality["counts"]["confirmedSourceExclude"] != {"sourceImages": 3, "oldLabelNails": 17}:
        raise ValueError("prior exclusion count drift")
    by_ordinal = {row["ordinal"]: row for row in triage["sourceTriage"]}
    if sorted(by_ordinal) != list(range(41, 61)):
        raise ValueError("shard source roster drift")
    rows = []
    for role, ordinals in EXPECTED.items():
        for ordinal in ordinals:
            old = by_ordinal[ordinal]
            if old["trainingUse"] != "prohibited":
                raise ValueError("old role drift")
            if role == "mask_visual_pass_role_pending":
                current = next(row for row in visual["sources"] if row["ordinal"] == ordinal)
                if (current["sourceImage"]["sha256"] != old["sourceImage"]["sha256"] or
                        current["sourceGroup"] != old["sourceGroup"] or len(current["nails"]) != old["oldLabelNails"]):
                    raise ValueError("visual identity/count drift")
            if ordinal == 60 and stoploss["source"]["sourceImage"]["sha256"] != old["sourceImage"]["sha256"]:
                raise ValueError("stoploss identity drift")
            rows.append({"ordinal": ordinal, "sourceFileName": old["sourceFileName"],
                         "sourceGroup": old["sourceGroup"], "sourceImage": old["sourceImage"],
                         "oldLabelNails": old["oldLabelNails"], "previousDecision": old["decision"],
                         "currentDecision": role, "trainingUse": "prohibited"})
    if len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20:
        raise ValueError("nonconserving source roster")
    groups = {}
    for role in EXPECTED:
        subset = [row for row in rows if row["currentDecision"] == role]
        groups[role] = {"sourceImages": len(subset),
                        "oldLabelNails": sum(row["oldLabelNails"] for row in subset)}
    if groups != {"source_quality_excluded": {"sourceImages": 4, "oldLabelNails": 22},
                  "mask_visual_pass_role_pending": {"sourceImages": 2, "oldLabelNails": 10},
                  "mask_rework": {"sourceImages": 5, "oldLabelNails": 29},
                  "pending_every_nail_review": {"sourceImages": 9, "oldLabelNails": 44}}:
        raise ValueError("shard progress denominator drift")
    return {"schemaVersion": 1, "ok": True,
            "decision": "shard003_progress_reconciled_training_still_prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)), "triage": bind(triage_path),
                       "priorQuality": bind(quality_path), "hybridVisual": bind(visual_path),
                       "source060Stoploss": bind(stoploss_path)},
            "counts": {"sourceImages": 20, "oldLabelNails": 105, "sourceGroups": 10,
                       "statusCounts": groups, "newTrainingApprovedSources": 0},
            "sources": sorted(rows, key=lambda row: row["ordinal"]),
            "historicalSnapshotChanged": False, "protectedRolesChanged": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    for option in ("triage", "prior-quality", "hybrid-visual", "source060-stoploss", "report", "verify-report"):
        parser.add_argument("--" + option, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(*(Path(saved["inputs"][key]["path"]) for key in
                          ("triage", "priorQuality", "hybridVisual", "source060Stoploss")))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_shard003_progress", "counts": saved["counts"]}
    else:
        if not all((args.triage, args.prior_quality, args.hybrid_visual, args.source060_stoploss, args.report)):
            parser.error("all four bound inputs and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.triage.resolve(), args.prior_quality.resolve(),
                       args.hybrid_visual.resolve(), args.source060_stoploss.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
