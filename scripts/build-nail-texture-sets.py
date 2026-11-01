#!/usr/bin/env python3
"""美甲纹理套装静态资产构建脚本。

从真实照片出发，调用本机 WeVisOne-VL 抠图服务（POST /matte，task=matting，
query=nails，与 v1.2.177 定版口径一致）取得每实例软边 alpha，再按浏览器端
`src/lib/nail-texture-recognition/` 的同口径数学移植，把每根手指的甲面
提取为「甲尖朝上、紧致裁剪、自带 alpha 轮廓、最长边 ≤256」的 RGBA PNG，
落盘 `public/nail-textures/<setId>/finger-1..5.png`，供
`src/lib/nail-texture-sets.ts` 的 NailTextureSet 契约消费。
实例接受门：服务实例数须恰为 5；bbox 贴编码图边界且面积低于中位数 25% 的
贴边细条按服务假阳性确定性剔除（明细写入报告），剔除后再执行计数门。

数学移植来源（只读参考，口径保持一致）：
- extract-mask-texture.ts：buildFeatheredAlphaMask（羽化半径 2 距离斜坡，
  与软 alpha 取 min）、rotateRgbaPlane（alpha 加权双线性，颜色按覆盖 alpha
  预累加再除回防灰边）、cropRgbaPlaneToAlphaBounds（紧致裁剪边距 2px）、
  downscaleRgbaPlane（面积平均、alpha 加权降采样）。
- mask-orientation.ts：estimateMaskPrincipalAngle（二阶矩主轴，半转角，
  axisRatio<1.1 视为 null）、normalizeHalfTurnAngle。
- vlm-refinement.ts：编码口径（exif 方向修正后长边 ≤1600、JPEG q0.85）、
  alphaGridFromRgba（灰度取 R 通道）、downsampleAlphaGrid（面积平均降采样，
  二值按 128 重算）、实例框在编码图（长边 ≤1600）坐标域。

用法：
    python scripts/build-nail-texture-sets.py \
        --plan output/nail-texture-sets/plan.json \
        --output public/nail-textures \
        --work-dir output/nail-texture-sets

产出：
- --output/<setId>/finger-1..5.png（仅构建成功的套装原子复制过去；
  失败套装保留旧资产不动）
- --work-dir/builds/<时间戳>/（本轮完整产物与失败留档）
- --work-dir/manifest.json（NailTextureSet 结构数组，仅含成功套装）
- --work-dir/build-report.json（逐实例角度、甲尖启发式、耗时与告警）
- --work-dir/cache/<编码字节 SHA-256>.json（服务响应缓存，重跑零推理）
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

import numpy as np
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# 常量（与参考源码同口径）
# ---------------------------------------------------------------------------

MATTE_IMAGE_MAX_EDGE = 1600      # vlm-refinement.ts MATTE_IMAGE_MAX_EDGE
MATTE_ALPHA_MAX_EDGE = 1024      # vlm-refinement.ts MATTE_ALPHA_MAX_EDGE
MATTE_ALPHA_THRESHOLD = 128      # 软边与二值几何共享阈值
MAX_TEXTURE_SIZE = 256           # extract-mask-texture.ts MAX_TEXTURE_SIZE
FEATHER_RADIUS = 2               # extract-mask-texture.ts DEFAULT_FEATHER_RADIUS
NORMALIZATION_EDGE_PAD = 2       # extract-mask-texture.ts NORMALIZATION_EDGE_PAD
AXIS_RATIO_MIN = 1.1             # mask-orientation.ts 近圆甲面阈值
TIP_WIDTH_RATIO = 0.92           # 甲尖启发式：窄/宽带宽度比低于该值才判向
JPEG_QUALITY = 85                # encodeImageForMatte quality 0.85
SERVICE_TIMEOUT_SECONDS = 180    # 单次 /matte 请求超时
BUSY_WALL_CLOCK_LIMIT = 1200     # 503 重试墙钟上限（秒）
NETWORK_RETRY = 5                # 网络异常重试次数
FINGER_FILE_NAMES = (1, 2, 3, 4, 5)  # finger-1..5.png；1=拇指…5=小指
EDGE_SLIVER_AREA_RATIO = 0.25    # 贴边假阳性过滤：实例面积低于中位数该比例且 bbox 贴编码图边界时剔除

# ---------------------------------------------------------------------------
# 编码与哈希
# ---------------------------------------------------------------------------


def compute_scale_to_max_edge(width: int, height: int, max_edge: int) -> float:
    """等比缩放到最长边不超过 max_edge 的比例；已足够小返回 1。"""
    longest = max(width, height)
    if longest <= 0:
        return 1.0
    if longest <= max_edge:
        return 1.0
    return max_edge / longest


def encode_source_image(path: str):
    """读源图 → exif 方向修正 → 长边 ≤1600 → JPEG q0.85 字节。

    返回 (jpeg_bytes, encoded_wh, original_wh)。
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        scale = compute_scale_to_max_edge(width, height, MATTE_IMAGE_MAX_EDGE)
        enc_w = max(1, round(width * scale))
        enc_h = max(1, round(height * scale))
        if (enc_w, enc_h) != (width, height):
            canvas = img.convert("RGB").resize((enc_w, enc_h), Image.BILINEAR)
        else:
            canvas = img.convert("RGB")
        buffer = io.BytesIO()
        canvas.save(buffer, "JPEG", quality=JPEG_QUALITY)
        # 保留全分辨率 RGB 原图（exif 修正后）供后续像素级提取
        full = img.convert("RGB")
    return buffer.getvalue(), (enc_w, enc_h), full.size, full


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 抠图服务调用（503 busy 等待重试；网络异常有限重试；响应按编码字节哈希缓存）
# ---------------------------------------------------------------------------


