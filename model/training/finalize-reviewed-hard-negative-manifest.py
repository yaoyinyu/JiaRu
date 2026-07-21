#!/usr/bin/env python3
"""Finalize hash-bound hard-negative review batches for candidate training.

The finalizer accepts one or more candidate-only manifests produced after
original-resolution visual review.  It replays their review and authorization
evidence, verifies every current image byte, rejects duplicate identities, and
only emits an ``approved_hard_negative_manifest`` when the fixed formal floor
of 100 images is met.  An insufficient but otherwise valid pool is written as
an auditable HOLD report whose items remain prohibited for training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES = 100
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
MINIMUM_IMAGE_SIDE = 320
REQUIRED_CANDIDATE_GATES = (
    "allThirtySevenOriginalResolutionReviewed",
    "allSourceImageHashesMatchBoundScreeningEvidence",
    "allRelevantShardReportAndDecisionHashesMatch",
    "authorizationAConfirmed",
    "candidateSourceIsolatedFromTrain",
    "candidateSourceIsolatedFromVal",
    "candidateSourceIsolatedFromFrozenTest",
    "officialDatasetUnchanged",
    "sharedSplitUnchanged",
    "trainingStillProhibited",
)


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


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def require_sha256(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256_PATTERN.fullmatch(result):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return result


def require_current_file(path_value: Any, expected: Any, label: str) -> Path:
    path = Path(str(path_value or "")).resolve()
    expected_hash = require_sha256(expected, f"{label} expected hash")
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ValueError(
            f"{label} SHA-256 drift: expected={expected_hash} "
            f"actual={actual_hash}: {path}"
        )
    return path


def require_file_name(value: Any, label: str) -> str:
    file_name = str(value or "")
    if (
        not file_name
        or Path(file_name).name != file_name
        or any(separator in file_name for separator in ("/", "\\"))
        or Path(file_name).suffix.lower() not in IMAGE_SUFFIXES
    ):
        raise ValueError(f"{label} has invalid image fileName: {file_name!r}")
    return file_name


def require_nonempty(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{label} is missing")
    return result


def validate_decodable_image(path: Path, file_name: str) -> tuple[int, int, str]:
    """Verify format, dimensions, and full pixel decoding before training use."""

    try:
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise ValueError(f"{file_name}: image dimensions changed while decoding")
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise ValueError(f"{file_name}: image cannot be fully decoded: {error}") from error
    expected_format = IMAGE_FORMAT_BY_SUFFIX[Path(file_name).suffix.lower()]
    if image_format != expected_format:
        raise ValueError(
            f"{file_name}: image format {image_format or 'UNKNOWN'} does not match "
            f"the {expected_format} file extension"
        )
    if min(width, height) < MINIMUM_IMAGE_SIDE:
        raise ValueError(
            f"{file_name}: image dimensions {width}x{height} are below "
            f"the {MINIMUM_IMAGE_SIDE}px minimum side"
        )
    return width, height, image_format


def require_summary_count(summary: dict[str, Any], key: str, expected: int) -> None:
    value = summary.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value != expected:
        raise ValueError(f"candidate manifest summary.{key} differs from current items")


def validate_candidate_review(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if (
        manifest.get("ok") is not True
        or manifest.get("decision")
        != "hard_negative_candidate_manifest_ready_not_materialized"
        or manifest.get("candidateOnly") is not True
    ):
        raise ValueError(f"candidate manifest is not a passing candidate-only review: {manifest_path}")

    gates = manifest.get("gates")
    if not isinstance(gates, dict):
        raise ValueError(f"candidate manifest gates are missing: {manifest_path}")
    for gate in REQUIRED_CANDIDATE_GATES:
        if gates.get(gate) is not True:
            raise ValueError(f"candidate manifest gate is not true: {gate}: {manifest_path}")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(f"candidate manifest inputs are missing: {manifest_path}")
    review_path = require_current_file(
        inputs.get("reviewDecisionsPath"),
        inputs.get("reviewDecisionsSha256"),
        "review decisions",
    )
    source_screening_path = require_current_file(
        inputs.get("sourceScreeningBatchPath"),
        inputs.get("sourceScreeningBatchSha256"),
        "source screening batch",
    )
    authorization_path = require_current_file(
        inputs.get("authorizationPath"),
        inputs.get("authorizationSha256"),
        "authorization evidence",
    )
    review = read_json(review_path, "review decisions")
    if (
        review.get("ok") is not True
        or review.get("decision")
        != "hard_negative_candidate_scan_complete_candidate_only"
    ):
        raise ValueError(f"review decisions are not a passing candidate-only review: {review_path}")

    policy = review.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("review decisions policy is missing")
    required_policy = {
        "candidateMustBeClear": True,
        "candidateMustContainNoValidHumanManicureSurfaceAnywhere": True,
        "candidateMustBeUsefulForDeploymentFalsePositiveSuppression": True,
        "candidateMustHaveAuthorizationA": True,
        "candidateMustBeSourceIsolatedFromTrainValAndFrozenTest": True,
        "rejectTemplates": True,
        "rejectIndependentNailTips": True,
        "rejectCollages": True,
        "rejectLowQuality": True,
        "rejectCroppedSources": True,
        "candidateOnly": True,
    }
    for key, expected in required_policy.items():
        if policy.get(key) is not expected:
            raise ValueError(f"review policy {key} is not {expected!r}")
    if not str(policy.get("trainingUse", "")).startswith("prohibited"):
        raise ValueError("review policy must keep candidates prohibited")

    review_inputs = review.get("inputs")
    if not isinstance(review_inputs, dict):
        raise ValueError("review decisions inputs are missing")
    screening_input = review_inputs.get("sourceScreeningBatch")
    authorization_input = review_inputs.get("authorization")
    if not isinstance(screening_input, dict) or not isinstance(authorization_input, dict):
        raise ValueError("review decisions do not bind screening and authorization")
    if require_current_file(
        screening_input.get("path"), screening_input.get("sha256"), "review screening input"
    ) != source_screening_path:
        raise ValueError("candidate and review screening paths differ")
    if require_current_file(
        authorization_input.get("path"),
        authorization_input.get("sha256"),
        "review authorization input",
    ) != authorization_path:
        raise ValueError("candidate and review authorization paths differ")
    if (
        authorization_input.get("decision") != "A"
        or authorization_input.get("status") != "confirmed"
        or "commercial-model-training"
        not in list(authorization_input.get("authorizedUses") or [])
    ):
        raise ValueError("authorization evidence does not permit commercial model training")

    candidates = manifest.get("candidates")
    review_candidates = review.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"candidate manifest contains no candidates: {manifest_path}")
    if not isinstance(review_candidates, list) or len(review_candidates) != len(candidates):
        raise ValueError("review candidate coverage differs from candidate manifest")
    review_by_name: dict[str, dict[str, Any]] = {}
    for number, item in enumerate(review_candidates, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"review candidate {number} must be an object")
        file_name = require_file_name(item.get("fileName"), f"review candidate {number}")
        if file_name in review_by_name:
            raise ValueError(f"duplicate review candidate fileName: {file_name}")
        review_by_name[file_name] = item

    prepared: list[dict[str, Any]] = []
    for number, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"candidate {number} must be an object")
        file_name = require_file_name(item.get("fileName"), f"candidate {number}")
        source_group = require_nonempty(item.get("sourceGroup"), f"{file_name} sourceGroup")
        image_hash = require_sha256(item.get("sha256"), f"{file_name} image SHA-256")
        image_path = require_current_file(item.get("sourcePath"), image_hash, f"{file_name} image")
        width, height, image_format = validate_decodable_image(image_path, file_name)
        if (
            item.get("authorization") != "A"
            or item.get("sourceIsolation")
            != "verified-zero-match-train-val-frozen-test"
            or item.get("humanManicureSurfaceAnywhere") is not False
            or item.get("candidatePurpose") != "deployment-false-positive-suppression"
            or item.get("role") != "hard-negative-candidate"
            or not str(item.get("trainingUse", "")).startswith("prohibited")
            or item.get("materializationStatus") != "not-materialized"
        ):
            raise ValueError(f"{file_name}: candidate state is not eligible for finalization")

        reviewed = review_by_name.get(file_name)
        if reviewed is None:
            raise ValueError(f"{file_name}: original-resolution review is missing")
        if (
            require_sha256(reviewed.get("sha256"), f"{file_name} reviewed image SHA-256")
            != image_hash
            or Path(str(reviewed.get("sourcePath", ""))).resolve() != image_path
            or reviewed.get("sourceGroup") != source_group
            or reviewed.get("role") != "hard-negative-candidate"
            or not str(reviewed.get("trainingUse", "")).startswith("prohibited")
            or reviewed.get("materializationStatus") != "not-materialized"
            or reviewed.get("candidateStatus") != "pass-candidate-only"
        ):
            raise ValueError(f"{file_name}: candidate and review identity/state differ")

        visual = reviewed.get("originalResolutionVisualReview")
        if not isinstance(visual, dict):
            raise ValueError(f"{file_name}: original-resolution visual review is missing")
        required_visual = {
            "reviewed": True,
            "clearEnoughForHardNegative": True,
            "validHumanManicureSurfaceAnywhere": False,
            "croppedTargetNail": False,
            "collage": False,
            "templateOrIndependentNailTip": False,
        }
        for key, expected in required_visual.items():
            if visual.get(key) is not expected:
                raise ValueError(f"{file_name}: visual review {key} is not {expected!r}")
        if not str(visual.get("reviewNote", "")).strip():
            raise ValueError(f"{file_name}: visual review note is missing")
        if visual.get("reviewed") is not True:
            raise ValueError(f"{file_name}: original-resolution review is not complete")
        reviewed_width = reviewed.get("width")
        reviewed_height = reviewed.get("height")
        if reviewed_width != width or reviewed_height != height:
            raise ValueError(
                f"{file_name}: reviewed dimensions {reviewed_width}x{reviewed_height} "
                f"differ from current {width}x{height}"
            )

        authorization = reviewed.get("authorizationEvidence")
        isolation = reviewed.get("sourceIsolationEvidence")
        if not isinstance(authorization, dict) or not isinstance(isolation, dict):
            raise ValueError(f"{file_name}: authorization/source isolation evidence is missing")
        if (
            authorization.get("decision") != "A"
            or authorization.get("authorizationEntryFileNameMatch") is not True
            or authorization.get("authorizationEntrySha256Match") is not True
            or authorization.get("trainingEligibility")
            != "permitted-after-visual-review-and-source-isolation"
        ):
            raise ValueError(f"{file_name}: authorization evidence is not eligible")
        if isolation.get("isolated") is not True:
            raise ValueError(f"{file_name}: source isolation did not pass")
        for key, value in isolation.items():
            if key.endswith("Matches") and value != 0:
                raise ValueError(f"{file_name}: source isolation {key} is not zero")

        prepared.append(
            {
                "fileName": file_name,
                "sourceGroup": source_group,
                "imageSha256": image_hash,
                "imagePath": str(image_path),
                "width": width,
                "height": height,
                "imageFormat": image_format,
                "role": "hard-negative",
                "originalResolutionVisualReview": True,
                "authorization": "A",
                "candidateManifestPath": str(manifest_path),
                "candidateManifestSha256": sha256_file(manifest_path),
                "reviewDecisionsPath": str(review_path),
                "reviewDecisionsSha256": sha256_file(review_path),
            }
        )

    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("candidate manifest summary is missing")
    require_summary_count(summary, "candidateImages", len(prepared))
    require_summary_count(summary, "safeHardNegativeCount", len(prepared))
    reviewed_images = summary.get("reviewedImages")
    excluded_images = summary.get("excludedImages")
    if (
        not isinstance(reviewed_images, int)
        or isinstance(reviewed_images, bool)
        or not isinstance(excluded_images, int)
        or isinstance(excluded_images, bool)
        or reviewed_images != len(prepared) + excluded_images
    ):
        raise ValueError("candidate manifest reviewed/excluded counts are inconsistent")

    return prepared, {
        "candidateManifestPath": str(manifest_path),
        "candidateManifestSha256": sha256_file(manifest_path),
        "reviewDecisionsPath": str(review_path),
        "reviewDecisionsSha256": sha256_file(review_path),
        "sourceScreeningBatchPath": str(source_screening_path),
        "sourceScreeningBatchSha256": sha256_file(source_screening_path),
        "authorizationPath": str(authorization_path),
        "authorizationSha256": sha256_file(authorization_path),
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    minimum = int(args.minimum_images)
    if minimum < FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES:
        raise ValueError(
            "minimum-images cannot lower the formal 100-image hard-negative gate"
        )
    manifest_paths = [Path(value).resolve() for value in args.candidate_manifest]
    if len({str(path).casefold() for path in manifest_paths}) != len(manifest_paths):
        raise ValueError("candidate-manifest arguments must be unique")

    all_items: list[dict[str, Any]] = []
    input_records: list[dict[str, str]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for path in manifest_paths:
        if not path.is_file():
            raise ValueError(f"candidate manifest is missing: {path}")
        items, input_record = validate_candidate_review(path, read_json(path, "candidate manifest"))
        for item in items:
            file_name = str(item["fileName"])
            image_hash = str(item["imageSha256"])
            if file_name in seen_names:
                raise ValueError(f"duplicate hard-negative fileName across batches: {file_name}")
            if image_hash in seen_hashes:
                raise ValueError(f"duplicate hard-negative image SHA-256 across batches: {image_hash}")
            seen_names.add(file_name)
            seen_hashes.add(image_hash)
            all_items.append(item)
        input_records.append(input_record)

    all_items.sort(key=lambda item: (str(item["fileName"]), str(item["imageSha256"])))
    approved = len(all_items) >= minimum
    training_use = "permitted" if approved else "prohibited"
    output_items = [dict(item, trainingUse=training_use) for item in all_items]
    decision = (
        "approved_hard_negative_manifest"
        if approved
        else "hold_insufficient_hard_negatives"
    )
    common = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": approved,
        "status": "PASS" if approved else "HOLD",
        "decision": decision,
        "trainingUse": training_use,
        "inputs": input_records,
        "summary": {
            "candidateManifestCount": len(manifest_paths),
            "reviewedHardNegativeImages": len(output_items),
            "sourceGroupCount": len({item["sourceGroup"] for item in output_items}),
            "minimumRequiredImages": minimum,
            "gapToMinimum": max(0, minimum - len(output_items)),
            "duplicateFileNames": 0,
            "duplicateImageSha256": 0,
        },
        "invariants": {
            "allCandidateManifestsAndReviewDecisionsHashBound": True,
            "allCurrentImageBytesMatch": True,
            "allOriginalResolutionVisualReviewsPass": True,
            "allAuthorizationACommercialTrainingEligible": True,
            "allReviewedSourceIsolationEvidencePass": True,
            "templatesIndependentTipsCollagesLowQualityAndCroppedRejected": True,
            "uniqueFileNamesAndImageSha256": True,
            "formalMinimumCannotBeLowered": True,
            "insufficientPoolRemainsTrainingProhibited": True,
        },
        "errors": [],
    }
    if approved:
        common["itemsSha256"] = canonical_sha256(output_items)
        common["items"] = output_items
    else:
        common["candidateItemsSha256"] = canonical_sha256(output_items)
        common["candidateItems"] = output_items
    return common


def verify_approved_report(
    path: Path,
    minimum_images: int = FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES,
) -> dict[str, Any]:
    """Replay an approved manifest from current review and image evidence."""

    report_path = path.resolve()
    report = read_json(report_path, "approved hard-negative manifest")
    if (
        report.get("schemaVersion") != 2
        or report.get("ok") is not True
        or report.get("status") != "PASS"
        or report.get("decision") != "approved_hard_negative_manifest"
        or report.get("trainingUse") != "permitted"
    ):
        raise ValueError("hard-negative manifest is not an approved schema v2 report")
    inputs = report.get("inputs")
    items = report.get("items")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("approved hard-negative manifest inputs are missing")
    if not isinstance(items, list) or len(items) < minimum_images:
        raise ValueError(
            f"approved hard-negative manifest has fewer than {minimum_images} items"
        )

    manifest_paths: list[str] = []
    for number, evidence in enumerate(inputs, start=1):
        if not isinstance(evidence, dict):
            raise ValueError(f"approved input {number} must be an object")
        candidate_path = require_current_file(
            evidence.get("candidateManifestPath"),
            evidence.get("candidateManifestSha256"),
            f"approved input {number} candidate manifest",
        )
        require_current_file(
            evidence.get("reviewDecisionsPath"),
            evidence.get("reviewDecisionsSha256"),
            f"approved input {number} review decisions",
        )
        require_current_file(
            evidence.get("sourceScreeningBatchPath"),
            evidence.get("sourceScreeningBatchSha256"),
            f"approved input {number} source screening",
        )
        require_current_file(
            evidence.get("authorizationPath"),
            evidence.get("authorizationSha256"),
            f"approved input {number} authorization",
        )
        manifest_paths.append(str(candidate_path))

    replay = build(
        argparse.Namespace(
            candidate_manifest=manifest_paths,
            minimum_images=max(FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES, minimum_images),
        )
    )
    expected_items = replay.get("items")
    if replay.get("ok") is not True or not isinstance(expected_items, list):
        raise ValueError("hard-negative evidence no longer meets the formal approval gate")
    if report.get("itemsSha256") != canonical_sha256(items):
        raise ValueError("approved hard-negative manifest items SHA-256 drift")
    if items != expected_items:
        raise ValueError("approved hard-negative manifest differs from current replayed evidence")
    if report.get("summary") != replay.get("summary"):
        raise ValueError("approved hard-negative manifest summary differs from current replay")
    if report.get("invariants") != replay.get("invariants"):
        raise ValueError("approved hard-negative manifest invariants differ from current replay")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize reviewed hard-negative candidate manifests."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--candidate-manifest",
        action="append",
        help="Candidate-only manifest path; repeat for additional reviewed batches.",
    )
    mode.add_argument(
        "--verify-report",
        help="Replay a previously approved schema v2 manifest from current evidence.",
    )
    parser.add_argument(
        "--minimum-images",
        type=int,
        default=FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES,
    )
    parser.add_argument("--output")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        report = verify_approved_report(report_path, args.minimum_images)
        print(
            json.dumps(
                {
                    "ok": True,
                    "decision": report["decision"],
                    "reviewedHardNegativeImages": report["summary"][
                        "reviewedHardNegativeImages"
                    ],
                    "report": str(report_path),
                },
                ensure_ascii=True,
            )
        )
        return
    if not args.output:
        parser.error("--output is required with --candidate-manifest")
    output_path = Path(args.output).resolve()
    if output_path.exists() and not args.overwrite:
        raise ValueError(f"output already exists; pass --overwrite to replace it: {output_path}")
    report = build(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "decision": report["decision"],
                **report["summary"],
                "output": str(output_path),
            },
            ensure_ascii=True,
        )
    )
    if report["ok"] is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
