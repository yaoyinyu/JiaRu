#!/usr/bin/env python3
"""Replay source29's two-manual, three-retained polygon candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, Polygon


CANONICAL_INDEX = Path(
    r"E:\AI Project\Codex\JiaRu_image\审核工作区\2026_7_14_A_v1"
    r"\positive-reinforcement-annotation-workspace-v1\training-truths-v1"
    r"\training-truth-index-v1.json"
)
QA = {
    1: {"positive": [[165, 820], [270, 861], [330, 910]],
        "negative": [[104, 822], [205, 945], [300, 815]]},
    5: {"positive": [[624, 1085], [730, 1100], [817, 1125]],
        "negative": [[600, 1055], [850, 1120], [730, 1175]]},
}


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


def build(progress_path: Path, manifest_path: Path, report_path: Path) -> dict:
    progress, manifest, report = map(load, (progress_path, manifest_path, report_path))
    row = next((item for item in progress["sourceDispositions"] if item["ordinal"] == 29), None)
    if (progress.get("schemaVersion") != 7 or not progress.get("ok") or row is None or
            row["decision"] != "confirmed_label_rework" or row["oldLabelNails"] != 5 or
            row["everyNailVisualApproval"] or row["trainingUse"] != "prohibited" or
            manifest["decision"] != "source029_hybrid_repair_candidate_only" or
            manifest["trainingUse"] != "prohibited" or
            Path(manifest["frozenProgressPath"]).resolve() != progress_path.resolve() or
            report["decision"] != "candidate_only_not_training_or_test_truth" or
            not report["ok"] or report["completedCount"] != 1 or
            report["polygonCount"] != 5 or report["retainedPolygonCount"] != 3 or
            report["manualPolygonCount"] != 2 or report["pairwiseOverlapCount"] != 0 or
            len(manifest["images"]) != 1 or len(report["outputs"]) != 1):
        raise ValueError("progress/manifest/build contract mismatch")
    item, output = manifest["images"][0], report["outputs"][0]
    if (item["fileName"] != row["sourceFileName"] or
            item["sourceGroup"] != row["sourceGroup"] or
            output["fileName"] != row["sourceFileName"] or
            output["sourceGroup"] != row["sourceGroup"] or
            output["validPolygonCount"] != 5 or output["pairwiseOverlapCount"] != 0 or
            Path(item["sourceAnnotationPath"]).resolve() !=
            Path(manifest["historicalCandidatePath"]).resolve()):
        raise ValueError("source29 file/group/historical candidate mismatch")
    old, new = load(Path(item["sourceAnnotationPath"])), load(Path(output["annotationPath"]))
    if (old["image"]["fileName"] != row["sourceFileName"] or
            old["image"]["sourceGroup"] != row["sourceGroup"] or
            new["image"]["fileName"] != row["sourceFileName"] or
            new["image"]["sourceGroup"] != row["sourceGroup"] or
            new["trainingUse"] != "prohibited" or len(old["annotations"]) != 5 or
            len(new["annotations"]) != 5 or len(item["nails"]) != 5):
        raise ValueError("annotation identity/count mismatch")
    canonical = load(CANONICAL_INDEX)
    if any(truth["fileName"] == row["sourceFileName"] for truth in canonical["canonicalTruths"]):
        raise ValueError("source29 already has canonical training truth")
    for index in (1, 2, 3):
        if (item["nails"][index] != {"sourceIndex": index + 1} or
                new["annotations"][index]["polygon"] != old["annotations"][index]["polygon"]):
            raise ValueError(f"retained nail {index + 1} changed")
    for index in (0, 4):
        if (new["annotations"][index]["polygon"] != item["nails"][index]["polygon"] or
                new["annotations"][index]["polygon"] == old["annotations"][index]["polygon"]):
            raise ValueError(f"manual nail {index + 1} unchanged/mismatch")
    shapes = [Polygon([(p["x"], p["y"]) for p in a["polygon"]])
              for a in new["annotations"]]
    if (any(not shape.is_valid or shape.area <= 1 for shape in shapes) or
            any(shapes[i].intersection(shapes[j]).area > 0
                for i in range(5) for j in range(i + 1, 5))):
        raise ValueError("polygon topology/overlap failure")
    pos, neg = 0, 0
    for index, points in QA.items():
        shape = shapes[index - 1]
        pos += sum(shape.contains(Point(x, y)) for x, y in points["positive"])
        neg += sum(not shape.covers(Point(x, y)) for x, y in points["negative"])
    if (pos, neg) != (6, 6):
        raise ValueError("independent manual polygon QA failure")
    image_copy = manifest_path.parent / "images" / row["sourceFileName"]
    if (sha(image_copy) != row["sourceImage"]["sha256"] or
            sha(Path(row["sourceImage"]["path"])) != row["sourceImage"]["sha256"] or
            sha(Path(row["sourceLabel"]["path"])) != row["sourceLabel"]["sha256"]):
        raise ValueError("frozen source/old label identity drift")
    crops = []
    if len(output["zoomPaths"]) != 5:
        raise ValueError("missing per-nail source/overlay crops")
    for pair in output["zoomPaths"]:
        crops.extend((bind(Path(pair["source"])), bind(Path(pair["overlay"]))))
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source029_hybrid_candidate_geometry_pass_visual_pending",
        "inputs": {"sourceScript": bind(Path(__file__)), "progressV7": bind(progress_path),
                   "canonicalIndex": bind(CANONICAL_INDEX), "manifest": bind(manifest_path),
                   "historicalCandidate": bind(Path(item["sourceAnnotationPath"])),
                   "buildReport": bind(report_path),
                   "builderScript": bind(Path(__file__).with_name("build-reviewed-manual-polygon-repair.py")),
                   "frozenSourceImage": row["sourceImage"], "frozenOldLabel": row["sourceLabel"],
                   "isolatedSourceImage": bind(image_copy),
                   "candidateAnnotation": bind(Path(output["annotationPath"])),
                   "candidateOverlay": bind(Path(output["overlayPath"])), "reviewCrops": crops},
        "sourceOrdinal": 29, "sourceFileName": row["sourceFileName"],
        "sourceGroup": row["sourceGroup"], "sourceImage": row["sourceImage"],
        "counts": {"canonicalTruthsWithSameFileName": 0,
                   "retainedHistoricalPolygons": 3, "redrawnManualPolygons": 2,
                   "legalPolygons": 5, "overlapPairs": 0,
                   "manualQaPositiveInside": pos, "manualQaNegativeOutside": neg,
                   "visualApproved": 0, "trainingApproved": 0},
        "historicalSnapshotChanged": False, "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["progressV7"]["path"]),
                        Path(inputs["manifest"]["path"]), Path(inputs["buildReport"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.progress, args.manifest, args.build_report, args.output)):
        parser.error("--progress, --manifest, --build-report and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.manifest.resolve(), args.build_report.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
