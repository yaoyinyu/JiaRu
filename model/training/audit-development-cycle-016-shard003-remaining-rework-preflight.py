#!/usr/bin/env python3
"""Freeze identity, canonical duplicate, and source-group priority for remaining reworks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ORDINALS = (45, 48, 54, 55)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def build(triage_path: Path, progress_path: Path, native_path: Path) -> dict:
    triage, progress, native = [json.loads(path.read_text(encoding="utf-8"))
                                for path in (triage_path, progress_path, native_path)]
    if (progress["decision"] != "shard003_progress_v2_reconciled_training_still_prohibited" or
            progress["counts"]["statusCounts"]["mask_rework"] !=
            {"sourceImages": 4, "oldLabelNails": 24} or
            native["decision"] != "isolated_original_resolution_repair_crops_pending_visual"):
        raise ValueError("upstream state drift")
    canonical_path = checked(native["inputs"]["canonicalIndex"])
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    roster = {row["ordinal"]: row for row in triage["sourceTriage"]}
    active = {row["ordinal"]: row for row in progress["sources"]}
    if [row["ordinal"] for row in progress["sources"] if row["currentDecision"] == "mask_rework"] != list(ORDINALS):
        raise ValueError("remaining rework roster drift")
    rows = []
    for ordinal in ORDINALS:
        source, status = roster[ordinal], active[ordinal]
        if (source["sourceImage"]["sha256"] != status["sourceImage"]["sha256"] or
                source["sourceGroup"] != status["sourceGroup"] or
                source["oldLabelNails"] != status["oldLabelNails"] or
                source["decision"] != "confirmed_label_rework" or
                status["trainingUse"] != "prohibited"):
            raise ValueError("rework source identity/role drift")
        for key in ("sourceImage", "sourceLabel", "overview"):
            checked(source[key])
        matches = [item for item in canonical["canonicalTruths"]
                   if item["fileName"] == source["sourceFileName"]]
        if len(matches) > 1:
            raise ValueError("conflicting canonical duplicate identities")
        rows.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                     "sourceGroup": source["sourceGroup"], "oldLabelNails": source["oldLabelNails"],
                     "sourceImage": source["sourceImage"], "sourceLabel": source["sourceLabel"],
                     "overview": source["overview"], "historicalCanonicalTruthCount": len(matches),
                     "sourceMarkerReview": source["sourceMarkerReview"],
                     "trainingUse": "prohibited"})
    if [row["oldLabelNails"] for row in rows] != [10, 5, 5, 4] or len({r["sourceGroup"] for r in rows}) != 3:
        raise ValueError("rework counts or source-group topology drift")
    if rows[0]["sourceGroup"] in {row["sourceGroup"] for row in progress["sources"]
                                   if row["currentDecision"] == "mask_visual_pass_role_pending"}:
        raise ValueError("source 45 already has a visually passed group")
    if rows[1]["sourceGroup"] != active[47]["sourceGroup"] or rows[2]["sourceGroup"] != rows[3]["sourceGroup"]:
        raise ValueError("known shared source groups drift")
    if [row["historicalCanonicalTruthCount"] for row in rows] != [1, 0, 1, 1]:
        raise ValueError("canonical identity counts drift")
    return {"schemaVersion": 1, "ok": True,
            "decision": "four_remaining_reworks_identity_verified_source045_first",
            "inputs": {"sourceScript": bind(Path(__file__)), "triage": bind(triage_path),
                       "progressV2": bind(progress_path), "nativeReview": bind(native_path),
                       "canonicalIndex": bind(canonical_path)},
            "counts": {"reworkSources": 4, "oldLabelNails": 24, "sourceGroups": 3,
                       "historicalCanonicalRecords": 3, "trainingApproved": 0},
            "sources": rows, "firstSourceOrdinal": 45,
            "priorityReason": "Source 45 offers ten full-nail correction candidates in a group with no mask-visual-pass image; source 48 repeats source 47's group, while 54/55 share one other group.",
            "limitations": "Preflight confirms identities and grouping only; every original-resolution nail, marker, and role gate remains pending.",
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--progress-v2", type=Path)
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(*(Path(saved["inputs"][key]["path"]) for key in
                          ("triage", "progressV2", "nativeReview")))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_remaining_rework_preflight",
                  "counts": saved["counts"]}
    else:
        if not all((args.triage, args.progress_v2, args.native_review, args.report)):
            parser.error("all three bound inputs and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.triage.resolve(), args.progress_v2.resolve(),
                       args.native_review.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
