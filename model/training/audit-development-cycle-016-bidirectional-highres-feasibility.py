#!/usr/bin/env python3
"""循环016双向高分辨率表示的预注册静态、梯度与资源审计。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch
from transformers import AutoModel


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(file_name: str, name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_model(plan: dict[str, Any]) -> torch.nn.Module:
    prerequisite = plan["prerequisites"]
    weight = Path(prerequisite["pretrainedWeight"])
    if sha256_file(weight) != prerequisite["pretrainedWeightSha256"]:
        raise ValueError("冻结DINOv2权重哈希漂移")
    torch.manual_seed(int(plan["training"]["seed"]))
    backbone = AutoModel.from_pretrained(
        prerequisite["huggingFaceModelId"],
        revision=prerequisite["huggingFaceRevision"],
        cache_dir=str(weight.parents[2]),
        local_files_only=True,
    )
    architecture = load_module("development-cycle-016-bidirectional-highres-model.py", "cycle016_bidirectional_model")
    return architecture.Dinov2BidirectionalHighResSegmenter(backbone)


def validate_bindings(plan: dict[str, Any]) -> None:
    for name, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"预注册输入哈希漂移：{name}")
    if sha256_file(Path(plan["prerequisites"]["pretrainedWeight"])) != plan["prerequisites"]["pretrainedWeightSha256"]:
        raise ValueError("DINOv2权重哈希漂移")
    materialization = json.loads(Path(plan["inputs"]["materializationReport"]["path"]).read_text(encoding="utf-8"))
    if materialization["datasetFilesSha256"] != plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("ROI v2文件树身份不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review["decision"] != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("验证真值审核未通过")


def inspect_onnx(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    graph = onnx.load(str(path))
    onnx.checker.check_model(graph, full_check=True)
    counts: dict[str, int] = {}
    for node in graph.graph.node:
        counts[node.op_type] = counts.get(node.op_type, 0) + 1
    for forbidden in plan["architecture"]["forbiddenOperators"]:
        if counts.get(forbidden, 0):
            raise ValueError(f"禁止的部署算子：{forbidden}")
    if counts.get("Gather", 0) > int(plan["architecture"]["maximumStaticGather"]):
        raise ValueError("静态Gather数超过DINOv2基线")
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    sample = np.linspace(-1, 1, 3 * 384 * 384, dtype=np.float32).reshape(1, 3, 384, 384)
    output = session.run(None, {session.get_inputs()[0].name: sample})[0]
    if list(output.shape) != plan["architecture"]["outputShape"] or not np.isfinite(output).all():
        raise ValueError("ORT CPU输出合同失败")
    return {"operatorCounts": counts, "cpuOutputShape": list(output.shape), "cpuOutputFinite": True,
            "cpuOutputMean": float(output.mean()), "cpuOutputMinimum": float(output.min()), "cpuOutputMaximum": float(output.max())}


def audit(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_bindings(plan)
    if sha256_file(Path(__file__).resolve().with_name("development-cycle-016-bidirectional-highres-model.py")) != plan["inputs"]["modelSource"]["sha256"]:
        raise ValueError("结构源码哈希漂移")
    output.mkdir(parents=True)
    model = load_model(plan).eval()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count > int(plan["architecture"]["maximumParameters"]):
        raise ValueError("参数量超限")
    sample = torch.zeros((1, 3, 384, 384), dtype=torch.float32)
    with torch.inference_mode():
        eager = model(sample)
        if list(eager.shape) != plan["architecture"]["outputShape"] or not torch.isfinite(eager).all():
            raise ValueError("PyTorch输出合同失败")
        torch.onnx.export(model, (sample,), str(output / "model.onnx"), input_names=["pixel_values"],
                          output_names=["logits"], opset_version=17, do_constant_folding=True, dynamo=False)
    onnx_path = output / "model.onnx"
    onnx_bytes = onnx_path.stat().st_size
    if onnx_bytes > int(plan["architecture"]["maximumFp32OnnxBytes"]):
        raise ValueError("ONNX体积超限")
    runtime = inspect_onnx(onnx_path, plan)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA不可用，无法执行梯度与显存门")
    model.backbone.gradient_checkpointing_enable()
    model = model.cuda().train()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    images = torch.linspace(-1, 1, 2 * 3 * 384 * 384, device="cuda").reshape(2, 3, 384, 384)
    truth = torch.zeros((2, 1, 384, 384), device="cuda")
    truth[:, :, 100:300, 150:270] = 1
    loss_module = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_bidirectional_loss")
    with torch.amp.autocast(device_type="cuda"):
        logits = model(images)
    loss, components = loss_module.soft_boundary_f1_loss(logits, truth, plan["loss"])
    loss.backward()
    gradients = {name: parameter.grad for name, parameter in model.named_parameters() if parameter.requires_grad}
    expected_unused = {"backbone.embeddings.mask_token"}
    missing = [name for name, gradient in gradients.items() if name not in expected_unused and
               (gradient is None or not torch.isfinite(gradient).all())]
    if any(gradients.get(name) is not None for name in expected_unused):
        raise ValueError("非遮蔽DINO前向的mask_token意外参与梯度")
    if missing:
        raise ValueError(f"全梯度门失败：{missing[:8]}")
    groups = {"backbone": "backbone.", "spatial": "spatial", "fusion": "top", "down": "down", "boundary": "boundary_tower", "output": "output"}
    nonzero_groups = {label: any(name.startswith(prefix) and gradient is not None and torch.count_nonzero(gradient).item() > 0
                                 for name, gradient in gradients.items()) for label, prefix in groups.items()}
    if not all(nonzero_groups.values()):
        raise ValueError(f"分支梯度为零：{nonzero_groups}")
    peak = int(torch.cuda.max_memory_allocated())
    if peak > int(plan["architecture"]["maximumCudaPeakAllocatedBytesBatch2"]):
        raise ValueError("batch2显存超限")
    report = {"schemaVersion": 1, "ok": True, "decision": "bidirectional_highres_static_feasible_pending_browser_and_microfit",
              "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
              "scope": plan["scope"], "architecture": plan["architecture"] | {"parameterCount": parameter_count},
              "model": {"path": str(onnx_path), "sha256": sha256_file(onnx_path), "bytes": onnx_bytes},
              "runtime": runtime, "gradient": {"usedFiniteParameterTensors": len(gradients) - len(expected_unused),
              "expectedUnused": sorted(expected_unused), "missingOrNonfinite": 0, "nonzeroGroups": nonzero_groups,
              "loss": float(loss.detach()), "components": components},
              "cuda": {"device": torch.cuda.get_device_name(0), "peakAllocatedBytes": peak, "physicalBatchSize": 2},
              "browser": {"status": "pending", "requiredBackends": ["wasm", "webgpu"]}, "errors": []}
    write_new(output / "feasibility-report.json", report)
    return report


def verify(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    for name, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入漂移：{name}")
    if sha256_file(Path(report["model"]["path"])) != report["model"]["sha256"]:
        raise ValueError("ONNX漂移")
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    runtime = inspect_onnx(Path(report["model"]["path"]), plan)
    if runtime != report["runtime"]:
        raise ValueError("ORT CPU重放不一致")
    return {"ok": True, "decision": "verified_bidirectional_highres_static_feasible_pending_browser_and_microfit",
            "modelSha256": report["model"]["sha256"], "peakAllocatedBytes": report["cuda"]["peakAllocatedBytes"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    result = verify(args.verify_report) if args.verify_report else audit(args.plan, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
