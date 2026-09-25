#!/usr/bin/env python3
"""Replay shard-002 source24 isolation while preserving the original split."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ISOLATED = "watermark_source_isolated_from_next_train_candidate"
STATUSES = (
    "pending_every_nail_review", "confirmed_label_rework",
    "confirmed_source_exclude", "watermark_review_required",
    "mask_visual_pass_pending_watermark_and_full_split",
    "mask_visual_pass_pending_full_split",
    "repaired_mask_visual_pass_pending_full_split",
    "repaired_mask_visual_pass_pending_watermark_and_full_split",
    "historical_truth_correction_visual_pass_pending_full_split", ISOLATED,
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
    if (prior.get("schemaVersion") != 6 or not prior.get("ok") or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["sourceGroups"] != 8 or
            prior["counts"]["everyNailVisualPassSources"] != 5 or
            prior["counts"]["everyNailVisualPassNails"] != 30 or
            prior["counts"]["newTrainingApprovedSources"] != 0 or
            isolation.get("decision") !=
            "source024_isolate_from_next_train_candidate_unproven_corner_logo_shortcut" or
            isolation["sourceOrdinal"] != 24 or
            isolation["sameGroupReviewedPeerOrdinal"] != 21 or
            isolation["watermark"]["shortcutAbsenceProven"] or
            isolation["watermark"]["overlapsCandidateNailMasks"] or
            isolation["newTrainingApprovedSources"] != 0 or
            isolation["historicalSnapshotChanged"] or
            isolation["inputs"]["progressV6"]["sha256"] != sha(prior_path)):
        raise ValueError("prior/isolation contract mismatch")
    for binding in isolation["inputs"].values():
        checked(binding)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        if row["ordinal"] == 24:
            if (row["decision"] != "confirmed_label_rework" or
                    row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
                    row["sourceFileName"] != isolation["sourceFileName"] or
                    row["sourceGroup"] != isolation["sourceGroup"] or
                    row["sourceImage"] != isolation["inputs"]["frozenSourceImage"] or
                    row["trainingUse"] != "prohibited"):
                raise ValueError("source24 identity/status mismatch")
            current["decision"] = ISOLATED
            current["reason"] = ("旧第5枚mask只覆盖装饰；历史手工候选仍漏透明甲身。"
                                 "新混合候选几何合法但未完成完整甲面视觉晋级；"
                                 "右下可见来源标记的捷径排除尚未证明，"
                                 "同来源组序号21已有视觉通过的纠错候选，"
                                 "故从下一版train候选隔离本图及派生物。")
            current["watermarkIsolationAudit"] = bind(isolation_path)
            current["hybridCandidateNotPromoted"] = isolation["inputs"]["hybridCandidate"]
            current["watermarkReviewRequired"] = True
        rows.append(current)
    if (len(rows) != 20 or len({r["ordinal"] for r in rows}) != 20 or
            len({r["sourceFileName"] for r in rows}) != 20 or
            len({r["sourceGroup"] for r in rows}) != 8):
        raise ValueError("shard identities drifted")
    by_status = {status: {"sourceImages": sum(r["decision"] == status for r in rows),
                          "oldLabelNails": sum(r["oldLabelNails"] for r in rows
                                               if r["decision"] == status)}
                 for status in STATUSES}
    if [by_status[s]["sourceImages"] for s in STATUSES] != [0, 7, 5, 2, 1, 1, 1, 1, 1, 1]:
        raise ValueError("status counts drifted")
    visual_rows = [r for r in rows if r["everyNailVisualApproval"]]
    if (sum(s["oldLabelNails"] for s in by_status.values()) != 104 or
            len(visual_rows) != 5 or sum(r["oldLabelNails"] for r in visual_rows) != 30 or
            any(r["trainingUse"] != "prohibited" for r in rows)):
        raise ValueError("denominator/training role drifted")
    return {
        "schemaVersion": 7, "ok": True,
        "decision": "shard002_source024_isolated_unproven_watermark_no_train_approval",
        "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV6": bind(prior_path),
                   "source24IsolationAudit": bind(isolation_path)},
        "sourceDispositions": rows,
        "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                   "byStatus": by_status, "everyNailVisualPassSources": 5,
                   "everyNailVisualPassNails": 30, "newTrainingApprovedSources": 0,
                   "nextTrainCandidateWatermarkIsolatedSources": 1},
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
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        current = build(Path(old["inputs"]["priorProgressV6"]["path"]),
                        Path(old["inputs"]["source24IsolationAudit"]["path"]))
        if current != old:
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