def request_matte(service_url: str, image_data_uri: str, cache_path: str | None):
    """POST /matte。命中缓存不发起请求；忙时按 retryAfterSeconds 等待重试。

    返回 (response_dict, cache_hit)。
    """
    if cache_path and os.path.isfile(cache_path):
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
        if isinstance(cached, dict) and cached.get("ok") is True:
            return cached, True

    body = json.dumps(
        {"image": image_data_uri, "task": "matting", "query": "nails"},
        ensure_ascii=False,
    ).encode("utf-8")
    endpoint = service_url.rstrip("/") + "/matte"
    started = time.monotonic()
    network_failures = 0
    last_error = None
    while True:
        if time.monotonic() - started > BUSY_WALL_CLOCK_LIMIT:
            raise RuntimeError(f"matte_busy_timeout: 超过 {BUSY_WALL_CLOCK_LIMIT}s 仍未取得空闲实例")
        try:
            request = urllib.request.Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=SERVICE_TIMEOUT_SECONDS) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if cache_path:
                atomic_write_json(cache_path, payload)
            return payload, False
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")
            if err.code == 503:
                try:
                    detail = json.loads(raw)
                except json.JSONDecodeError:
                    detail = {}
                wait = float(detail.get("retryAfterSeconds") or 3.0)
                time.sleep(max(0.5, wait) + 0.5)
                continue
            last_error = RuntimeError(f"matte_http_{err.code}: {raw[:300]}")
            raise last_error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            network_failures += 1
            last_error = err
            if network_failures >= NETWORK_RETRY:
                raise RuntimeError(f"matte_network_failed_after_{NETWORK_RETRY}: {err}") from err
            time.sleep(3.0 * network_failures)


def atomic_write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# alpha 栅格（解码 → 全图栅格归一 → 面积平均降采样 → 羽化）
# ---------------------------------------------------------------------------


def decode_instance_alpha_grid(alpha_png_bytes: bytes, encoded_wh, bbox):
    """解码实例 alphaPng：灰度落在 R 通道（vlm-refinement.ts alphaGridFromRgba）。

    alphaPng 与编码图同尺寸 → 直接作为全图栅格；
    与实例 bbox 同尺寸 → 按 bbox 左上角贴回全图栅格；
    其他尺寸 → 按全图等比栅格处理并记告警。
    返回 (full_grid_hxw_uint8, warnings)。
    """
    warnings = []
    png = Image.open(io.BytesIO(alpha_png_bytes)).convert("RGBA")
    alpha = np.asarray(png)[:, :, 0].astype(np.uint8)
    gh, gw = alpha.shape
    ew, eh = encoded_wh
    if (gw, gh) == (ew, eh):
        return alpha, warnings
    try:
        bx1, by1, bx2, by2 = [float(v) for v in bbox[:4]]
    except (TypeError, ValueError, IndexError):
        warnings.append("alpha_png_size_mismatch_treated_as_full_grid")
        return alpha, warnings
    if abs((bx2 - bx1) - gw) <= 2 and abs((by2 - by1) - gh) <= 2:
        full = np.zeros((eh, ew), dtype=np.uint8)
        ox = max(0, min(ew - 1, int(round(bx1))))
        oy = max(0, min(eh - 1, int(round(by1))))
        h = min(gh, eh - oy)
        w = min(gw, ew - ox)
        full[oy : oy + h, ox : ox + w] = alpha[:h, :w]
        warnings.append("alpha_png_local_grid_pasted_by_bbox")
        return full, warnings
    warnings.append("alpha_png_size_mismatch_treated_as_full_grid")
    return alpha, warnings


