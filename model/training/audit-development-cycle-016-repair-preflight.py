#!/usr/bin/env python3
"""Bind the shard-001 repair queue to immutable image, label and overlay evidence.

This preflight does not produce masks or grant training approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FINDINGS = {
    8: {
        1: ("repair", "old mask omits the visible proximal nail bed"),
        2: ("repair", "old mask omits the visible proximal nail bed"),
        3: ("recheck_after_repair", "review complete surface with the repaired source"),
        4: ("recheck_after_repair", "review complete surface and jewel boundary with the repaired source"),
        5: ("repair", "old mask includes handbag strap and stitching"),
    },
    18: {
        1: ("recheck_after_repair", "review the low-contrast side and tip boundary"),
        2: ("repair", "old tip and side boundary is jagged and inset"),
        3: ("repair", "old tip and side boundary is jagged and inset"),
        4: ("recheck_after_repair", "review the low-contrast side and tip boundary"),
        5: ("repair", "old upper-right tip contour is jagged and inset"),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bound(path: Path) -> dict[str, str]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": sha256(path)}


def check(binding: dict[str, str]) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha256(path) != binding["sha256"]:
        raise ValueError(f"bound evidence drift: {path}")


def build(inputs: dict[str, dict[str, str]]) -> dict:
    for binding in inputs.values():
        check(binding)
    disposition = json.loads(Path(inputs["disposition"]["path"]).read_text(encoding="utf-8"))
    shard = json.loads(Path(inputs["shard"]["path"]).read_text(encoding="utf-8"))
    if disposition.get("evidenceOk") is not True or shard.get("ok") is not True:
        raise ValueError("upstream report is not valid")
    if disposition["inputs"]["shardReport"]["sha256"] != inputs["shard"]["sha256"]:
        raise ValueError("disposition is bound to a different shard")
    if disposition["counts"]["labelReworkImages"] != 2 or disposition["counts"]["labelReworkOldLabelNails"] != 10:
        raise ValueError("upstream repair count drift")
    decisions = {row["ordinal"]: row for row in disposition["sourceDispositions"]}
    sources = {row["ordinal"]: row for row in shard["sourceImages"]}
    queue = []
    for ordinal in FINDINGS:
        decision, source = decisions[ordinal], sources[ordinal]
        if decision["disposition"] != "label_rework" or len(source["nails"]) != 5:
            raise ValueError(f"repair source drift: {ordinal}")
        if decision["sourceImageSha256"] != source["sourceImage"]["sha256"] or decision["sourceLabelSha256"] != source["sourceLabel"]["sha256"]:
            raise ValueError(f"source identity drift: {ordinal}")
        for key in ("sourceImage", "sourceLabel", "overview"):
            check(source[key])
        old_labels = Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
        if len(old_labels) != 5:
            raise ValueError(f"old label count drift: {ordinal}")
        nail_rows = []
        for nail in source["nails"]:
            index = nail["truthIndex"]
            check(nail["nativeOverlay"])
            status, reason = FINDINGS[ordinal][index]
            nail_rows.append({"truthIndex": index, "oldPolygonSha256": hashlib.sha256((old_labels[index - 1] + "\n").encode()).hexdigest(),
                              "nativeOverlay": nail["nativeOverlay"], "status": status, "reason": reason})
        if {n["truthIndex"] for n in nail_rows} != set(range(1, 6)):
            raise ValueError(f"nail index mismatch: {ordinal}")
        queue.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                      "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                      "sourceLabel": source["sourceLabel"], "nails": nail_rows,
                      "trainingUse": "prohibited_pending_repair_and_original_resolution_review"})
    watermark = sources[7]
    check(watermark["sourceImage"])
    if decisions[7]["sourceImageSha256"] != watermark["sourceImage"]["sha256"]:
        raise ValueError("watermark source drift")
    return {"schemaVersion": 1, "ok": True, "decision": "repair_queue_bound_no_masks_approved",
            "inputs": inputs, "repairSources": queue,
            "watermarkPreflight": {"ordinal": 7, "sourceImage": watermark["sourceImage"],
                                   "type": "visible_text_on_cloth_outside_nail_masks",
                                   "positionApproxOriginalPixels": [200, 465, 560, 530],
                                   "requiredAblations": ["remove", "occlude", "blur", "move_position"],
                                   "status": "pending_before_training"},
            "counts": {"repairImages": 2, "nailsReviewed": 10,
                       "oldPolygonsRequireRepair": sum(n["status"] == "repair" for row in queue for n in row["nails"]),
                       "remainingWholeSourceRecheckNails": sum(n["status"] == "recheck_after_repair" for row in queue for n in row["nails"]),
                       "newlyApprovedMasks": 0, "trainingApprovedImages": 0},
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disposition", type=Path)
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding="utf-8"))
        current = build(recorded["inputs"])
        ok = recorded == current
        print(json.dumps({"ok": ok, "decision": current["decision"] if ok else "reconstruction_mismatch", "counts": current["counts"]}))
        if not ok:
            raise SystemExit(1)
        return
    if not all((args.disposition, args.shard, args.output)):
        parser.error("--disposition, --shard and --output are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    inputs = {"sourceScript": bound(Path(__file__)), "disposition": bound(args.disposition), "shard": bound(args.shard)}
    report = build(inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
