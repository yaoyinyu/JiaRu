#!/usr/bin/env python3
"""Conserve shard002 after source30 occlusion quality exclusion."""

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


def build(prior_path: Path, occlusion_path: Path) -> dict:
    prior, occlusion = map(load, (prior_path, occlusion_path))
    if (prior["schemaVersion"] != 12 or not prior["ok"]
            or prior["counts"]["sourceImages"] != 20
            or prior["counts"]["oldLabelNails"] != 104
            or prior["counts"]["sourceGroups"] != 8
            or prior["counts"]["everyNailVisualPassSources"] != 8
            or prior["counts"]["everyNailVisualPassNails"] != 45
            or prior["counts"]["newTrainingApprovedSources"] != 0
            or occlusion["decision"] !=
            "source030_occluded_nail_surface_quality_exclude_next_train"
            or occlusion["manualBoundaryFeasible"]
            or occlusion["fullImageMaskVisualApproval"]
            or occlusion["newTrainingApprovedSources"] != 0
            or occlusion["trainingUse"] != "prohibited"
            or occlusion["inputs"]["priorProgressV12"]["sha256"] != sha(prior_path)):
        raise ValueError("v12/source30 occlusion contract mismatch")
    for report in (prior, occlusion):
        for item in report["inputs"].values():
            checked(item)
    for item in occlusion["evidenceImages"].values():
        checked(item)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        if row["ordinal"] == 30:
            if (row["decision"] != "confirmed_label_rework"
                    or row["oldLabelNails"] != 5
                    or row["everyNailVisualApproval"]
                    or row["sourceFileName"] != occlusion["sourceFileName"]
                    or row["sourceGroup"] != occlusion["sourceGroup"]
                    or row["sourceImage"] != occlusion["sourceImage"]
                    or row["sourceLabel"] != occlusion["oldLabel"]
                    or row["trainingUse"] != "prohibited"):
                raise ValueError("source30 frozen identity/role mismatch")
            current["decision"] = "confirmed_source_exclude"
            current["reason"] = (
                "第3枚立体花饰遮住近端甲面，原像素无法恢复被遮挡甲板边界；"
                "旧polygon与一次定向SAM均纳入装饰外缘，人工描边只能猜测不可见像素。"
                "按源图完整甲面质量门仅从下一版train候选排除本图及派生物；"
                "同组28/29已视觉通过，旧训练快照和历史失败不改。")
            current["sourceQualityDecisionAudit"] = bind(occlusion_path)
        rows.append(current)
    if (len(rows) != 20 or len({r["ordinal"] for r in rows}) != 20
            or len({r["sourceFileName"] for r in rows}) != 20
            or len({r["sourceGroup"] for r in rows}) != 8
            or sum(r["oldLabelNails"] for r in rows) != 104
            or any(r["trainingUse"] != "prohibited" for r in rows)):
        raise ValueError("shard identity/role conservation failed")
    statuses = prior["counts"]["byStatus"].keys()
    by_status = {status: {"sourceImages": sum(r["decision"] == status for r in rows),
                          "oldLabelNails": sum(r["oldLabelNails"] for r in rows
                                               if r["decision"] == status)}
                 for status in statuses}
    for status in statuses:
        old, new = prior["counts"]["byStatus"][status], by_status[status]
        shift = (1 if status == "confirmed_source_exclude" else
                 -1 if status == "confirmed_label_rework" else 0)
        if (new["sourceImages"] != old["sourceImages"] + shift
                or new["oldLabelNails"] != old["oldLabelNails"] + 5 * shift):
            raise ValueError("v13 category conservation failed")
    visual_rows = [r for r in rows if r["everyNailVisualApproval"]]
    if (len(visual_rows) != 8
            or sum(r["oldLabelNails"] for r in visual_rows) != 45
            or by_status["confirmed_label_rework"]["sourceImages"] != 0
            or by_status["confirmed_source_exclude"]["sourceImages"] != 7):
        raise ValueError("v13 queue/visual denominator mismatch")
    return {"schemaVersion": 13, "ok": True,
            "decision": "shard002_old_mask_rework_queue_closed_quality_and_watermark_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorProgressV12": bind(prior_path),
                       "source030OcclusionAudit": bind(occlusion_path)},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104,
                       "sourceGroups": 8, "byStatus": by_status,
                       "everyNailVisualPassSources": 8,
                       "everyNailVisualPassNails": 45,
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
    parser.add_argument("--occlusion", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for item in previous["inputs"].values():
            checked(item)
        current = build(Path(previous["inputs"]["priorProgressV12"]["path"]),
                        Path(previous["inputs"]["source030OcclusionAudit"]["path"]))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.occlusion, args.output)):
        parser.error("--prior, --occlusion and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.occlusion.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
