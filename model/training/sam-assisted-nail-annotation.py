from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import FastSAM, SAM


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert human/vision supplied nail boxes into reviewed SAM2 polygon annotations."
    )
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--annotation-dir", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--model", default="sam2.1_t.pt")
    parser.add_argument("--engine", choices=["sam2", "fastsam"], default="sam2")
    parser.add_argument(
        "--prompt-mode",
        choices=["box", "center", "box-center", "center-negative-corners"],
        default="center-negative-corners",
        help="SAM2 prompt strategy. Tight reviewed boxes should normally use box mode.",
    )
    parser.add_argument("--report", required=True)
    return parser


def polygon_from_mask(mask: np.ndarray, center: tuple[int, int]) -> list[dict[str, float]]:
    binary = (mask > 0.5).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise RuntimeError("SAM returned an empty mask")
    containing = [contour for contour in contours if cv2.pointPolygonTest(contour, center, False) >= 0]
    contour = max(containing or contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 16:
        raise RuntimeError("SAM mask contour is too small")
    epsilon = max(1.0, 0.003 * cv2.arcLength(contour, True))
    simplified = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(simplified) < 4:
        raise RuntimeError("SAM mask polygon has fewer than four points")
    return [{"x": float(x), "y": float(y)} for x, y in simplified]


def main() -> None:
    args = build_parser().parse_args()
    prompts_path = Path(args.prompts).resolve()
    image_dir = Path(args.image_dir).resolve()
    annotation_dir = Path(args.annotation_dir).resolve()
    overlay_dir = Path(args.overlay_dir).resolve()
    report_path = Path(args.report).resolve()
    document = json.loads(prompts_path.read_text(encoding="utf-8"))
    exclusions_path = prompts_path.parent / "review" / "data-exclusions.json"
    excluded_files = set()
    if exclusions_path.exists():
        exclusions = json.loads(exclusions_path.read_text(encoding="utf-8"))
        excluded_files = {item["fileName"] for item in exclusions.get("items", [])}
    model = SAM(args.model) if args.engine == "sam2" else FastSAM(args.model)
    annotation_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    errors = []
    fallback_prompt_count = 0

    for item in document["images"]:
        file_name = item["fileName"]
        if file_name in excluded_files:
            continue
        image_path = image_dir / file_name
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        width, height = image.size
        boxes = [
            [box[0] * width, box[1] * height, box[2] * width, box[3] * height]
            for box in item["boxes"]
        ]
        custom_positive_points = item.get("positivePoints", [None] * len(boxes))
        if len(custom_positive_points) != len(boxes):
            raise ValueError(f"{file_name} positivePoints count must match boxes count")
        prompt_modes = item.get("promptModes", [args.prompt_mode] * len(boxes))
        if len(prompt_modes) != len(boxes):
            raise ValueError(f"{file_name} promptModes count must match boxes count")
        allowed_prompt_modes = {"box", "center", "box-center", "center-negative-corners"}
        invalid_prompt_modes = sorted(set(prompt_modes) - allowed_prompt_modes)
        if invalid_prompt_modes:
            raise ValueError(f"{file_name} has invalid promptModes: {invalid_prompt_modes}")
        occluded_indices = set(item.get("occludedIndices", []))
        invalid_occluded_indices = sorted(
            index for index in occluded_indices if not isinstance(index, int) or index < 1 or index > len(boxes)
        )
        if invalid_occluded_indices:
            raise ValueError(
                f"{file_name} occludedIndices must contain 1-based box indices; invalid={invalid_occluded_indices}"
            )
        points = []
        positive_points = []
        labels = []
        for box_index, (x1, y1, x2, y2) in enumerate(boxes):
            inset_x = max(2.0, (x2 - x1) * 0.08)
            inset_y = max(2.0, (y2 - y1) * 0.08)
            item_positive_points = custom_positive_points[box_index]
            if item_positive_points:
                positive_set = [[point[0] * width, point[1] * height] for point in item_positive_points]
            else:
                positive_set = [[(x1 + x2) / 2, (y1 + y2) / 2]]
            positive_points.append(positive_set)
            points.append(
                positive_set
                + [
                    [x1 + inset_x, y1 + inset_y],
                    [x2 - inset_x, y1 + inset_y],
                    [x1 + inset_x, y2 - inset_y],
                    [x2 - inset_x, y2 - inset_y],
                ]
            )
            labels.append([1, 0, 0, 0, 0])
        try:
            mask_outputs = []
            if args.engine == "fastsam":
                base_results = model(
                    str(image_path), retina_masks=True, conf=0.1, iou=0.5, verbose=False
                )
                for prompt_index, box in enumerate(boxes, start=1):
                    result = model.predictor.prompt(base_results, bboxes=[box])[0]
                    if result.masks is None or len(result.masks.data) != 1:
                        raise RuntimeError(
                            f"prompt {prompt_index} (box) FastSAM returned "
                            f"{0 if result.masks is None else len(result.masks.data)} masks instead of one"
                        )
                    mask_outputs.append(result.masks.data[0].cpu().numpy())
            else:
                for prompt_index, (box, point_set, positive_set, label_set, prompt_mode) in enumerate(
                    zip(boxes, points, positive_points, labels, prompt_modes, strict=True),
                    start=1,
                ):
                    prompt_arguments = {"bboxes": [box]}
                    if prompt_mode == "center":
                        prompt_arguments = {
                            "points": [positive_set],
                            "labels": [[1] * len(positive_set)],
                        }
                    elif prompt_mode == "box-center":
                        prompt_arguments.update(
                            points=[positive_set], labels=[[1] * len(positive_set)]
                        )
                    elif prompt_mode == "center-negative-corners":
                        prompt_arguments.update(
                            points=[point_set],
                            labels=[([1] * len(positive_set)) + label_set[1:]],
                        )
                    result = model(str(image_path), verbose=False, **prompt_arguments)[0]
                    if result.masks is None or len(result.masks.data) != 1:
                        result = model(
                            str(image_path),
                            bboxes=[box],
                            verbose=False,
                        )[0]
                        fallback_prompt_count += 1
                    if result.masks is None or len(result.masks.data) != 1:
                        raise RuntimeError(
                            f"prompt {prompt_index} ({prompt_mode}) isolated prompt and box-only fallback returned "
                            f"{0 if result.masks is None else len(result.masks.data)} masks instead of one"
                        )
                    mask_outputs.append(result.masks.data[0].cpu().numpy())
            masks = np.stack(mask_outputs)
            annotations = []
            overlay = image.copy()
            draw = ImageDraw.Draw(overlay, "RGBA")
            for prompt_index, box in enumerate(boxes, start=1):
                draw.rectangle(box, outline=(255, 40, 40, 255), width=3)
                draw.text((box[0], box[1]), f"B{prompt_index}", fill=(255, 40, 40, 255))
            for index, (box, mask) in enumerate(zip(boxes, masks, strict=True), start=1):
                center = (int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2))
                try:
                    polygon = polygon_from_mask(mask, center)
                except Exception as error:
                    raise RuntimeError(
                        f"prompt {index} polygon conversion failed: {error}"
                    ) from error
                annotations.append(
                    {
                        "id": f"n{index}",
                        "label": "nail_texture",
                        "polygon": polygon,
                        "attributes": {
                            "fingerHint": "unknown",
                            "shape": "unknown",
                            "quality": 4,
                            "occluded": index in occluded_indices,
                            "artificialTip": True,
                            "annotationMethod": f"vision-guided-{args.engine}",
                        },
                    }
                )
                points = [(point["x"], point["y"]) for point in polygon]
                draw.polygon(points, fill=(0, 255, 80, 70), outline=(0, 210, 60, 255), width=3)
                draw.text(points[0], str(index), fill=(255, 0, 0, 255), stroke_width=2, stroke_fill=(255, 255, 255, 255))

            annotation_path = annotation_dir / f"{Path(file_name).stem}.json"
            annotation = {
                "version": "nail-texture-dataset/v1",
                "image": {
                    "id": Path(file_name).stem,
                    "fileName": file_name,
                    "width": width,
                    "height": height,
                    "sourceGroup": document["sourceGroup"],
                    "negative": False,
                },
                "annotations": annotations,
            }
            annotation_path.write_text(
                json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            overlay_path = overlay_dir / f"{Path(file_name).stem}-sam-reviewed-overlay.png"
            overlay.save(overlay_path)
            outputs.append(
                {
                    "fileName": file_name,
                    "annotationPath": str(annotation_path),
                    "overlayPath": str(overlay_path),
                    "polygonCount": len(annotations),
                }
            )
        except Exception as error:  # Preserve the rest of the batch for review.
            errors.append({"fileName": file_name, "message": str(error)})

    report = {
        "ok": not errors
        and len(outputs) == sum(item["fileName"] not in excluded_files for item in document["images"]),
        "method": (
            "vision-guided-unprompted-mask-pool-plus-per-box-fastsam"
            if args.engine == "fastsam"
            else "vision-guided-box-center-positive-corner-negative-prompts-plus-sam2"
        ),
        "engine": args.engine,
        "promptMode": args.prompt_mode,
        "model": args.model,
        "promptCount": sum(
            len(item["boxes"]) for item in document["images"] if item["fileName"] not in excluded_files
        ),
        "imageCount": sum(item["fileName"] not in excluded_files for item in document["images"]),
        "excludedFiles": sorted(excluded_files),
        "completedCount": len(outputs),
        "boxOnlyFallbackPromptCount": fallback_prompt_count,
        "errors": errors,
        "outputs": outputs,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