def downsample_alpha_grid(alpha: np.ndarray, max_edge: int = MATTE_ALPHA_MAX_EDGE) -> np.ndarray:
    """面积平均降采样到长边 ≤ max_edge；二值几何按 128 阈值重算。

    与 vlm-refinement.ts downsampleAlphaGrid 同口径（窗口起点
    floor(i*src/target)，终点 max(start+1, floor((i+1)*src/target))）。
    """
    h, w = alpha.shape
    longest = max(w, h)
    if longest <= max_edge:
        return alpha
    scale = max_edge / longest
    tw = max(1, round(w * scale))
    th = max(1, round(h * scale))

    def starts(total: int, target: int) -> np.ndarray:
        return np.floor(np.arange(target) * total / target).astype(np.int64)

    ys = starts(h, th)
    xs = starts(w, tw)
    y_ends = np.minimum(h, np.maximum(ys + 1, np.floor((np.arange(th) + 1) * h / th).astype(np.int64)))
    x_ends = np.minimum(w, np.maximum(xs + 1, np.floor((np.arange(tw) + 1) * w / tw).astype(np.int64)))

    a = alpha.astype(np.float64)
    sums = np.add.reduceat(a, ys, axis=0)
    sums = np.add.reduceat(sums, xs, axis=1)
    counts = (y_ends - ys)[:, None] * (x_ends - xs)[None, :]
    values = np.round(sums / counts)
    return values.astype(np.uint8)


def build_feathered_alpha(binary: np.ndarray, soft: np.ndarray, radius: int = FEATHER_RADIUS) -> np.ndarray:
    """羽化 alpha：前景像素到最近背景（含图边界）的距离斜坡，再与软 alpha 取 min。

    与 extract-mask-texture.ts buildFeatheredAlphaMask 同口径：
    图边界外视为背景；距离 ≥ radius 记 255；背景记 0。
    """
    h, w = binary.shape
    bg = binary == 0
    dist = np.full((h, w), np.inf)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d = math.hypot(dx, dy)
            shifted = np.ones((h, w), dtype=bool)
            ys0 = max(0, -dy)
            ys1 = min(h, h - dy)
            xs0 = max(0, -dx)
            xs1 = min(w, w - dx)
            if ys0 < ys1 and xs0 < xs1:
                shifted[ys0:ys1, xs0:xs1] = bg[ys0 + dy : ys1 + dy, xs0 + dx : xs1 + dx]
            dist = np.minimum(dist, np.where(shifted, d, np.inf))
    ramp = np.where(dist >= radius, 255.0, np.round(dist / radius * 255.0))
    ramp = np.where(binary != 0, ramp, 0.0)
    return np.minimum(ramp, soft.astype(np.float64)).astype(np.uint8)


# ---------------------------------------------------------------------------
# 主轴角与甲尖启发式（mask-orientation.ts 移植）
# ---------------------------------------------------------------------------


def normalize_half_turn_angle(angle: float) -> float:
    result = angle
    while result > math.pi / 2:
        result -= math.pi
    while result <= -math.pi / 2:
        result += math.pi
    return result


def estimate_principal_angle(binary: np.ndarray):
    """二阶矩主轴（半转角）。返回 (angle 或 None, axis_ratio)。"""
    ys, xs = np.nonzero(binary)
    total = int(xs.size)
    if total < 4:
        return None, 0.0
    mean_x = float(xs.mean())
    mean_y = float(ys.mean())
    dx = xs.astype(np.float64) - mean_x
    dy = ys.astype(np.float64) - mean_y
    mu20 = float((dx * dx).sum())
    mu02 = float((dy * dy).sum())
    mu11 = float((dx * dy).sum())
    trace = mu20 + mu02
    delta = math.sqrt((mu20 - mu02) ** 2 + 4.0 * mu11 * mu11)
    major = (trace + delta) / 2.0
    minor = (trace - delta) / 2.0
    if major <= 0:
        return None, 0.0
    ratio = math.inf if minor <= 1e-6 else major / minor
    if ratio < AXIS_RATIO_MIN:
        return None, ratio
    axis_angle = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
    return normalize_half_turn_angle(axis_angle + math.pi / 2), ratio


