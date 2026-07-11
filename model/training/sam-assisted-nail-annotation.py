from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import SAM


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert human/vision supplied nail boxes into reviewed SAM2 polygon annotations."
    )
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--annotation-dir", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--model", default="sam2.1_t.pt")
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
    model = SAM(args.model)
    annotation_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    errors = []
    fallback_prompt_count = 0

    for item in document["images"]:
        file_name = item["fileName"]
        image_path = image_dir / file_name
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        width, height = image.size
        boxes = [
            [box[0] * width, box[1] * height, box[2] * width, box[3] * height]
            for box in item["boxes"]
        ]
        points = []
        labels = []
        for x1, y1, x2, y2 in boxes:
            inset_x = max(2.0, (x2 - x1) * 0.08)
            inset_y = max(2.0, (y2 - y1) * 0.08)
            points.append(
                [
                    [(x1 + x2) / 2, (y1 + y2) / 2],
                    [x1 + inset_x, y1 + inset_y],
                    [x2 - inset_x, y1 + inset_y],
                    [x1 + inset_x, y2 - inset_y],
                    [x2 - inset_x, y2 - inset_y],
                ]
            )
            labels.append([1, 0, 0, 0, 0])
        try:
            mask_outputs = []
            for box, point_set, label_set in zip(boxes, points, labels, strict=True):
                result = model(
                    str(image_path),
                    bboxes=[box],
                    points=[point_set],
                    labels=[label_set],
                    verbose=False,
                )[0]
                if result.masks is None or len(result.masks.data) != 1:
                    result = model(
                        str(image_path),
                        bboxes=[box],
                        verbose=False,
                    )[0]
                    fallback_prompt_count += 1
                if result.masks is None or len(result.masks.data) != 1:
                    raise RuntimeError(
                        f"isolated prompt and box-only fallback returned {0 if result.masks is None else len(result.masks.data)} masks instead of one"
                    )
                mask_outputs.append(result.masks.data[0].cpu().numpy())
            masks = np.stack(mask_outputs)
            annotations = []
            overlay = image.copy()
            draw = ImageDraw.Draw(overlay, "RGBA")
            for index, (box, mask) in enumerate(zip(boxes, masks, strict=True), start=1):
                center = (int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2))
                polygon = polygon_from_mask(mask, center)
                annotations.append(
                    {
                        "id": f"n{index}",
                        "label": "nail_texture",
                        "polygon": polygon,
                        "attributes": {
                            "fingerHint": "unknown",
                            "shape": "unknown",
                            "quality": 4,
                            "occluded": False,
                            "artificialTip": True,
                            "annotationMethod": "vision-guided-sam2",
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
        "ok": not errors and len(outputs) == len(document["images"]),
        "method": "vision-guided-box-center-positive-corner-negative-prompts-plus-sam2",
        "model": args.model,
        "promptCount": sum(len(item["boxes"]) for item in document["images"]),
        "imageCount": len(document["images"]),
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
