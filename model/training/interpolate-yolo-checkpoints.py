from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interpolate two architecture-identical YOLO checkpoints into one student checkpoint."
    )
    parser.add_argument("--base")
    tuned_group = parser.add_mutually_exclusive_group()
    tuned_group.add_argument("--candidate", dest="candidate")
    tuned_group.add_argument("--tuned", dest="candidate")
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--output")
    parser.add_argument("--report")
    parser.add_argument("--verify-report")
    return parser


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.exists() or temporary.exists():
        raise ValueError(f"refusing to overwrite report or temporary file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def verify_report(report_path: Path) -> dict[str, object]:
    if not report_path.is_file():
        raise ValueError(f"interpolation report is missing: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    inputs = report.get("inputs")
    output = report.get("output")
    if not isinstance(inputs, dict) or not isinstance(output, dict):
        raise ValueError("interpolation report is missing bound artifacts")
    base = inputs.get("base")
    tuned = inputs.get("candidate") or inputs.get("tuned")
    if not isinstance(base, dict) or not isinstance(tuned, dict):
        raise ValueError("interpolation report is missing bound checkpoints")
    for label, record in (("base", base), ("tuned", tuned), ("output", output)):
        artifact_path = Path(str(record.get("path", ""))).resolve()
        if not artifact_path.is_file():
            raise ValueError(f"{label} checkpoint is missing")
        if sha256(artifact_path) != record.get("sha256"):
            raise ValueError(f"{label} checkpoint SHA-256 drifted")
        if artifact_path.stat().st_size != record.get("bytes"):
            raise ValueError(f"{label} checkpoint size drifted")
    return report


def main() -> None:
    args = build_parser().parse_args()
    if args.verify_report:
        report = verify_report(Path(args.verify_report).resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    missing = [
        name
        for name in ("base", "candidate", "alpha", "output", "report")
        if getattr(args, name) is None
    ]
    if missing:
        raise ValueError(
            "creation mode requires: " + ", ".join(f"--{name}" for name in missing)
        )
    if not 0.0 < args.alpha < 1.0:
        raise ValueError("--alpha must be strictly between 0 and 1")

    import torch

    base_path = Path(args.base).resolve()
    candidate_path = Path(args.candidate).resolve()
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    temporary_output = output_path.with_suffix(output_path.suffix + ".tmp")
    for source in (base_path, candidate_path):
        if not source.is_file():
            raise ValueError(f"checkpoint is missing: {source}")
    if base_path == candidate_path or sha256(base_path) == sha256(candidate_path):
        raise ValueError("base and candidate checkpoints must differ")
    if output_path in (base_path, candidate_path) or report_path in (
        base_path,
        candidate_path,
        output_path,
    ):
        raise ValueError("output and report paths must be distinct from all inputs")
    if output_path.exists() or temporary_output.exists():
        raise ValueError("refusing to overwrite existing output")
    if report_path.exists():
        raise ValueError("refusing to overwrite existing report")

    base_checkpoint = torch.load(base_path, map_location="cpu", weights_only=False)
    candidate_checkpoint = torch.load(
        candidate_path, map_location="cpu", weights_only=False
    )
    base_model = base_checkpoint.get("model")
    candidate_model = candidate_checkpoint.get("model")
    if base_model is None or candidate_model is None:
        raise ValueError("both checkpoints must contain a model")
    base_state = base_model.float().state_dict()
    candidate_state = candidate_model.float().state_dict()
    if list(base_state) != list(candidate_state):
        raise ValueError("checkpoint state keys differ")

    interpolated: dict[str, torch.Tensor] = {}
    floating_tensors = 0
    copied_tensors = 0
    parameter_elements = 0
    for name, base_tensor in base_state.items():
        candidate_tensor = candidate_state[name]
        if base_tensor.shape != candidate_tensor.shape:
            raise ValueError(f"checkpoint tensor shape differs: {name}")
        parameter_elements += base_tensor.numel()
        if torch.is_floating_point(base_tensor):
            interpolated[name] = torch.lerp(
                base_tensor.to(dtype=torch.float32),
                candidate_tensor.to(dtype=torch.float32),
                args.alpha,
            ).to(dtype=base_tensor.dtype)
            floating_tensors += 1
        else:
            interpolated[name] = base_tensor.clone()
            copied_tensors += 1

    output_checkpoint = copy.deepcopy(base_checkpoint)
    output_model = copy.deepcopy(base_model).float()
    output_model.load_state_dict(interpolated, strict=True)
    output_checkpoint["model"] = output_model
    output_checkpoint["ema"] = None
    output_checkpoint["optimizer"] = None
    output_checkpoint["scaler"] = None
    output_checkpoint["epoch"] = -1
    output_checkpoint["best_fitness"] = None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(output_checkpoint, temporary_output)
    os.replace(temporary_output, output_path)
    report = {
        "schemaVersion": "jiaru-yolo-checkpoint-interpolation/v1",
        "ok": True,
        "decision": "interpolated_candidate_checkpoint",
        "releaseStatus": "diagnostic-only-pending-validation",
        "trainingUse": "prohibited",
        "inputs": {
            "base": {
                "path": str(base_path),
                "sha256": sha256(base_path),
                "bytes": base_path.stat().st_size,
            },
            "candidate": {
                "path": str(candidate_path),
                "sha256": sha256(candidate_path),
                "bytes": candidate_path.stat().st_size,
            },
        },
        "alpha": args.alpha,
        "interpolation": {
            "baseWeight": 1.0 - args.alpha,
            "tunedWeight": args.alpha,
        },
        "structure": {
            "stateTensorCount": len(base_state),
            "floatingTensorCount": floating_tensors,
            "copiedNonFloatingTensorCount": copied_tensors,
            "parameterElements": parameter_elements,
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256(output_path),
            "bytes": output_path.stat().st_size,
        },
        "selectionPolicy": {
            "calibrationSplit": "source-isolated-val30-only",
            "frozenTest100InferenceProhibitedBeforeValWin": True,
            "productionPromotionAuthorized": False,
        },
    }
    write_json_atomic(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
