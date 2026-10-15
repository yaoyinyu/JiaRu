// 在受控原尺寸域内，Number精确容纳半整数乘F32比例；最终一次F32舍入复现原生FMA坐标。
const blocks = ["dec2", "dec1"];
const fields = ["lower", "upper", "weight0", "weight1"];
export const coordinateInputNames = blocks.flatMap((block) => ["y", "x"].flatMap((axis) =>
  fields.map((field) => `nativeCoord_${block}_${axis}_${field}`)));

export function nativeAxisCoordinates(incoming, outgoing, ratio) {
  if (![incoming, outgoing].every((n) => Number.isInteger(n) && n >= 1 && n <= 628) ||
      !Number.isFinite(ratio) || ratio !== Math.fround(incoming / outgoing)) throw new Error("native axis domain/ratio");
  const lower = new Int32Array(outgoing), upper = new Int32Array(outgoing);
  const weight0 = new Float32Array(outgoing), weight1 = new Float32Array(outgoing);
  for (let i = 0; i < outgoing; i++) {
    const value = Math.max(Math.fround((i + .5) * ratio - .5), 0);
    lower[i] = Math.min(Math.floor(value), incoming - 1);
    upper[i] = Math.min(lower[i] + 1, incoming - 1);
    weight1[i] = Math.fround(value - lower[i]);
    weight0[i] = Math.fround(1 - weight1[i]);
  }
  return { lower, upper, weight0, weight1 };
}

export function nativeCoordinateArrays(h, w, ratios) {
  if (![h, w].every((n) => Number.isInteger(n) && n >= 4 && n <= 628) ||
      !(ratios instanceof Float32Array) || ratios.length !== 4) throw new Error("controlled native size and four F32 ratios");
  const result = {};
  for (let scale = 0; scale < 2; scale++) {
    const factor = scale === 0 ? 4 : 2;
    for (const [axisIndex, axis, size] of [[0, "y", h], [1, "x", w]]) {
      const incoming = Math.floor(size / factor), outgoing = Math.floor(size / (factor / 2));
      const values = nativeAxisCoordinates(incoming, outgoing, ratios[scale * 2 + axisIndex]);
      for (const field of fields) {
        const integer = field === "lower" || field === "upper";
        const dims = integer ? [outgoing] : axis === "y" ? [1, 1, outgoing, 1] : [1, 1, 1, outgoing];
        result[`nativeCoord_${blocks[scale]}_${axis}_${field}`] = { values: values[field], dims, integer };
      }
    }
  }
  return result;
}

export function nativeCoordinateFeeds(ort, h, w, ratios) {
  return Object.fromEntries(Object.entries(nativeCoordinateArrays(h, w, ratios)).map(([name, row]) =>
    [name, new ort.Tensor(row.integer ? "int64" : "float32",
      row.integer ? BigInt64Array.from(row.values, BigInt) : row.values, row.dims)]));
}
