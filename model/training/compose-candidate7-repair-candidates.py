from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_bound_file(path_value: str, sha_value: str, label: str) -> Path:
    path = Path(path_value).resolve()
    if not path.is_file():
        raise ValueError(f"missing {label}: {path}")
    actual = sha256_file(path)
    if actual != sha_value:
        raise ValueError(f"{label} SHA-256 differs: expected={sha_value} actual={actual}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compose hash-bound candidate7 repair annotations without granting training truth."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-prompts", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = read_json(manifest_path)
    if manifest.get("schemaVersion") != 1 or manifest.get("decision") != "candidate7_repair_candidate_composition":
        raise ValueError("unsupported composition manifest")
    inputs = manifest.get("inputs", {})
    base_prompt_path = require_bound_file(
        str(inputs.get("basePrompts", "")), str(inputs.get("basePromptsSha256", "")), "base prompts"
    )
    base_report_path = require_bound_file(
        str(inputs.get("baseSamReport", "")), str(inputs.get("baseSamReportSha256", "")), "base SAM report"
    )
    base_prompts = read_json(base_prompt_path)
    base_report = read_json(base_report_path)
    if base_prompts.get("decision") != "sam_candidate_only_not_training_truth":
        raise ValueError("base prompts must remain candidate-only")
    if base_report.get("ok") is not True or base_report.get("decision") != "sam_candidate_only_not_training_truth":
        raise ValueError("base SAM report must pass and remain candidate-only")

    prompt_by_file = {str(item["fileName"]): item for item in base_prompts.get("images", [])}
    output_by_file = {str(item["fileName"]): item for item in base_report.get("outputs", [])}
    if set(prompt_by_file) != set(output_by_file):
        raise ValueError("base prompts and SAM report identities differ")

    replacements: dict[str, dict[str, Any]] = {}
    for item in manifest.get("replacements", []):
        file_name = str(item.get("fileName", ""))
        if not file_name or file_name in replacements or file_name not in prompt_by_file:
            raise ValueError(f"invalid replacement identity: {file_name}")
        annotation_path = require_bound_file(
            str(item.get("annotationPath", "")), str(item.get("annotationSha256", "")), f"annotation {file_name}"
        )
        evidence_path = require_bound_file(
            str(item.get("evidenceReport", "")), str(item.get("evidenceReportSha256", "")), f"evidence {file_name}"
        )
        evidence = read_json(evidence_path)
        evidence_output = next(
            (candidate for candidate in evidence.get("outputs", []) if candidate.get("fileName") == file_name),
            None,
        )
        if evidence.get("ok") is not True or evidence_output is None:
            raise ValueError(f"replacement evidence did not pass or lacks {file_name}")
        overlay_path = Path(str(evidence_output.get("overlayPath", ""))).resolve()
        if not overlay_path.is_file():
            raise ValueError(f"replacement overlay is missing: {overlay_path}")
        prompt_path_value = item.get("promptFile")
        if prompt_path_value:
            prompt_path = require_bound_file(
                str(prompt_path_value), str(item.get("promptFileSha256", "")), f"replacement prompts {file_name}"
            )
            replacement_prompts = read_json(prompt_path)
            replacement_item = next(
                (candidate for candidate in replacement_prompts.get("images", []) if candidate.get("fileName") == file_name),
                None,
            )
            if replacement_item is None:
                raise ValueError(f"replacement prompt file does not contain {file_name}")
        else:
            replacement_item = prompt_by_file[file_name]
        annotation = read_json(annotation_path)
        if annotation.get("image", {}).get("fileName") != file_name:
            raise ValueError(f"replacement annotation identity differs: {file_name}")
        expected = int(replacement_item.get("expectedFullyVisibleNails", len(replacement_item.get("boxes", []))))
        if len(replacement_item.get("boxes", [])) != expected or len(annotation.get("annotations", [])) != expected:
            raise ValueError(f"replacement prompt/annotation count differs from expected: {file_name}")
        replacements[file_name] = {
            "prompt": replacement_item,
            "annotationPath": annotation_path,
            "annotationSha256": sha256_file(annotation_path),
            "overlayPath": overlay_path,
            "overlaySha256": sha256_file(overlay_path),
            "evidenceReport": str(Path(str(item["evidenceReport"])).resolve()),
            "evidenceReportSha256": str(item["evidenceReportSha256"]),
            "replacementType": str(item.get("replacementType", "reviewed-replacement")),
        }

    output_dir = Path(args.output_dir).resolve()
    output_prompts = Path(args.output_prompts).resolve()
    report_path = Path(args.report).resolve()
    for target in (output_dir, output_prompts, report_path):
        if target.exists():
            raise ValueError(f"refusing to overwrite existing output: {target}")
    output_dir.mkdir(parents=True, exist_ok=False)

    combined_images: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for file_name in sorted(prompt_by_file):
        replacement = replacements.get(file_name)
        prompt_item = replacement["prompt"] if replacement else prompt_by_file[file_name]
        annotation_path = (
            replacement["annotationPath"]
            if replacement
            else Path(str(output_by_file[file_name]["annotationPath"])).resolve()
        )
        if not annotation_path.is_file():
            raise ValueError(f"missing base annotation: {annotation_path}")
        overlay_path = (
            replacement["overlayPath"]
            if replacement
            else Path(str(output_by_file[file_name]["overlayPath"])).resolve()
        )
        if not overlay_path.is_file():
            raise ValueError(f"missing candidate overlay: {overlay_path}")
        destination = output_dir / f"{Path(file_name).stem}.json"
        shutil.copyfile(annotation_path, destination)
        annotation = read_json(destination)
        polygon_count = len(annotation.get("annotations", []))
        combined_images.append(prompt_item)
        outputs.append(
            {
                "fileName": file_name,
                "sourceAnnotation": str(annotation_path),
                "sourceAnnotationSha256": sha256_file(annotation_path),
                "annotationPath": str(destination),
                "annotationSha256": sha256_file(destination),
                "overlayPath": str(overlay_path),
                "overlaySha256": sha256_file(overlay_path),
                "polygonCount": polygon_count,
                "sourceGroup": prompt_item["sourceGroup"],
                "replacementType": replacement["replacementType"] if replacement else "base-ranked-sam",
                "evidenceReport": replacement["evidenceReport"] if replacement else str(base_report_path),
                "evidenceReportSha256": (
                    replacement["evidenceReportSha256"] if replacement else sha256_file(base_report_path)
                ),
            }
        )

    combined_prompt_document = {
        **base_prompts,
        "source": "candidate7-reviewed-repair-composition",
        "decision": "sam_candidate_only_not_training_truth",
        "inputs": {
            "manifest": str(manifest_path),
            "manifestSha256": sha256_file(manifest_path),
            "basePrompts": str(base_prompt_path),
            "basePromptsSha256": sha256_file(base_prompt_path),
            "baseSamReport": str(base_report_path),
            "baseSamReportSha256": sha256_file(base_report_path),
        },
        "imageCount": len(combined_images),
        "promptCount": sum(len(item.get("boxes", [])) for item in combined_images),
        "unresolvedImageCount": 0,
        "unresolved": [],
        "images": combined_images,
    }
    output_prompts.parent.mkdir(parents=True, exist_ok=True)
    output_prompts.write_text(
        json.dumps(combined_prompt_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "schemaVersion": 1,
        "ok": True,
        "method": "candidate7-hash-bound-reviewed-repair-composition",
        "decision": "sam_candidate_only_not_training_truth",
        "trainingUse": "prohibited",
        "originalResolutionReviewRequired": True,
        "promptCount": combined_prompt_document["promptCount"],
        "imageCount": len(outputs),
        "completedCount": len(outputs),
        "errors": [],
        "inputs": combined_prompt_document["inputs"],
        "counts": {
            "images": len(outputs),
            "prompts": combined_prompt_document["promptCount"],
            "replacements": len(replacements),
        },
        "outputPrompts": str(output_prompts),
        "outputPromptsSha256": sha256_file(output_prompts),
        "outputs": outputs,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
