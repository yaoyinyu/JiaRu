#!/usr/bin/env python3
"""Replay source-023's original-resolution microrepair visual decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(progress_path: Path, candidate_path: Path, manual_path: Path) -> dict:
    progress, candidate, manual = map(load, (progress_path, candidate_path, manual_path))
    row = next((item for item in progress["sourceDispositions"] if item["ordinal"] == 23), None)
    if (not progress["ok"] or row is None or row["decision"] != "confirmed_label_rework" or
            candidate["decision"] != "source023_spur_microrepair_candidate_visual_pending" or
            candidate["sourceFileName"] != row["sourceFileName"] or
            candidate["sourceGroup"] != row["sourceGroup"] or
            candidate["counts"]["nails"] != 5 or
            candidate["counts"]["unchangedNails"] != 4 or
            candidate["counts"]["changedNails"] != 1 or
            candidate["counts"]["removedSpurVertices"] != 3 or
            candidate["counts"]["legalPolygons"] != 5 or
            candidate["counts"]["overlapPairs"] != 0 or
            candidate["counts"]["qaPositivePointsInside"] != 3 or
            candidate["counts"]["qaNegativePointsOutside"] != 3 or
            candidate["counts"]["visualApproved"] != 0 or
            candidate["trainingUse"] != "prohibited" or
            candidate["inputs"]["sourceImage"] != row["sourceImage"] or
            candidate["inputs"]["sourceLabel"] != row["sourceLabel"]):
        raise ValueError("frozen source/candidate gate mismatch")
    for binding in candidate["inputs"].values():
        if isinstance(binding, list):
            for item in binding:
                checked(item)
        else:
            checked(binding)
    if (manual["sourceOrdinal"] != 23 or manual["sourceFileName"] != row["sourceFileName"] or
            manual["decision"] != "five_masks_visual_pass_watermark_pending_full_split" or
            manual["visibleNailCount"] != 5 or not manual["watermarkReviewRequired"] or
            manual["trainingUse"] != "prohibited" or not manual["reason"] or
            any(manual[key] != 0 for key in
                ("missingNails", "duplicateMasks", "croppedNails", "maskContaminations"))):
        raise ValueError("manual decision/role mismatch")
    reviews = manual["nails"]
    if sorted(item["truthIndex"] for item in reviews) != [1, 2, 3, 4, 5]:
        raise ValueError("missing nail decision")
    if any(item["decision"] != "pass_original_resolution" or not item["reason"] for item in reviews):
        raise ValueError("unreviewed nail")
    nails = []
    for candidate_nail, decision in zip(candidate["nails"], reviews, strict=True):
        if candidate_nail["truthIndex"] != decision["truthIndex"]:
            raise ValueError("nail order mismatch")
        for key in ("sourceNative", "candidateNative"):
            checked(candidate_nail[key])
        nails.append({"truthIndex": decision["truthIndex"],
                      "decision": decision["decision"], "reason": decision["reason"],
                      "changedFromOld": candidate_nail["changedFromOld"],
                      "sourceNative": candidate_nail["sourceNative"],
                      "candidateNative": candidate_nail["candidateNative"]})
    return {"schemaVersion": 1, "ok": True,
            "decision": "source023_five_masks_visual_pass_watermark_pending_training_prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)), "progressV4": bind(progress_path),
                       "microrepairCandidate": bind(candidate_path),
                       "visualDecisions": bind(manual_path)},
            "sourceOrdinal": 23, "sourceFileName": row["sourceFileName"],
            "sourceGroup": row["sourceGroup"], "sourceImage": row["sourceImage"],
            "candidateAnnotation": candidate["inputs"]["candidateAnnotation"],
            "candidateOverlay": candidate["inputs"]["candidateOverlay"],
            "nails": nails,
            "counts": {"visualPassSources": 1, "visualPassNails": 5,
                       "legalPolygons": 5, "overlapPairs": 0,
                       "newTrainingApprovedSources": 0},
            "watermarkReviewRequired": True, "fullTrainSplitApproved": False,
            "trainingUse": "prohibited"}


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
        inputs = old["inputs"]
        current = build(Path(inputs["progressV4"]["path"]),
                        Path(inputs["microrepairCandidate"]["path"]),
                        Path(inputs["visualDecisions"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.progress, args.candidate_audit, args.visual_decisions, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.candidate_audit.resolve(), args.visual_decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
