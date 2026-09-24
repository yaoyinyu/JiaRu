#!/usr/bin/env python3
"""Replay shard-002 ledger after source28's five-mask visual repair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPAIRED = "repaired_mask_visual_pass_pending_full_split"
STATUSES = ("pending_every_nail_review", "confirmed_label_rework",
            "confirmed_source_exclude", "watermark_review_required",
            "mask_visual_pass_pending_watermark_and_full_split",
            "mask_visual_pass_pending_full_split", REPAIRED)


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


def build(prior_path: Path, repair_path: Path) -> dict:
    prior, repair = load(prior_path), load(repair_path)
    if (not prior["ok"] or prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or not repair["ok"] or
            repair["decision"] != "source028_five_repaired_masks_visual_pass_training_prohibited" or
            repair["sourceOrdinal"] != 28 or repair["counts"]["visualPassNails"] != 5 or
            repair["counts"]["overlapPairs"] != 0 or
            repair["counts"]["newTrainingApprovedSources"] != 0 or
            repair["inputs"]["progressV3"]["sha256"] != sha(prior_path)):
        raise ValueError("prior/repair report contract mismatch")
    for binding in list(prior["inputs"].values()) + list(repair["inputs"].values()):
        checked(binding)
    rows = []
    for item in prior["sourceDispositions"]:
        current = dict(item)
        if item["ordinal"] == 28:
            if (item["decision"] != "confirmed_label_rework" or item["oldLabelNails"] != 5 or
                    repair["sourceFileName"] != item["sourceFileName"] or
                    repair["sourceGroup"] != item["sourceGroup"] or
                    repair["sourceImage"] != item["sourceImage"]):
                raise ValueError("source28 identity/status mismatch")
            current["decision"] = REPAIRED
            current["everyNailVisualApproval"] = True
            current["repairVisualReport"] = bind(repair_path)
            current["repairedAnnotation"] = repair["candidateAnnotation"]
        rows.append(current)
    if len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20:
        raise ValueError("source count drift")
    by_status = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in rows if row["decision"] == status)}
                 for status in STATUSES}
    if [by_status[status]["sourceImages"] for status in STATUSES] != [0, 10, 5, 2, 1, 1, 1]:
        raise ValueError("status count mismatch")
    if sum(x["oldLabelNails"] for x in by_status.values()) != 104 or len({row["sourceGroup"] for row in rows}) != 8:
        raise ValueError("old denominator or source groups drift")
    visual_nails = sum(row["oldLabelNails"] for row in rows if row["everyNailVisualApproval"])
    if visual_nails != 20:
        raise ValueError("visual pass denominator mismatch")
    return {"schemaVersion": 4, "ok": True,
            "decision": "shard002_ten_label_reworks_two_watermark_sources_pending_no_train_approval",
            "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV3": bind(prior_path),
                       "source28RepairVisual": bind(repair_path)},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                       "byStatus": by_status, "everyNailVisualPassSources": 3,
                       "everyNailVisualPassNails": visual_nails,
                       "newTrainingApprovedSources": 0},
            "initialPendingEveryNailQueueClosed": True,
            "fullShardCleanTruthComplete": False, "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--repair", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["priorProgressV3"]["path"]),
                        Path(inputs["source28RepairVisual"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.prior, args.repair, args.output)):
        parser.error("--prior, --repair and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.repair.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
