from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DECISION = "interpolated_candidate_checkpoint"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Interpolate two architecture-identical Ultralytics checkpoints and "
            "write hash-bound candidate evidence."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base")
    mode.add_argument("--verify-report")
    parser.add_argument("--tuned")
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--output")
    parser.add_argument("--report")
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def ensure_new_output(path: Path, inputs: list[Path]) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing output: {path}")
    if any(path == input_path for input_path in inputs):
        raise ValueError("output path must differ from every input path")


def require_checkpoint(path: Path, torch: Any) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"checkpoint is missing: {path}")
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict):
        raise ValueError(f"checkpoint root is not a dictionary: {path}")
    if checkpoint.get("ema") is not None:
        raise ValueError(
            "checkpoint contains a non-empty ema model; freeze it to the model field first"
        )
    model = checkpoint.get("model")
    if model is None or not hasattr(model, "state_dict"):
        raise ValueError(f"checkpoint has no loadable model field: {path}")
    return checkpoint


def interpolate_state_dicts(
    base_state: dict[str, Any], tuned_state: dict[str, Any], alpha: float, torch: Any
) -> tuple[OrderedDict[str, Any], dict[str, int]]:
    if list(base_state) != list(tuned_state):
        raise ValueError("checkpoint model state keys differ")

    merged: OrderedDict[str, Any] = OrderedDict()
    floating = 0
    non_floating = 0
    changed_non_floating = 0

    for name, base_value in base_state.items():
        tuned_value = tuned_state[name]
        if not torch.is_tensor(base_value) or not torch.is_tensor(tuned_value):
            raise ValueError(f"state value is not a tensor: {name}")
        if base_value.shape != tuned_value.shape:
            raise ValueError(f"state tensor shape differs: {name}")
        if base_value.dtype != tuned_value.dtype:
            raise ValueError(f"state tensor dtype differs: {name}")

        if base_value.is_floating_point():
            floating += 1
            if alpha == 0.0:
                value = base_value.detach().clone()
            elif alpha == 1.0:
                value = tuned_value.detach().clone()
            else:
                value = torch.lerp(
                    base_value.detach().to(dtype=torch.float32),
                    tuned_value.detach().to(dtype=torch.float32),
                    alpha,
                ).to(dtype=base_value.dtype)
            merged[name] = value
            continue

        non_floating += 1
        if not torch.equal(base_value, tuned_value):
            changed_non_floating += 1
        endpoint = tuned_value if alpha >= 0.5 else base_value
        merged[name] = endpoint.detach().clone()

    return merged, {
        "stateTensors": len(merged),
        "floatingTensors": floating,
        "nonFloatingTensors": non_floating,
        "changedNonFloatingTensors": changed_non_floating,
    }


def build_interpolated_checkpoint(
    base_checkpoint: dict[str, Any],
    tuned_checkpoint: dict[str, Any],
    alpha: float,
    torch: Any,
) -> tuple[dict[str, Any], dict[str, int]]:
    base_model = base_checkpoint["model"]
    tuned_model = tuned_checkpoint["model"]
    base_state = base_model.state_dict()
    tuned_state = tuned_model.state_dict()
    merged_state, counts = interpolate_state_dicts(
        base_state, tuned_state, alpha, torch
    )

    merged_model = copy.deepcopy(base_model)
    result = merged_model.load_state_dict(merged_state, strict=True)
    if result.missing_keys or result.unexpected_keys:
        raise ValueError("interpolated state did not load strictly")

    checkpoint = copy.deepcopy(base_checkpoint)
    checkpoint["model"] = merged_model
    checkpoint["ema"] = None
    checkpoint["optimizer"] = None
    checkpoint["scaler"] = None
    checkpoint["updates"] = None
    checkpoint["epoch"] = -1
    checkpoint["best_fitness"] = None
    return checkpoint, counts


