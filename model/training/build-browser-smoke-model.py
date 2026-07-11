from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


MASK_CHANNELS = 32
ATTRIBUTE_COUNT = 4 + 1 + MASK_CHANNELS


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_detection_tensor() -> np.ndarray:
    candidates = np.zeros((3, ATTRIBUTE_COUNT), dtype=np.float32)
    candidates[0, :5] = [20.0, 32.0, 8.0, 20.0, 0.96]
    candidates[0, 5] = 8.0
    candidates[1, :5] = [44.0, 32.0, 8.0, 20.0, 0.91]
    candidates[1, 6] = 8.0
    candidates[2, :5] = [20.5, 32.5, 8.0, 20.0, 0.70]
    candidates[2, 5] = 8.0
    return np.transpose(candidates, (1, 0))[None, :, :]


def build_prototype_tensor(proto_size: int) -> np.ndarray:
    prototypes = np.zeros((1, MASK_CHANNELS, proto_size, proto_size), dtype=np.float32)
    prototypes[0, 0, :, :] = -1.0
    prototypes[0, 1, :, :] = -1.0
    prototypes[0, 0, 5:11, 4:6] = 1.0
    prototypes[0, 1, 5:11, 10:12] = 1.0
    return prototypes


def candidate_iou(left: np.ndarray, right: np.ndarray) -> float:
    left_min_x, left_max_x = left[0] - left[2] / 2, left[0] + left[2] / 2
    left_min_y, left_max_y = left[1] - left[3] / 2, left[1] + left[3] / 2
    right_min_x, right_max_x = right[0] - right[2] / 2, right[0] + right[2] / 2
    right_min_y, right_max_y = right[1] - right[3] / 2, right[1] + right[3] / 2
    intersection = max(0.0, min(left_max_x, right_max_x) - max(left_min_x, right_min_x)) * max(
        0.0, min(left_max_y, right_max_y) - max(left_min_y, right_min_y)
    )
    union = left[2] * left[3] + right[2] * right[3] - intersection
    return intersection / union if union > 0 else 0.0


def build_python_postprocess_reference(
    detections: np.ndarray, prototypes: np.ndarray, input_size: int
) -> list[dict[str, float | int]]:
    rows = np.transpose(detections[0], (1, 0))
    rows = rows[rows[:, 4] >= 0.35]
    rows = rows[np.argsort(-rows[:, 4])]
    selected: list[np.ndarray] = []
    for row in rows:
        if all(candidate_iou(row, kept) < 0.55 for kept in selected):
            selected.append(row)

    proto_height, proto_width = prototypes.shape[2:]
    reference: list[dict[str, float | int]] = []
    for row in selected:
        cx, cy, width, length, score = row[:5]
        coefficients = row[5:]
        activation = np.tensordot(coefficients, prototypes[0], axes=(0, 0))
        binary = np.zeros((proto_height, proto_width), dtype=np.uint8)
        min_x = max(0, int(np.floor((cx - width / 2) / input_size * proto_width)))
        max_x = min(proto_width, int(np.ceil((cx + width / 2) / input_size * proto_width)))
        min_y = max(0, int(np.floor((cy - length / 2) / input_size * proto_height)))
        max_y = min(proto_height, int(np.ceil((cy + length / 2) / input_size * proto_height)))
        binary[min_y:max_y, min_x:max_x] = (activation[min_y:max_y, min_x:max_x] >= 0).astype(
            np.uint8
        )
        reference.append(
            {
                "cx": float(cx),
                "cy": float(cy),
                "width": float(width),
                "length": float(length),
                "score": float(score),
                "maskForegroundPixels": int(binary.sum()),
            }
        )
    return reference


