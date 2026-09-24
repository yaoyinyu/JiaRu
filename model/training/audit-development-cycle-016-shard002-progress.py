#!/usr/bin/env python3
"""Reconstruct the current shard-002 source and nail-review ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(triage_path: Path, source21_path: Path, source22_path: Path) -> dict:
    triage, source21, source22 = map(load, (triage_path, source21_path, source22_path))
    if not triage["evidenceOk"] or triage["counts"]["oldLabelNailsBound"] != 104:
        raise ValueError("triage contract drift")
    if source21["sourceOrdinal"] != 21 or source21["decision"] != "confirmed_label_rework":
        raise ValueError("source 21 decision drift")
    if source22["sourceOrdinal"] != 22 or source22["decision"] != "mask_visual_pass_pending_watermark_and_full_split":
        raise ValueError("source 22 decision drift")
    if source21["inputs"]["sourceTriage"]["sha256"] != sha(triage_path) or source22["inputs"]["sourceTriage"]["sha256"] != sha(triage_path):
        raise ValueError("focused reports do not bind triage")
    rows = []
    for item in triage["sourceTriage"]:
        current = dict(item)
        if item["ordinal"] == 21:
            if item["decision"] != "pending_every_nail_review":
                raise ValueError("source21 prior status drift")
            current["decision"] = source21["decision"]
            current["focusedReport"] = bind(source21_path)
        elif item["ordinal"] == 22:
            if item["decision"] != "pending_every_nail_review":
                raise ValueError("source22 prior status drift")
            current["decision"] = source22["decision"]
            current["everyNailVisualApproval"] = True
            current["focusedReport"] = bind(source22_path)
        rows.append(current)
    statuses = ("pending_every_nail_review", "confirmed_label_rework",
                "confirmed_source_exclude", "watermark_review_required",
                "mask_visual_pass_pending_watermark_and_full_split")
    counts = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                       "oldLabelNails": sum(row["oldLabelNails"] for row in rows if row["decision"] == status)}
              for status in statuses}
    expected_images = [7, 7, 3, 2, 1]
    if [counts[status]["sourceImages"] for status in statuses] != expected_images:
        raise ValueError("status totals drift")
    if sum(item["oldLabelNails"] for item in rows) != 104:
        raise ValueError("old label denominator drift")
    return {"schemaVersion": 1, "ok": True,
            "decision": "shard002_three_source_exclusions_seven_reworks_one_visual_pass_pending_watermark",
            "inputs": {"sourceScript": bind(Path(__file__)), "sourceTriageV2": bind(triage_path),
                       "source21FocusedReview": bind(source21_path),
                       "source22FocusedReview": bind(source22_path)},
            "sourceDispositions": rows, "counts": {"sourceImages": 20,
                "oldLabelNails": 104, "sourceGroups": 8, "byStatus": counts,
                "everyNailVisualPassSources": 1, "everyNailVisualPassNails": 5,
                "newTrainingApprovedSources": 0},
            "fullShardSourceReviewComplete": False, "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("triage", "source21", "source22", "output", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for item in old["inputs"].values():
            if sha(Path(item["path"])) != item["sha256"]:
                raise ValueError("bound input drift")
        inputs = old["inputs"]
        current = build(Path(inputs["sourceTriageV2"]["path"]),
                        Path(inputs["source21FocusedReview"]["path"]),
                        Path(inputs["source22FocusedReview"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.triage, args.source21, args.source22, args.output)):
        parser.error("all input reports and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.triage.resolve(), args.source21.resolve(), args.source22.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
