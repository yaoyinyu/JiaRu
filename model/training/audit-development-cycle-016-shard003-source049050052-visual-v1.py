#!/usr/bin/env python3
"""Bind original-pixel visual decisions for shard-003 sources 49/50/52."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


DECISIONS = {
    49: ("mask_rework", [
        "旧轮廓基本覆盖横向甲面；仍须核验近端侧缘",
        "旧轮廓基本覆盖长甲；仍须核验透明边缘",
        "甲根左上旧轮廓侵入指腹，不能按旧mask批准",
        "左侧近端旧轮廓含大片皮肤，右端也越出甲尖",
        "近端旧轮廓含大片皮肤，须重绘完整甲面",
    ]),
    50: ("source_quality_excluded", [
        "短拇指旧轮廓上缘含皮肤尖刺，单独可返修",
        "旧轮廓覆盖可见甲面，饰物附近须复核",
        "旧轮廓覆盖可见甲面，透明边缘须复核",
        "旧轮廓覆盖可见甲面，饰物附近须复核",
        "白色作者水印直接覆盖透明甲尖，底层纹理与尖端轮廓不可由原像素确认",
    ]),
    52: ("source_quality_excluded", [
        "旧轮廓可供诊断，未批准",
        "旧轮廓可供诊断，未批准",
        "旧轮廓可供诊断，未批准",
        "白色蕾丝遮挡并透过甲尖，与旧轮廓重叠，完整甲面纹理边界不可确认",
    ]),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"binding drift: {path}")
    return path


def load_builder():
    path = Path(__file__).with_name("build-development-cycle-016-shard003-source049050052-native.py")
    spec = importlib.util.spec_from_file_location("native049050052", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(native_path: Path, prior_path: Path) -> tuple[dict, dict]:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    if not load_builder().verify(native_path)["ok"]:
        raise ValueError("native crop replay failed")
    if (prior["decision"] != "shard003_progress_v7_reconciled_training_still_prohibited"
            or prior["counts"]["sourceImages"] != 20
            or prior["counts"]["oldLabelNails"] != 105
            or prior["counts"]["sourceGroups"] != 10):
        raise ValueError("prior denominator drift")
    for item in prior["inputs"].values():
        checked(item)
    visual_rows = []
    for source in native["sources"]:
        ordinal = source["ordinal"]
        decision, notes = DECISIONS[ordinal]
        previous = prior["sources"][ordinal - 41]
        if (previous["currentDecision"] != "pending_every_nail_review"
                or previous["sourceImage"] != source["sourceImage"]
                or previous["sourceGroup"] != source["sourceGroup"]
                or len(notes) != previous["oldLabelNails"]):
            raise ValueError(f"identity or count drift: {ordinal}")
        visual_rows.append({
            "ordinal": ordinal,
            "sourceImage": source["sourceImage"],
            "sourceGroup": source["sourceGroup"],
            "historicalCanonicalCount": len(source["historicalCanonicalTruths"]),
            "currentDecision": decision,
            "nails": [{"truthIndex": nail["truthIndex"], "raw3x": nail["raw3x"],
                       "oldOutline3x": nail["oldOutline3x"], "finding": note}
                      for nail, note in zip(source["nails"], notes, strict=True)],
            "trainingUse": "prohibited",
        })
    visual = {
        "schemaVersion": 1, "ok": True,
        "decision": "source049_mask_rework_source050052_quality_excluded_next_train",
        "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                   "priorProgress": bind(prior_path)},
        "counts": {"sourceImages": 3, "oldLabelNails": 14,
                   "maskReworkImages": 1, "sourceQualityExcludedImages": 2,
                   "newTrainingApproved": 0},
        "sources": visual_rows,
        "historicalSnapshotChanged": False, "protectedRolesChanged": False,
        "trainingUse": "prohibited",
    }
    return visual, prior


def ledger(prior: dict, visual: dict, visual_path: Path) -> dict:
    decisions = {row["ordinal"]: row for row in visual["sources"]}
    rows = []
    for old in prior["sources"]:
        row = dict(old)
        if row["ordinal"] in decisions:
            row["currentDecision"] = decisions[row["ordinal"]]["currentDecision"]
            row["visualEvidence"] = bind(visual_path)
        rows.append(row)
    counts = {}
    for status in ("source_quality_excluded", "mask_visual_pass_role_pending",
                   "mask_rework", "pending_every_nail_review"):
        selected = [row for row in rows if row["currentDecision"] == status]
        counts[status] = {"sourceImages": len(selected),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in selected)}
    expected = {"source_quality_excluded": (11, 60),
                "mask_visual_pass_role_pending": (4, 20),
                "mask_rework": (1, 5), "pending_every_nail_review": (4, 20)}
    if (any((counts[key]["sourceImages"], counts[key]["oldLabelNails"]) != value
            for key, value in expected.items())
            or [row["ordinal"] for row in rows] != list(range(41, 61))
            or len({row["sourceGroup"] for row in rows}) != 10
            or any(row["trainingUse"] != "prohibited" for row in rows)):
        raise ValueError("shard reconciliation mismatch")
    return {"schemaVersion": 1, "ok": True,
            "decision": "shard003_progress_v8_reconciled_training_still_prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorProgress": visual["inputs"]["priorProgress"],
                       "source049050052Visual": bind(visual_path)},
            "counts": {"sourceImages": 20, "oldLabelNails": 105,
                       "sourceGroups": 10, "statusCounts": counts,
                       "newTrainingApprovedSources": 0},
            "sources": rows, "historicalSnapshotChanged": False,
            "protectedRolesChanged": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--prior-progress", type=Path)
    parser.add_argument("--visual-report", type=Path)
    parser.add_argument("--ledger-report", type=Path)
    parser.add_argument("--verify-ledger", type=Path)
    args = parser.parse_args()
    if args.verify_ledger:
        saved = json.loads(args.verify_ledger.read_text(encoding="utf-8"))
        for binding in saved["inputs"].values():
            checked(binding)
        visual_path = Path(saved["inputs"]["source049050052Visual"]["path"])
        visual_saved = json.loads(visual_path.read_text(encoding="utf-8"))
        for binding in visual_saved["inputs"].values():
            checked(binding)
        visual_new, prior = build(Path(visual_saved["inputs"]["nativeReview"]["path"]),
                                  Path(visual_saved["inputs"]["priorProgress"]["path"]))
        if visual_new != visual_saved or ledger(prior, visual_saved, visual_path) != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_shard003_progress_v8",
                  "counts": saved["counts"]}
    else:
        if not all((args.native_review, args.prior_progress, args.visual_report,
                    args.ledger_report)):
            parser.error("native, prior, visual and ledger paths required")
        for path in (args.visual_report, args.ledger_report):
            if path.exists():
                raise FileExistsError(path)
        visual, prior = build(args.native_review.resolve(), args.prior_progress.resolve())
        args.visual_report.write_text(json.dumps(visual, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
        result = ledger(prior, visual, args.visual_report)
        args.ledger_report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
