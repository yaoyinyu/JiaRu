from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


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


def read_dataset_yaml(path: Path) -> tuple[Path, str]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dataset.yaml is not an object")
    root_value = payload.get("path", ".")
    root = (path.parent / str(root_value)).resolve()
    split = str(payload.get("train", "images/train"))
    return root, split


def resolve_label_root(root: Path, image_root: Path) -> Path:
    relative = image_root.relative_to(root)
    parts = list(relative.parts)
    if "images" not in parts:
        raise ValueError("training image path does not contain an images segment")
    parts[parts.index("images")] = "labels"
    return root.joinpath(*parts)


def load_role_records(dataset_root: Path) -> dict[str, dict[str, str]]:
    source = dataset_root / "metadata" / "sources-isolation.csv"
    if not source.is_file():
        raise FileNotFoundError(f"source isolation metadata is missing: {source}")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records: dict[str, dict[str, str]] = {}
    for row in rows:
        name = str(row.get("fileName", ""))
        if not name or name in records:
            raise ValueError("source isolation metadata contains a missing or duplicate fileName")
        records[name] = {key: str(value or "") for key, value in row.items()}
    return records


def parse_yolo_polygons(path: Path, width: int, height: int) -> list[np.ndarray]:
    masks: list[np.ndarray] = []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return masks
    for line_number, line in enumerate(text.splitlines(), start=1):
        fields = line.split()
        if len(fields) < 7 or (len(fields) - 1) % 2:
            raise ValueError(f"invalid polygon at {path}:{line_number}")
        coordinates = np.asarray([float(value) for value in fields[1:]], dtype=np.float32)
        points = coordinates.reshape(-1, 2)
        points[:, 0] *= width
        points[:, 1] *= height
        points[:, 0] = np.clip(points[:, 0], 0, width - 1)
        points[:, 1] = np.clip(points[:, 1], 0, height - 1)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [np.rint(points).astype(np.int32)], 1)
        if int(mask.sum()) == 0:
            raise ValueError(f"empty truth polygon at {path}:{line_number}")
        masks.append(mask)
    return masks


