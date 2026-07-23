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
    parser.add_argument("--weights", required=True)
    parser.add_argument("--hard-negative-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--dataset-role", choices=["training", "independent-holdout"], required=True)
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
