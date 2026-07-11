from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one ONNX image and persist raw browser-contract outputs.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_path = manifest_path.parent / manifest["modelFile"]
    input_size = int(manifest["inputSize"])

    with Image.open(args.image) as opened:
        image = opened.convert("RGB")
        original_width, original_height = image.size
        scale = min(input_size / original_width, input_size / original_height)
        resized_width = max(1, round(original_width * scale))
        resized_height = max(1, round(original_height * scale))
        resized = image.resize((resized_width, resized_height), Image.Resampling.BILINEAR)

    pad_left = (input_size - resized_width) // 2
    pad_top = (input_size - resized_height) // 2
    canvas = Image.new("RGB", (input_size, input_size), (114, 114, 114))
    canvas.paste(resized, (pad_left, pad_top))
    tensor = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))[None, :, :, :]

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]
    values = session.run(output_names, {input_name: tensor})
    payload = {
        "modelVersion": manifest["version"],
        "outputContract": manifest.get("outputContract"),
        "input": {"name": input_name, "dims": list(tensor.shape)},
        "preprocess": {
            "inputSize": input_size,
            "originalWidth": original_width,
            "originalHeight": original_height,
            "scaleX": original_width / resized_width,
            "scaleY": original_height / resized_height,
            "resizeScale": scale,
            "resizedWidth": resized_width,
            "resizedHeight": resized_height,
            "padLeft": pad_left,
            "padTop": pad_top,
        },
        "outputs": {
            name: {"dims": list(value.shape), "data": value.astype(np.float32).ravel().tolist()}
            for name, value in zip(output_names, values, strict=True)
        },
    }
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output": str(output_path),
        "modelVersion": manifest["version"],
        "input": payload["input"],
        "outputs": {name: list(value.shape) for name, value in zip(output_names, values, strict=True)},
    }, indent=2))


if __name__ == "__main__":
    main()
