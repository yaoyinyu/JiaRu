#!/usr/bin/env python3
"""Conserve shard002 identities after source25 isolation and source27 repair."""

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


def build(prior_path: Path, visual_path: Path, watermark_path: Path) -> dict:
    prior, visual, watermark = map(load, (prior_path, visual_path, watermark_path))
    if (prior["schemaVersion"] != 10 or not prior["ok"] or
            prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["sourceGroups"] != 8 or
            prior["counts"]["everyNailVisualPassSources"] != 7 or
            prior["counts"]["everyNailVisualPassNails"] != 40 or
            prior["counts"]["newTrainingApprovedSources"] != 0 or
            visual["decision"] !=
            "source025_isolated_source027_five_masks_visual_pass_watermark_and_split_hold" or
            visual["source25"]["sourceOrdinal"] != 25 or
            visual["source25"]["maskVisualApproval"] or
            visual["source25"]["decision"] !=
            "watermark_source_isolated_from_next_train_candidate" or
            visual["source27"]["sourceOrdinal"] != 27 or
            visual["source27"]["visualPassNails"] != 5 or
            visual["source27"]["decision"] !=
            "repaired_mask_visual_pass_pending_watermark_and_full_split" or
            visual["newTrainingApprovedSources"] != 0 or
            watermark["decision"] !=
            "source027_logo_variants_visual_usable_model_ablation_and_split_hold" or
            watermark["sourceOrdinal"] != 27 or
            watermark["visualVariantCount"] != 4 or
            watermark["nailPixelsChanged"] != 0 or
            watermark["shortcutAbsenceProven"] or
            watermark["newTrainingApprovedSources"] != 0):
        raise ValueError("v10/source25/27 visual or watermark contract mismatch")
    for report in (visual, watermark):
        for binding in report["inputs"].values():
            checked(binding)
    if watermark["inputs"]["maskVisualAudit"]["sha256"] != sha(visual_path):
        raise ValueError("source27 watermark evidence not bound to mask audit")
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        ordinal = row["ordinal"]
        if ordinal in (25, 27):
            target = visual[f"source{ordinal}"]
            if (row["decision"] != "confirmed_label_rework" or
                    row["oldLabelNails"] != 5 or
                    row["everyNailVisualApproval"] or
                    row["sourceFileName"] != target["sourceFileName"] or
                    row["sourceGroup"] != target["sourceGroup"] or
                    row["sourceImage"] != target["sourceImage"] or
                    row["sourceLabel"] != target["oldLabel"] or
                    row["trainingUse"] != "prohibited"):
                raise ValueError(f"source {ordinal} v10 identity/quality mismatch")
            current["decision"] = target["decision"]
            current["visualDecisionAudit"] = bind(visual_path)
            current["watermarkShortcutAbsenceProven"] = False
            if ordinal == 25:
                current["reason"] = (
                    "旧第5枚透明近端无法可靠分界，一次定向SAM与旧缺陷polygon高度同构；"
                    "同组另有4张mask视觉通过图，来源标记捷径未证明，"
                    "仅从下一版train候选隔离本图及派生物，旧历史保持。")
                current["sameGroupVisualPassOrdinals"] = target["sameGroupVisualPassOrdinals"]
            else:
                current["reason"] = (
                    "原像素终审保留3枚完整旧polygon并以定向SAM补全第1枚绿色甲尖、"
                    "第5枚透明甲身；5甲合法零交叠。四水印变体视觉可用且甲面像素不变，"
                    "未来模型无捷径证明及全split训练门仍缺。")
                current["everyNailVisualApproval"] = True
                current["repairedAnnotation"] = target["hybridAnnotation"]
                current["watermarkVariantVisualAudit"] = bind(watermark_path)
                current["watermarkReviewRequired"] = True
        rows.append(current)
    if (len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20 or
            len({row["sourceFileName"] for row in rows}) != 20 or
            len({row["sourceGroup"] for row in rows}) != 8):
        raise ValueError("shard002 identity/group count drift")
    by_status = {status: {"sourceImages": sum(r["decision"] == status for r in rows),
                          "oldLabelNails": sum(r["oldLabelNails"] for r in rows
                                               if r["decision"] == status)}
                 for status in STATUSES}
    if ([by_status[status]["sourceImages"] for status in STATUSES] !=
            [0, 2, 5, 2, 1, 1, 2, 3, 1, 3]):
        raise ValueError("v11 category conservation failed")
    visual_rows = [row for row in rows if row["everyNailVisualApproval"]]
    if (sum(item["oldLabelNails"] for item in by_status.values()) != 104 or
            len(visual_rows) != 8 or
            sum(row["oldLabelNails"] for row in visual_rows) != 45 or
            any(row["trainingUse"] != "prohibited" for row in rows)):
        raise ValueError("v11 denominator/role drift")
    return {"schemaVersion": 11, "ok": True,
            "decision": "shard002_source025_isolated_source027_visual_pass_watermark_split_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorProgressV10": bind(prior_path),
                       "source025027VisualAudit": bind(visual_path),
                       "source027WatermarkVisualAudit": bind(watermark_path)},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104,
                       "sourceGroups": 8, "byStatus": by_status,
                       "everyNailVisualPassSources": 8,
                       "everyNailVisualPassNails": 45,
                       "newTrainingApprovedSources": 0,
                       "nextTrainCandidateWatermarkIsolatedSources": 3},
            "initialPendingEveryNailQueueClosed": True,
            "historicalSnapshotChanged": False,
            "fullShardCleanTruthComplete": False,
            "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--watermark", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        inputs = previous["inputs"]
        current = build(Path(inputs["priorProgressV10"]["path"]),
                        Path(inputs["source025027VisualAudit"]["path"]),
                        Path(inputs["source027WatermarkVisualAudit"]["path"]))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.visual, args.watermark, args.output)):
        parser.error("--prior, --visual, --watermark and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.visual.resolve(),
                   args.watermark.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
