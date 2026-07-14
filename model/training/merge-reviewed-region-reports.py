from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replace reviewed derived regions by parent while preserving provenance."
    )
    parser.add_argument("--base-report", required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--replacement-report", required=True)
    parser.add_argument("--replacement-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-report", required=True)
    return parser


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_file(root: Path, file_name: str) -> Path:
    if not file_name or Path(file_name).name != file_name:
        raise ValueError(f"unsafe output filename: {file_name!r}")
    path = (root / file_name).resolve()
    if path.parent != root or not path.is_file():
        raise FileNotFoundError(f"region output is missing or unsafe: {file_name}")
    return path


def validate_output(region: dict[str, object], root: Path) -> Path:
    file_name = str(region.get("outputFileName", ""))
    path = safe_file(root, file_name)
    actual = sha256_file(path)
    if actual != region.get("outputSha256"):
        raise ValueError(f"region sha256 mismatch: {file_name}")
    return path


def main() -> None:
    args = build_parser().parse_args()
    base_report_path = Path(args.base_report).resolve()
    replacement_report_path = Path(args.replacement_report).resolve()
    base_dir = Path(args.base_dir).resolve()
    replacement_dir = Path(args.replacement_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_report_path = Path(args.output_report).resolve()
    errors: list[str] = []

    base = load_json(base_report_path)
    replacement = load_json(replacement_report_path)
    if not base.get("ok"):
        errors.append("base region report must be ok")
    if not replacement.get("ok"):
        errors.append("replacement region report must be ok")

    base_by_parent: dict[str, dict[str, object]] = {}
    for item in base.get("outputs", []):
        parent = str(item.get("parentFileName", ""))
        if not parent or parent in base_by_parent:
            errors.append(f"base report has missing or duplicate parent: {parent!r}")
            continue
        base_by_parent[parent] = item

    replacements: dict[str, dict[str, object]] = {}
    for item in replacement.get("outputs", []):
        parent = str(item.get("parentFileName", ""))
        previous = base_by_parent.get(parent)
        if previous is None:
            errors.append(f"replacement parent is absent from base report: {parent}")
            continue
        if parent in replacements:
            errors.append(f"replacement report has duplicate parent: {parent}")
            continue
        if item.get("parentSha256") != previous.get("parentSha256"):
            errors.append(f"replacement parent sha256 mismatch: {parent}")
        if item.get("sourceGroup") != previous.get("sourceGroup"):
            errors.append(f"replacement sourceGroup mismatch: {parent}")
        replacements[parent] = item

    selected = [replacements.get(parent, item) for parent, item in base_by_parent.items()]
    names = [str(item.get("outputFileName", "")) for item in selected]
    if len(names) != len(set(names)):
        errors.append("merged report contains duplicate output filenames")

    materialized: list[tuple[Path, str]] = []
    if not errors:
        for item in selected:
            parent = str(item["parentFileName"])
            root = replacement_dir if parent in replacements else base_dir
            try:
                materialized.append((validate_output(item, root), str(item["outputFileName"])))
            except Exception as error:
                errors.append(str(error))

    if not errors:
        output_dir.mkdir(parents=True, exist_ok=True)
        for source, file_name in materialized:
            shutil.copy2(source, output_dir / file_name)

    outputs = selected if not errors else []
    report = {
        "ok": not errors,
        "version": "nail-texture-region-extraction/merged-v1",
        "baseReport": str(base_report_path),
        "replacementReport": str(replacement_report_path),
        "outputDir": str(output_dir),
        "baseCount": len(base_by_parent),
        "replacementCount": len(replacements),
        "completedCount": len(outputs),
        "replacedParents": sorted(replacements),
        "errors": errors,
        "outputs": outputs,
    }
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    output_report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("ok", "baseCount", "replacementCount", "completedCount", "errors")}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
