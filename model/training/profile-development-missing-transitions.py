#!/usr/bin/env python3
"""按稳定真值身份重放开发折漏检迁移；视觉结论必须另行审核。"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "development_error_profile", Path(__file__).with_name("profile-development-instance-errors.py")
)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
Q, D = P.QUALITY, P.DEVELOPMENT


def transitions(before, after):
    before, after = set(before), set(after)
    return {
        "newlyMissedTruthIndices": sorted(after - before),
        "recoveredTruthIndices": sorted(before - after),
        "persistentMissingTruthIndices": sorted(before & after),
        "missingCountDelta": len(after) - len(before),
        "newMissingImage": not before and bool(after),
        "fullyRecoveredImage": bool(before) and not after,
    }


def require_same_evaluation(records_by_report):
    def identities(records):
        return {stem: tuple(row[k] for k in (
            "imageSha256", "labelSha256", "sourceGroup", "role", "maskCount"
        )) for stem, row in records.items()}
    first = identities(records_by_report[0])
    if any(identities(rows) != first for rows in records_by_report[1:]):
        raise ValueError("evaluation image/label/source/role identity differs")


def semantic_contract(report):
    contract = dict(report["contract"])
    # 旧计划是否显式嵌入固定门只属来源说明；默认权重仍由深重放的质量器固定。
    contract.pop("formalFloorSource", None)
    contract.setdefault("spuriousWeights", {"duplicates": 1, "invalidPredictionMasks": 1.5, "falsePositives": 2})
    return contract


def load_evaluation(path):
    replay = subprocess.run(
        [sys.executable, str(P.QUALITY_REPORT_SCRIPT), "--verify-report", str(path)],
        capture_output=True, encoding="utf-8", errors="replace", check=False,
    )
    if replay.returncode:
        raise ValueError(f"quality replay failed: {path}: {replay.stdout} {replay.stderr}")
    report = P.read_json(path)
    if report.get("diagnosticOnly") is not True or report["contract"]["split"] != "val":
        raise ValueError("only train-internal development evidence is accepted")
    material = P.read_json(P.require_bound_file(report["inputs"]["materializationReport"], "materialization"))
    artifact_path = P.require_bound_file(report["inputs"]["artifactIndex"], "artifact index")
    artifact = P.read_json(artifact_path)
    records = {}
    for row in material["records"]:
        if row["developmentSplit"] != "val":
            continue
        stem = Path(row["fileName"]).stem
        if stem in records:
            raise ValueError(f"duplicate evaluation stem: {stem}")
        if row["role"] not in ("train-positive", "hard-negative"):
            raise ValueError("protected role is not development evidence")
        records[stem] = row
    artifact_root = Path(artifact["artifacts_dir"])
    predictions = {}
    if artifact["prediction_records_sha256"] != P.canonical_sha256(artifact["prediction_records"]):
        raise ValueError("prediction records drifted")
    for row in artifact["prediction_records"]:
        if row["stem"] in predictions:
            raise ValueError("duplicate prediction stem")
        if row["path"] is None:
            if row["sha256"] is not None or row["prediction_count"] != 0:
                raise ValueError("invalid empty prediction binding")
            predictions[row["stem"]] = None
        else:
            pred_path = (artifact_root / row["path"]).resolve()
            pred_path.relative_to(artifact_root.resolve())
            predictions[row["stem"]] = P.require_bound_file(
                {"path": str(pred_path), "sha256": row["sha256"]}, "predictions"
            )
    if set(records) != set(predictions):
        raise ValueError("evaluation coverage differs")
    root = Path(material["outputDir"])
    images = {}
    summary_rows = {row["stem"]: row for row in report["images"]}
    for stem, row in records.items():
        image_path = P.require_bound_file(
            {"path": str(root / row["image"]), "sha256": row["imageSha256"]}, "image"
        )
        label_path = P.require_bound_file(
            {"path": str(root / row["label"]), "sha256": row["labelSha256"]}, "label"
        )
        threshold = report["contract"]["scoreThreshold"]
        truth = Q.parse_label(label_path, prediction=False, threshold=threshold)
        raw = Q.parse_label(predictions[stem], prediction=True, threshold=threshold) if predictions[stem] else []
        kept = D.suppress_product_duplicates(raw)
        matches, missing, _ = Q.match_instances(truth, kept)
        if len(missing) != summary_rows[stem]["missingCount"]:
            raise ValueError("per-image missing count differs from replay")
        images[stem] = {"truth": truth, "raw": raw, "kept": kept, "matches": matches,
                        "missing": [i + 1 for i in missing], "image": image_path}
    return {"report": report, "records": records, "images": images, "path": path}


def instance_evidence(image, index):
    polygon = image["truth"][index - 1][0]
    def best(items):
        if not items:
            return {"iou": 0.0, "score": None}
        item = max(items, key=lambda item: Q.polygon_iou(polygon, item[0]))
        iou = Q.polygon_iou(polygon, item[0])
        return {"iou": round(iou, 8), "score": round(item[1], 8) if iou > 0 else None}
    raw, kept = best(image["raw"]), best(image["kept"])
    missing = index in image["missing"]
    if not missing:
        mechanism = "matched"
    elif raw["iou"] >= 0.5 and kept["iou"] < 0.5:
        mechanism = "product-postprocessing-removal"
    elif kept["iou"] >= 0.5:
        mechanism = "one-to-one-assignment-competition"
    elif raw["iou"] > 0:
        mechanism = "retained-mask-below-match-iou"
    else:
        mechanism = "no-overlapping-prediction-at-fixed-threshold"
    return {"missing": missing, "bestRaw": raw, "bestKept": kept, "mechanism": mechanism}


def validate_visual_reviews(rows, decisions):
    by_stem = {row["stem"]: row for row in rows}
    reviewed = decisions.get("images", [])
    if len(reviewed) != len(by_stem) or {row["stem"] for row in reviewed} != set(by_stem):
        raise ValueError("visual review coverage differs from changed-instance images")
    if decisions.get("trainingUse") != "prohibited" or decisions.get("releaseState") != "hold":
        raise ValueError("diagnostic visual reviews cannot promote training or release")
    counts = Counter()
    for row in reviewed:
        original = by_stem[row["stem"]]
        if row.get("imageSha256") != original["image"]["sha256"] or row.get("labelSha256") != original["labelSha256"]:
            raise ValueError("visual review image/label identity differs")
        if row.get("disposition") not in ("source-exclude", "annotation-rework", "reviewed-no-new-issue"):
            raise ValueError("unsupported review disposition")
        if not row.get("review") or row.get("originalResolutionReviewed") is not True:
            raise ValueError("original-resolution review evidence is required")
        counts[row["disposition"]] += 1
    return dict(counts)


def build_report(paths, review_dir=None, review_decisions=None):
    evaluations = [load_evaluation(path) for path in paths]
    require_same_evaluation([e["records"] for e in evaluations])
    base, candidate = evaluations[:2]
    for other in evaluations[1:]:
        if semantic_contract(other["report"]) != semantic_contract(base["report"]) or other["report"]["productDeduplication"] != base["report"]["productDeduplication"]:
            raise ValueError("evaluation or product postprocessing contract differs")
    keys = [e["report"]["experimentId"] for e in evaluations]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate experiment identity")
    rows, counts, by_source = [], Counter(), Counter()
    for stem in sorted(base["images"]):
        before, after = base["images"][stem], candidate["images"][stem]
        change = transitions(before["missing"], after["missing"])
        changed = sorted(set(change["newlyMissedTruthIndices"] + change["recoveredTruthIndices"]))
        counts["regressedCountImages"] += change["missingCountDelta"] > 0
        counts["improvedCountImages"] += change["missingCountDelta"] < 0
        counts["unchangedCountImages"] += change["missingCountDelta"] == 0
        counts["newMissingImages"] += change["newMissingImage"]
        counts["fullyRecoveredImages"] += change["fullyRecoveredImage"]
        counts["newlyMissedInstances"] += len(change["newlyMissedTruthIndices"])
        counts["recoveredInstances"] += len(change["recoveredTruthIndices"])
        counts["persistentMissingInstances"] += len(change["persistentMissingTruthIndices"])
        if not changed:
            continue
        counts["changedInstanceImages"] += 1
        counts["equalCountTurnoverImages"] += change["missingCountDelta"] == 0
        record = base["records"][stem]
        by_source[record["sourceGroup"]] += len(change["newlyMissedTruthIndices"])
        row = {"stem": stem, "sourceGroup": record["sourceGroup"],
               "image": {"path": str(after["image"]), "sha256": record["imageSha256"]},
               "labelSha256": record["labelSha256"], **change,
               "missingByExperiment": {key: e["images"][stem]["missing"] for key, e in zip(keys, evaluations)},
               "changedInstances": []}
        for index in changed:
            polygon = after["truth"][index - 1][0]
            row["changedInstances"].append({"truthIndex": index, "bounds": list(polygon.bounds),
                "area": round(polygon.area, 8), "geometryTags": P.shape_tags(polygon),
                "evidence": {key: instance_evidence(e["images"][stem], index) for key, e in zip(keys, evaluations)}})
        rows.append(row)
        if review_dir:
            render_review(row, evaluations, review_dir, len(rows))
    baseline_missing, candidate_missing = base["report"]["summary"]["missing"], candidate["report"]["summary"]["missing"]
    if baseline_missing + counts["newlyMissedInstances"] - counts["recoveredInstances"] != candidate_missing:
        raise ValueError("instance transitions do not close")
    result = {"schemaVersion": 1, "decision": "development_missing_transitions_replayed_visual_review_required",
              "diagnosticOnly": True, "releaseState": "hold", "visualReviewPassed": False,
              "protectedEvaluationUsed": False, "truthIndicesAreOneBased": True,
              "inputs": [{"path": str(path.resolve()), "sha256": P.sha256_file(path)} for path in paths],
              "contract": base["report"]["contract"], "experimentIds": keys,
              "summaries": {key: e["report"]["summary"] for key, e in zip(keys, evaluations)},
              "transitions": dict(counts), "newMissesBySourceGroup": dict(sorted(by_source.items())), "images": rows}
    if review_decisions:
        decisions = P.read_json(review_decisions)
        review_counts = validate_visual_reviews(rows, decisions)
        for row in decisions["images"]:
            for label, binding in row.get("upstream", {}).items():
                P.require_bound_file(binding, label)
        issues = review_counts.get("source-exclude", 0) + review_counts.get("annotation-rework", 0)
        result["visualReviewDecisions"] = {"path": str(review_decisions.resolve()), "sha256": P.sha256_file(review_decisions)}
        result["visualReview"] = {"performed": True, "counts": review_counts,
            "unresolvedImages": issues, "trainingUse": "prohibited",
            "oldSnapshotsAndDecisionsUnchanged": True,
            "currentDatasetSelectionEligible": False,
            "remainingEvaluationPositiveImages": base["report"]["summary"]["positiveImages"] - len(rows)}
        result["decision"] = "reviewed_development_truth_integrity_hold" if issues else "reviewed_diagnostic_transitions_not_release_evidence"
    result["contentSha256"] = P.canonical_sha256(result)
    return result


def render_review(row, evaluations, directory, ordinal):
    from PIL import Image, ImageDraw
    directory.mkdir(parents=True, exist_ok=True)
    stem = row["stem"]
    for label, e in zip(("baseline", "candidate"), evaluations[:2]):
        item = e["images"][stem]
        with Image.open(item["image"]) as source:
            canvas = source.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        for polygon, _, _ in item["kept"]:
            draw.line([(x * canvas.width, y * canvas.height) for x, y in polygon.exterior.coords], fill="cyan", width=2)
        for index, (polygon, _, _) in enumerate(item["truth"], 1):
            color = "red" if index in item["missing"] else "lime"
            draw.line([(x * canvas.width, y * canvas.height) for x, y in polygon.exterior.coords], fill=color, width=3)
            draw.text((polygon.centroid.x * canvas.width, polygon.centroid.y * canvas.height), str(index), fill=color, stroke_width=1, stroke_fill="black")
        canvas.save(directory / f"{ordinal:02d}-{label}.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality-report", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-dir", type=Path)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        expected = P.read_json(args.verify_report)
        paths = [P.require_bound_file(b, "quality report") for b in expected["inputs"]]
        reviews = P.require_bound_file(expected["visualReviewDecisions"], "visual reviews") if expected.get("visualReviewDecisions") else None
        actual = build_report(paths, review_decisions=reviews)
        if actual != expected:
            raise ValueError("missing-transition profile replay differs")
        print('{"ok":true,"decision":"missing_transition_profile_verified"}')
    else:
        if not args.quality_report or len(args.quality_report) < 2 or args.output is None:
            parser.error("at least baseline and candidate --quality-report plus --output are required")
        result = build_report(args.quality_report, args.review_dir, args.review_decisions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        import json
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result["transitions"]))


if __name__ == "__main__":
    main()
