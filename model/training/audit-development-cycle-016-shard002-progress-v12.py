#!/usr/bin/env python3
"""Conserve shard002 identities after source30/40 original-resolution review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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
    prior, visual = map(load, (prior_path, visual_path))
    if (prior["schemaVersion"] != 11 or not prior["ok"]
            or prior["counts"]["sourceImages"] != 20
            or prior["counts"]["oldLabelNails"] != 104
            or prior["counts"]["sourceGroups"] != 8
            or prior["counts"]["everyNailVisualPassSources"] != 8
            or prior["counts"]["everyNailVisualPassNails"] != 45
            or prior["counts"]["newTrainingApprovedSources"] != 0
            or visual["decision"] != "source030_rework_source040_quality_exclude"
            or visual["geometryPassCandidates"] != 4
            or visual["fullImageVisualApprovedSources"] != 0
            or visual["newTrainingApprovedSources"] != 0
            or visual["historicalSnapshotChanged"]):
        raise ValueError("v11/visual contract mismatch")
    for report in (prior, visual):
        for binding in report["inputs"].values():
            checked(binding)
    rows = []
    for row in prior["sourceDispositions"]:
        current = dict(row)
        ordinal = row["ordinal"]
        if ordinal in (30, 40):
            target = visual[f"source{ordinal}"]
            if (row["decision"] != "confirmed_label_rework"
                    or row["oldLabelNails"] != 5
                    or row["everyNailVisualApproval"]
                    or row["sourceFileName"] != target["sourceFileName"]
                    or row["sourceGroup"] != target["sourceGroup"]
                    or row["sourceImage"] != target["sourceImage"]
                    or row["sourceLabel"] != target["oldLabel"]
                    or row["trainingUse"] != "prohibited"):
                raise ValueError(f"source {ordinal} v11 identity/role mismatch")
            current["decision"] = target["decision"]
            current["visualDecisionAudit"] = bind(visual_path)
            current["reason"] = (
                "原像素显示第3枚立体花饰遮住甲面；一次SAM虽通过提示几何，第3枚仍把装饰并入边界；"
                "第5枚透明甲尖候选只作局部返修参考。整图不批准，后续人工定界或源图排除。"
                if ordinal == 30 else
                "第5枚低对比透明甲近端与指腹不可可靠分界；旧mask与一次SAM候选均侵入皮肤。"
                "按源图质量门仅从下一版train候选排除本图及派生物，旧训练快照不改。")
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
        old = prior["counts"]["byStatus"][status]
        new = by_status[status]
        shift = 1 if status == "confirmed_source_exclude" else (
            -1 if status == "confirmed_label_rework" else 0)
        if (new["sourceImages"] != old["sourceImages"] + shift
                or new["oldLabelNails"] != old["oldLabelNails"] + shift * 5):
            raise ValueError("v12 category conservation failed")
    visual_rows = [r for r in rows if r["everyNailVisualApproval"]]
    if len(visual_rows) != 8 or sum(r["oldLabelNails"] for r in visual_rows) != 45:
        raise ValueError("visual denominator drift")
    return {"schemaVersion": 12, "ok": True,
            "decision": "shard002_source040_quality_exclude_source030_rework_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorProgressV11": bind(prior_path),
                       "source030040VisualAudit": bind(visual_path)},
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        current = build(Path(previous["inputs"]["priorProgressV11"]["path"]),
                        Path(previous["inputs"]["source030040VisualAudit"]["path"]))
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
