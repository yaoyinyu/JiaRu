from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import Any

from _training_common import (
    count_files,
    load_dataset_config,
    resolve_best_weights_path,
    resolve_training_run_dir,
    write_json,
)


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _module_version(module_name: str) -> str | None:
    if not _module_available(module_name):
        return None
    try:
        module = __import__(module_name)
    except Exception:
        return None
    version = getattr(module, "__version__", None)
    return str(version) if version is not None else None


def _torch_info() -> dict[str, Any]:
    if not _module_available("torch"):
        return {"available": False, "version": None, "cuda_available": False, "device_count": 0}
    try:
        import torch

        return {
            "available": True,
            "version": str(getattr(torch, "__version__", "")),
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        }
    except Exception as exc:
        return {
            "available": True,
            "version": None,
            "cuda_available": False,
            "device_count": 0,
            "error": str(exc),
        }


def _is_local_weight_reference(model: str) -> bool:
    model_path = Path(model)
    return model_path.is_absolute() or model_path.parent != Path(".")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight the local environment before YOLO segmentation training.")
    parser.add_argument("--dataset", default="model/training/dataset.yaml", help="Path to dataset.yaml")
    parser.add_argument("--output-dir", default="model/exports/nail-texture-seg-v1", help="Directory for training outputs")
    parser.add_argument("--model", default="yolo11n-seg.pt", help="Ultralytics segmentation checkpoint to fine-tune")
    parser.add_argument("--run-name", default="nail-texture-seg-v1")
    parser.add_argument("--min-train-images", type=int, default=1)
    parser.add_argument("--min-val-images", type=int, default=1)
    parser.add_argument("--min-test-images", type=int, default=1)
    parser.add_argument("--require-local-model", action="store_true", help="Fail if --model does not point to an existing local file.")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 when any preflight check fails.")
    parser.add_argument("--output", default="", help="Optional JSON report path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_yaml = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    config = load_dataset_config(dataset_yaml)

    split_counts = {
        "train": count_files(config.dataset_root / config.train, IMAGE_SUFFIXES),
        "val": count_files(config.dataset_root / config.val, IMAGE_SUFFIXES),
        "test": count_files(config.dataset_root / config.test, IMAGE_SUFFIXES),
    }
    model_path = Path(args.model).expanduser()
    if not model_path.is_absolute():
        model_path = (Path.cwd() / model_path).resolve()
    model_exists = model_path.is_file()
    model_is_local_reference = _is_local_weight_reference(args.model)
    may_download_model = not model_exists and not model_is_local_reference

    checks = [
        {
            "name": "dataset_yaml_exists",
            "ok": dataset_yaml.is_file(),
            "detail": str(dataset_yaml),
        },
        {
            "name": "train_split_has_images",
            "ok": split_counts["train"] >= args.min_train_images,
            "detail": f"{split_counts['train']} train images",
        },
        {
            "name": "val_split_has_images",
            "ok": split_counts["val"] >= args.min_val_images,
            "detail": f"{split_counts['val']} val images",
        },
        {
            "name": "test_split_has_images",
            "ok": split_counts["test"] >= args.min_test_images,
            "detail": f"{split_counts['test']} test images",
        },
        {
            "name": "ultralytics_installed",
            "ok": _module_available("ultralytics"),
            "detail": _module_version("ultralytics") or "missing",
        },
        {
            "name": "local_model_available",
            "ok": model_exists or not args.require_local_model,
            "detail": str(model_path) if model_exists else f"{args.model} is not an existing local file",
        },
    ]

    warnings: list[str] = []
    if may_download_model:
        warnings.append(
            f"Model '{args.model}' is a named Ultralytics checkpoint and is not present locally; "
            "the first non-dry-run training may download it."
        )
    if not _module_available("ultralytics"):
        warnings.append("Install ultralytics before non-dry-run training: python -m pip install ultralytics")

    payload = {
        "ok": all(check["ok"] for check in checks),
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "platform": platform.platform(),
        },
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "split_counts": split_counts,
        "dependencies": {
            "ultralytics": {
                "available": _module_available("ultralytics"),
                "version": _module_version("ultralytics"),
            },
            "torch": _torch_info(),
        },
        "model": {
            "requested": args.model,
            "resolved_path": str(model_path),
            "exists": model_exists,
            "may_download": may_download_model,
            "require_local_model": args.require_local_model,
        },
        "output_dir": str(output_dir),
        "run_dir": str(resolve_training_run_dir(output_dir, args.run_name)),
        "best_weights_path": str(resolve_best_weights_path(output_dir, args.run_name)),
        "checks": checks,
        "warnings": warnings,
    }

    if args.output:
        write_json(Path(args.output).resolve(), payload)
    print(json.dumps(payload, indent=2))
    if args.strict and not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
