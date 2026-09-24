#!/usr/bin/env python3
"""Replay shard-002 progress after focused original-resolution source reviews."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FOCUS_ORDINALS = (25, 28, 33)
STATUSES = ("pending_every_nail_review", "confirmed_label_rework",
            "confirmed_source_exclude", "watermark_review_required",
            "mask_visual_pass_pending_watermark_and_full_split")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def build(prior_path: Path, focus_paths: dict[int, Path]) -> dict:
    prior = load(prior_path)
    if not prior["ok"] or prior["counts"]["sourceImages"] != 20 or prior["counts"]["oldLabelNails"] != 104:
        raise ValueError("prior ledger mismatch")
    if tuple(sorted(focus_paths)) != FOCUS_ORDINALS:
        raise ValueError("focused source set mismatch")
    for binding in prior["inputs"].values():
        checked(binding)
    focused = {ordinal: load(path) for ordinal, path in focus_paths.items()}
    rows = []
    for item in prior["sourceDispositions"]:
        current = dict(item)
        ordinal = item["ordinal"]
        if ordinal in focused:
            report = focused[ordinal]
            for binding in report["inputs"].values():
                checked(binding)
            if (item["decision"] != "pending_every_nail_review" or
                    report["decision"] != "confirmed_label_rework" or
                    report["sourceOrdinal"] != ordinal or
                    report["sourceFileName"] != item["sourceFileName"] or
                    report["sourceGroup"] != item["sourceGroup"] or
                    report["sourceImage"] != item["sourceImage"] or
                    report["sourceLabel"] != item["sourceLabel"] or
                    report["inputs"]["sourceTriage"]["sha256"] !=
                    prior["inputs"]["sourceTriageV2"]["sha256"] or
                    report["geometry"]["legalPolygons"] != item["oldLabelNails"] or
                    report["trainingUse"] != "prohibited"):
                raise ValueError(f"focused review mismatch: {ordinal}")
            current["decision"] = report["decision"]
            current["focusedReport"] = bind(focus_paths[ordinal])
        rows.append(current)
    if len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20:
        raise ValueError("source identity count mismatch")
    by_status = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in rows if row["decision"] == status)}
                 for status in STATUSES}
    if [by_status[status]["sourceImages"] for status in STATUSES] != [4, 10, 3, 2, 1]:
        raise ValueError("status count mismatch")
    if sum(row["oldLabelNails"] for row in rows) != 104 or sum(x["oldLabelNails"] for x in by_status.values()) != 104:
        raise ValueError("old denominator drift")
    if len({row["sourceGroup"] for row in rows}) != 8:
        raise ValueError("source group drift")
    return {"schemaVersion": 2, "ok": True,
            "decision": "shard002_three_more_label_reworks_four_sources_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV1": bind(prior_path),
                       **{f"source{ordinal}FocusedReview": bind(focus_paths[ordinal]) for ordinal in FOCUS_ORDINALS}},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                       "byStatus": by_status, "everyNailVisualPassSources": 1,
                       "everyNailVisualPassNails": 5, "newTrainingApprovedSources": 0},
            "fullShardSourceReviewComplete": False, "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--focus25", type=Path)
    parser.add_argument("--focus28", type=Path)
    parser.add_argument("--focus33", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["priorProgressV1"]["path"]),
                        {ordinal: Path(inputs[f"source{ordinal}FocusedReview"]["path"])
                         for ordinal in FOCUS_ORDINALS})
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.prior, args.focus25, args.focus28, args.focus33, args.output)):
        parser.error("all input reports and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), {25: args.focus25.resolve(), 28: args.focus28.resolve(),
                                          33: args.focus33.resolve()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
