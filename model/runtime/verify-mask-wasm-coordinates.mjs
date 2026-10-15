export async function captureCoordinates(wasm, cases, read, write) {
  const memory = new WebAssembly.Memory({ initial: 2, maximum: 4096 });
  const { instance } = await WebAssembly.instantiate(wasm, { env: { memory, exp: Math.exp } });
  const k = instance.exports, base = Math.ceil(Number(k.__heap_base.value) / 16) * 16;
  const sha = async (raw) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", raw)), (n) => n.toString(16).padStart(2, "0")).join("");
  const records = [];
  for (const row of cases) {
    for (let index = 0; index < row.coordinateAxes.length; index++) {
      const axis = row.coordinateAxes[index], n = axis.outgoing;
      const pointers = [base, base + n * 4, base + n * 8, base + n * 12];
      k.capture_coordinates(axis.incoming, n, axis.ratio, ...pointers);
      const fields = {};
      for (const [i, field] of ["lower", "upper", "weight0", "weight1"].entries()) {
        const raw = new Uint8Array(memory.buffer, pointers[i], n * 4).slice();
        const bytes = i < 2 ? BigInt64Array.from(new Int32Array(raw.buffer), (x) => BigInt(x)).buffer : raw.buffer;
        const expected = await read(axis.fields[field].path);
        const digest = await sha(bytes);
        if (digest !== axis.fields[field].sha256 || digest !== await sha(expected)) throw new Error("whole original coordinate bytes mismatch");
        await write(`${row.ordinal}-${index}-${field}.bin`, bytes);
        fields[field] = { ...axis.fields[field], actualSha256: digest };
      }
      records.push({ ordinal: row.ordinal, index, incoming: axis.incoming, outgoing: n, fields });
    }
  }
  if (records.length !== cases.length * 4) throw new Error("complete both resize axes denominator");
  return { ok: true, records, projectModelInputs: 0 };
}
