#!/usr/bin/env python3
"""Replay shard-002 source29 five-mask visual repair disposition."""

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


def build(prior_path: Path, visual_path: Path) -> dict:
    prior, visual = load(prior_path), load(visual_path)
    if (prior.get("schemaVersion") != 7 or not prior.get("ok") or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["sourceGroups"] != 8 or
            prior["counts"]["everyNailVisualPassSources"] != 5 or
            prior["counts"]["everyNailVisualPassNails"] != 30 or
            prior["counts"]["newTrainingApprovedSources"] != 0 or
            visual.get("decision") !=
            "source029_five_hybrid_masks_visual_pass_pending_full_split_training_prohibited" or
            visual["sourceOrdinal"] != 29 or
            visual["counts"]["visualPassNails"] != 5 or
            visual["counts"]["retainedReviewedPolygons"] != 3 or
            visual["counts"]["redrawnManualPolygons"] != 2 or
            visual["counts"]["legalPolygons"] != 5 or
            visual["counts"]["overlapPairs"] != 0 or
            visual["counts"]["newTrainingApprovedSources"] != 0 or
            visual["inputs"]["progressV7"]["sha256"] != sha(prior_path) or
            visual["historicalSnapshotChanged"] or
            visual["trainingUse"] != "prohibited"):
        raise ValueError("prior/source29 visual contract mismatch")
    for binding in visual["inputs"].values():
        checked(binding)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        if row["ordinal"] == 29:
            if (row["decision"] != "confirmed_label_rework" or
                    row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
                    row["sourceFileName"] != visual["sourceFileName"] or
                    row["sourceGroup"] != visual["sourceGroup"] or
                    row["sourceImage"] != visual["sourceImage"] or
                    row["trainingUse"] != "prohibited"):
                raise ValueError("source29 identity/status mismatch")
            current["decision"] = "repaired_mask_visual_pass_pending_full_split"
            current["reason"] = ("第1枚旧mask漏透明甲身、第5枚旧手工mask侵入指腹；"
                                 "两枚原像素手工重画，另外三枚逐甲复核后保留；"
                                 "五枚合法、零交叠、原分辨率视觉通过，仍待全split与角色门。")
            current["everyNailVisualApproval"] = True
            current["repairVisualReport"] = bind(visual_path)
            current["repairedAnnotation"] = visual["candidateAnnotation"]
        rows.append(current)
    if (len(rows) != 20 or len({r["ordinal"] for r in rows}) != 20 or
            len({r["sourceFileName"] for r in rows}) != 20 or
            len({r["sourceGroup"] for r in rows}) != 8):
        raise ValueError("shard identities drifted")
    by_status = {status: {"sourceImages": sum(r["decision"] == status for r in rows),
                          "oldLabelNails": sum(r["oldLabelNails"] for r in rows
                                               if r["decision"] == status)}
                 for status in STATUSES}
    if [by_status[s]["sourceImages"] for s in STATUSES] != [0, 6, 5, 2, 1, 1, 2, 1, 1, 1]:
        raise ValueError("status counts drifted")
    visual_rows = [r for r in rows if r["everyNailVisualApproval"]]
    if (sum(s["oldLabelNails"] for s in by_status.values()) != 104 or
            len(visual_rows) != 6 or sum(r["oldLabelNails"] for r in visual_rows) != 35 or
            any(r["trainingUse"] != "prohibited" for r in rows)):
        raise ValueError("denominator/role drifted")
    return {
        "schemaVersion": 8, "ok": True,
        "decision": "shard002_source029_five_masks_visual_pass_no_train_approval",
        "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV7": bind(prior_path),
                   "source29RepairVisual": bind(visual_path)},
        "sourceDispositions": rows,
        "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                   "byStatus": by_status, "everyNailVisualPassSources": 6,
                   "everyNailVisualPassNails": 35, "newTrainingApprovedSources": 0,
                   "nextTrainCandidateWatermarkIsolatedSources": 1},
        "initialPendingEveryNailQueueClosed": True,
        "historicalSnapshotChanged": False, "fullShardCleanTruthComplete": False,
        "fullTrainSplitApproved": False, "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        current = build(Path(old["inputs"]["priorProgressV7"]["path"]),
                        Path(old["inputs"]["source29RepairVisual"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.visual, args.output)):
        parser.error("--prior, --visual and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.visual.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