def resize_binary(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    if mask.shape == (height, width):
        return (mask > 0).astype(np.uint8)
    return (
        cv2.resize(mask.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST)
        > 0
    ).astype(np.uint8)


def mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    intersection = int(np.logical_and(left, right).sum())
    if intersection == 0:
        return 0.0
    union = int(np.logical_or(left, right).sum())
    return intersection / union if union else 0.0


def mask_bounds(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ValueError("prediction mask is empty")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def proposal_crop(
    rgb: np.ndarray,
    mask: np.ndarray,
    output_size: int,
    context_scale: float,
) -> Image.Image:
    height, width = mask.shape
    min_x, min_y, max_x, max_y = mask_bounds(mask)
    box_width = max_x - min_x
    box_height = max_y - min_y
    side = max(8.0, max(box_width, box_height) * context_scale)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    x0 = max(0, int(round(center_x - side / 2)))
    y0 = max(0, int(round(center_y - side / 2)))
    x1 = min(width, int(round(center_x + side / 2)))
    y1 = min(height, int(round(center_y + side / 2)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("proposal crop is empty")
    rgb_crop = rgb[y0:y1, x0:x1]
    mask_crop = (mask[y0:y1, x0:x1] * 255).astype(np.uint8)
    rgb_resized = cv2.resize(rgb_crop, (output_size, output_size), interpolation=cv2.INTER_AREA)
    mask_resized = cv2.resize(
        mask_crop, (output_size, output_size), interpolation=cv2.INTER_NEAREST
    )
    rgba = np.dstack([rgb_resized, mask_resized])
    return Image.fromarray(rgba, mode="RGBA")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a train-role-only masked proposal corpus for the nail verifier."
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--device", default="0")
    parser.add_argument("--proposal-confidence", type=float, default=0.01)
    parser.add_argument("--proposal-iou", type=float, default=0.7)
    parser.add_argument("--max-det", type=int, default=30)
    parser.add_argument("--positive-iou", type=float, default=0.5)
    parser.add_argument("--negative-iou", type=float, default=0.1)
    parser.add_argument("--crop-size", type=int, default=96)
    parser.add_argument("--context-scale", type=float, default=2.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_yaml = Path(args.dataset).resolve()
    weights = Path(args.weights).resolve()
    output = Path(args.output).resolve()
    if not dataset_yaml.is_file() or not weights.is_file():
        raise FileNotFoundError("dataset or weights are missing")
    if output.exists():
        raise ValueError(f"output must be fresh: {output}")
    if not 0 <= args.negative_iou < args.positive_iou <= 1:
        raise ValueError("IoU label thresholds are invalid")
    if args.crop_size < 32 or args.context_scale <= 1:
        raise ValueError("crop size or context scale is invalid")

    dataset_root, train_relative = read_dataset_yaml(dataset_yaml)
    image_root = (dataset_root / train_relative).resolve()
    label_root = resolve_label_root(dataset_root, image_root)
    all_role_records = load_role_records(dataset_root)
    role_records = {
        name: record
        for name, record in all_role_records.items()
        if record.get("split") == "train"
    }
    images = sorted(
        path
        for path in image_root.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        raise ValueError("training split has no images")
    if set(path.name for path in images) != set(role_records):
        raise ValueError("training images and source isolation metadata differ")
    for image in images:
        role = role_records[image.name]
        if role.get("split") != "train" or role.get("role") not in {
            "train-positive",
            "hard-negative",
        }:
            raise ValueError(f"non-train role entered verifier corpus: {image.name}")
        if role.get("imageSha256") != sha256_file(image):
            raise ValueError(f"image hash drift: {image.name}")

    from ultralytics import YOLO

    model = YOLO(str(weights))
    crop_root = output / "crops"
    records: list[dict[str, Any]] = []
    duplicate_or_partial_negatives = 0
    skipped_empty = 0
    prediction_total = 0

    results = model.predict(
        source=str(image_root),
        imgsz=args.imgsz,
        conf=args.proposal_confidence,
        iou=args.proposal_iou,
        max_det=args.max_det,
        device=args.device,
        retina_masks=True,
        stream=True,
        verbose=False,
    )
    expected_images = {path.resolve() for path in images}
    processed_images: set[Path] = set()
    for result in results:
        image_path = Path(str(result.path)).resolve()
        if image_path not in expected_images or image_path in processed_images:
            raise ValueError(f"prediction stream contains an unknown or duplicate image: {image_path}")
        processed_images.add(image_path)
        bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"cannot decode image: {image_path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        label_path = label_root / f"{image_path.stem}.txt"
        if not label_path.is_file():
            raise FileNotFoundError(f"label is missing: {label_path}")
        truth_masks = parse_yolo_polygons(label_path, width, height)
        role = role_records[image_path.name]
        if role["role"] == "hard-negative" and truth_masks:
            raise ValueError(f"hard negative has truth masks: {image_path.name}")
        if role["role"] == "train-positive" and not truth_masks:
            raise ValueError(f"positive image has no truth masks: {image_path.name}")

        if result.masks is None or result.boxes is None:
            continue
        masks = result.masks.data.detach().cpu().numpy()
        scores = result.boxes.conf.detach().cpu().numpy()
        if len(masks) != len(scores):
            raise ValueError("prediction masks and scores differ")
        prediction_total += len(scores)
        prediction_masks = [resize_binary(raw_mask, width, height) for raw_mask in masks]
        overlaps_by_prediction = [
            [mask_iou(prediction_mask, truth) for truth in truth_masks]
            for prediction_mask in prediction_masks
        ]
        matched_predictions: set[int] = set()
        used_truth: set[int] = set()
        pairs = sorted(
            (
                (iou, prediction_index, truth_index)
                for prediction_index, overlaps in enumerate(overlaps_by_prediction)
                for truth_index, iou in enumerate(overlaps)
            ),
            reverse=True,
        )
        for iou, prediction_index, truth_index in pairs:
            if iou < args.positive_iou:
                break
            if prediction_index in matched_predictions or truth_index in used_truth:
                continue
            matched_predictions.add(prediction_index)
            used_truth.add(truth_index)

        for index, (prediction_mask, score) in enumerate(
            zip(prediction_masks, scores, strict=True)
        ):
            if int(prediction_mask.sum()) == 0:
                skipped_empty += 1
                continue
            overlaps = overlaps_by_prediction[index]
            best_iou = max(overlaps, default=0.0)
            label = 1 if index in matched_predictions else 0
            if label == 0 and best_iou > args.negative_iou:
                duplicate_or_partial_negatives += 1
            relative_crop = Path("crops") / str(label) / f"{image_path.stem}__p{index:03d}.png"
            crop_path = output / relative_crop
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            proposal_crop(rgb, prediction_mask, args.crop_size, args.context_scale).save(
                crop_path, format="PNG", optimize=True
            )
            mask_digest = hashlib.sha256(prediction_mask.tobytes()).hexdigest()
            records.append(
                {
                    "id": f"{image_path.stem}:p{index:03d}",
                    "label": label,
                    "role": role["role"],
                    "sourceGroup": role["sourceGroup"],
                    "image": str(image_path),
                    "imageSha256": role["imageSha256"],
                    "labelPath": str(label_path),
                    "labelSha256": sha256_file(label_path),
                    "crop": relative_crop.as_posix(),
                    "cropSha256": sha256_file(crop_path),
                    "predictionIndex": index,
                    "predictionScore": round(float(score), 8),
                    "predictionMaskSha256": mask_digest,
                    "bestTruthMaskIou": round(best_iou, 8),
                }
            )

    if processed_images != expected_images:
        missing = sorted(str(path) for path in expected_images - processed_images)
        raise ValueError(f"prediction stream omitted training images: {missing[:5]}")

    records.sort(key=lambda item: item["id"])
    positive_count = sum(item["label"] == 1 for item in records)
    negative_count = sum(item["label"] == 0 for item in records)
    if positive_count < 100 or negative_count < 100:
        raise ValueError(
            f"proposal corpus is too small: positives={positive_count}, negatives={negative_count}"
        )
    manifest = {
        "schemaVersion": 1,
        "decision": "train_role_proposal_verifier_corpus_built",
        "trainingUse": "commercial-model-training",
        "inputs": {
            "datasetYaml": str(dataset_yaml),
            "datasetYamlSha256": sha256_file(dataset_yaml),
            "datasetRoot": str(dataset_root),
            "sourceIsolation": str(dataset_root / "metadata" / "sources-isolation.csv"),
            "sourceIsolationSha256": sha256_file(
                dataset_root / "metadata" / "sources-isolation.csv"
            ),
            "weights": str(weights),
            "weightsSha256": sha256_file(weights),
        },
        "configuration": {
            "imgsz": args.imgsz,
            "proposalConfidence": args.proposal_confidence,
            "proposalIou": args.proposal_iou,
            "maxDet": args.max_det,
            "positiveIou": args.positive_iou,
            "negativeIouDiagnosticBoundary": args.negative_iou,
            "labelPolicy": "one-to-one-greedy-mask-iou-match-positive-all-unmatched-negative",
            "cropSize": args.crop_size,
            "cropChannels": "RGBA=RGB-context+proposal-mask",
            "contextScale": args.context_scale,
        },
        "counts": {
            "sourceImages": len(images),
            "trainPositiveImages": sum(
                item["role"] == "train-positive" for item in role_records.values()
            ),
            "trainHardNegativeImages": sum(
                item["role"] == "hard-negative" for item in role_records.values()
            ),
            "rawPredictions": prediction_total,
            "positiveProposals": positive_count,
            "negativeProposals": negative_count,
            "duplicateOrPartialNegatives": duplicate_or_partial_negatives,
            "skippedEmpty": skipped_empty,
        },
        "rolePolicy": {
            "allowed": ["train-positive", "hard-negative"],
            "valUsedForTraining": False,
            "testUsedForTraining": False,
            "holdoutUsedForTraining": False,
        },
        "recordsSha256": canonical_sha256(records),
        "records": records,
    }
    manifest_path = output / "proposal-corpus-v1.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "ok": True,
        "manifest": str(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        "counts": manifest["counts"],
        "recordsSha256": manifest["recordsSha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
