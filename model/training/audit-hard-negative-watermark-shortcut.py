#!/usr/bin/env python3
"""Audit false positives and watermark shortcut sensitivity on hard negatives.

This diagnostic intentionally keeps the reviewed source bytes immutable.  It
compares predictions on the original image with two deterministic derivatives:

* ``crop12`` removes the bottom and right 12 percent before resizing;
* ``blur_corner`` heavily blurs the bottom-right watermark-prone region.

The report distinguishes a training-negative diagnostic from an independent
holdout audit.  A training manifest can prove stability, but never generalized
hard-negative quality by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from PIL import Image, ImageFilter


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"refusing to overwrite report: {path}")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_finalizer() -> ModuleType:
    script = Path(__file__).with_name("finalize-reviewed-hard-negative-manifest.py")
    spec = importlib.util.spec_from_file_location("hard_negative_finalizer", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load hard-negative finalizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_variants(
    items: list[dict[str, Any]], output_dir: Path, workers: int
) -> tuple[dict[str, list[Path]], list[dict[str, Any]]]:
    variants = {
        name: output_dir / "variants" / name
        for name in ("original", "crop12", "blur_corner")
    }
    for directory in variants.values():
        directory.mkdir(parents=True, exist_ok=False)
    def build_one(
        indexed_item: tuple[int, dict[str, Any]],
    ) -> tuple[int, dict[str, Path], dict[str, Any]]:
        index, item = indexed_item
        source = Path(str(item["imagePath"])).resolve()
        file_name = f"negative-{index:03d}.png"
        with Image.open(source) as opened:
            image = opened.convert("RGB")
        original = variants["original"] / file_name
        image.save(original, format="PNG", compress_level=1)

        crop_width = max(1, round(image.width * 0.88))
        crop_height = max(1, round(image.height * 0.88))
        cropped = image.crop((0, 0, crop_width, crop_height)).resize(
            image.size, Image.Resampling.LANCZOS
        )
        crop_path = variants["crop12"] / file_name
        cropped.save(crop_path, format="PNG", compress_level=1)

        corner = image.copy()
        left = round(image.width * 0.70)
        top = round(image.height * 0.82)
        region = corner.crop((left, top, image.width, image.height)).filter(
            ImageFilter.GaussianBlur(radius=max(12, round(min(image.size) * 0.02)))
        )
        corner.paste(region, (left, top))
        blur_path = variants["blur_corner"] / file_name
        corner.save(blur_path, format="PNG", compress_level=1)

        path_record = {
            "original": original,
            "crop12": crop_path,
            "blur_corner": blur_path,
        }
        record = {
            "fileName": item["fileName"],
            "sourceFileName": item.get("sourceFileName"),
            "sourcePath": str(source),
            "sourceSha256": item["imageSha256"],
            "sourceGroup": item["sourceGroup"],
            "width": image.width,
            "height": image.height,
            "variants": {
                "original": {
                    "path": str(original),
                    "sha256": sha256_file(original),
                },
                "crop12": {
                    "path": str(crop_path),
                    "sha256": sha256_file(crop_path),
                    "cropBox": [0, 0, crop_width, crop_height],
                },
                "blur_corner": {
                    "path": str(blur_path),
                    "sha256": sha256_file(blur_path),
                    "region": [left, top, image.width, image.height],
                },
            },
        }
        return index, path_record, record

    indexed_items = list(enumerate(items, start=1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        built = sorted(executor.map(build_one, indexed_items), key=lambda value: value[0])
    paths: dict[str, list[Path]] = {name: [] for name in variants}
    records: list[dict[str, Any]] = []
    for _, path_record, record in built:
        for name in variants:
            paths[name].append(path_record[name])
        records.append(record)
    return paths, records


def prediction_count(result: Any) -> tuple[int, list[float]]:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return 0, []
    confidences = getattr(boxes, "conf", None)
    if confidences is None:
        return len(boxes), []
    return len(boxes), [float(value) for value in confidences.detach().cpu().tolist()]


def require_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def verify_threshold_summary(
    value: Any, label: str, expected_images: int
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    expected_variants = {"original", "crop12", "blur_corner"}
    if set(value) != expected_variants:
        raise ValueError(f"{label} must contain exactly {sorted(expected_variants)}")
    verified: dict[str, dict[str, Any]] = {}
    for variant in sorted(expected_variants):
        summary = value[variant]
        if not isinstance(summary, dict):
            raise ValueError(f"{label}.{variant} must be an object")
        counts = summary.get("counts")
        if (
            not isinstance(counts, list)
            or len(counts) != expected_images
            or any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts)
        ):
            raise ValueError(
                f"{label}.{variant}.counts must contain {expected_images} non-negative integers"
            )
        detections = sum(counts)
        false_positive_images = sum(count > 0 for count in counts)
        if summary.get("images") != expected_images:
            raise ValueError(f"{label}.{variant}.images does not match records")
        if summary.get("detections") != detections:
            raise ValueError(f"{label}.{variant}.detections does not match counts")
        if summary.get("falsePositiveImages") != false_positive_images:
            raise ValueError(
                f"{label}.{variant}.falsePositiveImages does not match counts"
            )
        expected_rate = false_positive_images / expected_images
        if abs(require_number(summary.get("falsePositiveImageRate"), f"{label}.{variant}.falsePositiveImageRate") - expected_rate) > 1e-12:
            raise ValueError(f"{label}.{variant}.falsePositiveImageRate is inconsistent")
        if abs(require_number(summary.get("meanDetectionsPerImage"), f"{label}.{variant}.meanDetectionsPerImage") - detections / expected_images) > 1e-12:
            raise ValueError(f"{label}.{variant}.meanDetectionsPerImage is inconsistent")
        if summary.get("maximumDetectionsPerImage") != max(counts, default=0):
            raise ValueError(
                f"{label}.{variant}.maximumDetectionsPerImage is inconsistent"
            )
        maximum_confidence = require_number(
            summary.get("maximumConfidence"), f"{label}.{variant}.maximumConfidence"
        )
        if not 0 <= maximum_confidence <= 1:
            raise ValueError(f"{label}.{variant}.maximumConfidence must be in [0, 1]")
        verified[variant] = summary
    return verified


def verify_report(report_path: Path) -> dict[str, Any]:
    report = read_json(report_path, "watermark shortcut audit report")
    if report.get("schemaVersion") != 1:
        raise ValueError("watermark shortcut audit schemaVersion must be 1")
    role = report.get("datasetRole")
    if role not in {"training", "independent-holdout"}:
        raise ValueError("datasetRole must be training or independent-holdout")

    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be an object")
    weights_input = inputs.get("weights")
    manifest_input = inputs.get("hardNegativeManifest")
    if not isinstance(weights_input, dict) or not isinstance(manifest_input, dict):
        raise ValueError("weights and hardNegativeManifest inputs are required")
    weights = Path(str(weights_input.get("path", ""))).resolve()
    manifest = Path(str(manifest_input.get("path", ""))).resolve()
    if not weights.is_file() or sha256_file(weights) != weights_input.get("sha256"):
        raise ValueError("weights are missing or their SHA-256 has drifted")
    if not manifest.is_file() or sha256_file(manifest) != manifest_input.get("sha256"):
        raise ValueError("hard-negative manifest is missing or its SHA-256 has drifted")
    manifest_document = read_json(manifest, "hard-negative manifest")
    if manifest_document.get("itemsSha256") != manifest_input.get("itemsSha256"):
        raise ValueError("hard-negative manifest itemsSha256 does not match the audit")

    configuration = report.get("configuration")
    counts = report.get("counts")
    records = report.get("records")
    if not isinstance(configuration, dict) or not isinstance(counts, dict):
        raise ValueError("configuration and counts must be objects")
    if not isinstance(records, list) or len(records) < 100:
        raise ValueError("records must contain at least 100 hard-negative images")
    image_count = len(records)
    if counts != {"images": image_count, "variants": 3, "inferenceViews": image_count * 3}:
        raise ValueError("counts do not match the bound records")
    if canonical_sha256(records) != report.get("recordsSha256"):
        raise ValueError("recordsSha256 does not match records")

    file_names: set[str] = set()
    source_paths: set[str] = set()
    variant_paths: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} must be an object")
        file_name = record.get("fileName")
        source_path = Path(str(record.get("sourcePath", ""))).resolve()
        source_sha256 = record.get("sourceSha256")
        if not isinstance(file_name, str) or not file_name:
            raise ValueError(f"record {index} has no fileName")
        if file_name in file_names:
            raise ValueError(f"duplicate record fileName: {file_name}")
        file_names.add(file_name)
        source_identity = str(source_path).casefold()
        if source_identity in source_paths:
            raise ValueError(f"duplicate record sourcePath: {source_path}")
        source_paths.add(source_identity)
        if not source_path.is_file() or sha256_file(source_path) != source_sha256:
            raise ValueError(f"record {index} source is missing or has drifted")
        variants = record.get("variants")
        if not isinstance(variants, dict) or set(variants) != {
            "original",
            "crop12",
            "blur_corner",
        }:
            raise ValueError(f"record {index} must bind exactly three variants")
        for variant_name, variant in variants.items():
            if not isinstance(variant, dict):
                raise ValueError(f"record {index} variant {variant_name} must be an object")
            variant_path = Path(str(variant.get("path", ""))).resolve()
            variant_identity = str(variant_path).casefold()
            if variant_identity in variant_paths:
                raise ValueError(f"duplicate variant path: {variant_path}")
            variant_paths.add(variant_identity)
            if not variant_path.is_file() or sha256_file(variant_path) != variant.get("sha256"):
                raise ValueError(
                    f"record {index} variant {variant_name} is missing or has drifted"
                )

    deployment = verify_threshold_summary(
        report.get("deploymentThreshold"), "deploymentThreshold", image_count
    )
    verify_threshold_summary(
        report.get("diagnosticThreshold"), "diagnosticThreshold", image_count
    )
    max_false_positive_images = configuration.get("maxFalsePositiveImages")
    max_variant_detection_delta = configuration.get("maxVariantDetectionDelta")
    if (
        isinstance(max_false_positive_images, bool)
        or not isinstance(max_false_positive_images, int)
        or max_false_positive_images < 0
        or isinstance(max_variant_detection_delta, bool)
        or not isinstance(max_variant_detection_delta, int)
        or max_variant_detection_delta < 0
    ):
        raise ValueError("false-positive and variant-delta limits must be non-negative integers")
    original_detections = deployment["original"]["detections"]
    variant_deltas = {
        name: abs(summary["detections"] - original_detections)
        for name, summary in deployment.items()
        if name != "original"
    }
    if report.get("variantDetectionDeltas") != variant_deltas:
        raise ValueError("variantDetectionDeltas do not match deployment counts")
    deployment_pass = all(
        summary["falsePositiveImages"] <= max_false_positive_images
        for summary in deployment.values()
    )
    stability_pass = all(
        delta <= max_variant_detection_delta for delta in variant_deltas.values()
    )
    expected_ok = deployment_pass and stability_pass
    expected_eligible = expected_ok and role == "independent-holdout"
    expected_status = "PASS" if expected_ok else "HOLD"
    expected_decision = (
        "hard_negative_watermark_shortcut_stability_pass"
        if expected_ok
        else "hold_hard_negative_watermark_shortcut_instability"
    )
    if (
        report.get("ok") is not expected_ok
        or report.get("status") != expected_status
        or report.get("decision") != expected_decision
        or report.get("releaseGeneralizationEligible") is not expected_eligible
    ):
        raise ValueError("outer decision fields do not match recomputed evidence")
    return {
        "ok": True,
        "reportPath": str(report_path),
        "reportSha256": sha256_file(report_path),
        "datasetRole": role,
        "imageCount": image_count,
        "status": expected_status,
        "releaseGeneralizationEligible": expected_eligible,
        "weights": str(weights),
        "hardNegativeManifest": str(manifest),
    }


def predict(
    model: Any,
    paths: dict[str, list[Path]],
    confidence: float,
    imgsz: int,
    device: str,
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for variant, image_paths in paths.items():
        results = model.predict(
            source=[str(path) for path in image_paths],
            conf=confidence,
            imgsz=imgsz,
            device=device,
            verbose=False,
            stream=False,
        )
        counts: list[int] = []
        confidences: list[float] = []
        for result in results:
            count, values = prediction_count(result)
            counts.append(count)
            confidences.extend(values)
        false_positive_images = sum(count > 0 for count in counts)
        summaries[variant] = {
            "images": len(counts),
            "falsePositiveImages": false_positive_images,
            "falsePositiveImageRate": false_positive_images / len(counts),
            "detections": sum(counts),
            "meanDetectionsPerImage": sum(counts) / len(counts),
            "maximumDetectionsPerImage": max(counts, default=0),
            "maximumConfidence": max(confidences, default=0.0),
            "counts": counts,
        }
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit hard-negative watermark shortcut sensitivity."
    )
    parser.add_argument("--verify-report")
    parser.add_argument("--weights")
    parser.add_argument("--hard-negative-manifest")
    parser.add_argument("--output")
    parser.add_argument("--artifacts-dir")
    parser.add_argument("--dataset-role", choices=["training", "independent-holdout"])
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--device", default="0")
    parser.add_argument(
        "--workers", type=int, default=min(8, max(1, os.cpu_count() or 1))
    )
    parser.add_argument("--deployment-confidence", type=float, default=0.35)
    parser.add_argument("--diagnostic-confidence", type=float, default=0.20)
    parser.add_argument("--max-false-positive-images", type=int, default=0)
    parser.add_argument("--max-variant-detection-delta", type=int, default=0)
    args = parser.parse_args()
    if args.verify_report:
        forbidden = [
            args.weights,
            args.hard_negative_manifest,
            args.output,
            args.artifacts_dir,
            args.dataset_role,
        ]
        if any(value is not None for value in forbidden):
            raise ValueError("--verify-report cannot be combined with audit inputs")
        verification = verify_report(Path(args.verify_report).resolve())
        print(json.dumps(verification, ensure_ascii=False, indent=2))
        return
    if not all(
        [
            args.weights,
            args.hard_negative_manifest,
            args.output,
            args.artifacts_dir,
            args.dataset_role,
        ]
    ):
        parser.error(
            "--weights, --hard-negative-manifest, --output, --artifacts-dir "
            "and --dataset-role are required unless --verify-report is used"
        )
    if args.workers < 1:
        raise ValueError("--workers must be at least 1")

    weights = Path(args.weights).resolve()
    manifest_path = Path(args.hard_negative_manifest).resolve()
    output = Path(args.output).resolve()
    artifacts_dir = Path(args.artifacts_dir).resolve()
    if not weights.is_file():
        raise ValueError(f"weights are missing: {weights}")
    if output.exists() or artifacts_dir.exists():
        raise ValueError("output and artifacts-dir must not already exist")

    finalizer = load_finalizer()
    manifest = finalizer.verify_approved_report(manifest_path)
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) < 100:
        raise ValueError("hard-negative manifest must contain at least 100 approved items")
    artifacts_dir.mkdir(parents=True)
    paths, records = build_variants(items, artifacts_dir, args.workers)

    try:
        from ultralytics import YOLO

        model = YOLO(str(weights))
        deployment = predict(
            model, paths, args.deployment_confidence, args.imgsz, args.device
        )
        diagnostic = predict(
            model, paths, args.diagnostic_confidence, args.imgsz, args.device
        )
    except Exception:
        shutil.rmtree(artifacts_dir, ignore_errors=True)
        raise

    original_detections = deployment["original"]["detections"]
    variant_deltas = {
        name: abs(summary["detections"] - original_detections)
        for name, summary in deployment.items()
        if name != "original"
    }
    deployment_pass = all(
        summary["falsePositiveImages"] <= args.max_false_positive_images
        for summary in deployment.values()
    )
    stability_pass = all(
        delta <= args.max_variant_detection_delta for delta in variant_deltas.values()
    )
    shortcut_stability_pass = deployment_pass and stability_pass
    independent = args.dataset_role == "independent-holdout"
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": shortcut_stability_pass,
        "status": "PASS" if shortcut_stability_pass else "HOLD",
        "decision": (
            "hard_negative_watermark_shortcut_stability_pass"
            if shortcut_stability_pass
            else "hold_hard_negative_watermark_shortcut_instability"
        ),
        "datasetRole": args.dataset_role,
        "releaseGeneralizationEligible": shortcut_stability_pass and independent,
        "inputs": {
            "weights": {"path": str(weights), "sha256": sha256_file(weights)},
            "hardNegativeManifest": {
                "path": str(manifest_path),
                "sha256": sha256_file(manifest_path),
                "itemsSha256": manifest["itemsSha256"],
            },
        },
        "configuration": {
            "imgsz": args.imgsz,
            "device": args.device,
            "deploymentConfidence": args.deployment_confidence,
            "diagnosticConfidence": args.diagnostic_confidence,
            "maxFalsePositiveImages": args.max_false_positive_images,
            "maxVariantDetectionDelta": args.max_variant_detection_delta,
            "variants": {
                "crop12": "remove bottom/right 12 percent then resize",
                "blur_corner": "blur bottom-right 30 by 18 percent region",
            },
        },
        "counts": {"images": len(items), "variants": 3, "inferenceViews": len(items) * 3},
        "deploymentThreshold": deployment,
        "diagnosticThreshold": diagnostic,
        "variantDetectionDeltas": variant_deltas,
        "recordsSha256": canonical_sha256(records),
        "records": records,
        "limitations": [
            (
                "Training negatives can test shortcut stability but cannot prove "
                "generalization to unseen negatives."
                if not independent
                else "Independent holdout evidence is eligible for release-quality use."
            )
        ],
        "nextActions": (
            ["Run the same audit on a source-isolated, original-resolution-reviewed holdout."]
            if not independent
            else []
        ),
    }
    write_json(output, report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "status": report["status"],
                "releaseGeneralizationEligible": report["releaseGeneralizationEligible"],
                "deploymentThreshold": {
                    name: {
                        "falsePositiveImages": value["falsePositiveImages"],
                        "detections": value["detections"],
                    }
                    for name, value in deployment.items()
                },
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not shortcut_stability_pass:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
