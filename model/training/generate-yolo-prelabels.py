from __future__ import annotations

import argparse
import hashlib
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
    parser.add_argument("--source-group")
    parser.add_argument(
        "--workspace-manifest",
        help="Hash-bound annotation workspace manifest providing each image sourceGroup.",
    )
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--device", default="0")
    parser.add_argument("--max-det", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_image_entries(
    image_dir: Path, workspace_manifest: str | None, source_group: str | None
) -> tuple[list[Path], dict[str, dict[str, object]], Path | None]:
    if workspace_manifest:
        manifest_path = Path(workspace_manifest).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("ok") is not True or manifest.get("decision") != "annotation_workspace_ready_candidate_only":
            raise ValueError("workspace manifest must be a passing candidate-only annotation workspace")
        if Path(str(manifest.get("imageDir", ""))).resolve() != image_dir:
            raise ValueError("workspace manifest imageDir does not match --image-dir")
        entries = manifest.get("items", [])
        by_file = {str(item.get("fileName", "")): item for item in entries}
        if len(by_file) != len(entries):
            raise ValueError("workspace manifest contains duplicate or empty fileName values")
        image_paths = []
        for file_name in sorted(by_file):
            item = by_file[file_name]
            image_path = (image_dir / file_name).resolve()
            if image_path.parent != image_dir or not image_path.is_file():
                raise ValueError(f"workspace image is missing or unsafe: {file_name}")
            if sha256_file(image_path) != item.get("sha256"):
                raise ValueError(f"workspace image hash changed: {file_name}")
            if not str(item.get("sourceGroup", "")).strip():
                raise ValueError(f"workspace image sourceGroup is empty: {file_name}")
            if item.get("trainingUse") != "prohibited" or item.get("annotationTruthStatus") != "not-started":
                raise ValueError(f"workspace image has unsafe eligibility state: {file_name}")
            image_paths.append(image_path)
        return image_paths, by_file, manifest_path
    if not source_group or not source_group.strip():
        raise ValueError("--source-group is required when --workspace-manifest is not provided")
    image_paths = sorted(
        path for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    return image_paths, {
        path.name: {
            "fileName": path.name,
            "sha256": sha256_file(path),
            "sourceGroup": source_group.strip(),
            "trainingUse": "prohibited",
            "annotationTruthStatus": "not-started",
        }
        for path in image_paths
    }, None


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

    image_paths, entries_by_file, manifest_path = load_image_entries(
        image_dir, args.workspace_manifest, args.source_group
    )
    if not image_paths:
        raise RuntimeError(f"no supported images found in {image_dir}")

    model_path = Path(args.model).resolve()
    if not model_path.is_file():
        raise ValueError(f"model file not found: {model_path}")
    if args.dry_run:
        report = {
            "version": "nail-texture-yolo-prelabel/v2",
            "ok": True,
            "decision": "prelabel_input_validation_pass_candidate_generation_not_run",
            "model": str(model_path),
            "modelSha256": sha256_file(model_path),
            "imageDir": str(image_dir),
            "workspaceManifest": str(manifest_path) if manifest_path else None,
            "workspaceManifestSha256": sha256_file(manifest_path) if manifest_path else None,
            "imageCount": len(image_paths),
            "items": [
                {
                    "fileName": path.name,
                    "sha256": entries_by_file[path.name]["sha256"],
                    "sourceGroup": entries_by_file[path.name]["sourceGroup"],
                }
                for path in image_paths
            ],
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "decision": report["decision"], "imageCount": len(image_paths)}))
        return

    model = YOLO(str(model_path))
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
        entry = entries_by_file[image_path.name]
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
                "sourceGroup": entry["sourceGroup"],
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
            "sha256": entry["sha256"],
            "sourceGroup": entry["sourceGroup"],
            "candidateCount": len(annotations),
            "meanConfidence": round(sum(a["attributes"]["confidence"] for a in annotations) / len(annotations), 6) if annotations else 0,
            "annotationPath": str(annotation_path),
            "overlayPath": str(overlay_path),
            "decision": "candidate_only_not_training_truth",
        })

    report = {
        "version": "nail-texture-yolo-prelabel/v2",
        "ok": True,
        "decision": "candidate_only_not_training_truth",
        "model": str(model_path),
        "modelSha256": sha256_file(model_path),
        "imageDir": str(image_dir),
        "sourceGroup": args.source_group,
        "workspaceManifest": str(manifest_path) if manifest_path else None,
        "workspaceManifestSha256": sha256_file(manifest_path) if manifest_path else None,
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
