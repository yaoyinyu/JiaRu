#!/usr/bin/env python3
"""Replay source24's isolated repair candidate; visual promotion is separate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon


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
    row = next((r for r in progress["sourceDispositions"] if r["ordinal"] == 24), None)
    if (progress.get("schemaVersion") != 6 or not progress.get("ok") or row is None or
            row["decision"] != "confirmed_label_rework" or row["oldLabelNails"] != 5 or
            row["everyNailVisualApproval"] or row["trainingUse"] != "prohibited" or
            manifest["decision"] != "source024_hybrid_repair_candidate_only" or
            manifest["trainingUse"] != "prohibited" or
            Path(manifest["frozenProgressPath"]).resolve() != progress_path.resolve() or
            report["decision"] != "candidate_only_not_training_or_test_truth" or
            not report["ok"] or report["completedCount"] != 1 or
            report["polygonCount"] != 5 or report["retainedPolygonCount"] != 4 or
            report["manualPolygonCount"] != 1 or report["pairwiseOverlapCount"] != 0 or
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
        raise ValueError("source24 file/group/historical candidate mismatch")
    old = load(Path(item["sourceAnnotationPath"]))
    new = load(Path(output["annotationPath"]))
    if (old["image"]["fileName"] != row["sourceFileName"] or
            old["image"]["sourceGroup"] != row["sourceGroup"] or
            new["image"]["fileName"] != row["sourceFileName"] or
            new["image"]["sourceGroup"] != row["sourceGroup"] or
            new["trainingUse"] != "prohibited" or len(old["annotations"]) != 5 or
            len(new["annotations"]) != 5 or len(item["nails"]) != 5):
        raise ValueError("annotation identity/count mismatch")
    for index in range(4):
        if (item["nails"][index] != {"sourceIndex": index + 1} or
                new["annotations"][index]["polygon"] != old["annotations"][index]["polygon"]):
            raise ValueError(f"retained nail {index + 1} changed")
    if (new["annotations"][4]["polygon"] != item["nails"][4]["polygon"] or
            new["annotations"][4]["polygon"] == old["annotations"][4]["polygon"]):
        raise ValueError("manual fifth polygon missing or unchanged")
    shapes = [Polygon([(p["x"], p["y"]) for p in a["polygon"]])
              for a in new["annotations"]]
    if (any(not shape.is_valid or shape.area <= 1 for shape in shapes) or
            any(shapes[i].intersection(shapes[j]).area > 0
                for i in range(5) for j in range(i + 1, 5))):
        raise ValueError("polygon topology/overlap failure")
    image_copy = Path(manifest_path.parent / "images" / row["sourceFileName"])
    if sha(image_copy) != row["sourceImage"]["sha256"]:
        raise ValueError("isolated image copy differs from frozen source")
    crops = []
    if len(output["zoomPaths"]) != 5:
        raise ValueError("missing per-nail original-resolution crops")
    for pair in output["zoomPaths"]:
        crops.extend((bind(Path(pair["source"])), bind(Path(pair["overlay"]))))
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source024_hybrid_candidate_geometry_pass_visual_pending",
        "inputs": {"sourceScript": bind(Path(__file__)), "progressV6": bind(progress_path),
                   "manifest": bind(manifest_path), "historicalCandidate": bind(Path(item["sourceAnnotationPath"])),
                   "buildReport": bind(report_path), "builderScript": bind(Path(__file__).with_name("build-reviewed-manual-polygon-repair.py")),
                   "isolatedSourceImage": bind(image_copy), "candidateAnnotation": bind(Path(output["annotationPath"])),
                   "candidateOverlay": bind(Path(output["overlayPath"])), "reviewCrops": crops},
        "sourceOrdinal": 24, "sourceFileName": row["sourceFileName"],
        "sourceGroup": row["sourceGroup"], "sourceImage": row["sourceImage"],
        "counts": {"retainedHistoricalPolygons": 4, "redrawnManualPolygons": 1,
                   "legalPolygons": 5, "overlapPairs": 0, "visualApproved": 0,
                   "trainingApproved": 0},
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
        current = build(Path(inputs["progressV6"]["path"]),
                        Path(inputs["manifest"]["path"]), Path(inputs["buildReport"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.progress, args.manifest, args.build_report, args.output)):
        parser.error("--progress, --manifest, --build-report and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.manifest.resolve(), args.build_report.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
