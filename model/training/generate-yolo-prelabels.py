from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from ultralytics import YOLO

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate review-only YOLO segmentation prelabels.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--annotation-dir", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source-group", required=True)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--device", default="0")
    parser.add_argument("--max-det", type=int, default=12)
    return parser


def polygon_area(points: list[dict[str, float]]) -> float:
    coordinates = [(point["x"], point["y"]) for point in points]
    return abs(sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(coordinates, coordinates[1:] + coordinates[:1], strict=True)
    )) / 2


def main() -> None:
    args = build_parser().parse_args()
    image_dir = Path(args.image_dir).resolve()
    annotation_dir = Path(args.annotation_dir).resolve()
    overlay_dir = Path(args.overlay_dir).resolve()
    report_path = Path(args.report).resolve()
    annotation_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(
        path for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not image_paths:
        raise RuntimeError(f"no supported images found in {image_dir}")

    model = YOLO(str(Path(args.model).resolve()))
    results = model.predict(
        source=[str(path) for path in image_paths],
        conf=args.conf,
        iou=args.iou,
        imgsz=args.imgsz,
        device=args.device,
        max_det=args.max_det,
        retina_masks=True,
        stream=True,
        verbose=False,
    )

    items = []
    total_candidates = 0
    for image_path, result in zip(image_paths, results, strict=True):
        with Image.open(image_path) as source:
            width, height = source.size
        annotations = []
        confidences = result.boxes.conf.cpu().tolist() if result.boxes is not None else []
        polygons = result.masks.xy if result.masks is not None else []
        for index, (polygon, confidence) in enumerate(zip(polygons, confidences, strict=True), start=1):
            points = [{"x": float(x), "y": float(y)} for x, y in np.asarray(polygon)]
            if len(points) < 4 or polygon_area(points) < 16:
                continue
            annotations.append({
                "id": f"n{index}",
                "label": "nail_texture",
                "polygon": points,
                "attributes": {
                    "fingerHint": "unknown",
                    "shape": "unknown",
                    "quality": 2,
                    "occluded": False,
                    "artificialTip": False,
                    "annotationMethod": "yolo-real-seed-prelabel",
                    "confidence": round(float(confidence), 6),
                    "reviewRequired": True,
                },
            })

        annotation_path = annotation_dir / f"{image_path.stem}.json"
        annotation_path.write_text(json.dumps({
            "version": "nail-texture-dataset/v1",
            "decision": "candidate_only_not_training_truth",
            "image": {
                "id": image_path.stem,
                "fileName": image_path.name,
                "width": width,
                "height": height,
                "sourceGroup": args.source_group,
                "negative": False,
            },
            "annotations": annotations,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        overlay_path = overlay_dir / f"{image_path.stem}-yolo-prelabel-overlay.jpg"
        plotted = result.plot()
        Image.fromarray(plotted[..., ::-1]).save(overlay_path, quality=88)
        total_candidates += len(annotations)
        items.append({
            "fileName": image_path.name,
            "candidateCount": len(annotations),
            "meanConfidence": round(sum(a["attributes"]["confidence"] for a in annotations) / len(annotations), 6) if annotations else 0,
            "annotationPath": str(annotation_path),
            "overlayPath": str(overlay_path),
            "decision": "candidate_only_not_training_truth",
        })

    report = {
        "version": "nail-texture-yolo-prelabel/v1",
        "ok": True,
        "decision": "candidate_only_not_training_truth",
        "model": str(Path(args.model).resolve()),
        "imageDir": str(image_dir),
        "sourceGroup": args.source_group,
        "settings": {"conf": args.conf, "iou": args.iou, "imgsz": args.imgsz, "maxDet": args.max_det},
        "imageCount": len(items),
        "imagesWithCandidates": sum(1 for item in items if item["candidateCount"] > 0),
        "imagesWithoutCandidates": sum(1 for item in items if item["candidateCount"] == 0),
        "totalCandidates": total_candidates,
        "candidateCountHistogram": {
            str(count): sum(1 for item in items if item["candidateCount"] == count)
            for count in sorted({item["candidateCount"] for item in items})
        },
        "items": items,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("ok", "decision", "imageCount", "imagesWithCandidates", "imagesWithoutCandidates", "totalCandidates", "candidateCountHistogram")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()