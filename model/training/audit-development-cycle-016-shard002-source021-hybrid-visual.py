#!/usr/bin/env python3
"""Replay source21's hybrid mask visual review without reviving historical truth."""

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


def build(progress_path: Path, candidate_path: Path, decision_path: Path) -> dict:
    progress, candidate, manual = map(load, (progress_path, candidate_path, decision_path))
    row = next((item for item in progress["sourceDispositions"] if item["ordinal"] == 21), None)
    if (not progress["ok"] or row is None or row["decision"] != "confirmed_label_rework" or
            candidate["decision"] != "source021_hybrid_candidate_geometry_pass_visual_pending" or
            candidate["sourceOrdinal"] != 21 or candidate["sourceFileName"] != row["sourceFileName"] or
            candidate["sourceGroup"] != row["sourceGroup"] or
            candidate["counts"]["retainedReviewedSamPolygons"] != 4 or
            candidate["counts"]["redrawnManualPolygons"] != 1 or
            candidate["counts"]["legalPolygons"] != 5 or
            candidate["counts"]["overlapPairs"] != 0 or
            candidate["counts"]["manualQaPositiveInside"] != 3 or
            candidate["counts"]["manualQaNegativeOutside"] != 3 or
            candidate["counts"]["visualApproved"] != 0 or
            candidate["counts"]["trainingApproved"] != 0 or
            candidate["counts"]["newImageCount"] != 0 or
            candidate["trainingUse"] != "prohibited"):
        raise ValueError("prior/hybrid candidate gate mismatch")
    for binding in candidate["inputs"].values():
        if isinstance(binding, list):
            for item in binding:
                checked(item)
        else:
            checked(binding)
    if (manual["sourceOrdinal"] != 21 or manual["sourceFileName"] != row["sourceFileName"] or
            manual["decision"] !=
            "five_hybrid_masks_pass_original_resolution_historical_truth_correction_pending_full_split" or
            manual["visibleNailCount"] != 5 or manual["watermarkReviewRequired"] or
            manual["trainingUse"] != "prohibited" or not manual["reason"] or
            any(manual[key] != 0 for key in
                ("missingNails", "duplicateMasks", "croppedNails", "maskContaminations"))):
        raise ValueError("manual visual decision/role mismatch")
    reviews = manual["nails"]
    if sorted(item["truthIndex"] for item in reviews) != [1, 2, 3, 4, 5]:
        raise ValueError("missing nail visual decision")
    if any(item["decision"] != "pass_original_resolution" or not item["reason"] for item in reviews):
        raise ValueError("unreviewed nail")
    return {"schemaVersion": 1, "ok": True,
            "decision": "source021_five_hybrid_masks_visual_pass_historical_correction_training_prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)), "progressV5": bind(progress_path),
                       "hybridCandidateAudit": bind(candidate_path),
                       "visualDecisions": bind(decision_path)},
            "sourceOrdinal": 21, "sourceFileName": row["sourceFileName"],
            "sourceGroup": row["sourceGroup"], "sourceImage": row["sourceImage"],
            "historicalCanonicalIdentityAudit": candidate["inputs"]["canonicalIdentityAudit"],
            "candidateAnnotation": candidate["inputs"]["candidateAnnotation"],
            "candidateOverlay": candidate["inputs"]["candidateOverlay"],
            "reviewCrops": candidate["inputs"]["reviewCrops"],
            "nails": reviews,
            "counts": {"visualPassSources": 1, "visualPassNails": 5,
                       "retainedReviewedSamPolygons": 4,
                       "redrawnManualPolygons": 1, "legalPolygons": 5,
                       "overlapPairs": 0, "newImageCount": 0,
                       "newTrainingApprovedSources": 0},
            "historicalSnapshotChanged": False,
            "fullShardCleanTruthComplete": False,
            "fullTrainSplitApproved": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--candidate-audit", type=Path)
    parser.add_argument("--visual-decisions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        current = build(Path(old["inputs"]["progressV5"]["path"]),
                        Path(old["inputs"]["hybridCandidateAudit"]["path"]),
                        Path(old["inputs"]["visualDecisions"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.progress, args.candidate_audit, args.visual_decisions, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.candidate_audit.resolve(),
                   args.visual_decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
