#!/usr/bin/env python3
"""Finalize a reviewed independent hard-negative holdout without training use.

This is deliberately separate from ``finalize-reviewed-hard-negative-manifest.py``.
The training finalizer may emit ``trainingUse=permitted``; this finalizer never
does.  It deeply replays every candidate review and its pre-inference freeze,
then emits an immutable manifest that is eligible only for release evaluation
and long-term regression.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


FORMAL_MINIMUM_IMAGES = 100


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def load_training_finalizer() -> ModuleType:
    script = Path(__file__).with_name(
        "finalize-reviewed-hard-negative-manifest.py"
    )
    spec = importlib.util.spec_from_file_location(
        "reviewed_hard_negative_training_finalizer",
        script,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load reviewed hard-negative training finalizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_freeze_recorder() -> ModuleType:
    script = Path(__file__).with_name(
        "record-independent-hard-negative-authorization.py"
    )
    spec = importlib.util.spec_from_file_location(
        "independent_holdout_freeze_recorder_for_finalizer",
        script,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load independent holdout freeze recorder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_current_file(path_value: Any, hash_value: Any, label: str) -> Path:
    path = Path(str(path_value or "")).resolve()
    expected_hash = str(hash_value or "")
    if not path.is_file() or sha256_file(path) != expected_hash:
        raise ValueError(f"{label} is missing or its SHA-256 has drifted: {path}")
    return path


def freeze_evidence_from_input(
    input_record: dict[str, str],
    candidate_manifest: dict[str, Any],
) -> dict[str, Any]:
    screening_path = require_current_file(
        input_record.get("sourceScreeningBatchPath"),
        input_record.get("sourceScreeningBatchSha256"),
        "independent holdout source screening",
    )
    screening = read_json(screening_path, "independent holdout source screening")
    screening_inputs = screening.get("inputs")
    freeze_input = (
        screening_inputs.get("freezeManifest")
        if isinstance(screening_inputs, dict)
        else None
    )
    if not isinstance(freeze_input, dict):
        raise ValueError("independent holdout screening has no freeze manifest")
    freeze_path = require_current_file(
        freeze_input.get("path"),
        freeze_input.get("sha256"),
        "independent holdout freeze manifest",
    )
    verified = load_freeze_recorder().verify_freeze_manifest(freeze_path)
    candidate_inputs = candidate_manifest.get("inputs")
    if (
        not isinstance(candidate_inputs, dict)
        or Path(str(verified.get("authorizationRecord") or "")).resolve()
        != Path(str(candidate_inputs.get("authorizationPath") or "")).resolve()
        or verified.get("batchIdentitySha256")
        != freeze_input.get("batchIdentitySha256")
    ):
        raise ValueError("candidate manifest and freeze evidence identities differ")
    return {
        "freezeManifestPath": str(freeze_path),
        "freezeManifestSha256": sha256_file(freeze_path),
        "batchIdentitySha256": verified["batchIdentitySha256"],
        "candidateWeightsPath": verified["candidateWeights"],
        "candidateWeightsSha256": verified["candidateWeightsSha256"],
        "candidateThresholdReportPath": verified["candidateThresholdReport"],
        "candidateThresholdReportSha256": verified[
            "candidateThresholdReportSha256"
        ],
        "candidateScoreThreshold": verified["candidateScoreThreshold"],
    }


def build(
    candidate_manifest_values: list[str],
    minimum_images: int = FORMAL_MINIMUM_IMAGES,
) -> dict[str, Any]:
    if minimum_images < FORMAL_MINIMUM_IMAGES:
        raise ValueError(
            f"minimum-images cannot lower the formal {FORMAL_MINIMUM_IMAGES}-image gate"
        )
    paths = [Path(value).resolve() for value in candidate_manifest_values]
    if not paths:
        raise ValueError("at least one candidate manifest is required")
    if len({str(path).casefold() for path in paths}) != len(paths):
        raise ValueError("candidate-manifest arguments must be unique")

    training_finalizer = load_training_finalizer()
    all_items: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    weights_hashes: set[str] = set()
    score_thresholds: set[float] = set()
    for path in paths:
        if not path.is_file():
            raise ValueError(f"candidate manifest is missing: {path}")
        document = read_json(path, "independent holdout candidate manifest")
        items, input_record = training_finalizer.validate_candidate_review(
            path,
            document,
            expected_dataset_role="independent-holdout",
        )
        freeze_record = freeze_evidence_from_input(input_record, document)
        weights_hashes.add(str(freeze_record["candidateWeightsSha256"]))
        score_thresholds.add(float(freeze_record["candidateScoreThreshold"]))
        for item in items:
            file_name = str(item["fileName"])
            image_hash = str(item["imageSha256"])
            if file_name in seen_names:
                raise ValueError(
                    f"duplicate independent holdout fileName across batches: {file_name}"
                )
            if image_hash in seen_hashes:
                raise ValueError(
                    "duplicate independent holdout image SHA-256 across batches: "
                    f"{image_hash}"
                )
            if (
                item.get("role") != "independent-holdout"
                or item.get("authorizedDatasetRole") != "independent-holdout"
            ):
                raise ValueError(f"{file_name}: independent holdout role was not preserved")
            seen_names.add(file_name)
            seen_hashes.add(image_hash)
            all_items.append(
                {
                    **item,
                    "datasetRole": "independent-holdout",
                    "trainingUse": "prohibited",
                }
            )
        inputs.append({**input_record, **freeze_record})
    if len(weights_hashes) != 1:
        raise ValueError("all independent holdout batches must bind the same candidate weights")
    if len(score_thresholds) != 1:
        raise ValueError(
            "all independent holdout batches must bind the same candidate threshold"
        )

    all_items.sort(key=lambda item: (str(item["fileName"]), str(item["imageSha256"])))
    approved = len(all_items) >= minimum_images
    all_items = [
        {
            **item,
            "releaseEvaluationUse": "permitted" if approved else "prohibited",
            "longTermRegressionUse": "permitted" if approved else "prohibited",
        }
        for item in all_items
    ]
    decision = (
        "approved_independent_hard_negative_holdout"
        if approved
        else "hold_insufficient_independent_hard_negative_holdout"
    )
    report: dict[str, Any] = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": approved,
        "status": "PASS" if approved else "HOLD",
        "decision": decision,
        "datasetRole": "independent-holdout",
        "trainingUse": "prohibited",
        "releaseEvaluationUse": "permitted" if approved else "prohibited",
        "longTermRegressionUse": "permitted" if approved else "prohibited",
        "candidateWeightsSha256": next(iter(weights_hashes)),
        "candidateScoreThreshold": next(iter(score_thresholds)),
        "inputs": inputs,
        "summary": {
            "candidateManifestCount": len(paths),
            "reviewedIndependentHoldoutImages": len(all_items),
            "sourceGroupCount": len({item["sourceGroup"] for item in all_items}),
            "minimumRequiredImages": minimum_images,
            "gapToMinimum": max(0, minimum_images - len(all_items)),
            "duplicateFileNames": 0,
            "duplicateImageSha256": 0,
        },
        "invariants": {
            "allCandidateReviewsDeeplyReplayed": True,
            "allFreezeManifestsDeeplyReplayed": True,
            "allFrozenBeforeAuthorizedCandidateInference": True,
            "allCurrentImageBytesMatch": True,
            "allOriginalResolutionVisualReviewsPass": True,
            "allSourceIsolationEvidencePass": True,
            "allBatchesBindOneCandidateWeightsIdentity": True,
            "allBatchesBindOneDeeplyVerifiedCandidateThreshold": True,
            "uniqueFileNamesAndImageSha256": True,
            "formalMinimumCannotBeLowered": True,
            "trainingUseAlwaysProhibited": True,
            "releaseEvaluationUseRequiresMinimum": True,
        },
        "errors": [],
    }
    key = "items" if approved else "candidateItems"
    hash_key = "itemsSha256" if approved else "candidateItemsSha256"
    report[hash_key] = canonical_sha256(all_items)
    report[key] = all_items
    return report


def verify_approved_report(
    path: Path,
    minimum_images: int = FORMAL_MINIMUM_IMAGES,
) -> dict[str, Any]:
    report_path = path.resolve()
    report = read_json(report_path, "approved independent hard-negative holdout")
    if (
        report.get("schemaVersion") != 2
        or report.get("ok") is not True
        or report.get("status") != "PASS"
        or report.get("decision")
        != "approved_independent_hard_negative_holdout"
        or report.get("datasetRole") != "independent-holdout"
        or report.get("trainingUse") != "prohibited"
        or report.get("releaseEvaluationUse") != "permitted"
        or report.get("longTermRegressionUse") != "permitted"
    ):
        raise ValueError(
            "independent hard-negative holdout is not an approved schema v2 report"
        )
    inputs = report.get("inputs")
    items = report.get("items")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("approved independent holdout inputs are missing")
    if not isinstance(items, list) or len(items) < minimum_images:
        raise ValueError(
            f"approved independent holdout has fewer than {minimum_images} items"
        )
    candidate_paths: list[str] = []
    for number, evidence in enumerate(inputs, start=1):
        if not isinstance(evidence, dict):
            raise ValueError(f"approved holdout input {number} must be an object")
        candidate_path = require_current_file(
            evidence.get("candidateManifestPath"),
            evidence.get("candidateManifestSha256"),
            f"approved holdout input {number} candidate manifest",
        )
        require_current_file(
            evidence.get("freezeManifestPath"),
            evidence.get("freezeManifestSha256"),
            f"approved holdout input {number} freeze manifest",
        )
        candidate_paths.append(str(candidate_path))

    replay = build(
        candidate_paths,
        max(FORMAL_MINIMUM_IMAGES, minimum_images),
    )
    if replay.get("ok") is not True:
        raise ValueError("independent holdout evidence no longer passes approval")
    for field in (
        "decision",
        "datasetRole",
        "trainingUse",
        "releaseEvaluationUse",
        "longTermRegressionUse",
        "candidateWeightsSha256",
        "candidateScoreThreshold",
        "inputs",
        "summary",
        "invariants",
        "itemsSha256",
        "items",
        "errors",
    ):
        if report.get(field) != replay.get(field):
            raise ValueError(
                f"approved independent holdout {field} differs from current replay"
            )
    if report.get("itemsSha256") != canonical_sha256(items):
        raise ValueError("approved independent holdout items SHA-256 drift")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize a reviewed independent hard-negative holdout."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--candidate-manifest",
        action="append",
        help="Independent-holdout candidate manifest; repeat for additional frozen batches.",
    )
    mode.add_argument("--verify-report")
    parser.add_argument("--minimum-images", type=int, default=FORMAL_MINIMUM_IMAGES)
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.verify_report:
        if args.output:
            raise ValueError("--verify-report cannot be combined with --output")
        report_path = Path(args.verify_report).resolve()
        report = verify_approved_report(report_path, args.minimum_images)
        print(
            json.dumps(
                {
                    "ok": True,
                    "decision": report["decision"],
                    "datasetRole": report["datasetRole"],
                    "trainingUse": report["trainingUse"],
                    "reviewedIndependentHoldoutImages": report["summary"][
                        "reviewedIndependentHoldoutImages"
                    ],
                    "candidateWeightsSha256": report["candidateWeightsSha256"],
                    "report": str(report_path),
                },
                ensure_ascii=False,
            )
        )
        return
    if not args.output:
        parser.error("--output is required with --candidate-manifest")
    output = Path(args.output).resolve()
    if output.suffix.lower() != ".json":
        raise ValueError(f"output must be a .json file: {output}")
    if output.exists():
        raise ValueError(f"refusing to overwrite immutable holdout manifest: {output}")
    report = build(list(args.candidate_manifest or []), args.minimum_images)
    protected = {
        Path(str(value)).resolve()
        for evidence in report["inputs"]
        for key, value in evidence.items()
        if key.endswith("Path")
    }
    protected.update(
        Path(str(item["imagePath"])).resolve()
        for item in report.get("items", report.get("candidateItems", []))
    )
    if output in protected:
        raise ValueError(f"output must not overwrite input evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "decision": report["decision"],
                **report["summary"],
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    if report["ok"] is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
