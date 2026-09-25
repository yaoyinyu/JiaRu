#!/usr/bin/env python3
"""Conserve shard002 after source37/39 full-nail visual review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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


def build(prior_path: Path, visual_path: Path) -> dict:
    prior, visual = map(load, (prior_path, visual_path))
    if (prior["schemaVersion"] != 13 or not prior["ok"]
            or prior["counts"]["sourceImages"] != 20
            or prior["counts"]["oldLabelNails"] != 104
            or prior["counts"]["sourceGroups"] != 8
            or prior["counts"]["everyNailVisualPassSources"] != 8
            or prior["counts"]["everyNailVisualPassNails"] != 45
            or prior["counts"]["newTrainingApprovedSources"] != 0
            or not prior["oldMaskReworkQueueClosed"]
            or visual["decision"] !=
            "source037039_ten_masks_visual_pass_watermark_and_split_hold"
            or visual["inputs"]["priorProgressV13"]["sha256"] != sha(prior_path)
            or [item["sourceOrdinal"] for item in visual["sources"]] != [37, 39]
            or visual["visualPassNails"] != 10
            or visual["newTrainingApprovedSources"] != 0
            or visual["historicalSnapshotChanged"]):
        raise ValueError("v13/source37/39 visual contract mismatch")
    for report in (prior, visual):
        for item in report["inputs"].values():
            checked(item)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        ordinal = row["ordinal"]
        if ordinal in (37, 39):
            target = next(item for item in visual["sources"]
                          if item["sourceOrdinal"] == ordinal)
            if (row["decision"] != "watermark_review_required"
                    or row["oldLabelNails"] != 5
                    or row["everyNailVisualApproval"]
                    or row["sourceFileName"] != target["sourceFileName"]
                    or row["sourceGroup"] != target["sourceGroup"]
                    or row["sourceImage"] != target["sourceImage"]
                    or row["sourceLabel"] != target["oldLabel"]
                    or row["trainingUse"] != "prohibited"
                    or not target["maskVisualApproval"]
                    or target["visualPassNails"] != 5
                    or target["watermarkAblationComplete"]
                    or target["watermarkShortcutAbsenceProven"]
                    or target["trainingUse"] != "prohibited"):
                raise ValueError(f"source {ordinal} frozen identity/role mismatch")
            for mark in target["markInstances"]:
                if mark["candidateMaskOverlapPairs"] != 0:
                    raise ValueError(f"source {ordinal} watermark overlap drift")
            checked(target["hybridAnnotation"])
            current["decision"] = target["decision"]
            current["everyNailVisualApproval"] = True
            current["repairedAnnotation"] = target["hybridAnnotation"]
            current["visualDecisionAudit"] = bind(visual_path)
            current["watermarkRegistrationAudit"] = bind(visual_path)
            current["watermarkReviewRequired"] = True
            current["watermarkShortcutAbsenceProven"] = False
            current["reason"] = (
                "原分辨率五甲视觉通过：37第4/5枚SAM修去旧mask皮肤尖刺，"
                "其余三枚保留原像素复核完整旧polygon；袖口五处重复文字与角落标记"
                "均不入mask，但变体/下一模型无捷径证明欠缺。"
                if ordinal == 37 else
                "原分辨率五甲视觉通过：39第4枚SAM从指腹收回甲面，"
                "其余四枚保留原像素复核完整旧polygon；右侧作者文字图标不入mask，"
                "但变体/下一模型无捷径证明欠缺。")
        rows.append(current)
    if (len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20
            or len({row["sourceFileName"] for row in rows}) != 20
            or len({row["sourceGroup"] for row in rows}) != 8
            or sum(row["oldLabelNails"] for row in rows) != 104
            or any(row["trainingUse"] != "prohibited" for row in rows)):
        raise ValueError("shard identity/role conservation failed")
    statuses = prior["counts"]["byStatus"].keys()
    by_status = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in rows
                                               if row["decision"] == status)}
                 for status in statuses}
    for status in statuses:
        old, new = prior["counts"]["byStatus"][status], by_status[status]
        shift = (-2 if status == "watermark_review_required" else
                 2 if status == "repaired_mask_visual_pass_pending_watermark_and_full_split"
                 else 0)
        if (new["sourceImages"] != old["sourceImages"] + shift
                or new["oldLabelNails"] != old["oldLabelNails"] + 5 * shift):
            raise ValueError("v14 category conservation failed")
    visual_rows = [row for row in rows if row["everyNailVisualApproval"]]
    if (len(visual_rows) != 10
            or sum(row["oldLabelNails"] for row in visual_rows) != 55
            or by_status["watermark_review_required"]["sourceImages"] != 0
            or by_status["confirmed_label_rework"]["sourceImages"] != 0):
        raise ValueError("v14 visual/rework denominator mismatch")
    return {"schemaVersion": 14, "ok": True,
            "decision": "shard002_all_positive_masks_visually_dispositioned_watermark_and_split_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorProgressV13": bind(prior_path),
                       "source037039VisualAudit": bind(visual_path)},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104,
                       "sourceGroups": 8, "byStatus": by_status,
                       "everyNailVisualPassSources": 10,
                       "everyNailVisualPassNails": 55,
                       "newTrainingApprovedSources": 0,
                       "nextTrainCandidateWatermarkIsolatedSources": 3},
            "initialPendingEveryNailQueueClosed": True,
            "oldMaskReworkQueueClosed": True,
            "historicalSnapshotChanged": False,
            "fullShardCleanTruthComplete": False,
            "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for item in previous["inputs"].values():
            checked(item)
        current = build(Path(previous["inputs"]["priorProgressV13"]["path"]),
                        Path(previous["inputs"]["source037039VisualAudit"]["path"]))
        if current != previous:
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
