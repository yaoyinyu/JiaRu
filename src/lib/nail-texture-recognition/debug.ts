import type { NailTextureTensorSummary } from "./types.ts";
import type { ModelTensorLike } from "./postprocess.ts";

export interface SerializedModelTensor {
  dims?: number[];
  data: number[];
}

export function summarizeModelOutputs(
  outputs: Record<string, ModelTensorLike>,
  sampleSize: number = 8
): NailTextureTensorSummary[] {
  return Object.entries(outputs).map(([name, tensor]) => ({
    name,
    dims: tensor.dims ? Array.from(tensor.dims) : [],
    size: Array.from(tensor.data).length,
    sample: Array.from(tensor.data, (value) => Number(value) || 0).slice(0, sampleSize),
  }));
}

export function serializeModelOutputs(
  outputs: Record<string, ModelTensorLike>
): Record<string, SerializedModelTensor> {
  return Object.fromEntries(
    Object.entries(outputs).map(([name, tensor]) => [
      name,
      {
        dims: tensor.dims ? Array.from(tensor.dims) : [],
        data: Array.from(tensor.data, (value) => Number(value) || 0),
      },
    ])
  );
}
