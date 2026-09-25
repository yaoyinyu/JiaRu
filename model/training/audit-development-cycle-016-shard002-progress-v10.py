#!/usr/bin/env python3
"""Replay source32 repaired-mask visual approval without train promotion."""

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


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(prior_path: Path, visual_path: Path, model_path: Path) -> dict:
    prior, visual, model = map(load, (prior_path, visual_path, model_path))
    if (prior.get("schemaVersion") != 9 or not prior.get("ok") or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["sourceGroups"] != 8 or
            prior["counts"]["everyNailVisualPassSources"] != 6 or
            prior["counts"]["everyNailVisualPassNails"] != 35 or
            prior["counts"]["newTrainingApprovedSources"] != 0 or
            visual["decision"] !=
            "source032_repaired_five_masks_visual_pass_watermark_and_full_split_pending" or
            visual["sourceOrdinal"] != 32 or
            visual["counts"]["visualPassNails"] != 5 or
            visual["counts"]["newTrainingApprovedSources"] != 0 or
            visual["watermarkShortcutAbsenceProven"] or
            visual["fullTrainSplitApproved"] or
            visual["trainingUse"] != "prohibited" or
            model["decision"] !=
            "source032_frozen_development_weight_watermark_probe_diagnostic_only" or
            model["variantPredictions"]["original"]["instanceCount"] != 6 or
            model["independentWatermarkShortcutExclusionProven"] or
            model["trainingUse"] != "prohibited"):
        raise ValueError("prior/source32 visual and watermark contract mismatch")
    for report in (visual, model):
        for item in report["inputs"].values():
            if isinstance(item, list):
                for binding in item:
                    checked(binding)
            else:
                checked(item)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        if row["ordinal"] == 32:
            if (row["decision"] != "confirmed_label_rework" or
                    row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
                    row["sourceFileName"] != visual["sourceFileName"] or
                    row["sourceGroup"] != visual["sourceGroup"] or
                    row["sourceImage"] != visual["inputs"]["sourceImage"] or
                    row["sourceLabel"] != visual["inputs"]["oldLabel"] or
                    row["trainingUse"] != "prohibited"):
                raise ValueError("source32 prior identity/quality mismatch")
            current["decision"] = "repaired_mask_visual_pass_pending_watermark_and_full_split"
            current["reason"] = (
                "旧canonical与缺陷cycle012标签同构；旧mask与SAM首版均侵入皮肤。"
                "定向SAM后四枚人工polygon与一枚保留SAM逐甲原分辨率视觉通过，"
                "五甲合法且零交叠；右下来源标记旧权重单图诊断近乎不变，但"
                "未来模型无捷径证明和全split训练门未完成。")
            current["everyNailVisualApproval"] = True
            current["repairedVisualAudit"] = bind(visual_path)
            current["watermarkModelProbe"] = bind(model_path)
            current["watermarkShortcutAbsenceProven"] = False
        rows.append(current)
    if (len(rows) != 20 or len({r["ordinal"] for r in rows}) != 20 or
            len({r["sourceFileName"] for r in rows}) != 20 or
            len({r["sourceGroup"] for r in rows}) != 8):
        raise ValueError("frozen shard identities drifted")
    by_status = {status: {"sourceImages": sum(r["decision"] == status for r in rows),
                          "oldLabelNails": sum(r["oldLabelNails"] for r in rows
                                               if r["decision"] == status)}
                 for status in STATUSES}
    if [by_status[s]["sourceImages"] for s in STATUSES] != [0, 4, 5, 2, 1, 1, 2, 2, 1, 2]:
        raise ValueError("source32 status count drift")
    visual_rows = [row for row in rows if row["everyNailVisualApproval"]]
    if (sum(item["oldLabelNails"] for item in by_status.values()) != 104 or
            len(visual_rows) != 7 or
            sum(row["oldLabelNails"] for row in visual_rows) != 40 or
            any(row["trainingUse"] != "prohibited" for row in rows)):
        raise ValueError("source32 denominator/role drift")
    return {"schemaVersion": 10, "ok": True,
            "decision": "shard002_source032_mask_repair_visual_pass_watermark_and_split_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorProgressV9": bind(prior_path),
                       "source32VisualAudit": bind(visual_path),
                       "source32OldWeightProbe": bind(model_path)},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104,
                       "sourceGroups": 8, "byStatus": by_status,
                       "everyNailVisualPassSources": 7,
                       "everyNailVisualPassNails": 40,
                       "newTrainingApprovedSources": 0,
                       "nextTrainCandidateWatermarkIsolatedSources": 2},
            "initialPendingEveryNailQueueClosed": True,
            "historicalSnapshotChanged": False,
            "fullShardCleanTruthComplete": False,
            "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--model-probe", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            checked(item)
        inputs = prior["inputs"]
        current = build(Path(inputs["priorProgressV9"]["path"]),
                        Path(inputs["source32VisualAudit"]["path"]),
                        Path(inputs["source32OldWeightProbe"]["path"]))
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.visual, args.model_probe, args.output)):
        parser.error("--prior, --visual, --model-probe and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.visual.resolve(),
                   args.model_probe.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
