#!/usr/bin/env python3
"""Bind original-pixel source-quality stoploss for shard-003 sources 41/44/51."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


DECISIONS = {
    41: {
        "focusTruthIndices": [5],
        "reason": "第5枚拇指只见狭窄侧向甲面，近端及瓶侧一边的完整甲板无法从原像素确认；不得把侧面旧椭圆当完整纹理边界。",
    },
    44: {
        "focusTruthIndices": [3, 5, 6],
        "reason": "第3/5枚大型立体钻饰遮住甲端或近端甲面，旧polygon沿饰物外缘并入非甲面；第6枚同类饰物亦跨甲面。被遮挡的完整甲缘不可可靠定界，不猜测隐藏区域。",
    },
    51: {
        "focusTruthIndices": [1, 2],
        "reason": "第1枚旧polygon越入项坠和背景，虽可见长甲仍需重画；第2枚仅露尖侧窄条，完整甲身及根部不可见，旧polygon大量覆盖黑色背景，整图按源图门止损。",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bound(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha256(path) != binding["sha256"]:
        raise ValueError(f"绑定证据漂移：{path}")
    return path


def load_script(name: str):
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(native_report_path: Path) -> dict:
    native_module = load_script("build-development-cycle-016-shard003-source041044051-native.py")
    native_verify = native_module.verify(native_report_path)
    if not native_verify["ok"] or native_verify["counts"] != {
        "sourceImages": 3, "oldLabelNails": 17, "visualApprovals": 0,
    }:
        raise ValueError("原像素无填充裁块重放或计数失败")
    native = json.loads(native_report_path.read_text(encoding="utf-8"))
    triage_path = checked(native["inputs"]["sourceTriage"])
    triage_module = load_script("audit-development-cycle-016-shard003-source-triage.py")
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    if triage_module.build(Path(triage["inputs"]["shardReport"]["path"])) != triage:
        raise ValueError("分片003源图总览分流重建失败")
    if triage["counts"]["statusCounts"] != {
        "pending_every_nail_review": 9,
        "needs_second_source_review": 3,
        "confirmed_label_rework": 8,
    } or triage["counts"]["oldLabelNailsBound"] != 105:
        raise ValueError("上游源图分流口径漂移")
    rows = []
    for source in native["sources"]:
        ordinal = source["ordinal"]
        if ordinal not in DECISIONS:
            raise ValueError("源图二审对象漂移")
        old = next(row for row in triage["sourceTriage"] if row["ordinal"] == ordinal)
        if (old["decision"] != "needs_second_source_review" or
                old["sourceImage"] != source["sourceImage"] or
                old["sourceLabel"] != source["sourceLabel"] or
                old["sourceGroup"] != source["sourceGroup"] or
                old["oldLabelNails"] != len(source["nails"])):
            raise ValueError(f"上游源图身份漂移：{ordinal}")
        focus_indices = DECISIONS[ordinal]["focusTruthIndices"]
        focus = []
        for index in focus_indices:
            nail = source["nails"][index - 1]
            if nail["truthIndex"] != index:
                raise ValueError(f"焦点甲序号漂移：{ordinal}/{index}")
            checked(nail["raw3x"])
            checked(nail["oldOutline3x"])
            focus.append({"truthIndex": index, "cropBox": nail["cropBox"],
                          "raw3x": nail["raw3x"], "oldOutline3x": nail["oldOutline3x"]})
        rows.append({
            "ordinal": ordinal,
            "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"],
            "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"],
            "isolatedImage": source["isolatedImage"],
            "oldLabelNails": len(source["nails"]),
            "focusNails": focus,
            "decision": "confirmed_source_exclude_next_train_candidate",
            "reason": DECISIONS[ordinal]["reason"],
            "newTrainingUse": "prohibited",
        })
    if [row["ordinal"] for row in rows] != [41, 44, 51] or sum(row["oldLabelNails"] for row in rows) != 17:
        raise ValueError("源图止损计数漂移")
    rework = [row for row in triage["sourceTriage"] if row["decision"] == "confirmed_label_rework"]
    pending = [row for row in triage["sourceTriage"] if row["decision"] == "pending_every_nail_review"]
    if (len(rework) != 8 or sum(row["oldLabelNails"] for row in rework) != 44 or
            len(pending) != 9 or sum(row["oldLabelNails"] for row in pending) != 44):
        raise ValueError("排除后的队列守恒失败")
    return {
        "schemaVersion": 1,
        "evidenceOk": True,
        "decision": "shard003_three_sources_quality_exclude_next_train_candidate",
        "inputs": {
            "sourceScript": bound(Path(__file__)),
            "nativeReview": bound(native_report_path),
            "sourceTriage": native["inputs"]["sourceTriage"],
            "shardReport": native["inputs"]["shardReport"],
        },
        "counts": {
            "sourceImages": 20, "oldLabelNails": 105, "sourceGroups": 10,
            "confirmedSourceExclude": {"sourceImages": 3, "oldLabelNails": 17},
            "confirmedLabelRework": {"sourceImages": 8, "oldLabelNails": 44},
            "pendingEveryNailReview": {"sourceImages": 9, "oldLabelNails": 44},
            "remainingNextTrainCandidateSourcesBeforeOtherGates": 17,
            "newEveryNailVisualApprovals": 0,
            "newTrainingApprovedSources": 0,
        },
        "sourceDecisions": rows,
        "scope": {
            "exclusionAppliesTo": "next_train_candidate_and_derivatives_only",
            "historicalTrainSnapshotsAndFailures": "unchanged",
            "sourceAndMaskTruthOfRemainingImages": "pending_original_resolution_review",
            "sourceMarkerReview": "pending_independent_review",
            "fullTrainSplitApproved": False,
            "protectedTestOrHoldoutRead": False,
            "trainingUse": "prohibited",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            checked(binding)
        report = build(Path(old["inputs"]["nativeReview"]["path"]))
        if report != old:
            raise SystemExit("reconstruction_mismatch")
    else:
        if not args.native_report or not args.output:
            parser.error("--native-report and --output required")
        if args.output.exists():
            raise FileExistsError(args.output)
        report = build(args.native_report.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
