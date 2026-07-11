from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DatasetConfig:
    dataset_root: Path
    train: str
    val: str
    test: str
    names: dict[int, str]
    task: str
    class_count: int
    image_size: int
    metadata: dict[str, Any]


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if text in {"true", "false"}:
      return text == "true"
    if text.isdigit():
      return int(text)
    try:
        return float(text)
    except ValueError:
        return text


def load_dataset_config(dataset_yaml_path: Path) -> DatasetConfig:
    """
    Parses the small dataset.yaml used in this repo without requiring PyYAML.
    It supports the subset we actually write: root-level scalars and one nested mapping.
    """
    raw_lines = dataset_yaml_path.read_text(encoding="utf-8").splitlines()
    root: dict[str, Any] = {}
    current_key: str | None = None
    current_map: dict[str, Any] | None = None

    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith("  "):
            current_map = None
            current_key = None
            if stripped.endswith(":"):
                current_key = stripped[:-1]
                current_map = {}
                root[current_key] = current_map
                continue
            key, value = stripped.split(":", 1)
            root[key.strip()] = _parse_scalar(value)
            continue
        if current_map is None or current_key is None:
            raise ValueError(f"Unexpected indentation in {dataset_yaml_path}: {line}")
        nested = stripped
        key, value = nested.split(":", 1)
        parsed_key = _parse_scalar(key)
        current_map[parsed_key] = _parse_scalar(value)

    dataset_root = (dataset_yaml_path.parent / str(root["path"])).resolve()
    names = root.get("names", {})
    if not isinstance(names, dict):
        raise ValueError("dataset.yaml names must be a mapping")

    return DatasetConfig(
        dataset_root=dataset_root,
        train=str(root["train"]),
        val=str(root["val"]),
        test=str(root["test"]),
        names={int(key): str(value) for key, value in names.items()},
        task=str(root["task"]),
        class_count=int(root["class_count"]),
        image_size=int(root["image_size"]),
        metadata=dict(root.get("metadata", {})),
    )


def ensure_python_dependency(module_name: str, install_hint: str) -> Any:
    try:
        return __import__(module_name)
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"Missing Python dependency '{module_name}'. Install it before running the non-dry-run path.\n"
            f"Suggested command: {install_hint}"
        ) from exc


def count_files(directory: Path, suffixes: tuple[str, ...]) -> int:
    if not directory.exists():
        return 0
    return sum(1 for item in directory.iterdir() if item.is_file() and item.suffix.lower() in suffixes)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_resolved_dataset_yaml(path: Path, config: DatasetConfig) -> Path:
    """Write an Ultralytics runtime YAML with an absolute dataset root."""
    lines = [
        f"path: {json.dumps(str(config.dataset_root), ensure_ascii=False)}",
        f"train: {config.train}",
        f"val: {config.val}",
        f"test: {config.test}",
        "",
        "names:",
        *[f"  {index}: {json.dumps(name, ensure_ascii=False)}" for index, name in sorted(config.names.items())],
        "",
        f"task: {config.task}",
        f"class_count: {config.class_count}",
        f"image_size: {config.image_size}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def resolve_training_run_dir(output_dir: Path, run_name: str) -> Path:
    return output_dir / run_name


def resolve_best_weights_path(output_dir: Path, run_name: str) -> Path:
    return resolve_training_run_dir(output_dir, run_name) / "weights" / "best.pt"
