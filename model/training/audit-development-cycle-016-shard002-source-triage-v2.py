#!/usr/bin/env python3
"""Bind shard-002 original-image triage without approving any nail masks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DECISIONS = {
    21: ("pending_every_nail_review", "完整手部可见；侧向透明延长甲的甲根与甲尖仍须逐枚审核。", []),
    22: ("pending_every_nail_review", "五甲完整可见；须逐甲核对透明甲根、装饰与右下角来源标记。", []),
    23: ("pending_every_nail_review", "五甲可见；交错手势和低对比边缘须逐甲审核。", []),
    24: ("confirmed_label_rework", "第5枚只覆盖绿色装饰段，右侧透明裸色甲身仍在完整可见甲面内。", [5]),
    25: ("pending_every_nail_review", "五甲可见；立体花饰和侧向长甲须逐甲审核。", []),
    26: ("pending_every_nail_review", "双手十甲可见；立体饰件及相邻甲面边界须逐甲审核。", []),
    27: ("confirmed_label_rework", "第5枚横向透明甲仅标出绿色末段，仍可见的透明甲身未覆盖。", [5]),
    28: ("pending_every_nail_review", "五枚超长透明甲可见；锯齿边与局部装饰须逐甲复核。", []),
    29: ("confirmed_label_rework", "第1枚横向拇指仅标绿色末段，仍可见的透明裸色甲身未覆盖。", [1]),
    30: ("confirmed_label_rework", "第3枚立体花饰旁的旧polygon出现细长支路，与完整透明甲面边界不符。", [3]),
    31: ("pending_every_nail_review", "五甲虽可见但源图压缩较重，需确认原像素甲缘可判后再逐甲审核。", []),
    32: ("confirmed_label_rework", "透明裸色甲面与旧绿色mask明显不一致，第5枚横向拇指仍有透明甲身未覆盖。", [5]),
    33: ("pending_every_nail_review", "五枚远距细甲可见；polygon根部锯齿及清晰度须逐甲复核。", []),
    34: ("confirmed_source_exclude", "原图右侧第4枚小指甲的左侧甲缘被邻指遮住，仅局部可见；整图排除。v1总览初筛仅列待审，原图复看后收紧。", [4]),
    35: ("confirmed_source_exclude", "第5枚顶部侧向甲只露薄尖端，原像素无法确认完整甲身，按源图门整图排除。", [5]),
    36: ("confirmed_source_exclude", "第4枚拇指甲呈极窄侧视条，完整甲面不可见，按源图门整图排除。", [4]),
    37: ("watermark_review_required", "袖口横向重复文字水印清晰可见；未做消融前不进入新train。", []),
    38: ("pending_every_nail_review", "五枚低对比长甲可见；装饰与甲尖须逐甲审核。", []),
    39: ("watermark_review_required", "右侧白色文字与图标水印清晰可见；未做消融前不进入新train。", []),
    40: ("confirmed_label_rework", "第5枚竖直甲的旧mask底部锯齿伸入指腹；右侧水印亦须单独消融。", [5]),
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bound(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def build(shard_path: Path) -> dict:
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    expected = {"shard": 2, "startOrdinal": 21, "endOrdinal": 40,
                "sourceImages": 20, "roiInstances": 104, "sourceGroups": 8}
    if not shard["ok"] or shard["decision"] != "full_train_review_shard_pending_visual_decisions" or shard["shard"] != expected:
        raise ValueError("shard identity mismatch")
    if shard["counts"] != {"sourceImages": 20, "roiInstances": 104, "visualApprovals": 0}:
        raise ValueError("pre-triage visual count drift")
    for item in shard["inputs"].values():
        checked(item)
    rows = []
    seen_groups = set()
    total_nails = 0
    for row in shard["sourceImages"]:
        ordinal = row["ordinal"]
        if ordinal not in DECISIONS:
            raise ValueError(f"unreviewed source: {ordinal}")
        for key in ("sourceImage", "sourceLabel", "overview"):
            checked(row[key])
        for nail in row["nails"]:
            checked(nail["nativeOverlay"])
            if nail["visualDecision"] != "pending_original_resolution_review":
                raise ValueError("shard builder must not auto-approve masks")
        state, reason, focus = DECISIONS[ordinal]
        if not reason or any(index < 1 or index > len(row["nails"]) for index in focus):
            raise ValueError(f"invalid human triage: {ordinal}")
        total_nails += len(row["nails"])
        seen_groups.add(row["sourceGroup"])
        rows.append({"ordinal": ordinal, "sourceFileName": row["sourceFileName"],
                     "sourceGroup": row["sourceGroup"], "sourceImage": row["sourceImage"],
                     "sourceLabel": row["sourceLabel"], "overview": row["overview"],
                     "oldLabelNails": len(row["nails"]), "decision": state,
                     "reason": reason,
                     "focusNails": [{"truthIndex": index,
                                     "nativeOverlay": row["nails"][index - 1]["nativeOverlay"]}
                                    for index in focus],
                     "everyNailVisualApproval": False, "trainingUse": "prohibited"})
    if [r["ordinal"] for r in rows] != list(range(21, 41)) or total_nails != 104 or len(seen_groups) != 8:
        raise ValueError("shard source count mismatch")
    status_counts = {name: sum(row["decision"] == name for row in rows) for name in
                     ("pending_every_nail_review", "confirmed_label_rework",
                      "confirmed_source_exclude", "watermark_review_required")}
    if status_counts != {"pending_every_nail_review": 9, "confirmed_label_rework": 6,
                         "confirmed_source_exclude": 3, "watermark_review_required": 2}:
        raise ValueError("source triage status drift")
    prior_path = Path(__file__).resolve().parents[1] / "reviews" / "cycle016-shard002-source-triage-v1.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    if prior["sourceTriage"][13]["ordinal"] != 34 or prior["sourceTriage"][13]["decision"] != "pending_every_nail_review":
        raise ValueError("prior source-34 triage drift")
    return {"schemaVersion": 1, "evidenceOk": True,
            "decision": "shard002_source034_occlusion_excluded_no_mask_approval",
            "inputs": {"sourceScript": bound(Path(__file__)), "shardReport": bound(shard_path),
                       "fullTrainInventory": shard["inputs"]["inventoryReport"],
                       "priorSourceTriage": bound(prior_path)},
            "counts": {"reviewedOriginalSourceOverviews": 20, "oldLabelNailsBound": total_nails,
                       "sourceGroups": len(seen_groups), "statusCounts": status_counts,
                       "everyNailVisualApprovals": 0, "newTrainingApprovedSources": 0},
            "sourceTriage": rows,
            "scope": {"originalResolutionSourceOverviewAndFocusedNativeCropReview": True,
                      "everyNailOriginalResolutionReviewComplete": False,
                      "fullTrainSplitApproved": False, "trainingUse": "prohibited",
                      "protectedTestOrHoldoutUsedForSelection": False}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            checked(binding)
        current = build(Path(old["inputs"]["shardReport"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}, ensure_ascii=False))
        return
    if not args.shard_report or not args.output:
        parser.error("--shard-report and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.shard_report.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
