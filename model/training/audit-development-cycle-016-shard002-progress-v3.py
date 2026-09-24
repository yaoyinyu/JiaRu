#!/usr/bin/env python3
"""Replay closure of shard-002's initially pending every-nail source queue."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ORDINALS = (23, 26, 31, 38)
EXPECTED = {23: "confirmed_label_rework", 26: "mask_visual_pass_pending_full_split",
            31: "confirmed_source_exclude", 38: "confirmed_source_exclude"}
STATUSES = ("pending_every_nail_review", "confirmed_label_rework",
            "confirmed_source_exclude", "watermark_review_required",
            "mask_visual_pass_pending_watermark_and_full_split",
            "mask_visual_pass_pending_full_split")


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


def build(prior_path: Path, focus_paths: dict[int, Path]) -> dict:
    prior = load(prior_path)
    if not prior["ok"] or prior["counts"]["sourceImages"] != 20 or prior["counts"]["oldLabelNails"] != 104:
        raise ValueError("prior ledger mismatch")
    if tuple(sorted(focus_paths)) != ORDINALS:
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
                    report["decision"] != EXPECTED[ordinal] or
                    report["priorDecision"] != item["decision"] or
                    report["sourceOrdinal"] != ordinal or
                    report["sourceFileName"] != item["sourceFileName"] or
                    report["sourceGroup"] != item["sourceGroup"] or
                    report["sourceImage"] != item["sourceImage"] or
                    report["sourceLabel"] != item["sourceLabel"] or
                    report["inputs"]["priorProgressV2"]["sha256"] != sha(prior_path) or
                    report["geometry"]["legalPolygons"] != item["oldLabelNails"] or
                    report["counts"]["newTrainingApprovedSources"] != 0 or
                    report["trainingUse"] != "prohibited"):
                raise ValueError(f"focused review mismatch: {ordinal}")
            current["decision"] = report["decision"]
            current["everyNailVisualApproval"] = report["counts"]["visualPassNails"] == item["oldLabelNails"]
            current["focusedReport"] = bind(focus_paths[ordinal])
        rows.append(current)
    if len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20:
        raise ValueError("source identity count mismatch")
    by_status = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in rows if row["decision"] == status)}
                 for status in STATUSES}
    if [by_status[status]["sourceImages"] for status in STATUSES] != [0, 11, 5, 2, 1, 1]:
        raise ValueError("status count mismatch")
    if sum(row["oldLabelNails"] for row in rows) != 104 or sum(x["oldLabelNails"] for x in by_status.values()) != 104:
        raise ValueError("old denominator drift")
    if len({row["sourceGroup"] for row in rows}) != 8:
        raise ValueError("source group drift")
    visual_pass = sum(row["oldLabelNails"] for row in rows if row["everyNailVisualApproval"])
    if visual_pass != 15:
        raise ValueError("visual pass count mismatch")
    return {"schemaVersion": 3, "ok": True,
            "decision": "shard002_initial_every_nail_queue_closed_repairs_and_watermarks_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV2": bind(prior_path),
                       **{f"source{ordinal}FocusedReview": bind(focus_paths[ordinal]) for ordinal in ORDINALS}},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                       "byStatus": by_status, "everyNailVisualPassSources": 2,
                       "everyNailVisualPassNails": visual_pass, "newTrainingApprovedSources": 0},
            "initialPendingEveryNailQueueClosed": True,
            "fullShardCleanTruthComplete": False, "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    for ordinal in ORDINALS:
        parser.add_argument(f"--focus{ordinal}", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["priorProgressV2"]["path"]),
                        {ordinal: Path(inputs[f"source{ordinal}FocusedReview"]["path"])
                         for ordinal in ORDINALS})
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    focus_paths = {ordinal: getattr(args, f"focus{ordinal}") for ordinal in ORDINALS}
    if not args.prior or not args.output or any(path is None for path in focus_paths.values()):
        parser.error("all input reports and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), {ordinal: path.resolve() for ordinal, path in focus_paths.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