def tip_direction_heuristic(alpha: np.ndarray, band_fraction: float = 1.0 / 3.0):
    """沿主轴（旋转后为竖直）比较两端 1/3 带的平均宽度，窄端为甲尖。

    返回 (heuristic_tip: "top"|"bottom"|"ambiguous", ratio, tip_ambiguous)。
    """
    if alpha.ndim == 3:
        alpha = alpha[:, :, 3]
    solid = alpha >= MATTE_ALPHA_THRESHOLD
    row_width = solid.sum(axis=1).astype(np.float64)
    h = row_width.size
    k = max(1, int(h * band_fraction))
    top = float(row_width[:k].mean())
    bottom = float(row_width[h - k :].mean())
    wider = max(top, bottom)
    narrower = min(top, bottom)
    ratio = (narrower / wider) if wider > 0 else 0.0
    if ratio < TIP_WIDTH_RATIO:
        tip = "top" if top < bottom else "bottom"
        return tip, ratio, False
    return "ambiguous", ratio, True


# ---------------------------------------------------------------------------
# RGBA 平面操作（extract-mask-texture.ts 移植）
# ---------------------------------------------------------------------------


def rotate_rgba_plane(src: np.ndarray, applied: float) -> np.ndarray:
    """alpha 加权双线性旋转。颜色按覆盖 alpha 预累加再除回，防止透明邻域发灰。

    applied 为画布坐标（+y 向下）旋转角；与 TS rotateRgbaPlane 同口径。
    """
    if abs(applied) <= 1e-9:
        return src
    if abs(abs(applied) - math.pi) <= 1e-9:
        return np.rot90(src, 2).copy()
    h, w = src.shape[:2]
    cos_a = math.cos(applied)
    sin_a = math.sin(applied)
    out_w = max(1, math.ceil(abs(w * cos_a) + abs(h * sin_a)))
    out_h = max(1, math.ceil(abs(w * sin_a) + abs(h * cos_a)))

    ys, xs = np.mgrid[0:out_h, 0:out_w].astype(np.float64)
    dx = xs + 0.5 - out_w / 2.0
    dy = ys + 0.5 - out_h / 2.0
    sx = cos_a * dx + sin_a * dy - 0.5 + w / 2.0
    sy = -sin_a * dx + cos_a * dy - 0.5 + h / 2.0

    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    fx = sx - x0
    fy = sy - y0

    src_f = src.astype(np.float64)
    src_alpha = src_f[:, :, 3]
    acc_rgb = np.zeros((out_h, out_w, 3), dtype=np.float64)
    acc_a = np.zeros((out_h, out_w), dtype=np.float64)

    for oy in (0, 1):
        for ox in (0, 1):
            wx = (1.0 - fx) if ox == 0 else fx
            wy = (1.0 - fy) if oy == 0 else fy
            weight = wx * wy
            px = x0 + ox
            py = y0 + oy
            valid = (px >= 0) & (px < w) & (py >= 0) & (py < h) & (weight > 0)
            if not valid.any():
                continue
            py_c = np.clip(py, 0, h - 1)
            px_c = np.clip(px, 0, w - 1)
            alpha_v = np.where(valid, src_alpha[py_c, px_c], 0.0)
            covered = weight * (alpha_v / 255.0)
            for ch in range(3):
                acc_rgb[:, :, ch] += np.where(
                    valid, src_f[py_c, px_c, ch] * covered, 0.0
                )
            acc_a += np.where(valid, alpha_v * weight, 0.0)

    color_weight = acc_a / 255.0
    out = np.zeros((out_h, out_w, 4), dtype=np.uint8)
    has_color = color_weight > 0
    for ch in range(3):
        values = np.zeros((out_h, out_w), dtype=np.float64)
        np.divide(acc_rgb[:, :, ch], color_weight, out=values, where=has_color)
        out[:, :, ch] = np.clip(np.round(values), 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(np.round(np.minimum(255.0, acc_a)), 0, 255).astype(np.uint8)
    return out


def crop_rgba_plane_to_alpha_bounds(src: np.ndarray, pad: int = NORMALIZATION_EDGE_PAD) -> np.ndarray:
    """紧致裁剪到 alpha>0 边界，外扩 pad 像素（防软边被硬切）。"""
    alpha = src[:, :, 3]
    ys, xs = np.nonzero(alpha > 0)
    if xs.size == 0:
        return src
    h, w = src.shape[:2]
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(w - 1, int(xs.max()) + pad)
    y1 = min(h - 1, int(ys.max()) + pad)
    return src[y0 : y1 + 1, x0 : x1 + 1].copy()


def downscale_rgba_plane(src: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """面积平均、alpha 加权降采样（与 TS downscaleRgbaPlane 同口径）。"""
    h, w = src.shape[:2]
    alpha = src[:, :, 3].astype(np.float64)

    def starts(total: int, target: int) -> np.ndarray:
        return np.floor(np.arange(target) * total / target).astype(np.int64)

    ys = starts(h, target_h)
    xs = starts(w, target_w)
    y_counts = np.maximum(1, np.diff(np.append(ys, h)))
    x_counts = np.maximum(1, np.diff(np.append(xs, w)))

    weighted = src[:, :, :3].astype(np.float64) * (alpha / 255.0)[:, :, None]
    sums = np.add.reduceat(weighted, ys, axis=0)
    sums = np.add.reduceat(sums, xs, axis=1)
    alpha_sums = np.add.reduceat(alpha, ys, axis=0)
    alpha_sums = np.add.reduceat(alpha_sums, xs, axis=1)

    weight_sum = alpha_sums / 255.0
    counts = y_counts[:, None] * x_counts[None, :]
    out = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    has_weight = weight_sum > 0
    for ch in range(3):
        values = np.zeros((target_h, target_w), dtype=np.float64)
        np.divide(sums[:, :, ch], weight_sum, out=values, where=has_weight)
        out[:, :, ch] = np.clip(np.round(values), 0, 255).astype(np.uint8)
    avg_alpha = alpha_sums / counts
    out[:, :, 3] = np.clip(np.round(np.minimum(255.0, avg_alpha)), 0, 255).astype(np.uint8)
    return out


def compute_dominant_color(planes) -> str:
    """五枚纹理不透明像素（alpha≥128）按 4096 桶（4bit/通道）量化取 top1 平均 hex。"""
    bins = np.zeros(4096, dtype=np.int64)
    sum_r = np.zeros(4096, dtype=np.float64)
    sum_g = np.zeros(4096, dtype=np.float64)
    sum_b = np.zeros(4096, dtype=np.float64)
    for plane in planes:
        alpha = plane[:, :, 3]
        mask = alpha >= MATTE_ALPHA_THRESHOLD
        if not mask.any():
            continue
        r = plane[:, :, 0][mask].astype(np.int64)
        g = plane[:, :, 1][mask].astype(np.int64)
        b = plane[:, :, 2][mask].astype(np.int64)
        key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
        np.add.at(bins, key, 1)
        np.add.at(sum_r, key, r)
        np.add.at(sum_g, key, g)
        np.add.at(sum_b, key, b)
    top = int(bins.argmax())
    if bins[top] <= 0:
        return "#808080"
    avg = (sum_r[top] / bins[top], sum_g[top] / bins[top], sum_b[top] / bins[top])
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(v))) for v in avg))


