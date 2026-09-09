#!/usr/bin/env python3
"""对已重放通过的train内开发质量报告生成聚合错误剖面。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
QUALITY_REPORT_SCRIPT = HERE / "build-development-instance-quality-report.py"
REBASELINE_QUALITY_REPORT_SCRIPT = HERE / "build-development-clean-rebaseline-report.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DEVELOPMENT = load_module("jiaru_development_quality", QUALITY_REPORT_SCRIPT)
QUALITY = DEVELOPMENT.QUALITY


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_bound_file(binding: Any, label: str) -> Path:
    if not isinstance(binding, dict):
        raise ValueError(f"{label} binding is missing")
    path = Path(str(binding.get("path", ""))).resolve()
    if not path.is_file() or sha256_file(path) != binding.get("sha256"):
        raise ValueError(f"{label} is missing or drifted: {path}")
    return path


def shape_tags(polygon: Any) -> list[str]:
    min_x, min_y, max_x, max_y = polygon.bounds
    width, height = max_x - min_x, max_y - min_y
    area = float(polygon.area)
    aspect = height / width if width > 0 else float("inf")
    tags: list[str] = []
    if area <= 0.0025:
        tags.append("tiny")
    elif area <= 0.006:
        tags.append("small")
    if aspect >= 2.2:
        tags.append("elongated")
    elif aspect <= 0.6:
        tags.append("wide")
    if min(min_x, min_y, 1 - max_x, 1 - max_y) <= 0.025:
        tags.append("edge-adjacent")
    return tags or ["ordinary-geometry"]


def choose_next_variable(
    positive_mass: float, total_mass: float, cooccurring_missing_images: int, error_images: int
) -> dict[str, Any]:
    positive_share = positive_mass / total_mass if total_mass else 0.0
    cooccurrence_share = cooccurring_missing_images / error_images if error_images else 0.0
    if positive_share >= 0.80 and cooccurrence_share >= 0.50:
        choice = "targeted_source_isolated_real_positive_augmentation"
        reason = (
            "杂散质量主要发生在正图，且多数错误图同时漏甲；单纯候选抑制可能继续损伤召回，"
            "应优先补充同形态但来源隔离的完整甲面真值。"
        )
    else:
        choice = "single_structural_candidate_suppression"
        reason = "杂散并非主要与正图漏甲共现，可先用一个结构性候选抑制变量做可证伪对照。"
    return {
        "selectedVariable": choice,
        "positiveSpuriousMassShare": round(positive_share, 8),
        "errorImageMissingCooccurrenceShare": round(cooccurrence_share, 8),
        "reason": reason,
    }


def build_report(quality_report_path: Path) -> dict[str, Any]:
    quality_document = read_json(quality_report_path)
    verifier = (
        REBASELINE_QUALITY_REPORT_SCRIPT
        if quality_document.get("schemaVersion") == 2
        and quality_document.get("evaluationKind") == "single_read_only_clean_truth_rebaseline"
        else QUALITY_REPORT_SCRIPT
    )
    replay = subprocess.run(
        [sys.executable, str(verifier), "--verify-report", str(quality_report_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if replay.returncode != 0:
        raise ValueError(f"development quality report replay failed: {replay.stderr.strip()}")
    report = quality_document
    inputs = report.get("inputs", {})
    materialization_path = require_bound_file(inputs.get("materializationReport"), "materialization report")
    artifact_path = require_bound_file(inputs.get("artifactIndex"), "artifact index")
    materialization = read_json(materialization_path)
    artifact = read_json(artifact_path)
    dataset_root = Path(str(materialization.get("outputDir", ""))).resolve()
    records = {
        Path(str(row["fileName"])).stem: row
        for row in materialization.get("records", [])
        if row.get("developmentSplit") == "val"
    }
    prediction_records = artifact.get("prediction_records")
    if not isinstance(prediction_records, list) or artifact.get(
        "prediction_records_sha256"
    ) != canonical_sha256(prediction_records):
        raise ValueError("prediction record coverage is missing or drifted")
    prediction_paths: dict[str, Path | None] = {}
    artifact_root = Path(str(artifact.get("artifacts_dir", artifact_path.parent))).resolve()
    for row in prediction_records:
        stem = str(row.get("stem", ""))
        relative = row.get("path")
        if relative is None:
            if row.get("sha256") is not None or int(row.get("prediction_count", -1)) != 0:
                raise ValueError(f"invalid zero-prediction record: {stem}")
            prediction_paths[stem] = None
            continue
        path = (artifact_root / str(relative)).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError as error:
            raise ValueError(f"prediction path escapes artifact root: {stem}") from error
        if not path.is_file() or sha256_file(path) != row.get("sha256"):
            raise ValueError(f"prediction evidence drifted: {stem}")
        prediction_paths[stem] = path
    if set(records) != set(prediction_paths):
        raise ValueError("materialization and prediction coverage differ")

    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    morphology: Counter[str] = Counter()
    cooccurrence: Counter[str] = Counter()
    threshold = float(report.get("contract", {}).get("scoreThreshold", 0.25))
    for stem in sorted(records):
        record = records[stem]
        truth = QUALITY.parse_label(dataset_root / str(record["label"]), prediction=False, threshold=threshold)
        path = prediction_paths[stem]
        raw = QUALITY.parse_label(path, prediction=True, threshold=threshold) if path else []
        predicted = DEVELOPMENT.suppress_product_duplicates(raw)
        matches, missing, unmatched = QUALITY.match_instances(truth, predicted)
        role, source_group = str(record["role"]), str(record["sourceGroup"])
        row_counts: Counter[str] = Counter()
        invalid = sum(not item[2] for item in predicted)
        row_counts["invalidPredictionMasks"] += invalid
        for index in unmatched:
            polygon = predicted[index][0]
            best_iou = max((QUALITY.polygon_iou(item[0], polygon) for item in truth), default=0.0)
            category = "duplicates" if best_iou >= 0.10 else "falsePositives"
            row_counts[category] += 1
            morphology.update(f"{category}:{tag}" for tag in shape_tags(polygon))
        row_counts["missing"] += len(missing)
        row_counts["weakShapeMatches"] += sum(iou < 0.75 for _, _, iou in matches)
        if row_counts["duplicates"] or row_counts["falsePositives"] or invalid:
            row_counts["errorImages"] += 1
            cooccurrence["errorImages"] += 1
            if missing:
                cooccurrence["spuriousAndMissingImages"] += 1
            else:
                cooccurrence["spuriousWithoutMissingImages"] += 1
        by_role[role].update(row_counts)
        by_source[source_group].update(row_counts)

    def serialize(rows: dict[str, Counter[str]]) -> list[dict[str, Any]]:
        result = []
        for name, counts in rows.items():
            weighted = counts["duplicates"] + 1.5 * counts["invalidPredictionMasks"] + 2 * counts["falsePositives"]
            result.append({"name": name, **dict(counts), "weightedSpuriousMass": weighted})
        return sorted(result, key=lambda row: (-row["weightedSpuriousMass"], row["name"]))

    role_rows = serialize(by_role)
    source_rows = serialize(by_source)
    total_mass = sum(float(row["weightedSpuriousMass"]) for row in role_rows)
    positive_mass = next(
        (float(row["weightedSpuriousMass"]) for row in role_rows if row["name"] == "train-positive"), 0.0
    )
    recommendation = choose_next_variable(
        positive_mass,
        total_mass,
        cooccurrence["spuriousAndMissingImages"],
        cooccurrence["errorImages"],
    )
    profile = {
        "roles": role_rows,
        "sourceGroups": source_rows,
        "morphology": dict(sorted(morphology.items())),
        "cooccurrence": dict(cooccurrence),
        "weightedSpuriousMass": total_mass,
        "recommendation": recommendation,
    }
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "development_instance_error_profile_ready",
        "trainingUse": "prohibited",
        "formalCalibrationOrReleaseEvidence": False,
        "inputs": {
            "qualityReport": str(quality_report_path),
            "qualityReportSha256": sha256_file(quality_report_path),
            "materializationReportSha256": sha256_file(materialization_path),
            "artifactIndexSha256": sha256_file(artifact_path),
            "weightsSha256": report["inputs"]["weights"]["sha256"],
            "scoreThreshold": threshold,
        },
        "profile": profile,
        "profileSha256": canonical_sha256(profile),
        "policy": {
            "oldValidationTestOrHoldoutRead": False,
            "oneNextVariableOnly": True,
            "cannotSelectFormalThreshold": True,
            "cannotPromoteWeights": True,
        },
    }


def first_difference(left: Any, right: Any, path: str = "$") -> str | None:
    if type(left) is not type(right):
        return f"{path}: type differs"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys differ"
        for key in sorted(left):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length differs"
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]")
            if difference:
                return difference
        return None
    return None if left == right else f"{path}: value differs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile train-internal development instance errors.")
    parser.add_argument("--quality-report")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        if args.quality_report or args.output:
            parser.error("--verify-report does not accept generation arguments")
        path = Path(args.verify_report).resolve()
        saved = read_json(path)
        rebuilt = build_report(Path(saved.get("inputs", {}).get("qualityReport", "")).resolve())
        difference = first_difference(saved, rebuilt)
        if difference:
            raise ValueError(f"error profile replay mismatch at {difference}")
        print(json.dumps({"ok": True, "reportSha256": sha256_file(path)}, ensure_ascii=False))
        return 0
    if not args.quality_report or not args.output:
        parser.error("generation requires --quality-report and --output")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    report = build_report(Path(args.quality_report).resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "recommendation": report["profile"]["recommendation"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
