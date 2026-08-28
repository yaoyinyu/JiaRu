from __future__ import annotations

import cv2
import numpy as np


FEATURE_NAMES = [
    "detector_score",
    "mask_area_ratio",
    "mask_bbox_fill",
    "mask_aspect_ratio",
    "mask_solidity",
    "mask_compactness",
    "mask_centroid_x",
    "mask_centroid_y",
    "inside_skin_ratio",
    "ring_skin_ratio",
    "inside_brightness_mean",
    "inside_brightness_std",
    "inside_saturation_mean",
    "inside_highlight_ratio",
    "inside_edge_mean",
    "ring_color_distance",
]


def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    maximum = np.maximum(np.maximum(red, green), blue)
    minimum = np.minimum(np.minimum(red, green), blue)
    saturation = np.divide(
        maximum - minimum,
        np.maximum(maximum, 1),
        dtype=np.float32,
    )
    primary = (
        (red > 75)
        & (green > 38)
        & (blue > 22)
        & (red > green + 4)
        & (red > blue + 12)
        & (saturation > 0.08)
        & (saturation < 0.68)
    )
    light = (
        (red > 165)
        & (green > 140)
        & (blue > 120)
        & (red >= green + 2)
        & (red >= blue + 8)
        & (saturation < 0.35)
    )
    return np.logical_or(primary, light)


def extract_proposal_features(rgba: np.ndarray, detector_score: float) -> np.ndarray:
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("proposal feature input must be RGBA")
    rgb = rgba[:, :, :3].astype(np.uint8)
    mask = rgba[:, :, 3] >= 128
    height, width = mask.shape
    area = int(mask.sum())
    if area <= 0:
        raise ValueError("proposal feature mask is empty")
    ys, xs = np.nonzero(mask)
    min_x, max_x = int(xs.min()), int(xs.max()) + 1
    min_y, max_y = int(ys.min()), int(ys.max()) + 1
    bbox_width = max_x - min_x
    bbox_height = max_y - min_y
    bbox_area = max(1, bbox_width * bbox_height)
    aspect = max(bbox_width, bbox_height) / max(1, min(bbox_width, bbox_height))

    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contour = max(contours, key=cv2.contourArea)
    contour_area = max(float(cv2.contourArea(contour)), 1.0)
    hull_area = max(float(cv2.contourArea(cv2.convexHull(contour))), 1.0)
    perimeter = max(float(cv2.arcLength(contour, closed=True)), 1.0)

    kernel = np.ones((7, 7), dtype=np.uint8)
    dilated = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1) > 0
    ring = np.logical_and(dilated, ~mask)
    skin = _skin_mask(rgb)
    inside_rgb = rgb[mask].astype(np.float32)
    ring_rgb = rgb[ring].astype(np.float32)
    maximum = inside_rgb.max(axis=1)
    minimum = inside_rgb.min(axis=1)
    saturation = (maximum - minimum) / np.maximum(maximum, 1.0)
    brightness = (
        inside_rgb[:, 0] * 0.299
        + inside_rgb[:, 1] * 0.587
        + inside_rgb[:, 2] * 0.114
    )
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Laplacian(gray, cv2.CV_32F)
    ring_distance = (
        float(np.linalg.norm(inside_rgb.mean(axis=0) - ring_rgb.mean(axis=0)))
        if len(ring_rgb) else 0.0
    )
    return np.asarray(
        [
            float(detector_score),
            area / (width * height),
            area / bbox_area,
            aspect,
            contour_area / hull_area,
            4.0 * np.pi * contour_area / (perimeter * perimeter),
            float(xs.mean() / width),
            float(ys.mean() / height),
            float(skin[mask].mean()),
            float(skin[ring].mean()) if int(ring.sum()) else 0.0,
            float(brightness.mean()),
            float(brightness.std()),
            float(saturation.mean()),
            float(np.logical_and(maximum >= 245, saturation <= 0.12).mean()),
            float(np.abs(edges[mask]).mean()),
            ring_distance,
        ],
        dtype=np.float32,
    )
