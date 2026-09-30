"""按哈希计划验证条件精修的零优化梯度、导出、CPU及浏览器合同。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import onnx
import onnxruntime as ort
import torch
from PIL import Image
from transformers import AutoModel


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bind(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def checked(binding):
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"binding mismatch: {path}")
    return path


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(str(path))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode())


def pixel_input(row):
    with Image.open(checked(row["paths"]["rgb"])) as image:
        rgb = np.asarray(image.convert("RGB")).copy()
    with Image.open(checked(row["paths"]["coarse"])) as image:
        coarse = np.asarray(image).copy()
    with Image.open(checked(row["paths"]["target"])) as image:
        target = np.asarray(image).copy()
    values = (rgb.astype(np.float64)/255 - np.array([.485,.456,.406]))/np.array([.229,.224,.225])
    packed = np.concatenate([values.transpose(2,0,1), coarse[None]/255],axis=0).astype(np.float32)
    return packed, (target[None]/255).astype(np.float32), rgb, coarse


def validate(plan):
    for binding in plan["inputs"].values():
        checked(binding)
    checked({"path":plan["prerequisites"]["pretrainedWeight"],"sha256":plan["prerequisites"]["pretrainedWeightSha256"]})
    manifest = read(plan["inputs"]["manifest"]["path"])
    material = read(plan["inputs"]["materialization"]["path"])
    data = read(plan["inputs"]["dataGate"]["path"])
    records = manifest["records"]
    if [r["id"] for r in records] != plan["candidateIds"] or len(records) != 45 or sum(r["presenceTarget"] for r in records) != 34:
        raise ValueError("reconstruction_mismatch: all45/34/11 denominator")
    if data["decision"] != "all45_diagnostic_data_gates_pass_pending_conditional_model_feasibility" or data["counts"]["newTrainingApprovedImages"] != 0:
        raise ValueError("diagnostic data gate")
    root = Path(material["outputDir"])
    expected = {Path(plan["inputs"]["manifest"]["path"]).resolve()}
    for row in records:
        for binding in row["paths"].values():
            expected.add(checked(binding).resolve())
    actual = {p.resolve() for p in root.rglob("*") if p.is_file() and p.name != "materialization-report.json"}
    if expected != actual or len(expected) != 271:
        raise ValueError("reconstruction_mismatch: complete ROI file tree")
    tree = hashlib.sha256("\n".join(sorted(f"{p.relative_to(root).as_posix()}\t{sha(p)}" for p in expected)).encode()).hexdigest()
    if tree != material["datasetFilesSha256"]:
        raise ValueError("ROI datasetFilesSha256")
    return records


def load_model(plan):
    torch.manual_seed(plan["seed"])
    prerequisite = plan["prerequisites"]
    weight = Path(prerequisite["pretrainedWeight"])
    backbone = AutoModel.from_pretrained(prerequisite["huggingFaceModelId"],revision=prerequisite["huggingFaceRevision"],cache_dir=str(weight.parents[2]),local_files_only=True)
    architecture = module("conditional_model",plan["inputs"]["modelSource"]["path"])
    return architecture.ConditionalNailRefiner(backbone), architecture


def inspect_onnx(path, plan):
    graph = onnx.load(str(path))
    onnx.checker.check_model(graph, full_check=True)
    counts = {}
    for node in graph.graph.node:
        counts[node.op_type] = counts.get(node.op_type,0)+1
    if any(counts.get(k,0) for k in plan["limits"]["forbiddenOperators"]) or counts.get("Gather",0)>40:
        raise ValueError("deployment operators")
    options = ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    session = ort.InferenceSession(str(path),options,providers=["CPUExecutionProvider"])
    if session.get_inputs()[0].shape != [1,4,384,384] or session.get_outputs()[0].shape != [1,1,384,384]:
        raise ValueError("ONNX four-channel contract")
    return session, counts


def audit(plan_path, output):
    plan=read(plan_path);records=validate(plan)
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True)
    torch.set_num_threads(2)
    model, architecture = load_model(plan)
    if not torch.cuda.is_available(): raise RuntimeError("CUDA required")
    parameter_count=sum(p.numel() for p in model.parameters())
    if parameter_count>plan["limits"]["maximumParameters"]: raise ValueError("parameters")
    by_id={r["id"]:r for r in records}
    selected=[by_id[k] for k in plan["runtimeProbeIds"]]
    loaded=[pixel_input(r) for r in selected]
    # 全45目标的损失梯度只作用于新临时logits，无训练权重或优化步骤。
    loss_rows=[]
    for row in records:
        _, target, _, _=pixel_input(row)
        logits=torch.zeros_like(torch.from_numpy(target)[None],requires_grad=True)
        loss,components=architecture.conditional_mask_loss(logits,torch.from_numpy(target)[None],boundary_weight=plan["loss"]["boundaryWeight"])
        loss.backward();gradient=logits.grad
        finite=bool(torch.isfinite(gradient).all());nonzero=bool(torch.count_nonzero(gradient))
        negative_sign=bool((gradient>0).all()) if not row["presenceTarget"] else None
        if not finite or not nonzero or negative_sign is False: raise ValueError("empty/positive logit gradient")
        loss_rows.append({"id":row["id"],"positive":bool(row["presenceTarget"]),"loss":float(loss.detach()),"gradientFinite":finite,"gradientNonzero":nonzero,"emptyAllGradientsPositive":negative_sign,"components":components})
    model=model.cuda().train();model.backbone.gradient_checkpointing_enable()
    sample=torch.from_numpy(np.stack([v[0] for v in loaded])).cuda()
    target=torch.from_numpy(np.stack([v[1] for v in loaded])).cuda()
    torch.cuda.reset_peak_memory_stats()
    seen_channels=[]
    hook=model.backbone.register_forward_pre_hook(lambda _m,_a,kw:seen_channels.append(int(kw["pixel_values"].shape[1])),with_kwargs=True)
    with torch.amp.autocast("cuda"): logits=model(sample)
    loss,components=architecture.conditional_mask_loss(logits,target,boundary_weight=plan["loss"]["boundaryWeight"])
    loss.backward();hook.remove()
    expected_unused={"backbone.embeddings.mask_token"}
    grads={name:p.grad for name,p in model.named_parameters() if p.requires_grad}
    missing=[name for name,g in grads.items() if name not in expected_unused and (g is None or not torch.isfinite(g).all())]
    if missing or any(grads.get(n) is not None for n in expected_unused): raise ValueError(f"full gradient: {missing}")
    prefixes={"backbone":"backbone.","spatial":"spatial","semantic":"semantic","merge":"merge","top":"top","down":"down","boundary":"boundary_tower","output":"output"}
    branches={key:any(n.startswith(prefix) and g is not None and bool(torch.count_nonzero(g)) for n,g in grads.items()) for key,prefix in prefixes.items()}
    condition_grad=grads["spatial384.layers.0.weight"][:,3]
    peak=torch.cuda.max_memory_allocated()
    if not all(branches.values()) or not bool(torch.count_nonzero(condition_grad)) or seen_channels != [3] or peak>plan["limits"]["maximumCudaPeakAllocatedBytesBatch2"]: raise ValueError("condition/backbone/resource gradient")
    gradient_report={"finiteUsedParameterTensors":len(grads)-len(expected_unused),"expectedUnused":sorted(expected_unused),"branches":branches,"conditionChannelNonzero":True,"backboneInputChannels":seen_channels,"peakAllocatedBytes":peak,"device":torch.cuda.get_device_name(0),"loss":float(loss.detach()),"components":components,"perCandidateLogitGradients":loss_rows}
    model.zero_grad(set_to_none=True);model.backbone.gradient_checkpointing_disable();model=model.cpu().eval()
    del sample,target,logits,loss,grads,condition_grad
    torch.cuda.empty_cache()
    probe=torch.from_numpy(loaded[0][0][None])
    with torch.inference_mode():
        original=model(probe).numpy()
        zero=probe.clone();zero[:,3]=0
        changed=model(zero).numpy()
        prompt_change=float(np.max(np.abs(original-changed)))
        if prompt_change<plan["limits"]["minimumPromptOutputChange"]: raise ValueError("condition has no structural output effect")
        torch.onnx.export(model,(probe,),str(output/"model.onnx"),input_names=["candidate_input"],output_names=["logits"],opset_version=17,do_constant_folding=True,dynamo=False)
    if (output/"model.onnx").stat().st_size>plan["limits"]["maximumFp32OnnxBytes"]: raise ValueError("ONNX bytes")
    session,operators=inspect_onnx(output/"model.onnx",plan)
    runtime=[]
    for row,values in zip(selected,loaded):
        x,_,rgb,coarse=values
        with torch.inference_mode(): eager=model(torch.from_numpy(x[None])).numpy()
        cpu=session.run(None,{"candidate_input":x[None]})[0]
        delta=float(np.max(np.abs(cpu-eager)))
        if not np.isfinite(cpu).all() or delta>plan["limits"]["maximumTorchCpuAbsoluteError"]: raise ValueError("CPU parity")
        folder=output/row["id"];folder.mkdir()
        for name,data in [("packed",x),("rgb",rgb),("coarse",coarse),("cpu",cpu)]: data.tofile(folder/f"{name}.bin")
        runtime.append({"id":row["id"],"torchCpuMaxAbsoluteError":delta,"files":{n:bind(folder/f"{n}.bin") for n in ["packed","rgb","coarse","cpu"]}})
    # 45条正/空真值仅用作接口逆映射oracle，不是模型预测或发布质量。
    controls=[]
    for row in records:
        with Image.open(checked(row["paths"]["target"])) as image:truth=np.asarray(image).copy()>=128
        control_logits=np.where(truth,16.,-16.).astype(np.float32)
        probability=(1/(1+np.exp(-control_logits))).astype(np.float32)
        w,h=row["nativeSize"]
        resized=np.asarray(Image.fromarray(probability).resize((w,h),Image.Resampling.BILINEAR))>=.5
        (output/f"{row['id']}-oracle.bin").write_bytes(control_logits.tobytes())
        (output/f"{row['id']}-native.bin").write_bytes(resized.astype(np.uint8).tobytes())
        controls.append({"id":row["id"],"cropBox":row["cropBox"],"nativeSize":row["nativeSize"],"kind":"mask" if resized.any() else "rejected","files":{"logits":bind(output/f"{row['id']}-oracle.bin"),"mask":bind(output/f"{row['id']}-native.bin")}})
    report={"schemaVersion":1,"ok":True,"decision":"conditional_refinement_static_gradient_feasible_pending_browser","inputs":{"plan":bind(plan_path),**plan["inputs"]},"model":bind(output/"model.onnx")|{"bytes":(output/"model.onnx").stat().st_size,"parameterCount":parameter_count},"operators":operators,"gradient":gradient_report,"promptOutputChangeMax":prompt_change,"runtimeProbes":runtime,"inverseOracleControls":controls,"optimizerSteps":0,"trainingApprovedImages":0,"scope":"Untrained conditional model interface and loss reachability only; no quality, independent validation, full split or release claim."}
    write_new(output/"feasibility-report.json",report)
    return report


def verify(path):
    report=read(path);plan=read(checked(report["inputs"]["plan"]))
    validate(plan)
    for binding in report["inputs"].values(): checked(binding)
    session,operators=inspect_onnx(checked(report["model"]),plan)
    if operators!=report["operators"] or not report["ok"] or report["optimizerSteps"]!=0: raise ValueError("static report gates")
    for row in report["runtimeProbes"]:
        for b in row["files"].values(): checked(b)
        x=np.fromfile(row["files"]["packed"]["path"],np.float32).reshape(1,4,384,384)
        cpu=np.fromfile(row["files"]["cpu"]["path"],np.float32).reshape(1,1,384,384)
        if np.max(np.abs(session.run(None,{"candidate_input":x})[0]-cpu))>1e-6: raise ValueError("CPU output replay")
    for row in report["inverseOracleControls"]:
        for b in row["files"].values():checked(b)
    return {"ok":True,"decision":"verified_conditional_static_gradient_pending_browser","model":report["model"],"optimizerSteps":0}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--plan",type=Path);parser.add_argument("--output",type=Path);parser.add_argument("--verify-report",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    guard=module("conditional_readonly_guard",root/"model/training/train-yolo-seg.py")
    guard.install_read_only_ultralytics_image_check()
    plan=read(args.plan if args.plan else read(args.verify_report)["inputs"]["plan"]["path"])
    cache_roots=[Path(p) for p in plan["cacheCleanupRoots"]]
    try:
        result=verify(args.verify_report) if args.verify_report else audit(args.plan.resolve(),args.output.resolve())
        print(json.dumps({"ok":result["ok"],"decision":result["decision"],"model":result["model"],"gradient":{k:v for k,v in result.get("gradient",{}).items() if k!="perCandidateLogitGradients"},"promptOutputChangeMax":result.get("promptOutputChangeMax"),"optimizerSteps":0},ensure_ascii=False))
    finally:
        for p in cache_roots:guard.remove_ultralytics_label_caches(p)


if __name__=="__main__": main()
