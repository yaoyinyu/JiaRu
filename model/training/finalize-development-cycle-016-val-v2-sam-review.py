#!/usr/bin/env python3
"""冻结 cycle016 val-v2 SAM 候选的原分辨率视觉裁决。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(review_path: Path, decisions_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    binding = decisions.get("inputs", {}).get("reviewReport", {})
    if Path(binding.get("path", "")).resolve() != review_path.resolve():
        raise ValueError("裁决未绑定当前审核报告路径")
    if binding.get("sha256") != sha256_file(review_path):
        raise ValueError("裁决绑定的审核报告哈希漂移")
    records = review.get("records", [])
    rows = decisions.get("decisions", [])
    if len(records) != 57 or len(rows) != 57:
        raise ValueError("审核报告或裁决未覆盖固定57实例")
    if [row.get("id") for row in rows] != [row.get("id") for row in records]:
        raise ValueError("裁决与审核报告未逐实例同序同构")
    if [row.get("sequence") for row in rows] != list(range(1, 58)):
        raise ValueError("裁决序号不连续")
    allowed = set(review.get("allowedVerdicts", []))
    if allowed != {"accept_sam", "manual_repair"}:
        raise ValueError("审核报告裁决枚举异常")
    if any(row.get("verdict") not in allowed or not str(row.get("notes", "")).strip() for row in rows):
        raise ValueError("裁决值非法或缺少视觉审核说明")
    if len({row["id"] for row in rows}) != 57:
        raise ValueError("裁决身份重复")
    accept_count = sum(row["verdict"] == "accept_sam" for row in rows)
    manual_count = sum(row["verdict"] == "manual_repair" for row in rows)
    declared = decisions.get("counts", {})
    if declared != {"instances": 57, "acceptSam": accept_count, "manualRepair": manual_count}:
        raise ValueError("裁决汇总计数不一致")
    return review, decisions


def finalize(review_path: Path, decisions_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output_path}")
    review, decisions = validate(review_path, decisions_path)
    merged = []
    for record, decision in zip(review["records"], decisions["decisions"], strict=True):
        merged.append({
            "sequence": decision["sequence"],
            "id": record["id"],
            "sourceFileName": record["sourceFileName"],
            "sourceGroup": record["sourceGroup"],
            "truthIndex": record["truthIndex"],
            "sourceImage": record["sourceImage"],
            "sourceImageSha256": record["sourceImageSha256"],
            "sourceLabel": record["sourceLabel"],
            "sourceLabelSha256": record["sourceLabelSha256"],
            "candidatePolygon": record["candidatePolygon"],
            "metrics": record["metrics"],
            "reviewPage": decision["reviewPage"],
            "verdict": decision["verdict"],
            "notes": decision["notes"],
        })
    counts = {
        "instances": 57,
        "acceptSam": sum(row["verdict"] == "accept_sam" for row in merged),
        "manualRepair": sum(row["verdict"] == "manual_repair" for row in merged),
    }
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "sam_visual_review_frozen_manual_residual_required",
        "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "trainingUse": "prohibited_until_v2_full_review_pass"},
        "inputs": {
            "reviewReport": {"path": str(review_path), "sha256": sha256_file(review_path)},
            "decisions": {"path": str(decisions_path), "sha256": sha256_file(decisions_path)},
        },
        "counts": counts,
        "records": merged,
        "stopLoss": "manual_repair实例禁止再次运行SAM，必须进入原分辨率人工多边形编辑",
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    review_path = Path(report["inputs"]["reviewReport"]["path"])
    decisions_path = Path(report["inputs"]["decisions"]["path"])
    for name, path in (("reviewReport", review_path), ("decisions", decisions_path)):
        if sha256_file(path) != report["inputs"][name]["sha256"]:
            raise ValueError(f"冻结报告输入哈希漂移：{name}")
    review, decisions = validate(review_path, decisions_path)
    if len(report.get("records", [])) != 57 or report.get("counts") != decisions["counts"]:
        raise ValueError("冻结报告记录或汇总计数异常")
    if [row["id"] for row in report["records"]] != [row["id"] for row in review["records"]]:
        raise ValueError("冻结报告身份顺序漂移")
    return {"ok": True, "decision": "verified_frozen_sam_visual_review", "counts": report["counts"], "reportSha256": sha256_file(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-report")
    parser.add_argument("--decisions")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not all((args.review_report, args.decisions, args.output)):
        raise ValueError("冻结模式需要--review-report、--decisions与--output")
    report = finalize(Path(args.review_report).resolve(), Path(args.decisions).resolve(), Path(args.output).resolve())
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