def build_model(input_size: int, proto_size: int) -> onnx.ModelProto:
    detections = build_detection_tensor()
    prototypes = build_prototype_tensor(proto_size)
    graph = helper.make_graph(
        [
            helper.make_node(
                "Constant",
                inputs=[],
                outputs=["output0"],
                value=numpy_helper.from_array(detections, name="detections_value"),
            ),
            helper.make_node(
                "Constant",
                inputs=[],
                outputs=["output1"],
                value=numpy_helper.from_array(prototypes, name="prototype_value"),
            ),
        ],
        "nail_texture_browser_smoke",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, input_size, input_size])],
        [
            helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(detections.shape)),
            helper.make_tensor_value_info("output1", TensorProto.FLOAT, list(prototypes.shape)),
        ],
    )
    model = helper.make_model(
        graph,
        producer_name="jiaru-browser-smoke-model",
        opset_imports=[helper.make_opsetid("", 17)],
    )
    model.ir_version = min(model.ir_version, 10)
    onnx.checker.check_model(model)
    return model


def write_json(file_path: Path, payload: object) -> None:
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic real ONNX artifact for browser runtime smoke tests."
    )
    parser.add_argument(
        "--output-dir",
        default="public/models/nail-texture-seg-smoke",
        help="Directory for the isolated smoke model and manifest.",
    )
    parser.add_argument("--model-version", default="nail-texture-seg-smoke-v1")
    parser.add_argument("--input-size", type=int, default=64)
    parser.add_argument("--proto-size", type=int, default=16)
    args = parser.parse_args()

    if args.input_size < 32 or args.proto_size < 4:
        raise ValueError("input-size must be >= 32 and proto-size must be >= 4")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / f"{args.model_version}.onnx"
    manifest_path = output_dir / "manifest.json"
    output_dump_path = output_dir / "model-output.json"

    model = build_model(args.input_size, args.proto_size)
    onnx.save(model, model_path)
    model_size_bytes = model_path.stat().st_size
    model_sha256 = sha256_file(model_path)
    detections = build_detection_tensor()
    prototypes = build_prototype_tensor(args.proto_size)
    python_reference = build_python_postprocess_reference(
        detections, prototypes, args.input_size
    )

    write_json(
        manifest_path,
        {
            "version": args.model_version,
            "task": "segment",
            "inputSize": args.input_size,
            "inputLayout": "NCHW",
            "colorOrder": "RGB",
            "normalization": "zero_to_one",
            "resizeMode": "letterbox",
            "backendPreferences": ["webgpu", "wasm"],
            "modelFile": model_path.name,
            "outputContract": "ultralytics-seg-raw-v1",
            "modelSizeBytes": model_size_bytes,
            "sha256": model_sha256,
            "labels": ["nail_texture"],
            "smokeOnly": True,
        },
    )
    write_json(
        output_dump_path,
        {
            "modelVersion": args.model_version,
            "outputContract": "ultralytics-seg-raw-v1",
            "input": {"name": "images", "dims": [1, 3, args.input_size, args.input_size]},
            "preprocess": {
                "inputSize": args.input_size,
                "originalWidth": args.input_size,
                "originalHeight": args.input_size,
                "scaleX": 1,
                "scaleY": 1,
                "resizeScale": 1,
                "resizedWidth": args.input_size,
                "resizedHeight": args.input_size,
                "padLeft": 0,
                "padTop": 0,
            },
            "outputs": {
                "output0": {"dims": list(detections.shape), "data": detections.flatten().tolist()},
                "output1": {"dims": list(prototypes.shape), "data": prototypes.flatten().tolist()},
            },
            "pythonReference": python_reference,
            "expect": {
                "rawCandidateCount": 3,
                "candidateCount": 2,
                "minScore": 0.8,
                "firstSuggestedFinger": None,
                "requireMasks": True,
            },
        },
    )

    print(
        json.dumps(
            {
                "ok": True,
                "modelPath": str(model_path),
                "manifestPath": str(manifest_path),
                "outputDumpPath": str(output_dump_path),
                "modelSizeBytes": model_size_bytes,
                "sha256": model_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
