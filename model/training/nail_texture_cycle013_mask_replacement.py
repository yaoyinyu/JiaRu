#!/usr/bin/env python3
"""循环013逐甲ROI二值mask映回与一一对应替换运行时。"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from shapely.geometry import Polygon


def square_crop(
    box: tuple[float, float, float, float],
    width: int,
    height: int,
    context_ratio: float,
    minimum_side: int = 16,
) -> tuple[int, int, int, int] | None:
    """以候选框中心构建确定性方形ROI；无法完整落入原图时返回None。"""

    if width <= 0 or height <= 0 or not 0 <= context_ratio <= 2:
        return None
    x0, y0, x1, y1 = (float(value) for value in box)
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)) or x1 <= x0 or y1 <= y0:
        return None
    side = max(minimum_side, int(math.ceil(max(x1 - x0, y1 - y0) * (1 + 2 * context_ratio))))
    if side > width or side > height:
        return None
    center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
    left = min(max(int(round(center_x - side / 2)), 0), width - side)
    top = min(max(int(round(center_y - side / 2)), 0), height - side)
    return left, top, left + side, top + side


def normalized_polygon(points: Any) -> Polygon | None:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] < 3 or array.shape[1] != 2:
        return None
    if not np.isfinite(array).all() or (array < 0).any() or (array > 1).any():
        return None
    polygon = Polygon(array.tolist())
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
        if polygon.geom_type == "MultiPolygon":
            polygon = max(polygon.geoms, key=lambda item: item.area)
    if polygon.geom_type != "Polygon" or polygon.is_empty or polygon.area <= 0:
        return None
    return polygon


def polygon_points(polygon: Polygon) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in list(polygon.exterior.coords)[:-1]]


def polygon_mask(polygon: Polygon, width: int, height: int) -> np.ndarray:
    points = np.asarray(
        [[round(x * (width - 1)), round(y * (height - 1))] for x, y in polygon.exterior.coords],
        dtype=np.int32,
    )
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [points], 1)
    return mask


def mask_iou(left: Polygon, right: Polygon) -> float:
    intersection = left.intersection(right).area
    union = left.union(right).area
    return float(intersection / union) if union else 0.0


def map_roi_binary_mask(
    roi_mask: Any,
    crop_box: tuple[int, int, int, int],
    image_width: int,
    image_height: int,
    threshold: float = 0.5,
) -> tuple[np.ndarray | None, Polygon | None, str | None, dict[str, Any]]:
    """把stage2二维像素mask映回原图；不通过时返回可审计失败原因。"""

    array = np.asarray(roi_mask, dtype=np.float32)
    if array.ndim != 2 or array.size == 0:
        return None, None, "stage2-mask-not-2d", {}
    if not np.isfinite(array).all():
        return None, None, "stage2-mask-not-finite", {}
    left, top, right, bottom = crop_box
    if not (0 <= left < right <= image_width and 0 <= top < bottom <= image_height):
        return None, None, "crop-out-of-bounds", {}
    if not 0 < threshold < 1:
        return None, None, "mask-threshold-invalid", {}
    binary = (array >= threshold).astype(np.uint8)
    if int(binary.sum()) == 0:
        return None, None, "stage2-mask-empty", {"roiMaskPixels": 0}
    if binary[0, :].any() or binary[-1, :].any() or binary[:, 0].any() or binary[:, -1].any():
        return None, None, "stage2-mask-touches-roi-boundary", {"roiMaskPixels": int(binary.sum())}
    crop_width, crop_height = right - left, bottom - top
    mapped_crop = cv2.resize(binary, (crop_width, crop_height), interpolation=cv2.INTER_NEAREST)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mapped_crop, connectivity=8)
    if component_count <= 1:
        return None, None, "stage2-mask-empty-after-map", {"roiMaskPixels": int(binary.sum())}
    component_areas = stats[1:, cv2.CC_STAT_AREA]
    largest_label = int(np.argmax(component_areas)) + 1
    largest = (labels == largest_label).astype(np.uint8)
    full_mask = np.zeros((image_height, image_width), dtype=np.uint8)
    full_mask[top:bottom, left:right] = largest
    contours, _ = cv2.findContours(full_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, "stage2-mask-no-contour", {"roiMaskPixels": int(binary.sum())}
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    if len(contour) < 3:
        return None, None, "stage2-mask-contour-too-small", {"roiMaskPixels": int(binary.sum())}
    points = [[float(x) / image_width, float(y) / image_height] for x, y in contour]
    polygon = normalized_polygon(points)
    if polygon is None:
        return None, None, "stage2-mask-polygon-invalid", {"roiMaskPixels": int(binary.sum())}
    return full_mask, polygon, None, {
        "roiMaskPixels": int(binary.sum()),
        "mappedMaskPixels": int(full_mask.sum()),
        "connectedComponents": int(component_count - 1),
        "discardedComponents": int(component_count - 2),
    }


def replace_candidate_mask(
    stage1_polygon_points: Any,
    stage2_mask: Any,
    stage2_score: float,
    crop_box: tuple[int, int, int, int],
    image_width: int,
    image_height: int,
    contract: dict[str, float],
) -> dict[str, Any]:
    """以stage2像素mask替换一个stage1 mask；任何失败都保留stage1。"""

    stage1_polygon = normalized_polygon(stage1_polygon_points)
    if stage1_polygon is None:
        raise ValueError("stage1 polygon无效，不能作为回退mask")
    fallback_mask = polygon_mask(stage1_polygon, image_width, image_height)
    if not math.isfinite(float(stage2_score)) or float(stage2_score) < float(contract["minimumStage2Score"]):
        return {
            "mask": fallback_mask,
            "polygon": polygon_points(stage1_polygon),
            "maskSource": "stage1-fallback",
            "refinementStatus": "fallback-stage2-score",
            "stage2Accepted": False,
        }
    mapped_mask, stage2_polygon, reason, mapping = map_roi_binary_mask(
        stage2_mask,
        crop_box,
        image_width,
        image_height,
        float(contract["maskThreshold"]),
    )
    if reason is not None or mapped_mask is None or stage2_polygon is None:
        return {
            "mask": fallback_mask,
            "polygon": polygon_points(stage1_polygon),
            "maskSource": "stage1-fallback",
            "refinementStatus": f"fallback-{reason}",
            "stage2Accepted": False,
            "mapping": mapping,
        }
    area_ratio = stage2_polygon.area / stage1_polygon.area
    overlap = mask_iou(stage1_polygon, stage2_polygon)
    stage1_center = stage1_polygon.centroid
    stage2_center = stage2_polygon.centroid
    center_shift = math.hypot(stage2_center.x - stage1_center.x, stage2_center.y - stage1_center.y)
    x0, y0, x1, y1 = stage1_polygon.bounds
    stage1_diagonal = max(math.hypot(x1 - x0, y1 - y0), 1e-9)
    center_shift_ratio = center_shift / stage1_diagonal
    geometry = {
        "areaRatioToStage1": area_ratio,
        "maskIouWithStage1": overlap,
        "centerShiftToStage1Diagonal": center_shift_ratio,
    }
    if not float(contract["minimumAreaRatioToStage1"]) <= area_ratio <= float(contract["maximumAreaRatioToStage1"]):
        reason = "stage2-area-ratio"
    elif overlap < float(contract["minimumMaskIouWithStage1"]):
        reason = "stage2-stage1-overlap"
    elif center_shift_ratio > float(contract["maximumCenterShiftToStage1Diagonal"]):
        reason = "stage2-center-shift"
    else:
        reason = None
    if reason is not None:
        return {
            "mask": fallback_mask,
            "polygon": polygon_points(stage1_polygon),
            "maskSource": "stage1-fallback",
            "refinementStatus": f"fallback-{reason}",
            "stage2Accepted": False,
            "mapping": mapping,
            "geometry": geometry,
        }
    return {
        "mask": mapped_mask,
        "polygon": polygon_points(stage2_polygon),
        "maskSource": "stage2-replacement",
        "refinementStatus": "replaced-with-stage2-pixel-mask",
        "stage2Accepted": True,
        "mapping": mapping,
        "geometry": geometry,
    }


def replace_masks_one_to_one(
    stage1_candidates: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    image_width: int,
    image_height: int,
    contract: dict[str, float],
) -> list[dict[str, Any]]:
    """严格按proposalIndex把每个stage2结果绑定到一个stage1候选。"""

    if len(stage1_candidates) != len(stage2_results):
        raise ValueError("stage1候选数与stage2结果数不一致")
    stage1_indices = [int(item["proposalIndex"]) for item in stage1_candidates]
    stage2_indices = [int(item["proposalIndex"]) for item in stage2_results]
    if len(set(stage1_indices)) != len(stage1_indices) or stage1_indices != stage2_indices:
        raise ValueError("stage1与stage2 proposalIndex不是唯一同序一一对应")
    outputs: list[dict[str, Any]] = []
    for stage1, stage2 in zip(stage1_candidates, stage2_results, strict=True):
        if stage2.get("error"):
            polygon = normalized_polygon(stage1.get("polygon"))
            if polygon is None:
                raise ValueError("stage1 polygon无效，不能回退")
            replacement = {
                "mask": polygon_mask(polygon, image_width, image_height),
                "polygon": polygon_points(polygon),
                "maskSource": "stage1-fallback",
                "refinementStatus": "fallback-stage2-inference-error",
                "stage2Accepted": False,
            }
        else:
            replacement = replace_candidate_mask(
                stage1.get("polygon"),
                stage2.get("mask"),
                float(stage2.get("score", 0.0)),
                tuple(int(value) for value in stage1["cropBox"]),
                image_width,
                image_height,
                contract,
            )
        outputs.append(
            {
                **replacement,
                "proposalIndex": int(stage1["proposalIndex"]),
                "score": float(stage1["score"]),
                "cropBox": [int(value) for value in stage1["cropBox"]],
                "stage2Score": float(stage2.get("score", 0.0)),
            }
        )
    return outputs