def atomic_torch_save(value: dict[str, Any], path: Path, torch: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        torch.save(value, temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_json_write(value: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def import_torch() -> Any:
    try:
        import torch
    except ImportError as error:
        raise RuntimeError(
            "PyTorch is required; use the project training Python runtime"
        ) from error
    return torch


def validate_alpha(alpha: float | None) -> float:
    if alpha is None or not 0.0 <= alpha <= 1.0:
        raise ValueError("--alpha must be between 0 and 1 inclusive")
    return alpha


def create(args: argparse.Namespace) -> None:
    if not args.tuned or args.alpha is None or not args.output or not args.report:
        raise ValueError("creation requires --tuned, --alpha, --output, and --report")

    alpha = validate_alpha(args.alpha)
    base = Path(args.base).resolve()
    tuned = Path(args.tuned).resolve()
    output = Path(args.output).resolve()
    report = Path(args.report).resolve()
    if base == tuned:
        raise ValueError("base and tuned checkpoints must differ")
    ensure_new_output(output, [base, tuned])
    ensure_new_output(report, [base, tuned, output])

    torch = import_torch()
    base_checkpoint = require_checkpoint(base, torch)
    tuned_checkpoint = require_checkpoint(tuned, torch)
    interpolated, counts = build_interpolated_checkpoint(
        base_checkpoint, tuned_checkpoint, alpha, torch
    )
    interpolated["jiaru_interpolation"] = {
        "schemaVersion": SCHEMA_VERSION,
        "baseSha256": sha256_file(base),
        "tunedSha256": sha256_file(tuned),
        "alpha": alpha,
    }

    try:
        atomic_torch_save(interpolated, output, torch)
        document = {
            "schemaVersion": SCHEMA_VERSION,
            "ok": True,
            "decision": DECISION,
            "releaseStatus": "diagnostic-only-pending-validation",
            "trainingUse": "derived-from-authorized-candidate-training",
            "interpolation": {
                "alpha": alpha,
                "baseWeight": 1.0 - alpha,
                "tunedWeight": alpha,
                "nonFloatingSelection": (
                    "tuned" if alpha >= 0.5 else "base"
                ),
            },
            "inputs": {
                "base": {"path": str(base), "sha256": sha256_file(base)},
                "tuned": {"path": str(tuned), "sha256": sha256_file(tuned)},
            },
            "output": {
                "path": str(output),
                "sha256": sha256_file(output),
                "sizeBytes": output.stat().st_size,
            },
            "counts": counts,
            "qualityGate": (
                "The derived checkpoint must independently pass canonical val, frozen "
                "test, fresh holdout, Beta, device, export, and rollback gates."
            ),
        }
        atomic_json_write(document, report)
    except Exception:
        if output.exists() and not report.exists():
            output.unlink()
        raise

    print(
        json.dumps(
            {
                "ok": True,
                "decision": DECISION,
                "alpha": alpha,
                "output": str(output),
                "report": str(report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def verify(report_path: Path) -> dict[str, Any]:
    report_path = report_path.resolve()
    report = load_json(report_path)
    if report.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("interpolation report schema version differs")
    if report.get("ok") is not True or report.get("decision") != DECISION:
        raise ValueError("interpolation report is not an approved derivation record")
    if report.get("releaseStatus") != "diagnostic-only-pending-validation":
        raise ValueError("interpolation report release status differs")

    inputs = report.get("inputs")
    output_record = report.get("output")
    interpolation = report.get("interpolation")
    if not isinstance(inputs, dict) or not isinstance(output_record, dict):
        raise ValueError("interpolation report path records are missing")
    if not isinstance(interpolation, dict):
        raise ValueError("interpolation report parameters are missing")

    base = Path(str((inputs.get("base") or {}).get("path", ""))).resolve()
    tuned = Path(str((inputs.get("tuned") or {}).get("path", ""))).resolve()
    output = Path(str(output_record.get("path", ""))).resolve()
    alpha = validate_alpha(interpolation.get("alpha"))
    for path, record, label in (
        (base, inputs.get("base"), "base"),
        (tuned, inputs.get("tuned"), "tuned"),
        (output, output_record, "output"),
    ):
        if not path.is_file():
            raise ValueError(f"{label} checkpoint is missing")
        if not isinstance(record, dict) or sha256_file(path) != record.get("sha256"):
            raise ValueError(f"{label} checkpoint SHA-256 drifted")

    torch = import_torch()
    base_checkpoint = require_checkpoint(base, torch)
    tuned_checkpoint = require_checkpoint(tuned, torch)
    output_checkpoint = require_checkpoint(output, torch)
    _, expected_counts = build_interpolated_checkpoint(
        base_checkpoint, tuned_checkpoint, alpha, torch
    )
    if report.get("counts") != expected_counts:
        raise ValueError("interpolation tensor counts drifted")

    expected_state, _ = interpolate_state_dicts(
        base_checkpoint["model"].state_dict(),
        tuned_checkpoint["model"].state_dict(),
        alpha,
        torch,
    )
    actual_state = output_checkpoint["model"].state_dict()
    if list(actual_state) != list(expected_state):
        raise ValueError("output checkpoint state keys drifted")
    for name, expected in expected_state.items():
        if not torch.equal(actual_state[name], expected):
            raise ValueError(f"output checkpoint interpolation drifted: {name}")

    metadata = output_checkpoint.get("jiaru_interpolation")
    if not isinstance(metadata, dict):
        raise ValueError("output checkpoint interpolation metadata is missing")
    if (
        metadata.get("schemaVersion") != SCHEMA_VERSION
        or metadata.get("baseSha256") != inputs["base"]["sha256"]
        or metadata.get("tunedSha256") != inputs["tuned"]["sha256"]
        or metadata.get("alpha") != alpha
    ):
        raise ValueError("output checkpoint interpolation metadata drifted")

    return {
        "ok": True,
        "decision": DECISION,
        "alpha": alpha,
        "reportPath": str(report_path),
        "reportSha256": sha256_file(report_path),
        "output": str(output),
        "outputSha256": sha256_file(output),
        "counts": expected_counts,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.verify_report:
        if any(
            value is not None
            for value in (args.tuned, args.alpha, args.output, args.report)
        ):
            raise ValueError("--verify-report cannot be combined with creation arguments")
        print(
            json.dumps(
                verify(Path(args.verify_report)),
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    create(args)


if __name__ == "__main__":
    main()
