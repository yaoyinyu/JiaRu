#!/usr/bin/env python3
"""Replay shard-002 source33 logo-risk isolation without revising old snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


STATUSES = (
    "pending_every_nail_review", "confirmed_label_rework",
    "confirmed_source_exclude", "watermark_review_required",
    "mask_visual_pass_pending_watermark_and_full_split",
    "mask_visual_pass_pending_full_split",
    "repaired_mask_visual_pass_pending_full_split",
    "repaired_mask_visual_pass_pending_watermark_and_full_split",
    "historical_truth_correction_visual_pass_pending_full_split",
    "watermark_source_isolated_from_next_train_candidate",
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


def build(prior_path: Path, isolation_path: Path) -> dict:
    prior, isolation = load(prior_path), load(isolation_path)
    if (prior.get("schemaVersion") != 8 or not prior.get("ok") or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["sourceGroups"] != 8 or
            prior["counts"]["everyNailVisualPassSources"] != 6 or
            prior["counts"]["everyNailVisualPassNails"] != 35 or
            prior["counts"]["newTrainingApprovedSources"] != 0 or
            isolation.get("decision") !=
            "source033_isolate_from_next_train_candidate_defective_old_masks_unproven_logo_shortcut" or
            isolation["sourceOrdinal"] != 33 or
            isolation["counts"]["polygons"] != 5 or
            isolation["counts"]["newTrainingApprovedSources"] != 0 or
            isolation["inputs"]["progressV8"]["sha256"] != sha(prior_path) or
            isolation["nextTrainCandidateDisposition"] != "isolate_source_and_all_derivatives" or
            isolation["historicalSnapshotChanged"] or
            isolation["watermark"]["fourVariantAblationComplete"] or
            isolation["watermark"]["shortcutAbsenceProven"] or
            isolation["trainingUse"] != "prohibited"):
        raise ValueError("prior/source33 isolation contract mismatch")
    for binding in isolation["inputs"].values():
        checked(binding)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        if row["ordinal"] == 33:
            if (row["decision"] != "confirmed_label_rework" or
                    row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
                    row["sourceFileName"] != isolation["sourceFileName"] or
                    row["sourceGroup"] != isolation["sourceGroup"] or
                    row["sourceImage"] != isolation["inputs"]["sourceImage"] or
                    row["sourceLabel"] != isolation["inputs"]["cycle012Label"] or
                    row["trainingUse"] != "prohibited"):
                raise ValueError("source33 identity/status mismatch")
            current["decision"] = "watermark_source_isolated_from_next_train_candidate"
            current["reason"] = ("历史候选报告虽曾标记五甲待物化批准，逐顶点复算证实其与"
                                 "当前缺陷cycle012标签同构；旧甲根锯齿/侵皮肤。右下小红书"
                                 "标记未完成四变体消融，故本图及派生物从下一版train候选隔离。")
            current["isolationAudit"] = bind(isolation_path)
            current["nextTrainCandidateDisposition"] = "isolate_source_and_all_derivatives"
        rows.append(current)
    if (len(rows) != 20 or len({r["ordinal"] for r in rows}) != 20 or
            len({r["sourceFileName"] for r in rows}) != 20 or
            len({r["sourceGroup"] for r in rows}) != 8):
        raise ValueError("shard identities drifted")
    by_status = {status: {"sourceImages": sum(r["decision"] == status for r in rows),
                          "oldLabelNails": sum(r["oldLabelNails"] for r in rows
                                               if r["decision"] == status)}
                 for status in STATUSES}
    if [by_status[s]["sourceImages"] for s in STATUSES] != [0, 5, 5, 2, 1, 1, 2, 1, 1, 2]:
        raise ValueError("status counts drifted")
    visual_rows = [r for r in rows if r["everyNailVisualApproval"]]
    if (sum(s["oldLabelNails"] for s in by_status.values()) != 104 or
            len(visual_rows) != 6 or sum(r["oldLabelNails"] for r in visual_rows) != 35 or
            any(r["trainingUse"] != "prohibited" for r in rows)):
        raise ValueError("denominator/role drifted")
    return {
        "schemaVersion": 9, "ok": True,
        "decision": "shard002_source033_logo_risk_isolated_no_train_approval",
        "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV8": bind(prior_path),
                   "source33Isolation": bind(isolation_path)},
        "sourceDispositions": rows,
        "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                   "byStatus": by_status, "everyNailVisualPassSources": 6,
                   "everyNailVisualPassNails": 35, "newTrainingApprovedSources": 0,
                   "nextTrainCandidateWatermarkIsolatedSources": 2},
        "initialPendingEveryNailQueueClosed": True,
        "historicalSnapshotChanged": False, "fullShardCleanTruthComplete": False,
        "fullTrainSplitApproved": False, "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--isolation", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        current = build(Path(previous["inputs"]["priorProgressV8"]["path"]),
                        Path(previous["inputs"]["source33Isolation"]["path"]))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.isolation, args.output)):
        parser.error("--prior, --isolation and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.isolation.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