# ---------------------------------------------------------------------------
# 单实例提取
# ---------------------------------------------------------------------------


def extract_one_instance(full_image, original_wh, grid, solid_bounds, plan_flip: bool):
    """单实例：栅格边界→原图域裁剪→羽化 alpha→旋转摆正→启发式→紧致裁剪→≤256。"""
    warnings = []
    img_w, img_h = original_wh
    gh, gw = grid.shape
    min_x, min_y, max_x, max_y = solid_bounds
    span_x = max_x - min_x + 1
    span_y = max_y - min_y + 1

    scale_x = img_w / gw
    scale_y = img_h / gh
    src_x = max(0, math.floor(min_x * scale_x))
    src_y = max(0, math.floor(min_y * scale_y))
    src_w = max(1, math.ceil(span_x * scale_x))
    src_h = max(1, math.ceil(span_y * scale_y))
    # 裁剪框不得越过原图
    src_w = min(src_w, img_w - src_x)
    src_h = min(src_h, img_h - src_y)

    crop = np.asarray(full_image.crop((src_x, src_y, src_x + src_w, src_y + src_h))).copy()

    binary = grid >= MATTE_ALPHA_THRESHOLD
    feathered = build_feathered_alpha(binary, grid, FEATHER_RADIUS)

    # 羽化 alpha 按栅格实心窗口逐轴映射到裁剪平面（与 TS 的最近邻映射同口径）
    col_idx = np.minimum(min_x + (np.arange(src_w) * span_x) // src_w, gw - 1)
    row_idx = np.minimum(min_y + (np.arange(src_h) * span_y) // src_h, gh - 1)
    alpha_plane = feathered[np.ix_(row_idx, col_idx)]

    plane = np.dstack([crop, alpha_plane])

    angle, axis_ratio = estimate_principal_angle(binary[min_y : max_y + 1, min_x : max_x + 1])
    applied = -(angle if angle is not None else 0.0)
    if plan_flip:
        applied += math.pi
    rotated = rotate_rgba_plane(plane, applied)

    heuristic_tip, tip_ratio, tip_ambiguous = tip_direction_heuristic(rotated)
    if tip_ambiguous:
        warnings.append("tip_ambiguous")

    tightened = crop_rgba_plane_to_alpha_bounds(rotated, NORMALIZATION_EDGE_PAD)
    longest = max(tightened.shape[0], tightened.shape[1])
    if longest > MAX_TEXTURE_SIZE:
        scale = MAX_TEXTURE_SIZE / longest
        out_w = max(1, round(tightened.shape[1] * scale))
        out_h = max(1, round(tightened.shape[0] * scale))
        tightened = downscale_rgba_plane(tightened, out_w, out_h)

    info = {
        "angle": None if angle is None else round(angle, 4),
        "axisRatio": None if not math.isfinite(axis_ratio) else round(axis_ratio, 4),
        "rotationApplied": round(applied, 4),
        "sourceRect": [src_x, src_y, src_w, src_h],
        "heuristicTip": heuristic_tip,
        "tipWidthRatio": round(tip_ratio, 4),
        "tip_ambiguous": tip_ambiguous,
        "outSize": [int(tightened.shape[1]), int(tightened.shape[0])],
        "warnings": warnings,
    }
    return tightened, info


# ---------------------------------------------------------------------------
# 套装构建
# ---------------------------------------------------------------------------


def pick_instance_box(instance: dict):
    """优先 bbox（x1,y1,x2,y2），异常时退回 box（与 TS candidateFromMatteInstance 同口径）。"""
    bbox = instance.get("bbox") or []
    box = instance.get("box") or []
    if len(bbox) >= 4 and bbox[2] > bbox[0]:
        return [float(v) for v in bbox[:4]]
    if len(box) >= 4 and box[2] > box[0]:
        return [float(v) for v in box[:4]]
    if len(bbox) >= 4:
        return [float(v) for v in bbox[:4]]
    if len(box) >= 4:
        return [float(v) for v in box[:4]]
    return [0.0, 0.0, 1.0, 1.0]


def source_relative_path(path: str) -> str:
    """来源相对路径：优先相对 JiaRu_image 素材仓根，失败时回退完整路径。"""
    normalized = path.replace("/", os.sep)
    parts = normalized.lower().split(os.sep)
    if "jiaru_image" in parts:
        idx = len(parts) - 1 - parts[::-1].index("jiaru_image")
        root = os.sep.join(parts[: idx + 1])
        root = root[:1].upper() + root[1:] if root and root[1:2] == ":" else root
        rel = os.path.relpath(normalized, root)
        return rel.replace(os.sep, "/")
    return path.replace(os.sep, "/")


def build_set(entry: dict, work_dir: str, service_url: str, builds_dir: str):
    """构建单个套装。返回 (set_record, manifest_entry 或 None, output_files 或 None)。"""
    set_id = entry["setId"]
    started = time.monotonic()
    record = {
        "setId": set_id,
        "name": entry.get("name", set_id),
        "source": entry["source"],
        "ok": False,
        "warnings": [],
        "instances": [],
    }

    if not os.path.isfile(entry["source"]):
        record["warnings"].append("source_file_missing")
        record["error"] = "source_file_missing"
        return record, None, None

    actual_sha = sha256_file(entry["source"])
    record["sourceSha256"] = actual_sha
    if entry.get("sourceSha256") and entry["sourceSha256"].lower() != actual_sha:
        record["warnings"].append("source_sha256_mismatch")
        record["error"] = "source_sha256_mismatch"
        return record, None, None

    jpeg_bytes, encoded_wh, original_wh, full_image = encode_source_image(entry["source"])
    encoded_sha = sha256_bytes(jpeg_bytes)
    record["encodedSha256"] = encoded_sha
    record["encodedSize"] = list(encoded_wh)
    record["originalSize"] = list(original_wh)

    cache_path = os.path.join(work_dir, "cache", f"{encoded_sha}.json")
    data_uri = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
    response, cache_hit = request_matte(service_url, data_uri, cache_path)
    record["cacheHit"] = cache_hit
    if not response.get("ok"):
        record["error"] = "matte_response_not_ok"
        record["warnings"].append("matte_response_not_ok")
        return record, None, None

    instances = response.get("instances") or []
    # 确定性贴边假阳性过滤：bbox 贴编码图边界且面积低于中位数 25% 的实例，
    # 是服务在图像角落的误检（真实甲面不会被编码边界裁成细条），剔除后
    # 计数门仍要求恰好 5 枚真甲；剔除明细写入报告以便复核。
    if instances:
        ew, eh = encoded_wh
        areas = [float(inst.get("area") or 0) for inst in instances]
        median_area = float(np.median(areas))
        kept = []
        filtered_out = []
        for inst in instances:
            box = pick_instance_box(inst)
            touches_border = box[0] <= 1 or box[1] <= 1 or box[2] >= ew - 1 or box[3] >= eh - 1
            if touches_border and float(inst.get("area") or 0) < EDGE_SLIVER_AREA_RATIO * median_area:
                filtered_out.append({"bbox": [round(v, 2) for v in box], "area": inst.get("area")})
            else:
                kept.append(inst)
        if filtered_out:
            record["warnings"].append(f"edge_sliver_filtered:{len(filtered_out)}")
            record["edgeSliverFilteredInstances"] = filtered_out
            instances = kept
    record["instanceCount"] = len(instances)
    if len(instances) != 5:
        record["error"] = "instance_count_not_5"
        record["warnings"].append("instance_count_not_5")
        return record, None, None

    ranked = sorted(
        ({"index": inst.get("index", i), "inst": inst, "box": pick_instance_box(inst)} for i, inst in enumerate(instances)),
        key=lambda item: ((item["box"][0] + item["box"][2]) / 2.0, (item["box"][1] + item["box"][3]) / 2.0),
    )

    build_dir = os.path.join(builds_dir, set_id)
    os.makedirs(build_dir, exist_ok=True)
    mapping_by_rank = {m["rank"]: m for m in entry["mapping"]}
    planes = []
    textures = []
    for rank, item in enumerate(ranked, start=1):
        inst = item["inst"]
        box = item["box"]
        mapping = mapping_by_rank.get(rank)
        if mapping is None:
            record["error"] = f"missing_mapping_rank_{rank}"
            record["warnings"].append(f"missing_mapping_rank_{rank}")
            return record, None, None
        alpha_png = inst.get("alphaPng") or ""
        if not alpha_png.startswith("data:image"):
            record["error"] = f"rank_{rank}_alpha_png_missing"
            record["warnings"].append(f"rank_{rank}_alpha_png_missing")
            return record, None, None
        png_bytes = base64.b64decode(alpha_png.split(",", 1)[1])
        grid, grid_warnings = decode_instance_alpha_grid(png_bytes, encoded_wh, box)
        binary = grid >= MATTE_ALPHA_THRESHOLD
        ys, xs = np.nonzero(binary)
        if xs.size == 0:
            record["error"] = f"rank_{rank}_empty_alpha"
            record["warnings"].append(f"rank_{rank}_empty_alpha")
            return record, None, None
        solid_bounds = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

        plane, info = extract_one_instance(
            full_image, original_wh, grid, solid_bounds, bool(mapping.get("flip"))
        )
        info.update(
            {
                "rank": rank,
                "instanceIndex": item["index"],
                "finger": int(mapping["finger"]),
                "flip": bool(mapping.get("flip")),
                "bboxEncoded": [round(v, 2) for v in box],
                "gridSize": [int(grid.shape[1]), int(grid.shape[0])],
                "serviceArea": inst.get("area"),
            }
        )
        record["instances"].append(info)
        record["warnings"].extend(f"rank{rank}:{w}" for w in grid_warnings)

        file_name = f"finger-{mapping['finger']}.png"
        out_path = os.path.join(build_dir, file_name)
        Image.fromarray(plane, "RGBA").save(out_path, "PNG")
        planes.append(plane)
        textures.append({"finger": int(mapping["finger"]) - 1, "src": f"/nail-textures/{set_id}/{file_name}"})

    if sorted(t["finger"] for t in textures) != [0, 1, 2, 3, 4]:
        record["error"] = "finger_mapping_incomplete"
        record["warnings"].append("finger_mapping_incomplete")
        return record, None, None

    dominant = compute_dominant_color(planes)
    elapsed = round(time.monotonic() - started, 2)
    record["ok"] = True
    record["dominantColor"] = dominant
    record["elapsedSeconds"] = elapsed
    manifest_entry = {
        "id": set_id,
        "name": record["name"],
        "source": f"真实照片 {source_relative_path(entry['source'])}，WeVisOne-VL 抠图提取",
        "dominantColor": dominant,
        # textures 元素是 {"finger", "src"} 字典；按 finger 键排序后原样输出，禁止解包迭代 dict
        "textures": sorted(textures, key=lambda item: item["finger"]),
    }
    return record, manifest_entry, build_dir


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从真实照片构建 /editor 美甲纹理套装静态资产")
    parser.add_argument("--plan", required=True, help="plan.json 路径")
    parser.add_argument("--output", required=True, help="public 纹理输出目录")
    parser.add_argument("--work-dir", required=True, help="缓存/报告/产物留档目录")
    parser.add_argument("--service-url", default="http://127.0.0.1:8008", help="本机抠图服务地址")
    parser.add_argument("--only", default=None, help="仅构建指定 setId（其余跳过）")
    args = parser.parse_args(argv)

    with open(args.plan, "r", encoding="utf-8") as handle:
        plan = json.load(handle)

    work_dir = os.path.abspath(args.work_dir)
    output_dir = os.path.abspath(args.output)
    builds_dir = os.path.join(work_dir, "builds", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(work_dir, "cache"), exist_ok=True)
    os.makedirs(builds_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    report = {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "service": args.service_url,
        "plan": os.path.abspath(args.plan),
        "constants": {
            "matteImageMaxEdge": MATTE_IMAGE_MAX_EDGE,
            "matteAlphaMaxEdge": MATTE_ALPHA_MAX_EDGE,
            "alphaThreshold": MATTE_ALPHA_THRESHOLD,
            "maxTextureSize": MAX_TEXTURE_SIZE,
            "featherRadius": FEATHER_RADIUS,
            "edgePad": NORMALIZATION_EDGE_PAD,
            "tipWidthRatio": TIP_WIDTH_RATIO,
            "edgeSliverAreaRatio": EDGE_SLIVER_AREA_RATIO,
        },
        "warmup": None,
        "sets": [],
    }

    # 热身：取首个目标源图打一张并丢弃结果（结果同时写入缓存，后续直接命中）
    targets = [e for e in plan if (args.only is None or e.get("setId") == args.only)]
    if targets:
        warm_entry = targets[0]
        warm_started = time.monotonic()
        try:
            warm_jpeg, _, _, _ = encode_source_image(warm_entry["source"])
            warm_sha = sha256_bytes(warm_jpeg)
            warm_cache = os.path.join(work_dir, "cache", f"{warm_sha}.json")
            warm_uri = "data:image/jpeg;base64," + base64.b64encode(warm_jpeg).decode("ascii")
            _, warm_hit = request_matte(args.service_url, warm_uri, warm_cache)
            report["warmup"] = {
                "source": warm_entry["source"],
                "encodedSha256": warm_sha,
                "cacheHit": warm_hit,
                "elapsedSeconds": round(time.monotonic() - warm_started, 2),
            }
        except Exception as err:  # 热身失败不阻断主流程，由各套装自身重试与报告兜底
            report["warmup"] = {"source": warm_entry["source"], "error": str(err)}

    manifest = []
    failed = 0
    for entry in plan:
        set_id = entry.get("setId", "?")
        if args.only is not None and set_id != args.only:
            continue
        print(f"[build] {set_id} 开始", flush=True)
        try:
            record, manifest_entry, build_dir = build_set(entry, work_dir, args.service_url, builds_dir)
        except Exception as err:
            record = {
                "setId": set_id,
                "name": entry.get("name", set_id),
                "source": entry.get("source"),
                "ok": False,
                "error": f"exception: {err}",
                "warnings": [],
                "instances": [],
            }
            manifest_entry, build_dir = None, None
        report["sets"].append(record)

        if record.get("ok") and manifest_entry and build_dir:
            # 仅成功套装原子复制到 public；失败套装保留旧资产
            target_dir = os.path.join(output_dir, set_id)
            os.makedirs(target_dir, exist_ok=True)
            for name in sorted(os.listdir(build_dir)):
                src = os.path.join(build_dir, name)
                tmp = os.path.join(target_dir, name + ".tmp")
                shutil.copyfile(src, tmp)
                os.replace(tmp, os.path.join(target_dir, name))
            manifest.append(manifest_entry)
            print(f"[build] {set_id} 完成 dominant={record['dominantColor']} instances=5", flush=True)
        else:
            failed += 1
            print(f"[build] {set_id} 失败: {record.get('error')}", flush=True)

    atomic_write_json(os.path.join(work_dir, "manifest.json"), manifest)
    atomic_write_json(os.path.join(work_dir, "build-report.json"), report)

    print(
        f"[done] 成功 {len(manifest)} 套，失败 {failed} 套；manifest={os.path.join(work_dir, 'manifest.json')}",
        flush=True,
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
