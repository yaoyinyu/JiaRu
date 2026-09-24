#!/usr/bin/env python3
"""Replay shard-002 status after source23 repair and source21 SAM rejection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


WATERMARK_REPAIRED = "repaired_mask_visual_pass_pending_watermark_and_full_split"
STATUSES = ("pending_every_nail_review", "confirmed_label_rework",
            "confirmed_source_exclude", "watermark_review_required",
            "mask_visual_pass_pending_watermark_and_full_split",
            "mask_visual_pass_pending_full_split",
            "repaired_mask_visual_pass_pending_full_split", WATERMARK_REPAIRED)


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


def build(prior_path: Path, repair_path: Path,
          sam_v1_path: Path, sam_v2_path: Path) -> dict:
    prior, repair, sam_v1, sam_v2 = map(load,
                                        (prior_path, repair_path, sam_v1_path, sam_v2_path))
    if (not prior["ok"] or prior["counts"]["sourceImages"] != 20 or
            prior["counts"]["oldLabelNails"] != 104 or
            prior["counts"]["everyNailVisualPassSources"] != 3 or
            repair["decision"] != "source023_five_masks_visual_pass_watermark_pending_training_prohibited" or
            repair["sourceOrdinal"] != 23 or repair["counts"]["visualPassNails"] != 5 or
            repair["counts"]["newTrainingApprovedSources"] != 0 or
            repair["inputs"]["progressV4"]["sha256"] != sha(prior_path)):
        raise ValueError("prior/source23 contract mismatch")
    for candidate, legal, positive in ((sam_v1, 4, 3), (sam_v2, 5, 4)):
        if (candidate["decision"] != "shard002_sam_candidate_geometry_rejected" or
                candidate["sourceOrdinal"] != 21 or
                candidate["counts"]["legalPolygons"] != legal or
                candidate["counts"]["positivePointRowsInside"] != positive or
                candidate["counts"]["visualApproved"] != 0 or
                candidate["counts"]["trainingApproved"] != 0 or
                candidate["inputs"]["prompts"]["sha256"] == ""):
            raise ValueError("source21 historical rejection drift")
    for report in (prior, repair, sam_v1, sam_v2):
        for binding in report["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
    first_ann = load(Path(sam_v1["inputs"]["annotation"]["path"]))
    second_ann = load(Path(sam_v2["inputs"]["annotation"]["path"]))
    if (sam_v1["sourceFileName"] != sam_v2["sourceFileName"] or
            sam_v1["sourceGroup"] != sam_v2["sourceGroup"] or
            [item["polygon"] for item in first_ann["annotations"][2:]] !=
            [item["polygon"] for item in second_ann["annotations"][2:]]):
        raise ValueError("source21 directed retry changed nails 3-5")
    rows = []
    for item in prior["sourceDispositions"]:
        current = dict(item)
        if item["ordinal"] == 23:
            if (item["decision"] != "confirmed_label_rework" or
                    item["oldLabelNails"] != 5 or
                    repair["sourceFileName"] != item["sourceFileName"] or
                    repair["sourceGroup"] != item["sourceGroup"] or
                    repair["sourceImage"] != item["sourceImage"]):
                raise ValueError("source23 identity/status mismatch")
            current["decision"] = WATERMARK_REPAIRED
            current["everyNailVisualApproval"] = True
            current["watermarkReviewRequired"] = True
            current["repairVisualReport"] = bind(repair_path)
            current["repairedAnnotation"] = repair["candidateAnnotation"]
        if item["ordinal"] == 21:
            if (item["decision"] != "confirmed_label_rework" or
                    item["sourceFileName"] != sam_v1["sourceFileName"] or
                    item["sourceFileName"] != sam_v2["sourceFileName"] or
                    item["sourceGroup"] != sam_v1["sourceGroup"]):
                raise ValueError("source21 identity/status mismatch")
            current["samCandidateV1Rejected"] = bind(sam_v1_path)
            current["samCandidateV2Rejected"] = bind(sam_v2_path)
            current["nextRepairMode"] = "manual_polygon_review_after_one_directed_retry"
        rows.append(current)
    if len(rows) != 20 or len({row["ordinal"] for row in rows}) != 20:
        raise ValueError("source count drift")
    by_status = {status: {"sourceImages": sum(row["decision"] == status for row in rows),
                          "oldLabelNails": sum(row["oldLabelNails"] for row in rows
                                               if row["decision"] == status)}
                 for status in STATUSES}
    if [by_status[status]["sourceImages"] for status in STATUSES] != [0, 9, 5, 2, 1, 1, 1, 1]:
        raise ValueError("status count mismatch")
    visual_nails = sum(row["oldLabelNails"] for row in rows if row["everyNailVisualApproval"])
    if (sum(value["oldLabelNails"] for value in by_status.values()) != 104 or
            visual_nails != 25 or len({row["sourceGroup"] for row in rows}) != 8):
        raise ValueError("denominator/source group drift")
    return {"schemaVersion": 5, "ok": True,
            "decision": "shard002_nine_label_reworks_source23_watermark_pending_no_train_approval",
            "inputs": {"sourceScript": bind(Path(__file__)), "priorProgressV4": bind(prior_path),
                       "source23RepairVisual": bind(repair_path),
                       "source21SamV1Rejected": bind(sam_v1_path),
                       "source21SamV2Rejected": bind(sam_v2_path)},
            "sourceDispositions": rows,
            "counts": {"sourceImages": 20, "oldLabelNails": 104, "sourceGroups": 8,
                       "byStatus": by_status, "everyNailVisualPassSources": 4,
                       "everyNailVisualPassNails": visual_nails,
                       "newTrainingApprovedSources": 0},
            "initialPendingEveryNailQueueClosed": True,
            "fullShardCleanTruthComplete": False, "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--repair", type=Path)
    parser.add_argument("--sam-v1", type=Path)
    parser.add_argument("--sam-v2", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["priorProgressV4"]["path"]),
                        Path(inputs["source23RepairVisual"]["path"]),
                        Path(inputs["source21SamV1Rejected"]["path"]),
                        Path(inputs["source21SamV2Rejected"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.prior, args.repair, args.sam_v1, args.sam_v2, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.repair.resolve(), args.sam_v1.resolve(),
                   args.sam_v2.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
