#!/usr/bin/env python3
"""核验固定32例人工视觉初审的证据绑定与训练真值止损裁决。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_module():
    path = Path(__file__).resolve().with_name("build-development-cycle-016-train-truth-review.py")
    spec = importlib.util.spec_from_file_location("cycle016_train_truth_review_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载原分辨率审核包构建器")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def adjudicate(workspace_path: Path, decisions_path: Path) -> dict:
    if not load_module().verify(workspace_path)["ok"]:
        raise ValueError("原分辨率审核包不能重放")
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if (decisions["workspaceReport"] != {"path": str(workspace_path), "sha256": sha256(workspace_path)} or
            decisions["visualApprovalCount"] != 0 or decisions["trainingUse"] != "unchanged" or
            len(decisions["items"]) != 32):
        raise ValueError("人工初审身份、数量或禁训状态不符")
    permitted = {"selected_mask_appears_complete_only", "needs_second_visual_review",
                 "source_exclude_confirmed", "selected_mask_rework_confirmed"}
    for record, review in zip(workspace["records"], decisions["items"], strict=True):
        if (review["ordinal"] != record["ordinal"] or review["id"] != record["id"] or
                review["sourceImageSha256"] != record["sourceImage"]["sha256"] or
                review["sourceLabelSha256"] != record["sourceLabel"]["sha256"] or
                review["nativeOverlaySha256"] != record["nativeOverlay"]["sha256"] or
                review["status"] not in permitted or not review["note"].strip()):
            raise ValueError(f"人工初审逐例绑定失败：{record['id']}")
    counts = dict(sorted(Counter(row["status"] for row in decisions["items"]).items()))
    confirmed = [row for row in decisions["items"] if row["status"] in {
        "source_exclude_confirmed", "selected_mask_rework_confirmed"}]
    baseline_failed = {row["id"] for row in workspace["records"] if not row["baseline"]["jointPass"]}
    candidate_new_failed = {row["id"] for row in workspace["records"]
                            if row["baseline"]["jointPass"] and not row["candidate"]["jointPass"]}
    if len(baseline_failed) != 19 or len(candidate_new_failed) != 2:
        raise ValueError("固定失败分母重建不一致")
    if not confirmed:
        raise ValueError("本裁决要求存在已确认的真值缺陷")
    return {
        "schemaVersion": 1, "evidenceOk": True, "trainingQualityPass": False,
        "decision": "train_truth_review_detected_defects_full_split_reaudit_before_more_training",
        "inputs": {"workspaceReport": {"path": str(workspace_path), "sha256": sha256(workspace_path)},
                   "visualDecisions": {"path": str(decisions_path), "sha256": sha256(decisions_path)}},
        "counts": {"fixedSelectedTrainInstances": 32, "baselineJointFailures": len(baseline_failed),
                   "candidateNewJointFailures": len(candidate_new_failed), "visualStatuses": counts,
                   "confirmedDefects": len(confirmed), "confirmedDefectsAmongBaselineFailures": sum(row["id"] in baseline_failed for row in confirmed),
                   "visualApprovals": 0},
        "confirmed": [{"ordinal": row["ordinal"], "id": row["id"], "status": row["status"], "note": row["note"]} for row in confirmed],
        "datasetFilesSha256": workspace["datasetFilesSha256"],
        "scope": {"onlyFixed32SelectedTrainInstances": True, "fullTrainSplitApproved": False,
                  "testOrHoldoutRead": False, "trainingUse": "unchanged",
                  "historicalMetricsAndFailures": "unchanged", "moreTrainingBeforeFullSplitAudit": "prohibited"},
        "errors": [],
    }


def verify(report_path: Path) -> dict:
    actual = json.loads(report_path.read_text(encoding="utf-8"))
    workspace = Path(actual["inputs"]["workspaceReport"]["path"])
    decisions = Path(actual["inputs"]["visualDecisions"]["path"])
    expected = adjudicate(workspace, decisions)
    if actual != expected:
        raise ValueError("视觉初审裁决与当前证据重放不一致")
    return {"ok": True, "decision": "verified_train_truth_review_detected_defects",
            "trainingQualityPass": False, "counts": expected["counts"],
            "datasetFilesSha256": expected["datasetFilesSha256"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if args.output.exists():
            raise FileExistsError(args.output)
        result = adjudicate(args.workspace, args.decisions)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result if args.verify_report else {
        key: result[key] for key in ("evidenceOk", "trainingQualityPass", "decision", "counts", "confirmed")},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
