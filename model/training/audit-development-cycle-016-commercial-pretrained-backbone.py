#!/usr/bin/env python3
"""审计可商用预训练编码器并导出DINOv2-small ROI静态ONNX。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F
from torch import nn
from transformers import AutoModel


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


class Dinov2RoiSegmenter(nn.Module):
    def __init__(self, backbone: nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        self.decoder = nn.Sequential(
            nn.Conv2d(384, 128, 3, padding=1, bias=False),
            nn.GroupNorm(8, 128),
            nn.GELU(),
            nn.Conv2d(128, 64, 3, padding=1, bias=False),
            nn.GroupNorm(8, 64),
            nn.GELU(),
            nn.Conv2d(64, 1, 1),
        )
        self.refine = nn.Sequential(
            nn.Conv2d(4, 16, 3, padding=1, bias=False),
            nn.GroupNorm(4, 16),
            nn.GELU(),
            nn.Conv2d(16, 1, 3, padding=1),
        )

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        padded = F.pad(pixel_values, (4, 4, 4, 4), mode="replicate")
        tokens = self.backbone(
            pixel_values=padded,
            interpolate_pos_encoding=True,
            return_dict=False,
        )[0][:, 1:, :]
        features = tokens.transpose(1, 2).reshape(pixel_values.shape[0], 384, 28, 28)
        coarse = self.decoder(features)
        coarse = F.interpolate(coarse, size=(384, 384), mode="bilinear", align_corners=False)
        return coarse + self.refine(torch.cat((pixel_values, coarse), dim=1))


def validate_sources(plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = Path(plan["sourceSnapshotManifest"])
    if sha256_file(manifest_path) != plan["sourceSnapshotManifestSha256"]:
        raise ValueError("许可来源快照manifest哈希不一致")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, binding in manifest.items():
        if isinstance(binding, dict) and "path" in binding and "sha256" in binding:
            if sha256_file(Path(binding["path"])) != binding["sha256"]:
                raise ValueError(f"许可来源快照漂移：{name}")
    dino_readme = Path(manifest["dinov2-README.md"]["path"]).read_text(encoding="utf-8")
    dino_card = Path(manifest["dinov2-MODEL_CARD.md"]["path"]).read_text(encoding="utf-8")
    apple_license = Path(manifest["apple-mobilevit-xx-smallEvidence"]["path"]).read_text(encoding="utf-8")
    nvidia_license = Path(manifest["nvidiaSegFormerLicense"]["path"]).read_text(encoding="utf-8")
    timm_readme = Path(manifest["timm-README.md"]["path"]).read_text(encoding="utf-8")
    checks = {
        "dinov2ApacheCodeAndWeights": "DINOv2 code and model weights are released under the Apache License 2.0" in dino_readme,
        "dinov2ModelCardApache": "**License:** Apache License 2.0" in dino_card,
        "appleResearchOnly": "exclusively for Research Purposes" in apple_license and "does not include any commercial exploitation" in apple_license,
        "nvidiaNoncommercial": "only may be used or intended for use\nnon-commercially" in nvidia_license,
        "timmImageNetAmbiguity": "one should assume that the original dataset license applies to the weights" in timm_readme,
    }
    if not all(checks.values()):
        raise ValueError(f"许可文本语义检查失败：{checks}")
    decisions = [
        {"id": "facebook-dinov2-small", "decision": "eligible_for_commercial_feasibility", "reason": "官方仓库明确声明常规DINOv2代码和模型权重均为Apache-2.0；模型卡同样登记Apache-2.0。"},
        {"id": "apple-mobilevit-xx-small", "decision": "rejected_noncommercial_research_only", "reason": "官方权重协议限定Research Purposes并明确排除商业开发、商业产品或服务。"},
        {"id": "nvidia-mit-b0", "decision": "rejected_noncommercial_research_only", "reason": "官方SegFormer许可证第3.3条限定非商业研究或评估使用。"},
        {"id": "timm-imagenet-pretrained-family", "decision": "rejected_ambiguous_commercial_weight_rights", "reason": "官方README要求假定ImageNet原数据许可适用于权重并建议商业使用前寻求法律意见，不满足本项目明确商用门。"},
    ]
    expected = {row["id"]: row["expectedDecision"] for row in plan["shortlist"]}
    if {row["id"]: row["decision"] for row in decisions} != expected:
        raise ValueError("许可裁决与预注册计划不一致")
    return {"manifest": {"path": str(manifest_path), "sha256": sha256_file(manifest_path)}, "checks": checks}, decisions


def load_model(plan: dict[str, Any]) -> Dinov2RoiSegmenter:
    selected = plan["selected"]
    weight_path = Path(selected["cachedWeight"])
    if sha256_file(weight_path) != selected["cachedWeightSha256"]:
        raise ValueError("DINOv2冻结权重哈希不一致")
    torch.manual_seed(1604)
    backbone = AutoModel.from_pretrained(
        selected["huggingFaceModelId"],
        revision=selected["revision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    return Dinov2RoiSegmenter(backbone).eval()


def inspect_onnx(model_path: Path, expected_output: list[int]) -> dict[str, Any]:
    model = onnx.load(str(model_path))
    onnx.checker.check_model(model, full_check=True)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    sample = np.linspace(-1.0, 1.0, 3 * 384 * 384, dtype=np.float32).reshape(1, 3, 384, 384)
    output = session.run([output_meta.name], {input_meta.name: sample})[0]
    if list(output.shape) != expected_output:
        raise ValueError(f"ONNX输出尺寸不符合合同：{output.shape}")
    if not np.isfinite(output).all():
        raise ValueError("ONNX输出包含非有限值")
    return {
        "input": {"name": input_meta.name, "shape": input_meta.shape, "type": input_meta.type},
        "output": {"name": output_meta.name, "shape": list(output.shape), "type": output_meta.type},
        "operators": sorted({node.op_type for node in model.graph.node}),
        "operatorCount": len(model.graph.node),
        "runtimeProviders": session.get_providers(),
        "sampleOutput": {"minimum": float(output.min()), "maximum": float(output.max()), "mean": float(output.mean()), "finite": True},
    }


def export_and_report(plan_path: Path, model_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source_evidence, decisions = validate_sources(plan)
    if model_path.exists():
        raise ValueError(f"ONNX输出已存在，禁止覆盖：{model_path}")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = load_model(plan)
    sample = torch.zeros(tuple(plan["runtimeContract"]["inputShape"]), dtype=torch.float32)
    with torch.inference_mode():
        eager = model(sample)
    if list(eager.shape) != plan["runtimeContract"]["outputShape"] or not torch.isfinite(eager).all():
        raise ValueError("PyTorch静态输入输出合同失败")
    with torch.inference_mode():
        torch.onnx.export(
            model,
            (sample,),
            str(model_path),
            input_names=["pixel_values"],
            output_names=["logits"],
            opset_version=int(plan["runtimeContract"]["opset"]),
            do_constant_folding=True,
            dynamo=False,
        )
    runtime = inspect_onnx(model_path, plan["runtimeContract"]["outputShape"])
    bytes_count = model_path.stat().st_size
    within_cap = bytes_count <= int(plan["runtimeContract"]["maximumFp32OnnxBytesForPilot"])
    if not within_cap:
        raise ValueError(f"FP32 ONNX超过pilot体积上限：{bytes_count}")
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "commercial_pretrained_backbone_selected_pending_browser_runtime",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "sourceSnapshot": source_evidence["manifest"],
            "cachedWeight": {"path": plan["selected"]["cachedWeight"], "sha256": plan["selected"]["cachedWeightSha256"]},
        },
        "licenseAudit": {"checks": source_evidence["checks"], "decisions": decisions, "selected": plan["selected"]["id"]},
        "architecture": {
            "name": "DINOv2-small ViT-S/14 plus fixed full-resolution ROI decoder",
            "backboneParameters": sum(parameter.numel() for parameter in model.backbone.parameters()),
            "totalParameters": sum(parameter.numel() for parameter in model.parameters()),
            "inputShape": plan["runtimeContract"]["inputShape"],
            "internalPaddedShape": plan["runtimeContract"]["internalPaddedShape"],
            "patchGrid": plan["runtimeContract"]["patchGrid"],
            "outputShape": plan["runtimeContract"]["outputShape"],
            "paddingReason": "384不能被patch size 14整除；模型内部对四边各复制填充4像素至392，避免丢弃输入边缘，再输出384全分辨率logit。",
        },
        "model": {"path": str(model_path), "sha256": sha256_file(model_path), "bytes": bytes_count, "withinPilotCap": within_cap, "opset": plan["runtimeContract"]["opset"]},
        "runtime": runtime,
        "browserRuntime": {"status": "pending", "requiredBackends": plan["runtimeContract"]["requiredBackends"]},
        "environment": {"python": os.sys.version.split()[0], "torch": torch.__version__, "transformers": __import__("transformers").__version__, "onnx": onnx.__version__, "onnxruntime": ort.__version__},
        "errors": [],
    }
    write_atomic(report_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    if sha256_file(Path(report["model"]["path"])) != report["model"]["sha256"]:
        raise ValueError("ONNX模型哈希漂移")
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    validate_sources(plan)
    runtime = inspect_onnx(Path(report["model"]["path"]), report["architecture"]["outputShape"])
    if runtime != report["runtime"]:
        raise ValueError("ONNX运行时重放结果不一致")
    return {"ok": True, "decision": "verified_commercial_pretrained_backbone_feasibility_pending_browser", "model": report["model"], "selected": report["licenseAudit"]["selected"]}


def verify_browser(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("decision") != "commercial_pretrained_backbone_browser_feasible_for_fourth_pilot":
        raise ValueError("浏览器报告结论不符合合同")
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"浏览器证据哈希漂移：{label}")

    feasibility = json.loads(Path(report["inputs"]["feasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if feasibility.get("ok") is not True or feasibility.get("licenseAudit", {}).get("selected") != "facebook-dinov2-small":
        raise ValueError("上游许可/ONNX可行性报告未通过")
    if feasibility["model"]["sha256"] != report["model"]["sha256"]:
        raise ValueError("浏览器报告与上游ONNX身份不一致")

    runtime = report["browserRuntime"]
    if runtime.get("webgpuExposed") is not True or "HeadlessChrome/153" not in runtime.get("userAgent", ""):
        raise ValueError("浏览器或WebGPU环境合同未满足")
    results = runtime.get("results", [])
    if {row.get("backend") for row in results} != {"wasm", "webgpu"}:
        raise ValueError("浏览器后端集合不完整")
    for row in results:
        expected = (
            row.get("ok") is True
            and row.get("finite") is True
            and row.get("inputNames") == ["pixel_values"]
            and row.get("outputNames") == ["logits"]
            and row.get("outputDims") == [1, 1, 384, 384]
            and float(row.get("initMs", -1)) >= 0
            and float(row.get("inferMs", -1)) >= 0
        )
        if not expected:
            raise ValueError(f"浏览器后端结果失败：{row.get('backend')}")

    snapshot = Path(report["inputs"]["playwrightSnapshot"]["path"]).read_text(encoding="utf-8")
    evaluation = Path(report["inputs"]["playwrightEval"]["path"]).read_text(encoding="utf-8")
    snapshot = snapshot.replace('\\"', '"')
    evaluation = evaluation.replace('\\"', '"')
    for token in ('"webgpuExposed": true', '"backend": "wasm"', '"backend": "webgpu"', '"finite": true'):
        if token not in snapshot or token not in evaluation:
            raise ValueError(f"Playwright证据缺少字段：{token}")
    console_lines = [line for line in Path(report["inputs"]["consoleLog"]["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(console_lines) != 1 or "favicon.ico" not in console_lines[0] or "404" not in console_lines[0]:
        raise ValueError("浏览器控制台出现未登记错误")
    return {
        "ok": True,
        "decision": "verified_commercial_pretrained_backbone_browser_feasible_for_fourth_pilot",
        "model": report["model"],
        "backends": sorted(row["backend"] for row in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--verify-browser-report", type=Path)
    args = parser.parse_args()
    if args.verify_browser_report:
        print(json.dumps(verify_browser(args.verify_browser_report), ensure_ascii=False, indent=2))
    elif args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.model or not args.report:
            parser.error("构建需要--plan、--model与--report")
        print(json.dumps(export_and_report(args.plan, args.model, args.report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
