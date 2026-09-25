#!/usr/bin/env python3
"""Bind shard-003 source overview triage without approving source images or masks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


# A source overview and focused native crop establish only the stated defect or
# question. Every retained nail still requires its own original-resolution review.
DECISIONS = {
    41: ("needs_second_source_review", "第5枚右侧甲面紧贴产品瓶，须在无填充原像素局部确认左缘是否完整可见。", [5]),
    42: ("pending_every_nail_review", "五枚长甲在总览中可见；透明边界与旧polygon仍须逐甲审核。", []),
    43: ("pending_every_nail_review", "五枚甲面在总览中可见；蝴蝶结装饰与裸色近端仍须逐甲审核。", []),
    44: ("needs_second_source_review", "双手十甲中多枚大型立体钻饰覆盖甲面；先在原像素确定被遮挡甲面是否仍可可靠定界。", [3, 5]),
    45: ("confirmed_label_rework", "第4枚旧polygon底端锯齿并伸入非甲面，整图十甲继续逐甲审核。", [4]),
    46: ("pending_every_nail_review", "五甲总览可见；横向透明甲和衣袖邻界仍须逐甲审核。", []),
    47: ("confirmed_label_rework", "第5枚旧polygon只覆盖有色段，右侧透明甲尖仍完整可见。", [5]),
    48: ("confirmed_label_rework", "第2枚旧polygon顶端有明显不随甲缘的突刺，饰物和皮肤边界须返修。", [2]),
    49: ("pending_every_nail_review", "五枚长甲总览可见；透明近端与相邻手指须逐甲核对。", []),
    50: ("pending_every_nail_review", "五枚长甲总览可见；拇指甲根锯齿及透明近端须逐甲复核。", []),
    51: ("needs_second_source_review", "仅两枚旧标注；第1枚长甲贴近项坠且旧polygon延至其边，第2枚侧视远距甲面须确认完整性。", [1, 2]),
    52: ("pending_every_nail_review", "四枚旧标注对应总览可见甲面；远距边界和可能漏甲须原像素逐甲审核。", []),
    53: ("confirmed_label_rework", "第5枚旧polygon只覆盖绿色甲尖，近端透明裸粉甲身仍可见。", [5]),
    54: ("confirmed_label_rework", "第5枚横向甲旧polygon漏右侧透明甲尖；纸页交界须逐甲核对。", [5]),
    55: ("confirmed_label_rework", "第1/2/3枚旧polygon只罩有色区域，旁边透明甲身仍完整可见。", [1, 2, 3]),
    56: ("pending_every_nail_review", "五甲总览可见；纸卷交界与装饰边缘仍须逐甲审核。", []),
    57: ("pending_every_nail_review", "五枚低对比长甲总览可见，旧轮廓仍须逐甲原像素确认。", []),
    58: ("pending_every_nail_review", "五枚低对比长甲总览可见，甲根与甲尖锯齿仍须逐甲确认。", []),
    59: ("confirmed_label_rework", "第1枚旧polygon只罩金箔局部，周围裸粉甲面仍完整可见。", [1]),
    60: ("confirmed_label_rework", "第5枚旧polygon只罩蓝绿甲尖，近端透明裸粉甲身仍可见。", [5]),
}

EXPECTED_SHARD = {
    "shard": 3, "startOrdinal": 41, "endOrdinal": 60,
    "sourceImages": 20, "roiInstances": 105, "sourceGroups": 10,
}
EXPECTED_STATUS = {
    "pending_every_nail_review": 9,
    "needs_second_source_review": 3,
    "confirmed_label_rework": 8,
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


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha256(path) != binding["sha256"]:
        raise ValueError(f"证据文件漂移：{path}")


def verify_shard_report(path: Path) -> None:
    builder = Path(__file__).resolve().with_name("build-development-cycle-016-full-train-review-shard.py")
    spec = importlib.util.spec_from_file_location("full_train_shard_builder", builder)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载冻结分片构建器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.verify(path)
    if not result["ok"] or result["decision"] != "verified_full_train_review_shard_pending_visual_decisions":
        raise ValueError("冻结分片审核包重放失败")


def build(shard_path: Path) -> dict:
    verify_shard_report(shard_path)
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    if shard["shard"] != EXPECTED_SHARD or shard["counts"] != {
        "sourceImages": 20, "roiInstances": 105, "visualApprovals": 0,
    }:
        raise ValueError("分片003身份或原始计数漂移")
    if set(DECISIONS) != set(range(41, 61)):
        raise ValueError("源图总览决策未覆盖全部20张")
    rows = []
    total_nails = 0
    for source in shard["sourceImages"]:
        ordinal = source["ordinal"]
        state, reason, focus = DECISIONS[ordinal]
        nails = source["nails"]
        if not reason or any(index < 1 or index > len(nails) for index in focus):
            raise ValueError(f"人工分流说明或焦点甲序号非法：{ordinal}")
        for key in ("sourceImage", "sourceLabel", "overview"):
            checked(source[key])
        for nail in nails:
            checked(nail["nativeOverlay"])
            if nail["visualDecision"] != "pending_original_resolution_review":
                raise ValueError("分片构建器不得自动批准甲面")
        total_nails += len(nails)
        rows.append({
            "ordinal": ordinal,
            "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"],
            "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"],
            "overview": source["overview"],
            "oldLabelNails": len(nails),
            "decision": state,
            "reason": reason,
            "focusNails": [
                {"truthIndex": index, "nativeOverlay": nails[index - 1]["nativeOverlay"]}
                for index in focus
            ],
            "everyNailVisualApproval": False,
            "sourceMarkerReview": "pending_independent_review",
            "trainingUse": "prohibited",
        })
    if [row["ordinal"] for row in rows] != list(range(41, 61)):
        raise ValueError("源图序号或排序漂移")
    if total_nails != 105 or len({row["sourceGroup"] for row in rows}) != 10:
        raise ValueError("旧甲数或来源组数漂移")
    statuses = {state: sum(row["decision"] == state for row in rows) for state in EXPECTED_STATUS}
    if statuses != EXPECTED_STATUS:
        raise ValueError("总览分流分布漂移")
    return {
        "schemaVersion": 1,
        "evidenceOk": True,
        "decision": "shard003_source_overview_triage_only_no_mask_approval",
        "inputs": {
            "sourceScript": bound(Path(__file__)),
            "shardReport": bound(shard_path),
            "fullTrainInventory": shard["inputs"]["inventoryReport"],
        },
        "counts": {
            "reviewedOriginalSourceOverviews": 20,
            "oldLabelNailsBound": total_nails,
            "sourceGroups": 10,
            "statusCounts": statuses,
            "everyNailVisualApprovals": 0,
            "newTrainingApprovedSources": 0,
        },
        "sourceTriage": rows,
        "scope": {
            "originalResolutionSourceOverviewAndFocusedNativeCropReview": True,
            "everyNailOriginalResolutionReviewComplete": False,
            "fullTrainSplitApproved": False,
            "trainingUse": "prohibited",
            "historicalMetricsAndFailures": "unchanged",
            "protectedTestOrHoldoutUsedForSelection": False,
        },
    }


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
        result = current
    else:
        if not args.shard_report or not args.output:
            parser.error("--shard-report and --output required")
        if args.output.exists():
            raise FileExistsError(args.output)
        result = build(args.shard_report.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": result["decision"], "counts": result["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
