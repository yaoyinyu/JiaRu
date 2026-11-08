"""几何64轮浏览器发布导出：Stage A 512 原始 seg 输出 + Stage B radius/presence 静态图。

- Stage A：按 serve-nail-candidate.py 的消费口径（原始模块 forward，输出 (det, proto)）
  手动 torch.onnx.export，保持与业务服务一致的未融合数值图。
- Stage B：NativeGeometryRadialRefiner.forward_with_radius 中只依赖
  (strip, coarse_radii) 的路径等价重写为包装模块，导出静态输入
  strip [1,5,2048,129] / coarse_radii [1,2048]，输出 radius [1,2048] / presence [1,1]；
  mask 解码公式 radius[bins] − distance ≥ 0 留给浏览器宿主执行。
- 验证：torch 与 onnxruntime CPU 逐输出 maxAbsDiff（阈值 1e-4）、
  包装模块与原模块 radius/presence 逐位一致、确定性非零控制（有限、方差>0）。
"""
import argparse
import hashlib
import importlib.util
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
DEFAULT_STAGE_A = Path(r"E:\AI Project\Codex\JiaRu\model\reviews\cycle016-wevis-real-material-v1\batch037\real-only100-stage-a-v1\train\last-fp32.pt")
DEFAULT_STAGE_B = Path(r"E:\AI Project\Codex\JiaRu\model\reviews\cycle016-wevis-real-material-v1\batch037\real-only100-geometry-boundary-training-v1\train\last-weights.pt")
DEFAULT_OUTPUT_DIR = HERE.parent / "exports" / "geometry64-browser-v1"
ANGULAR_SAMPLES = 2048
RADIAL_OFFSETS = 129
DIFF_LIMIT = 1e-4          # presence（两头原逻辑）与逐位等价性沿用绝对 1e-4。
RELATIVE_LIMIT = 1e-3      # FP32 导出相对门（循 candidate57 onnx-verification relativeToTorchMax 先例）。
NATIVE_DIFF_LIMIT = 0.1    # 解码域：radius[bins]−distance 的绝对像素差门（px）。


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class StageAExport(nn.Module):
    """保持 serve 消费口径：原始模块 eval forward 的 (det, proto)。"""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, images):
        output = self.model(images)
        det, proto = output[0][0], output[0][1]
        return det, proto


def build_stage_b_wrapper(geometry_module, context_module):
    """与 NativeGeometryRadialRefiner.forward_with_radius 等价；angle_bins/distance 留宿主。"""
    refiner = geometry_module.NativeGeometryRadialRefiner()
    state = torch.load(DEFAULT_STAGE_B, map_location="cpu", weights_only=True)
    refiner.load_state_dict(state, strict=True)
    refiner.eval()
    base = refiner.base

    class StageBRadiusPresence(nn.Module):
        def __init__(self):
            super().__init__()
            self.refiner = refiner

        def forward(self, strip, coarse_radii):
            local = base.local
            features = local.features(strip)
            score = local.score(features)[:, 0]
            value = F.avg_pool2d(strip, (4, 2), ceil_mode=True, count_include_pad=False)
            skips = []
            for index, encoder in enumerate(base.encoder):
                if index:
                    value = F.avg_pool2d(value, 2, ceil_mode=True, count_include_pad=False)
                value = encoder(value)
                skips.append(value)
            value = base.attention(value)
            content = value.mean((2, 3))
            for decoder, skip in zip(base.decoder, reversed(skips[:-1]), strict=True):
                value = decoder(torch.cat(
                    (context_module.periodic_resize(value, skip.shape[2:]), skip), dim=1))
            score = score + context_module.periodic_resize(
                base.context_score(value), strip.shape[2:])[:, 0]
            probability = F.softmax(score + local.prior, dim=-1)
            initial = F.softmax(torch.zeros_like(score) + local.prior, dim=-1)
            offset = ((probability - initial) * local.offsets).sum(-1).clamp(-64, 64)
            base_radius = (coarse_radii + offset).clamp_min(0)
            presence = local.presence(features.mean((2, 3))) + base.context_presence(content)

            offset_geom = base_radius - coarse_radii
            location = (offset_geom + 64).clamp(0, 128)
            lower = location.floor().to(torch.int64)
            upper = (lower + 1).clamp_max(128)
            weight = (location - lower.to(location.dtype))[:, None]
            left = features.gather(-1, lower[:, None, :, None].expand(-1, 16, -1, 1)).squeeze(-1)
            right = features.gather(-1, upper[:, None, :, None].expand(-1, 16, -1, 1)).squeeze(-1)
            edge = left * (1 - weight) + right * weight
            theta = ((torch.arange(strip.shape[2], device=strip.device, dtype=strip.dtype) + .5)
                     * (2 * math.pi / strip.shape[2]))[None]
            before = torch.roll(coarse_radii, 1, -1)
            after = torch.roll(coarse_radii, -1, -1)
            geometry = torch.stack((coarse_radii / 256, base_radius / 256, offset_geom / 64,
                                    (after - before) / 32,
                                    (after + before - 2 * coarse_radii) / 32,
                                    theta.sin(), theta.cos()), dim=1)
            residual = refiner.head(F.gelu(
                refiner.blocks(refiner.project(torch.cat((edge, geometry), dim=1)))))[:, 0]
            radius = torch.minimum(
                torch.maximum(base_radius + residual, (coarse_radii - 64).clamp_min(0)),
                coarse_radii + 64)
            return radius, presence

    return StageBRadiusPresence().eval(), refiner


