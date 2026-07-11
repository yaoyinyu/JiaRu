from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from onnxruntime.quantization import (
    CalibrationDataReader,
    CalibrationMethod,
    QuantFormat,
    QuantType,
    quantize_static,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def letterbox_rgb(image_path: Path, input_size: int) -> np.ndarray:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        scale = min(input_size / image.width, input_size / image.height)
        width = max(1, round(image.width * scale))
        height = max(1, round(image.height * scale))
        resized = image.resize((width, height), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (input_size, input_size), (114, 114, 114))
        canvas.paste(resized, ((input_size - width) // 2, (input_size - height) // 2))
        array = np.asarray(canvas, dtype=np.float32) / 255.0
    return np.transpose(array, (2, 0, 1))[None, ...]


class NailCalibrationReader(CalibrationDataReader):
    def __init__(self, input_name: str, image_paths: list[Path], input_size: int):
        self._samples = iter(
            [{input_name: letterbox_rgb(image_path, input_size)} for image_path in image_paths]
        )

    def get_next(self) -> dict[str, np.ndarray] | None:
        return next(self._samples, None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an isolated QDQ INT8 ONNX candidate for browser compatibility evaluation."
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--input-name", default="images")
    parser.add_argument("--input-size", type=int, default=640)
    parser.add_argument("--max-samples", type=int, default=32)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model_path = Path(args.model).resolve()
    calibration_dir = Path(args.calibration_dir).resolve()
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    image_paths = sorted(
        path
        for path in calibration_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )[: args.max_samples]
    if not image_paths:
        raise RuntimeError(f"No calibration images found in {calibration_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    quantize_static(
        model_input=str(model_path),
        model_output=str(output_path),
        calibration_data_reader=NailCalibrationReader(
            args.input_name, image_paths, args.input_size
        ),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
        calibrate_method=CalibrationMethod.MinMax,
    )

    source_size = model_path.stat().st_size
    quantized_size = output_path.stat().st_size
    report = {
        "ok": True,
        "kind": "static-qdq-int8-evaluation-candidate",
        "sourceModel": str(model_path),
        "quantizedModel": str(output_path),
        "inputName": args.input_name,
        "inputSize": args.input_size,
        "calibrationSamples": len(image_paths),
        "sourceSizeBytes": source_size,
        "quantizedSizeBytes": quantized_size,
        "sizeReductionRatio": round(1 - quantized_size / source_size, 6),
        "sha256": sha256_file(output_path),
        "promotionAllowed": False,
        "requiredNextGates": [
            "onnx-runtime-load",
            "segmentation-metrics-comparison",
            "browser-webgpu-and-wasm-runtime",
            "edge-quality-review",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
