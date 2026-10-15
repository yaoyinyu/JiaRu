// 隔离验收运行时；正式manifest接入前必须完成全后端非零控制及学得验收。
const align = (n) => Math.ceil(n / 16) * 16;
const shapes = [
  ["enc1", 4, 16], ["enc2", 16, 32], ["enc3", 32, 64],
  ["dec2", 96, 32], ["dec1", 48, 16],
];
export const parameterShapes = Object.fromEntries(shapes.flatMap(([name, incoming, channels]) => [
  [`${name}.conv0`, [channels, incoming, 3, 3]],
  [`${name}.gamma1`, [channels]], [`${name}.beta1`, [channels]],
  [`${name}.conv3`, [channels, channels, 3, 3]],
  [`${name}.gamma4`, [channels]], [`${name}.beta4`, [channels]],
]).concat([["delta.weight", [16]], ["delta.bias", [1]]]));

class Arena {
  constructor(start) { this.start = this.end = this.highWater = align(start); this.free = []; this.live = 0; this.peakLive = 0; }
  take(bytes) {
    bytes = align(bytes);
    const index = this.free.findIndex((block) => block.bytes >= bytes);
    let ptr;
    if (index < 0) { ptr = this.end; this.end += bytes; }
    else {
      const block = this.free[index]; ptr = block.ptr; block.ptr += bytes; block.bytes -= bytes;
      if (block.bytes === 0) this.free.splice(index, 1);
    }
    this.highWater = Math.max(this.highWater, this.end);
    this.live += bytes; this.peakLive = Math.max(this.peakLive, this.live);
    return { ptr, bytes };
  }
  release(block) {
    this.live -= block.bytes; this.free.push({ ...block }); this.free.sort((a, b) => a.ptr - b.ptr);
    for (let i = this.free.length - 2; i >= 0; i--) {
      if (this.free[i].ptr + this.free[i].bytes === this.free[i + 1].ptr) {
        this.free[i].bytes += this.free[i + 1].bytes; this.free.splice(i + 1, 1);
      }
    }
    while (this.free.length && this.free.at(-1).ptr + this.free.at(-1).bytes === this.end) {
      this.end = this.free.pop().ptr;
    }
  }
}

export function schedule(h, w, heapStart) {
  if (![h, w].every((n) => Number.isInteger(n) && n >= 4 && n <= 661)) throw new Error("native size outside controlled domain");
  const arena = new Arena(heapStart), steps = [];
  const tensor = (c, y, x, bytes = 8) => ({ ...arena.take(c * y * x * bytes), c, h: y, w: x });
  const push = (op, data) => steps.push({ op, ...data });
  const input = tensor(4, h, w, 4);
  let x = tensor(4, h, w); push("promote", { input, out: x });
  function block(name, first, second, channels) {
    let out = tensor(channels, first.h, first.w);
    push("conv3", { name: name + ".conv0", first, second, out });
    arena.release(first); if (second) arena.release(second);
    push("gn4", { name, suffix: "1", out }); push("gelu", { name, suffix: "2", out });
    const last = tensor(channels, out.h, out.w);
    push("conv3", { name: name + ".conv3", first: out, out: last }); arena.release(out);
    out = last;
    push("gn4", { name, suffix: "4", out }); push("gelu", { name, suffix: "5", out });
    return out;
  }
  function pool(first) {
    const out = tensor(first.c, Math.floor(first.h / 2), Math.floor(first.w / 2));
    push("pool2", { first, out }); return out;
  }
  const enc1 = block("enc1", x, null, 16);
  const enc2 = block("enc2", pool(enc1), null, 32);
  x = block("enc3", pool(enc2), null, 64);
  function decoder(name, first, skip, ratioOffset, channels) {
    const resized = tensor(first.c, skip.h, skip.w);
    push("resize64", { first, out: resized, ratioOffset }); arena.release(first);
    return block(name, resized, skip, channels);
  }
  x = decoder("dec2", x, enc2, 0, 32);
  x = decoder("dec1", x, enc1, 2, 16);
  const output = tensor(1, h, w, 4);
  push("final_mask", { first: x, input, out: output }); arena.release(x); arena.release(input);
  if (arena.live !== output.bytes) throw new Error("workspace lifetime mismatch");
  return { input, output, steps, highWaterBytes: arena.highWater, peakLiveBytes: arena.peakLive,
    workspaceBytes: arena.highWater - arena.start, materializedConcatBytes: 0 };
}

function validateConfig(config, weights) {
  if (!(weights instanceof Float32Array) || !weights.every(Number.isFinite)) throw new Error("finite exact F32 parameters required");
  if (JSON.stringify(Object.keys(config.tensors)) !== JSON.stringify(Object.keys(parameterShapes))) throw new Error("complete ordered parameter slots");
  let offset = 0;
  for (const [name, shape] of Object.entries(parameterShapes)) {
    const row = config.tensors[name];
    if (JSON.stringify(row.shape) !== JSON.stringify(shape) || row.offset !== offset) throw new Error("parameter shape/offset mismatch");
    offset += shape.reduce((a, b) => a * b, 1);
  }
  if (offset !== weights.length) throw new Error("parameter denominator mismatch");
  for (const [name] of shapes) for (const suffix of ["1", "4"]) {
    const epsilon = config.epsilon[`${name}.${suffix}`];
    if (!Number.isFinite(epsilon) || epsilon <= 0 || Math.fround(epsilon) !== epsilon) throw new Error("original F32 epsilon");
  }
  if (JSON.stringify(config.gelu) !== JSON.stringify([Math.fround(Math.SQRT2), 1, .5])) throw new Error("original GELU constant bits");
}