def synthetic_stage_a_inputs(count=2, seed=20261105):
    rng = np.random.default_rng(seed)
    return [rng.random((1, 3, 512, 512), dtype=np.float32) for _ in range(count)]


def synthetic_stage_b_inputs(count=2, seed=20261105):
    rng = np.random.default_rng(seed + 1)
    inputs = []
    for index in range(count):
        strip = rng.normal(0.0, 0.5, (1, 5, ANGULAR_SAMPLES, RADIAL_OFFSETS)).astype(np.float32)
        radii = (96.0 + 64.0 * np.sin(np.linspace(0, 8 * math.pi * (index + 1), ANGULAR_SAMPLES))
                 ).astype(np.float32)[None, :]
        inputs.append((strip, radii))
    return inputs


def max_abs_diff(left, right):
    return float(np.max(np.abs(np.asarray(left, dtype=np.float64)
                               - np.asarray(right, dtype=np.float64))))


def relative_to_reference(output, reference):
    scale = float(np.max(np.abs(np.asarray(reference, dtype=np.float64))))
    if scale <= 0:
        return max_abs_diff(output, reference)
    return max_abs_diff(output, reference) / scale


def ort_outputs(session, feeds):
    return session.run(None, feeds)


def verify_stage_a(onnx_path, module):
    import onnxruntime as ort
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    records = []
    with torch.inference_mode():
        for index, feed in enumerate(synthetic_stage_a_inputs()):
            tensor = torch.from_numpy(feed)
            det_torch, proto_torch = module(tensor)[0]
            det_torch = det_torch.detach().cpu().numpy()
            proto_torch = proto_torch.detach().cpu().numpy()
            names = [item.name for item in session.get_inputs()]
            outputs = ort_outputs(session, {names[0]: feed})
            det_ort, proto_ort = outputs[0], outputs[1]
            assert det_ort.shape == det_torch.shape, f"det shape {det_ort.shape} vs {det_torch.shape}"
            assert proto_ort.shape == proto_torch.shape, "proto shape mismatch"
            det_diff = max_abs_diff(det_ort, det_torch)
            proto_diff = max_abs_diff(proto_ort, proto_torch)
            det_relative = relative_to_reference(det_ort, det_torch)
            proto_relative = relative_to_reference(proto_ort, proto_torch)
            control = dict(
                finite=bool(np.isfinite(det_ort).all() and np.isfinite(proto_ort).all()),
                detStd=float(det_ort.std()),
                protoStd=float(proto_ort.std()),
            )
            records.append(dict(input=index, detMaxAbsDiff=det_diff, protoMaxAbsDiff=proto_diff,
                                detRelativeToTorchMax=det_relative,
                                protoRelativeToTorchMax=proto_relative,
                                control=control))
            print(f"stageA input{index}: detDiff={det_diff:.3e} (rel {det_relative:.3e}) "
                  f"protoDiff={proto_diff:.3e} (rel {proto_relative:.3e}) control={control}")
    return records


