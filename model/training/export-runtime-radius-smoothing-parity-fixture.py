#!/usr/bin/env python3
"""导出运行时半径平滑的跨语言对拍 fixture（方案 S5，2026-11-17）。

从 634 冻结预测 mask 里分层抽 16 枚，记录：
- 拟合出的 2048-bin 半径向量（float32，与 TS Float32Array 同值）
- 裁剪几何（height/width/centerY/centerX）与 angularSamples
- Python 侧按「与 TS 同构的配方」算出的解码指纹与平滑参数

只读冻结证据（运行前校验哈希），只写 tests/fixtures/，不写 model/reviews/。

工具链注意：本脚本只在写文件时用 write_bytes + utf-8，避免 CRLF 污染。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(r"E:\AI Project\Codex\JiaRu")
EVIDENCE_ROOT = REPO_ROOT / "model" / "reviews"
DEFAULT_PLAN = REPO_ROOT / "model" / "training" / "nail-texture-development-cycle-093-bias-neutral-smoothing-plan-v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "radius-smoothing-parity-v1.json"

ANGULAR_SAMPLES = 2048
DEVIATION_RMS_ARC = 0.7
GRID_ARC = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
STRATA = 4
PER_STRATUM = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_mask(mask: np.ndarray) -> str:
    """指纹口径：布尔 mask 按行主序按位打包（bit i 对应 byte i>>3 的第 i&7 位）。"""
    packed = np.packbits(mask.reshape(-1).astype(np.uint8), bitorder="little")
    return hashlib.sha256(packed.tobytes()).hexdigest()


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    if path.exists():
        raise ValueError(f"fixture 已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def guard_output(path: Path) -> None:
    if EVIDENCE_ROOT.resolve() in path.resolve().parents:
        raise ValueError("禁止写入冻结证据目录")
    if (REPO_ROOT / "public" / "models").resolve() in path.resolve().parents:
        raise ValueError("禁止写入生产模型目录")


def load_metric_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("cycle092_metrics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载度量模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- TS 同构配方


def lattice_like_runtime(height: int, width: int, center_y: float, center_x: float, samples: int) -> tuple[np.ndarray, np.ndarray]:
    """对齐 computeRadialLattice：angle→wrapped→floor(angle*N/2π)，distance 存 float32。"""
    grid_y = np.arange(height, dtype=np.float64)[:, None] - center_y
    grid_x = np.arange(width, dtype=np.float64)[None, :] - center_x
    angle = np.arctan2(grid_y, np.broadcast_to(grid_x, (height, width)))
    two_pi = 2 * math.pi
    wrapped = angle - np.floor(angle / two_pi) * two_pi
    bins = np.floor(wrapped * (samples / two_pi)).astype(np.int64)
    bins = np.clip(bins, 0, samples - 1)
    distance = np.hypot(grid_y, np.broadcast_to(grid_x, (height, width))).astype(np.float32)
    return bins.reshape(-1), distance.reshape(-1)


def decode_runtime(radius_f32: np.ndarray, bins: np.ndarray, distance_f32: np.ndarray) -> np.ndarray:
    """对齐 radialMaskLogits + 零阈值：float32 减法后与 0 比较。"""
    values = radius_f32[bins].astype(np.float32)
    logits = (values - distance_f32).astype(np.float32)
    return logits >= np.float32(0.0)


def gaussian_kernel(sigma_bins: float) -> np.ndarray | None:
    if not sigma_bins > 0 or not math.isfinite(sigma_bins):
        return None
    half = max(1, int(math.ceil(3 * sigma_bins)))
    kernel = np.zeros(2 * half + 1, dtype=np.float64)
    total = 0.0
    for offset in range(-half, half + 1):
        weight = math.exp(-0.5 * (offset / sigma_bins) ** 2)
        kernel[offset + half] = weight
        total += weight
    if not total > 0:
        return None
    for index in range(kernel.size):
        kernel[index] /= total
    return kernel


def circular_convolve(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    length = values.size
    half = (kernel.size - 1) // 2
    output = np.zeros(length, dtype=np.float64)
    base = np.arange(length)
    for tap in range(-half, half + 1):
        source = (base + tap + length * (half + 1)) % length
        output += values[source] * kernel[tap + half]
    return output


def rms_delta(left: np.ndarray, right: np.ndarray) -> float:
    total = 0.0
    for index in range(left.size):
        total += float(left[index] - right[index]) ** 2
    return math.sqrt(total / max(1, left.size))


def perimeter_of(radius: np.ndarray, arc_per_bin: float) -> float:
    total = 0.0
    length = radius.size
    for index in range(length):
        delta = float(radius[(index + 1) % length] - radius[index])
        total += math.hypot(arc_per_bin, delta)
    return total


def decoded_area(radius: np.ndarray, bins: np.ndarray, distance: np.ndarray) -> int:
    values = radius[bins].astype(np.float32)
    logits = (values - distance).astype(np.float32)
    return int(np.count_nonzero(logits >= np.float32(0.0)))


def smooth_like_runtime(radius_f32: np.ndarray, bins: np.ndarray, distance: np.ndarray) -> dict[str, Any]:
    """对齐 smoothRadiusVector（RMS 有界循环高斯 + 面积补偿）。"""
    original = radius_f32.astype(np.float64)
    median_radius = float(np.median(original))
    arc_per_bin = 2 * math.pi * max(1.0, median_radius) / original.size

    chosen = original
    chosen_sigma = 0.0
    for sigma in sorted(GRID_ARC):
        kernel = gaussian_kernel(sigma / arc_per_bin)
        if kernel is None:
            continue
        candidate = circular_convolve(original, kernel)
        if rms_delta(candidate, original) <= DEVIATION_RMS_ARC:
            chosen = candidate
            chosen_sigma = sigma
    if chosen_sigma == 0.0:
        return {
            "applied": False,
            "sigmaArcPixels": 0.0,
            "radius": radius_f32,
            "areaCompensationPixels": 0.0,
        }

    target_area = decoded_area(original, bins, distance)
    current_area = decoded_area(chosen, bins, distance)
    perimeter = perimeter_of(chosen, arc_per_bin)
    delta = (target_area - current_area) / max(1.0, perimeter)
    compensation = 0.0
    compensated = chosen
    if math.isfinite(delta) and abs(delta) <= 2:
        shifted = chosen + delta
        remaining = (target_area - decoded_area(shifted, bins, distance)) / max(1.0, perimeter)
        if math.isfinite(remaining) and abs(remaining) <= 2:
            compensated = shifted + remaining
            compensation = delta + remaining
        else:
            compensated = shifted
            compensation = delta
    return {
        "applied": True,
        "sigmaArcPixels": chosen_sigma,
        "radius": compensated.astype(np.float32),
        "areaCompensationPixels": compensation,
    }


def mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    a = left.astype(bool)
    b = right.astype(bool)
    union = int(np.count_nonzero(a | b))
    if union == 0:
        return 1.0
    return float(np.count_nonzero(a & b)) / union


def contour_radius_runtime(mask: np.ndarray) -> tuple[np.ndarray, float, float]:
    """按**运行时原点**（wrapped·N/2π，无 +π）用最大外轮廓拟合 2048-bin 半径向量。

    与 092 模块 contour_radius 的唯一差别是 bin 原点：模块用 floor((θ+π)/2π·N)，
    与 TS computeRadialLattice 相差 N/2 个 bin（半圈）。若不换算，把模块向量直接
    喂给 TS lattice 会得到旋转 180° 的 mask，因此这里按运行时口径重拟合。
    """
    contours = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    if not contours:
        raise ValueError("空轮廓")
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    ys, xs = np.nonzero(mask)
    cy = float(ys.mean())
    cx = float(xs.mean())
    dy = contour[:, 1].astype(np.float64) - cy
    dx = contour[:, 0].astype(np.float64) - cx
    radius = np.hypot(dy, dx)
    angle = np.arctan2(dy, dx)
    two_pi = 2 * math.pi
    wrapped = angle - np.floor(angle / two_pi) * two_pi
    index = np.floor(wrapped * (ANGULAR_SAMPLES / two_pi)).astype(np.int64)
    index = np.clip(index, 0, ANGULAR_SAMPLES - 1)
    order = np.argsort(index, kind="stable")
    sorted_index = index[order]
    sorted_radius = radius[order]
    unique, starts = np.unique(sorted_index, return_index=True)
    maxima = np.maximum.reduceat(sorted_radius, starts)
    vector = np.full(ANGULAR_SAMPLES, np.nan, dtype=np.float64)
    vector[unique] = maxima
    filled = np.nonzero(~np.isnan(vector))[0]
    if filled.size < 16:
        raise ValueError("轮廓覆盖的角度bin过少")
    positions = np.concatenate([filled - ANGULAR_SAMPLES, filled, filled + ANGULAR_SAMPLES])
    values = np.concatenate([vector[filled], vector[filled], vector[filled]])
    return np.interp(np.arange(ANGULAR_SAMPLES), positions, values), cy, cx


def contour_radius_audit(mask: np.ndarray, module: Any) -> tuple[np.ndarray, float, float]:
    return module.contour_radius(mask)


# ---------------------------------------------------------------- 主流程


def collect_cases(plan: dict[str, Any]) -> list[dict[str, Any]]:
    for label in ("evaluationReport", "evaluationPlan", "metricModule"):
        binding = plan["inputs"][label]
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{label}")

    module = load_metric_module(Path(plan["inputs"]["metricModule"]["path"]))
    evaluation = json.loads(Path(plan["inputs"]["evaluationReport"]["path"]).read_text(encoding="utf-8"))
    evaluation_plan = json.loads(Path(plan["inputs"]["evaluationPlan"]["path"]).read_text(encoding="utf-8"))

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    for item in evaluation_plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))

    margin = 12
    cases: list[dict[str, Any]] = []
    for source_index, record in enumerate(evaluation["records"]):
        source_ordinal = source_index + 1
        bundle = np.load(Path(record["candidate"]["prediction"]["path"]))
        shape = tuple(int(v) for v in bundle["maskShape"])
        predictions = module.unpack_bits(bundle["masksPacked"], shape)
        height, width = shape[1], shape[2]

        payloads: list[tuple[dict[str, Any], Any]] = []
        for item in inputs_by_source[source_ordinal]:
            payload = np.load(Path(item["payload"]["path"]))
            if "truthPacked" not in payload.files:
                continue
            payloads.append((item, payload))

        for truth_index, (item, payload) in enumerate(payloads):
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = module.unpack_bits(payload["truthPacked"], payload_shape)
            scores = [module.mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            prediction = predictions[best]

            ys, xs = np.nonzero(truth)
            py, px = np.nonzero(prediction)
            if py.size == 0:
                continue
            expanded = (
                max(0, min(int(ys.min()), int(py.min())) - margin),
                min(height, max(int(ys.max()), int(py.max())) + margin + 1),
                max(0, min(int(xs.min()), int(px.min())) - margin),
                min(width, max(int(xs.max()), int(px.max())) + margin + 1),
            )
            prediction_crop = prediction[expanded[0]:expanded[1], expanded[2]:expanded[3]]
            try:
                vector, center_y, center_x = contour_radius_runtime(prediction_crop)
                vector_audit, _, _ = contour_radius_audit(prediction_crop, module)
            except ValueError:
                continue

            cases.append(
                {
                    "sourceOrdinal": source_ordinal,
                    "truthIndex": truth_index + 1,
                    "fileName": record["identity"]["fileName"],
                    "height": int(prediction_crop.shape[0]),
                    "width": int(prediction_crop.shape[1]),
                    "centerY": center_y,
                    "centerX": center_x,
                    "vector": vector.astype(np.float32),
                    "vectorAudit": vector_audit.astype(np.float64),
                    "predictionCrop": prediction_crop,
                    "area": int(np.count_nonzero(prediction_crop)),
                }
            )
    return cases


def select(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(cases, key=lambda entry: (entry["area"], entry["sourceOrdinal"], entry["truthIndex"]))
    total = len(ordered)
    picked: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for stratum in range(STRATA):
        lower = stratum * total // STRATA
        upper = (stratum + 1) * total // STRATA
        size = upper - lower
        if size <= 0:
            continue
        for fraction in (0.125, 0.375, 0.625, 0.875):
            offset = min(size - 1, int(fraction * size))
            entry = ordered[lower + offset]
            key = (entry["sourceOrdinal"], entry["truthIndex"])
            if key in seen:
                continue
            seen.add(key)
            picked.append(entry)
    return picked[: STRATA * PER_STRATUM]


def build_fixture(plan_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    cases = select(collect_cases(plan))
    if len(cases) < 8:
        raise ValueError("可用样本不足")

    entries: list[dict[str, Any]] = []
    applied_count = 0
    reconstruction_ious: list[float] = []
    convention_mismatches: list[int] = []
    for index, case in enumerate(cases):
        vector32 = case["vector"]
        bins, distance = lattice_like_runtime(
            case["height"], case["width"], case["centerY"], case["centerX"], ANGULAR_SAMPLES
        )
        radius_runtime = decode_runtime(vector32, bins, distance)
        smoothed = smooth_like_runtime(vector32, bins, distance)
        radius_after = smoothed["radius"]
        runtime_after = decode_runtime(radius_after, bins, distance)

        # 自检①：运行时原点拟合的重建与预测 mask 的 IoU（对齐审计里 ~0.998 的保真度）
        reconstruction_iou = mask_iou(case["predictionCrop"], radius_runtime.reshape(case["height"], case["width"]))
        reconstruction_ious.append(reconstruction_iou)

        # 自检②：审计原点（floor((θ+π)/2π·N)）与运行时原点重建的差异像素数，应为 0
        grid_y = np.arange(case["height"], dtype=np.float64)[:, None] - case["centerY"]
        grid_x = np.arange(case["width"], dtype=np.float64)[None, :] - case["centerX"]
        distance64 = np.hypot(grid_y, np.broadcast_to(grid_x, (case["height"], case["width"]))).reshape(-1)
        theta = np.arctan2(grid_y, np.broadcast_to(grid_x, (case["height"], case["width"])))
        bin_audit = (np.floor((theta + math.pi) / (2 * math.pi) * ANGULAR_SAMPLES).astype(np.int64) % ANGULAR_SAMPLES).reshape(-1)
        audit_before = distance64 <= case["vectorAudit"][bin_audit]
        convention_mismatch = int(np.count_nonzero(audit_before != radius_runtime))
        convention_mismatches.append(convention_mismatch)

        if smoothed["applied"]:
            applied_count += 1

        entries.append(
            {
                "index": index,
                "sourceOrdinal": case["sourceOrdinal"],
                "truthIndex": case["truthIndex"],
                "fileName": case["fileName"],
                "height": case["height"],
                "width": case["width"],
                "centerY": case["centerY"],
                "centerX": case["centerX"],
                "angularSamples": ANGULAR_SAMPLES,
                "area": case["area"],
                "reconstructionIoU": round(reconstruction_iou, 9),
                "radius": {
                    "dtype": "float32",
                    "byteOrder": "little",
                    "encoding": "base64",
                    "base64": base64.b64encode(vector32.astype("<f4").tobytes()).decode("ascii"),
                },
                "expected": {
                    "applied": bool(smoothed["applied"]),
                    "sigmaArcPixels": float(smoothed["sigmaArcPixels"]),
                    "areaCompensationPixels": round(float(smoothed["areaCompensationPixels"]), 9),
                    "areaBefore": int(np.count_nonzero(radius_runtime)),
                    "areaAfter": int(np.count_nonzero(runtime_after)),
                    "sha256Before": sha256_mask(radius_runtime.reshape(case["height"], case["width"])),
                    "sha256After": sha256_mask(runtime_after.reshape(case["height"], case["width"])),
                },
            }
        )

    return {
        "schemaVersion": 1,
        "name": "radius-smoothing-parity-v1",
        "purpose": "运行时 smoothRadiusVector 与 Python 参考实现的逐位一致性对拍（方案 S5）。",
        "recipe": {
            "lattice": "computeRadialLattice：angle=atan2(dy,dx)，wrapped=angle-floor(angle/2π)·2π，bin=floor(wrapped·N/2π)，distance=float32(hypot)",
            "decode": "float32(float32(radius[bin]) − distance) ≥ 0（对齐 radialMaskLogits 零阈值）",
            "smoothing": {
                "mode": "rms-bounded-gaussian",
                "deviationRmsArcPixels": DEVIATION_RMS_ARC,
                "gridArcPixels": GRID_ARC,
                "areaCompensation": True,
                "arcPerBin": "2π·max(1, median(radius)) / bins",
                "kernel": "half=max(1,ceil(3σ))；权重 exp(−0.5·(k/σ)²) 归一化",
            },
            "sha256Mask": "布尔 mask 按行主序 packbits(bitorder=little) 后 sha256",
        },
        "source": {
            "plan": str(plan_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "planSha256": sha256_file(plan_path),
            "note": "半径向量由冻结预测 mask 的最大外轮廓拟合，fixture 不含任何真值像素。",
        },
        "selection": {
            "strategy": "按预测 mask 面积排序后四分层，每层取 0.125/0.375/0.625/0.875 位次",
            "count": len(entries),
            "appliedCount": applied_count,
            "minReconstructionIoU": round(min(reconstruction_ious), 9),
            "meanReconstructionIoU": round(sum(reconstruction_ious) / len(reconstruction_ious), 9),
            "maxConventionMismatchPixels": max(convention_mismatches),
        },
        "binOriginNote": (
            "审计模块 contour_radius 用 floor((θ+π)/2π·N)%N，TS computeRadialLattice 用 floor(wrapped·N/2π)，"
            "两者原点半圈（N/2 bin）。本 fixture 的半径向量按运行时原点重拟合；"
            "minReconstructionIoU 与 maxConventionMismatchPixels 用于确认两种口径重建等价。"
        ),
        "cases": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    guard_output(arguments.output)

    fixture = build_fixture(arguments.plan)
    payload = (json.dumps(fixture, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    write_bytes_atomic(arguments.output, payload)
    selection = fixture["selection"]
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "cases": selection["count"],
                "applied": selection["appliedCount"],
                "minReconstructionIoU": selection["minReconstructionIoU"],
                "maxConventionMismatchPixels": selection["maxConventionMismatchPixels"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