export async function createMaskRuntime(wasmBytes, config, weights, maxBytes = 256 * 1024 * 1024) {
  validateConfig(config, weights);
  if (!Number.isInteger(maxBytes) || maxBytes < 131072 || maxBytes > 256 * 1024 * 1024 || maxBytes % 65536) throw new Error("fixed bounded WASM memory required");
  const memory = new WebAssembly.Memory({ initial: maxBytes / 65536, maximum: maxBytes / 65536 });
  const { instance } = await WebAssembly.instantiate(wasmBytes, { env: { memory, exp: Math.exp } });
  const k = instance.exports, parameterBase = align(Number(k.__heap_base.value));
  if (parameterBase + weights.byteLength >= maxBytes) throw new Error("parameter memory overflow");
  new Float32Array(memory.buffer, parameterBase, weights.length).set(weights);
  const heapStart = align(parameterBase + weights.byteLength);
  const parameter = (name) => parameterBase + config.tensors[name].offset * 4;
  let running = false;
  return {
    memory, heapStart,
    plan: (h, w) => schedule(h, w, heapStart),
    async run(candidate, h, w, ratios, observe) {
      if (running) throw new Error("concurrent runtime call rejected");
      if (!(candidate instanceof Float32Array) || candidate.length !== 4 * h * w || !candidate.every(Number.isFinite)) throw new Error("complete finite F32 candidate");
      const expected = [Math.fround(Math.floor(h / 4) / Math.floor(h / 2)), Math.fround(Math.floor(w / 4) / Math.floor(w / 2)), Math.fround(Math.floor(h / 2) / h), Math.fround(Math.floor(w / 2) / w)];
      if (!(ratios instanceof Float32Array) || ratios.length !== 4 || ratios.some((a, i) => a !== expected[i])) throw new Error("original F32 native resize ratios");
      const plan = schedule(h, w, heapStart);
      if (plan.highWaterBytes > memory.buffer.byteLength) throw new Error("bounded memory exhausted before model input");
      running = true;
      const started = performance.now();
      try {
        new Float32Array(memory.buffer, plan.input.ptr, candidate.length).set(candidate);
        for (let ordinal = 0; ordinal < plan.steps.length; ordinal++) {
          const step = plan.steps[ordinal], a = step.first, b = step.second, out = step.out;
          switch (step.op) {
            case "promote": k.promote(step.input.ptr, out.ptr, out.c * out.h * out.w); break;
            case "conv3": k.conv3(a.ptr, b?.ptr ?? 0, parameter(step.name), out.ptr, a.c, b?.c ?? 0, out.c, out.h, out.w); break;
            case "gn4": k.gn4(out.ptr, parameter(`${step.name}.gamma${step.suffix}`), parameter(`${step.name}.beta${step.suffix}`), out.c, out.h, out.w, config.epsilon[`${step.name}.${step.suffix}`]); break;
            case "gelu": k.gelu(out.ptr, out.c * out.h * out.w, ...config.gelu); break;
            case "pool2": k.pool2(a.ptr, out.ptr, a.c, a.h, a.w); break;
            case "resize64": k.resize64(a.ptr, out.ptr, a.c, a.h, a.w, out.h, out.w, ratios[step.ratioOffset], ratios[step.ratioOffset + 1]); break;
            case "final_mask": k.final_mask(a.ptr, parameter("delta.weight"), parameter("delta.bias"), step.input.ptr, out.ptr, a.c, h * w); break;
            default: throw new Error("unknown frozen kernel");
          }
          if (observe) {
            const Type = step.op === "final_mask" ? Float32Array : Float64Array;
            await observe({ ordinal, op: step.op, name: step.name, suffix: step.suffix,
              shape: [1, out.c, out.h, out.w], values: new Type(memory.buffer, out.ptr, out.c * out.h * out.w) });
          }
        }
        const mask = new Float32Array(memory.buffer, plan.output.ptr, h * w).slice();
        if (!mask.every(Number.isFinite)) throw new Error("nonfinite mask output");
        return { mask, elapsedMs: performance.now() - started,
          wasmMemoryBytes: memory.buffer.byteLength, workspaceHighWaterBytes: plan.highWaterBytes,
          peakLiveWorkspaceBytes: plan.peakLiveBytes, materializedConcatBytes: 0,
          precision: "f32_parameters_f64_features_f32_coordinates_seed_and_final", presenceExecuted: false };
      } finally { running = false; }
    },
    erf64: (x) => k.erf64(x),
  };
}