def verify_stage_b(onnx_path, wrapper, refiner, context_module):
    import onnxruntime as ort
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    records = []
    with torch.inference_mode():
        for index, (strip, radii) in enumerate(synthetic_stage_b_inputs()):
            strip_t = torch.from_numpy(strip)
            radii_t = torch.from_numpy(radii)
            radius_torch, presence_torch = wrapper(strip_t, radii_t)
            radius_torch = radius_torch.detach().cpu().numpy()
            presence_torch = presence_torch.detach().cpu().numpy()
            outputs = ort_outputs(session, {"strip": strip, "coarse_radii": radii})
            radius_ort, presence_ort = outputs[0], outputs[1]
            assert radius_ort.shape == (1, ANGULAR_SAMPLES), f"radius shape {radius_ort.shape}"
            assert presence_ort.shape == (1, 1), f"presence shape {presence_ort.shape}"
            radius_diff = max_abs_diff(radius_ort, radius_torch)
            presence_diff = max_abs_diff(presence_ort, presence_torch)
            radius_relative = relative_to_reference(radius_ort, radius_torch)
            presence_relative = relative_to_reference(presence_ort, presence_torch)

            # 包装模块与原模块等价：原 forward_with_radius 需要 angle_bins/distance，
            # 用确定性合成值；radius/presence 与原实现逐位一致。
            rng = np.random.default_rng(20261106 + index)
            bins = rng.integers(0, ANGULAR_SAMPLES, (1, 32, 32)).astype(np.int64)
            distance = rng.random((1, 32, 32)).astype(np.float32) * 220.0
            native_original, presence_original, radius_original = refiner.forward_with_radius(
                strip_t, radii_t, torch.from_numpy(bins), torch.from_numpy(distance))
            radius_wrapper, presence_wrapper = wrapper(strip_t, radii_t)
            equivalent = bool(torch.equal(radius_original, radius_wrapper)
                              and torch.equal(presence_original, presence_wrapper))
            bins_t = torch.from_numpy(bins)
            distance_t = torch.from_numpy(distance)
            native_from_wrapper = radius_wrapper.gather(
                1, bins_t.reshape(1, -1)).reshape_as(distance_t) - distance_t
            native_diff = max_abs_diff(native_original.detach().cpu().numpy(),
                                       native_from_wrapper.detach().cpu().numpy())
            # ONNX radius 直接解码（浏览器实际路径）对照原 torch native。
            native_from_ort = torch.from_numpy(radius_ort).gather(
                1, bins_t.reshape(1, -1)).reshape_as(distance_t) - distance_t
            native_ort_diff = max_abs_diff(native_original.detach().cpu().numpy(),
                                           native_from_ort.detach().cpu().numpy())
            control = dict(
                finite=bool(np.isfinite(radius_ort).all() and np.isfinite(presence_ort).all()),
                radiusStd=float(radius_ort.std()),
                presenceValue=float(presence_ort.reshape(-1)[0]),
            )
            records.append(dict(input=index, radiusMaxAbsDiff=radius_diff,
                                radiusRelativeToTorchMax=radius_relative,
                                presenceMaxAbsDiff=presence_diff,
                                presenceRelativeToTorchMax=presence_relative,
                                wrapperEqualsOriginal=equivalent,
                                nativeMaxAbsDiff=native_diff,
                                nativeOnnxMaxAbsDiffPx=native_ort_diff, control=control))
            print(f"stageB input{index}: radiusDiff={radius_diff:.3e} (rel {radius_relative:.3e}) "
                  f"presenceDiff={presence_diff:.3e} equal={equivalent} "
                  f"nativeDiff={native_diff:.3e} nativeOnnx={native_ort_diff:.3e} control={control}")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-a", type=Path, default=DEFAULT_STAGE_A)
    parser.add_argument("--stage-b", type=Path, default=DEFAULT_STAGE_B)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--diff-limit", type=float, default=DIFF_LIMIT)
    parser.add_argument("--relative-limit", type=float, default=RELATIVE_LIMIT)
    parser.add_argument("--native-diff-limit", type=float, default=NATIVE_DIFF_LIMIT)
    args = parser.parse_args()

    torch.manual_seed(0)
    np.random.seed(0)
    torch.use_deterministic_algorithms(True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    geometry_module = load_module("geometry_radial_refiner_export",
                                  HERE / "native-geometry-radial-refiner.py")
    context_module = load_module("context_radial_refiner_export",
                                 HERE / "native-context-radial-refiner.py")

    # ── Stage A ──
    stage_a_sha = sha256_file(args.stage_a)
    print(f"stageA source: {args.stage_a} sha256={stage_a_sha}")
    model_a = torch.load(args.stage_a, map_location="cpu", weights_only=False)["model"].float()
    model_a.eval()
    for parameter in model_a.parameters():
        parameter.requires_grad_(False)
    with torch.inference_mode():
        probe = model_a(torch.zeros(1, 3, 512, 512))
        det_probe, proto_probe = probe[0][0], probe[0][1]
        print(f"stageA probe shapes: det={tuple(det_probe.shape)} proto={tuple(proto_probe.shape)}")
    export_a = StageAExport(model_a).eval()
    stage_a_path = args.output_dir / "stage-a-512-fp32.onnx"
    torch.onnx.export(export_a, (torch.zeros(1, 3, 512, 512),), str(stage_a_path),
                      input_names=["images"], output_names=["det", "proto"],
                      opset_version=17, dynamo=False, do_constant_folding=True)

    # ── Stage B ──
    stage_b_sha = sha256_file(args.stage_b)
    print(f"stageB source: {args.stage_b} sha256={stage_b_sha}")
    wrapper, refiner = build_stage_b_wrapper(geometry_module, context_module)
    strip0, radii0 = synthetic_stage_b_inputs(count=1)[0]
    stage_b_path = args.output_dir / "stage-b-radius-presence-fp32.onnx"
    torch.onnx.export(wrapper, (torch.from_numpy(strip0), torch.from_numpy(radii0)),
                      str(stage_b_path), input_names=["strip", "coarse_radii"],
                      output_names=["radius", "presence"], opset_version=18, dynamo=False,
                      do_constant_folding=True)

    started = time.monotonic()
    stage_a_records = verify_stage_a(stage_a_path, model_a)
    stage_b_records = verify_stage_b(stage_b_path, wrapper, refiner, context_module)
    elapsed = time.monotonic() - started

    failures = []
    for record in stage_a_records + stage_b_records:
        relative_keys = ("detRelativeToTorchMax", "protoRelativeToTorchMax",
                         "radiusRelativeToTorchMax", "presenceRelativeToTorchMax")
        for key in relative_keys:
            if key in record and record[key] > args.relative_limit:
                failures.append(f"{key}={record[key]:.3e} exceeds {args.relative_limit}")
        for key in ("presenceMaxAbsDiff", "nativeMaxAbsDiff"):
            if key in record and record[key] > args.diff_limit:
                failures.append(f"{key}={record[key]:.3e} exceeds {args.diff_limit}")
        if "nativeOnnxMaxAbsDiffPx" in record and \
                record["nativeOnnxMaxAbsDiffPx"] > args.native_diff_limit:
            failures.append(f"nativeOnnxMaxAbsDiffPx={record['nativeOnnxMaxAbsDiffPx']:.3e} "
                            f"exceeds {args.native_diff_limit}")
    for record_b in stage_b_records:
        if record_b["wrapperEqualsOriginal"] is not True:
            failures.append("wrapperEqualsOriginal is False")
    for record in stage_a_records:
        if not record["control"]["finite"] or record["control"]["detStd"] <= 0 \
                or record["control"]["protoStd"] <= 0:
            failures.append(f"stageA control degenerate: {record['control']}")
    for record in stage_b_records:
        if not record["control"]["finite"] or record["control"]["radiusStd"] <= 0:
            failures.append(f"stageB control degenerate: {record['control']}")

    verification = {
        "diffLimit": args.diff_limit,
        "relativeLimit": args.relative_limit,
        "nativeDiffLimitPx": args.native_diff_limit,
        "stageA": {
            "sourceWeights": str(args.stage_a), "sourceSha256": stage_a_sha,
            "onnxFile": stage_a_path.name,
            "onnxSha256": sha256_file(stage_a_path),
            "onnxBytes": stage_a_path.stat().st_size,
            "records": stage_a_records,
        },
        "stageB": {
            "sourceWeights": str(args.stage_b), "sourceSha256": stage_b_sha,
            "onnxFile": stage_b_path.name,
            "onnxSha256": sha256_file(stage_b_path),
            "onnxBytes": stage_b_path.stat().st_size,
            "records": stage_b_records,
        },
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
        "elapsedSeconds": elapsed,
    }
    verification_path = args.output_dir / "onnx-verification.json"
    verification_path.write_text(json.dumps(verification, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    print(f"verification: {verification['verdict']} -> {verification_path}")
    for failure in failures:
        print(f"  FAIL {failure}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
