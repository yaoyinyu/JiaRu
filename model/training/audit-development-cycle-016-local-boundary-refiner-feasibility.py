#!/usr/bin/env python3
"""审计冻结粗模型的RGB引导局部边界残差修正器可行性。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(file_name: str, module_name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class DilatedResidualBlock(nn.Module):
    def __init__(self, channels: int, dilation: int) -> None:
        super().__init__()
        self.conv = nn.Conv2d(channels, channels, 3, padding=dilation, dilation=dilation, bias=False)
        self.norm = nn.GroupNorm(8, channels)
        self.activation = nn.GELU()

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return value + self.activation(self.norm(self.conv(value)))


class LocalBoundaryResidualRefiner(nn.Module):
    def __init__(self, input_channels: int, channels: int, dilations: list[int]) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(input_channels, channels, 3, padding=1, bias=False),
            nn.GroupNorm(8, channels),
            nn.GELU(),
        )
        self.blocks = nn.Sequential(*(DilatedResidualBlock(channels, dilation) for dilation in dilations))
        self.output = nn.Conv2d(channels, 1, 1)
        nn.init.normal_(self.output.weight, mean=0.0, std=1.0e-3)
        nn.init.zeros_(self.output.bias)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.output(self.blocks(self.stem(value)))


def fixed_boundary_band(coarse_logits: torch.Tensor, radius: int) -> torch.Tensor:
    prediction = (coarse_logits >= 0).to(coarse_logits.dtype)
    dilated = F.max_pool2d(prediction, kernel_size=3, stride=1, padding=1)
    eroded = -F.max_pool2d(-prediction, kernel_size=3, stride=1, padding=1)
    edge = (dilated - eroded > 0).to(coarse_logits.dtype)
    return F.max_pool2d(edge, kernel_size=radius * 2 + 1, stride=1, padding=radius) > 0


class FrozenCoarseLocalBoundaryRefiner(nn.Module):
    def __init__(self, coarse: nn.Module, config: dict[str, Any]) -> None:
        super().__init__()
        self.coarse = coarse
        for parameter in self.coarse.parameters():
            parameter.requires_grad_(False)
        self.coarse.eval()
        self.band_radius = int(config["bandRadiusPixels"])
        self.residual_scale = float(config["residualLogitScale"])
        self.refiner = LocalBoundaryResidualRefiner(
            int(config["refinerInputChannels"]),
            int(config["refinerChannels"]),
            [int(value) for value in config["dilations"]],
        )

    def train(self, mode: bool = True) -> "FrozenCoarseLocalBoundaryRefiner":
        super().train(mode)
        self.coarse.eval()
        return self

    def forward_with_aux(self, pixel_values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        with torch.no_grad():
            coarse_logits = self.coarse(pixel_values=pixel_values)
        band = fixed_boundary_band(coarse_logits, self.band_radius)
        refiner_input = torch.cat((pixel_values, torch.tanh(coarse_logits / 4.0)), dim=1)
        residual = self.refiner(refiner_input) * self.residual_scale
        final_logits = coarse_logits + band.to(residual.dtype) * residual
        return final_logits, coarse_logits, band, residual

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        final_logits, _, _, _ = self.forward_with_aux(pixel_values)
        return final_logits


def validate_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    for label, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不一致：{label}")
    seventh = json.loads(Path(plan["inputs"]["seventhReport"]["path"]).read_text(encoding="utf-8"))
    gain = json.loads(Path(plan["inputs"]["pointRendGainAudit"]["path"]).read_text(encoding="utf-8"))
    reachability = json.loads(Path(plan["inputs"]["bandReachabilityReport"]["path"]).read_text(encoding="utf-8"))
    if seventh.get("decision") != "roi_dinov2_soft_boundary_f1_internal_pilot_fail" or seventh.get("completedEpochs") != 30:
        raise ValueError("第七轮冻结报告不一致")
    if gain.get("decision") != "pointrend_not_broadly_effective_close_branch" or not gain.get("ok"):
        raise ValueError("PointRend关闭判决不一致")
    if reachability.get("decision") != plan["reachabilityGate"]["requiredBandReachabilityDecision"] or not reachability.get("ok"):
        raise ValueError("32像素修正带理论上限未通过")
    analysis = reachability["analysis"]
    if analysis["band"]["disagreementCoverage"] < float(plan["reachabilityGate"]["requiredBandDisagreementCoverage"]):
        raise ValueError("32像素修正带覆盖率低于合同")
    if analysis["oracleAggregate"]["meanBoundaryF1"] < float(plan["reachabilityGate"]["requiredOracleMeanBoundaryF1"]):
        raise ValueError("32像素修正带Boundary F1上限低于合同")
    if analysis["oracleAggregate"]["jointInstancePassRate"] < float(plan["reachabilityGate"]["requiredOracleJointInstancePassRate"]):
        raise ValueError("32像素修正带联合率上限低于合同")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["datasetContract"]["requiredDatasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != plan["datasetContract"]["requiredFinalReviewDecision"]:
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return seventh, dataset_report, Path(dataset_report["outputDir"])


def load_model(plan: dict[str, Any]) -> FrozenCoarseLocalBoundaryRefiner:
    seventh, _, _ = validate_plan(plan)
    training_plan_path = Path(seventh["inputs"]["plan"]["path"])
    if not training_plan_path.is_file() or sha256_file(training_plan_path) != seventh["inputs"]["plan"]["sha256"]:
        raise ValueError("第七轮训练计划哈希漂移")
    training_plan = json.loads(training_plan_path.read_text(encoding="utf-8"))
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_local_refiner_coarse_architecture")
    trainer = load_module("train-development-cycle-016-soft-boundary-f1-pilot.py", "cycle016_local_refiner_coarse_trainer")
    coarse = trainer.build_model(training_plan, architecture)
    checkpoint = torch.load(Path(plan["inputs"]["seventhWeights"]["path"]), map_location="cpu", weights_only=True)
    coarse.load_state_dict(checkpoint["model"], strict=True)
    torch.manual_seed(1605)
    return FrozenCoarseLocalBoundaryRefiner(coarse, plan["architecture"])


def audit_model(model: FrozenCoarseLocalBoundaryRefiner, plan: dict[str, Any], images: torch.Tensor, truth: torch.Tensor) -> dict[str, Any]:
    architecture = plan["architecture"]
    coarse_parameters = sum(parameter.numel() for parameter in model.coarse.parameters())
    refiner_parameters = sum(parameter.numel() for parameter in model.refiner.parameters())
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    context_radius = 1 + sum(int(value) for value in architecture["dilations"])
    if coarse_parameters != int(architecture["expectedCoarseParameters"]):
        raise ValueError(f"冻结粗模型参数量不一致：{coarse_parameters}")
    if refiner_parameters != int(architecture["expectedTrainableRefinerParameters"]):
        raise ValueError(f"修正器参数量不一致：{refiner_parameters}")
    if total_parameters != int(architecture["expectedTotalParameters"]):
        raise ValueError(f"总参数量不一致：{total_parameters}")
    if total_parameters > int(architecture["maximumTotalParameters"]):
        raise ValueError("总参数量超过合同")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("修正器训练可行性预注册为CUDA")
    model = model.to(device).train()
    images = images.to(device, non_blocking=True)
    truth = truth.to(device, non_blocking=True)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    with torch.amp.autocast(device_type="cuda"):
        final_logits, coarse_logits, band, residual = model.forward_with_aux(images)
    soft_loss = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_local_refiner_loss")
    loss, parts = soft_loss.soft_boundary_f1_loss(final_logits, truth, plan["loss"])
    loss.backward()
    refiner_named = [(name, parameter.grad) for name, parameter in model.refiner.named_parameters()]
    coarse_gradient_names = [name for name, parameter in model.coarse.named_parameters() if parameter.grad is not None]
    missing_refiner = [name for name, gradient in refiner_named if gradient is None]
    nonfinite_refiner = [name for name, gradient in refiner_named if gradient is not None and not torch.isfinite(gradient).all().item()]
    zero_refiner = [name for name, gradient in refiner_named if gradient is not None and torch.count_nonzero(gradient).item() == 0]
    outside = ~band
    outside_equal = torch.equal(final_logits[outside], coarse_logits[outside])
    target_logits = torch.where(truth >= 0.5, torch.full_like(truth, 20.0), torch.full_like(truth, -20.0))
    exact_residual = target_logits - coarse_logits.float()
    reconstructed = coarse_logits.float() + band.float() * exact_residual
    expected = torch.where(band, target_logits, coarse_logits.float())
    expression_exact = torch.equal(reconstructed, expected)
    peak = int(torch.cuda.max_memory_allocated())
    return {
        "coarseParameters": coarse_parameters,
        "trainableRefinerParameters": refiner_parameters,
        "totalParameters": total_parameters,
        "contextRadiusPixels": context_radius,
        "bandRadiusPixels": int(architecture["bandRadiusPixels"]),
        "allCoarseRequiresGradFalse": all(not parameter.requires_grad for parameter in model.coarse.parameters()),
        "coarseGradientTensorCount": len(coarse_gradient_names),
        "coarseGradientNames": coarse_gradient_names,
        "refinerGradientTensorCount": len(refiner_named),
        "missingRefinerGradientNames": missing_refiner,
        "nonfiniteRefinerGradientNames": nonfinite_refiner,
        "zeroRefinerGradientNames": zero_refiner,
        "allRefinerGradientsFinite": not missing_refiner and not nonfinite_refiner,
        "everyRefinerParameterTensorNonzeroGradient": not missing_refiner and not zero_refiner,
        "outsideBandBitwiseEqualToCoarse": outside_equal,
        "perfectResidualExpressionExact": expression_exact,
        "bandPixelFraction": float(band.float().mean()),
        "residualFinite": bool(torch.isfinite(residual).all().item()),
        "loss": float(loss.detach()),
        "lossParts": parts,
        "lossFinite": bool(torch.isfinite(loss).item()),
        "peakAllocatedBytes": peak,
        "maximumBytes": int(architecture["maximumCudaPeakAllocatedBytesBatch2"]),
        "withinMemoryCap": peak <= int(architecture["maximumCudaPeakAllocatedBytesBatch2"]),
        "device": torch.cuda.get_device_name(0),
        "physicalBatchSize": int(images.shape[0]),
    }


def inspect_onnx(model_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    graph = onnx.load(str(model_path))
    onnx.checker.check_model(graph, full_check=True)
    counts = Counter(node.op_type for node in graph.graph.node)
    forbidden = sorted(set(counts).intersection(plan["architecture"]["forbiddenDeploymentOperators"]))
    ceiling_failures = {
        name: {"actual": int(counts.get(name, 0)), "maximum": int(maximum)}
        for name, maximum in plan["architecture"].get("baselineOperatorCeilings", {}).items()
        if int(counts.get(name, 0)) > int(maximum)
    }
    if forbidden:
        raise ValueError(f"部署ONNX包含禁止动态算子：{forbidden}")
    if ceiling_failures:
        raise ValueError(f"部署ONNX相对基线新增受限算子：{ceiling_failures}")
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    sample = np.linspace(-1.0, 1.0, 3 * 384 * 384, dtype=np.float32).reshape(1, 3, 384, 384)
    output = session.run([output_meta.name], {input_meta.name: sample})[0]
    if list(output.shape) != plan["architecture"]["outputShape"] or not np.isfinite(output).all():
        raise ValueError("ONNX静态输出合同失败")
    return {
        "input": {"name": input_meta.name, "shape": input_meta.shape, "type": input_meta.type},
        "output": {"name": output_meta.name, "shape": list(output.shape), "type": output_meta.type},
        "operatorCounts": dict(sorted(counts.items())),
        "forbiddenDeploymentOperatorsPresent": forbidden,
        "baselineOperatorCeilings": plan["architecture"].get("baselineOperatorCeilings", {}),
        "operatorCeilingFailures": ceiling_failures,
        "operatorCount": len(graph.graph.node),
        "runtimeProviders": session.get_providers(),
        "sampleOutput": {"minimum": float(output.min()), "maximum": float(output.max()), "mean": float(output.mean()), "finite": True},
    }


def export_and_report(plan_path: Path, model_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    _, dataset_report, dataset_root = validate_plan(plan)
    guards = load_module("train-yolo-seg.py", "cycle016_local_refiner_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_local_refiner_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    if len(val_records) != int(plan["datasetContract"]["requiredValidationInstances"]):
        raise ValueError("ROI v2验证实例数不一致")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_local_refiner_dataset")
    dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=1605)
    images, truth, identities = next(iter(DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0)))
    model = load_model(plan)
    audit = audit_model(model, plan, images, truth)
    gate = plan["reachabilityGate"]
    gates = {
        "coarseFrozen": audit["allCoarseRequiresGradFalse"] and audit["coarseGradientTensorCount"] == 0,
        "refinerGradientsFinite": audit["allRefinerGradientsFinite"],
        "allRefinerParametersReceiveGradient": audit["everyRefinerParameterTensorNonzeroGradient"],
        "outsideBandIdentity": audit["outsideBandBitwiseEqualToCoarse"],
        "perfectResidualExpression": audit["perfectResidualExpressionExact"],
        "contextRadius": audit["contextRadiusPixels"] >= int(plan["architecture"]["minimumContextRadiusPixels"]),
        "memoryWithinCap": audit["withinMemoryCap"],
        "lossAndResidualFinite": audit["lossFinite"] and audit["residualFinite"],
    }
    if not all(gates.values()):
        report = {"schemaVersion": 1, "ok": False, "decision": "local_boundary_refiner_gradient_or_resource_unreachable_no_training", "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "modelAudit": audit, "gates": gates, "identities": list(identities), "errors": []}
        write_atomic(report_path, report)
        return report
    if model_path.exists():
        raise ValueError(f"ONNX输出已存在，禁止覆盖：{model_path}")
    model = model.cpu().eval()
    sample = torch.zeros(tuple(plan["architecture"]["inputShape"]), dtype=torch.float32)
    with torch.inference_mode():
        eager = model(sample)
        if list(eager.shape) != plan["architecture"]["outputShape"] or not torch.isfinite(eager).all():
            raise ValueError("PyTorch静态输出合同失败")
        torch.onnx.export(model, (sample,), str(model_path), input_names=["pixel_values"], output_names=["logits"], opset_version=int(plan["architecture"]["opset"]), do_constant_folding=True, dynamo=False)
    runtime = inspect_onnx(model_path, plan)
    model_bytes = model_path.stat().st_size
    if model_bytes > int(plan["architecture"]["maximumFp32OnnxBytes"]):
        raise ValueError("FP32 ONNX超过预注册体积上限")
    removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "local_boundary_refiner_static_feasible_pending_browser_runtime",
        "scope": plan["scope"],
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
        "singleChangedVariable": plan["singleChangedVariable"],
        "architecture": plan["architecture"],
        "loss": plan["loss"],
        "reachabilityGate": gate,
        "modelAudit": audit,
        "gates": gates,
        "model": {"path": str(model_path), "sha256": sha256_file(model_path), "bytes": model_bytes, "withinCap": True},
        "runtime": runtime,
        "browserRuntime": {"status": "pending", "requiredBackends": plan["architecture"]["requiredBackends"]},
        "datasetIntegrity": {"removedCachesBefore": removed_before, "removedCachesAfter": removed_after, "datasetFilesSha256After": integrity["datasetFilesSha256"], "verified": integrity["ok"]},
        "probeIdentities": list(identities),
        "environment": {"python": os.sys.version.split()[0], "torch": torch.__version__, "onnx": onnx.__version__, "onnxruntime": ort.__version__},
        "errors": [],
    }
    write_atomic(report_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    validate_plan(plan)
    if report.get("decision") != "local_boundary_refiner_static_feasible_pending_browser_runtime" or not report.get("ok") or not all(report.get("gates", {}).values()):
        raise ValueError("局部边界修正器静态门未通过")
    model_path = Path(report["model"]["path"])
    if sha256_file(model_path) != report["model"]["sha256"]:
        raise ValueError("局部边界修正器ONNX哈希漂移")
    runtime = inspect_onnx(model_path, plan)
    if runtime != report["runtime"]:
        raise ValueError("局部边界修正器ONNX运行时重放不一致")
    return {"ok": True, "decision": "verified_local_boundary_refiner_static_feasible_pending_browser", "model": report["model"], "modelAudit": report["modelAudit"], "datasetIntegrity": report["datasetIntegrity"]}


def verify_browser(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("decision") != "local_boundary_refiner_browser_feasible_for_ninth_pilot":
        raise ValueError("浏览器报告结论不符合合同")
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"浏览器证据哈希漂移：{label}")
    feasibility = json.loads(Path(report["inputs"]["feasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "local_boundary_refiner_static_feasible_pending_browser_runtime" or feasibility["model"]["sha256"] != report["model"]["sha256"]:
        raise ValueError("浏览器报告与静态模型身份不一致")
    runtime = report["browserRuntime"]
    if runtime.get("webgpuExposed") is not True or "HeadlessChrome/" not in runtime.get("userAgent", ""):
        raise ValueError("真实Chromium或WebGPU环境合同未满足")
    results = runtime.get("results", [])
    if {row.get("backend") for row in results} != {"wasm", "webgpu"}:
        raise ValueError("浏览器后端集合不完整")
    for row in results:
        if not (row.get("ok") is True and row.get("finite") is True and row.get("inputNames") == ["pixel_values"] and row.get("outputNames") == ["logits"] and row.get("outputDims") == [1, 1, 384, 384] and float(row.get("initMs", -1)) >= 0 and float(row.get("inferMs", -1)) >= 0):
            raise ValueError(f"浏览器后端结果失败：{row.get('backend')}")
    snapshot = Path(report["inputs"]["playwrightSnapshot"]["path"]).read_text(encoding="utf-8").replace('\\"', '"')
    evaluation = Path(report["inputs"]["playwrightEval"]["path"]).read_text(encoding="utf-8").replace('\\"', '"')
    for token in ('"webgpuExposed": true', '"backend": "wasm"', '"backend": "webgpu"', '"finite": true'):
        if token not in snapshot or token not in evaluation:
            raise ValueError(f"Playwright证据缺少字段：{token}")
    console_lines = [line for line in Path(report["inputs"]["consoleLog"]["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(console_lines) != 1 or "favicon.ico" not in console_lines[0] or "404" not in console_lines[0]:
        raise ValueError("浏览器控制台出现未登记错误")
    return {"ok": True, "decision": "verified_local_boundary_refiner_browser_feasible_for_ninth_pilot", "model": report["model"], "backends": sorted(row["backend"] for row in results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--verify-browser-report", type=Path)
    args = parser.parse_args()
    if args.verify_browser_report:
        print(json.dumps(verify_browser(args.verify_browser_report.resolve()), ensure_ascii=False, indent=2))
    elif args.verify_report:
        print(json.dumps(verify(args.verify_report.resolve()), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.model or not args.report:
            parser.error("构建需要--plan、--model与--report")
        result = export_and_report(args.plan.resolve(), args.model.resolve(), args.report.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
