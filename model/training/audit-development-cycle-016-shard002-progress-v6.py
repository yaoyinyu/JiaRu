#!/usr/bin/env python3
"""Replay shard-002 ledger after source21 historical-truth correction review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE21_STATUS = "historical_truth_correction_visual_pass_pending_full_split"
STATUSES = (
    "pending_every_nail_review", "confirmed_label_rework",
    "confirmed_source_exclude", "watermark_review_required",
    "mask_visual_pass_pending_watermark_and_full_split",
    "mask_visual_pass_pending_full_split",
    "repaired_mask_visual_pass_pending_full_split",
    "repaired_mask_visual_pass_pending_watermark_and_full_split",
    SOURCE21_STATUS,
)


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


def build(prior_path: Path, visual_path: Path, canonical_path: Path) -> dict:
    prior, visual, canonical = map(load, (prior_path, visual_path, canonical_path))
    if (prior.get("schemaVersion") != 5 or not prior.get("ok") or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["sourceGroups"] != 8 or
            prior["counts"]["everyNailVisualPassNails"] != 25 or
            prior["counts"]["newTrainingApprovedSources"] != 0):
        raise ValueError("prior ledger contract mismatch")
    if (visual.get("decision") !=
            "source021_five_hybrid_masks_visual_pass_historical_correction_training_prohibited" or
            visual["sourceOrdinal"] != 21 or
            visual["counts"]["visualPassNails"] != 5 or
            visual["counts"]["newImageCount"] != 0 or
            visual["counts"]["newTrainingApprovedSources"] != 0 or
            visual["counts"]["legalPolygons"] != 5 or
            visual["counts"]["overlapPairs"] != 0 or
            visual["inputs"]["progressV5"]["sha256"] != sha(prior_path) or
            visual["historicalCanonicalIdentityAudit"]["sha256"] != sha(canonical_path) or
            canonical.get("decision") !=
            "historical_approved_truth_is_same_defective_cycle012_polygon" or
            canonical["newImageCount"] != 0 or
            canonical["newTrainingApprovedSources"] != 0 or
            canonical["inputs"]["progressV5"]["sha256"] != sha(prior_path)):
        raise ValueError("source21 correction/identity contract mismatch")
    # The source-specific auditors reconstruct and inspect their complete input graphs.
    for report in (prior, visual, canonical):
        for binding in report["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        if row["ordinal"] == 21:
            if (row["decision"] != "confirmed_label_rework" or
                    row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
                    row["sourceFileName"] != visual["sourceFileName"] or
                    row["sourceFileName"] != canonical["sourceFileName"] or
                    row["sourceGroup"] != visual["sourceGroup"] or
                    row["sourceGroup"] != canonical["sourceGroup"] or
                    row["sourceImage"] != visual["sourceImage"] or
                    row["sourceImage"] != canonical["inputs"]["sourceImage"] or
                    row["sourceLabel"] != canonical["inputs"]["cycle012Label"] or
                    "samCandidateV1Rejected" not in row or
                    "samCandidateV2Rejected" not in row):
                raise ValueError("source21 old row identity/rejection mismatch")
            current["decision"] = SOURCE21_STATUS
            current["reason"] = ("旧批准真值与cycle012缺陷标签逐顶点相同；"
                                 "4枚审过SAM多边形保留、1枚人工重画，5枚原分辨率终审通过；"
                                 "仅历史真值纠错候选，待全split及角色审核。")
            current["everyNailVisualApproval"] = True
            current["historicalCanonicalIdentityAudit"] = bind(canonical_path)
            current["repairVisualReport"] = bind(visual_path)
            current["repairedAnnotation"] = visual["candidateAnnotation"]
            current.pop("nextRepairMode", None)
        rows.append(current)
    if (len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20 or
            len({row["sourceFileName"] for row in rows}) != 20 or
            len({row["sourceGroup"] for row in rows}) != 8):
        raise ValueError("shard identities drifted")
    by_status = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in rows
                                               if row["decision"] == status)}
                 for status in STATUSES}
    if [by_status[status]["sourceImages"] for status in STATUSES] != [0, 8, 5, 2, 1, 1, 1, 1, 1]:
        raise ValueError("status counts drifted")
    visual_rows = [row for row in rows if row["everyNailVisualApproval"]]
    if (sum(value["oldLabelNails"] for value in by_status.values()) != 104 or
            len(visual_rows) != 5 or sum(row["oldLabelNails"] for row in visual_rows) != 30 or
            any(row["trainingUse"] != "prohibited" for row in rows)):
        raise ValueError("mask denominator or role drifted")
    return {
        "schemaVersion": 6, "ok": True,
        "decision": "shard002_source021_historical_truth_correction_visual_pass_no_train_approval",
        "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV5": bind(prior_path),
                   "source21RepairVisual": bind(visual_path),
                   "source21CanonicalIdentity": bind(canonical_path)},
        "sourceDispositions": rows,
        "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                   "byStatus": by_status, "everyNailVisualPassSources": 5,
                   "everyNailVisualPassNails": 30, "newTrainingApprovedSources": 0,
                   "newImageCountFromSource21": 0},
        "initialPendingEveryNailQueueClosed": True,
        "historicalSnapshotChanged": False, "fullShardCleanTruthComplete": False,
        "fullTrainSplitApproved": False, "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["priorProgressV5"]["path"]),
                        Path(inputs["source21RepairVisual"]["path"]),
                        Path(inputs["source21CanonicalIdentity"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.visual, args.canonical, args.output)):
        parser.error("--prior, --visual, --canonical and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.visual.resolve(), args.canonical.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
