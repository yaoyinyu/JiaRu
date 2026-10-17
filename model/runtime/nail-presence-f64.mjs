// 隔离开发候选；完整非零控制与学得验收通过前不进入生产路由。
import { createMaskRuntime } from "./nail-mask-f64-v3.mjs";

const MAX_SIDE = 661;
const AUXILIARY_LIMIT = 8 * 1024 * 1024;

function dimensions(h, w) {
  if (![h, w].every((n) => Number.isInteger(n) && n >= 4 && n <= MAX_SIDE)) {
    throw new Error("presence native size outside controlled domain");
  }
  return [Math.floor(h / 4), Math.floor(w / 4)];
}

export function presenceWorkspaceBytes(h = MAX_SIDE, w = MAX_SIDE) {
  const [oh, ow] = dimensions(h, w);
  // 固定数组载荷上界，不是浏览器进程峰值或端到端内存实测。
  return (h + 1) * (w + 1) * 4 + oh * ow * 8 + 128 * 8 + 129 * 4 + 4;
}

export function createPresenceComputer(weights, bias, maxH = MAX_SIDE, maxW = MAX_SIDE) {
  const [maxOH, maxOW] = dimensions(maxH, maxW);
  if (!(weights instanceof Float32Array) || weights.length !== 128 || !weights.every(Number.isFinite)
      || !(bias instanceof Float32Array) || bias.length !== 1 || !bias.every(Number.isFinite)) {
    throw new Error("exact finite F32 presence parameters [1,128] and [1] required");
  }
  if (presenceWorkspaceBytes(maxH, maxW) > AUXILIARY_LIMIT) throw new Error("presence auxiliary allocation limit");
  const originalWeights = weights.slice(), originalBias = bias[0];
  const integral = new Uint32Array((maxH + 1) * (maxW + 1));
  const pooled = new Float64Array(maxOH * maxOW);
  const features = new Float64Array(128);
  let active = null;

  return {
    auxiliaryArrayBytes: presenceWorkspaceBytes(maxH, maxW),
    prepare(candidate, h, w) {
      const [oh, ow] = dimensions(h, w);
      if (h > maxH || w > maxW) throw new Error("presence workspace dimensions exceeded");
      if (active) throw new Error("presence input already prepared");
      if (!(candidate instanceof Float32Array) || candidate.length !== 4 * h * w || !candidate.every(Number.isFinite)) {
        throw new Error("complete finite F32 candidate required");
      }
      const plane = h * w, stride = w + 1;
      integral.fill(0, 0, (h + 1) * stride);
      for (let y = 0; y < h; y++) {
        let rowSum = 0;
        for (let x = 0; x < w; x++) {
          const seed = candidate[3 * plane + y * w + x];
          if (seed !== 0 && seed !== 1) throw new Error("original binary coarse seed required");
          rowSum += seed;
          integral[(y + 1) * stride + x + 1] = integral[y * stride + x + 1] + rowSum;
        }
      }
      let denominator = 0;
      for (let y = 0; y < oh; y++) {
        const y0 = Math.floor(y * h / oh), y1 = Math.ceil((y + 1) * h / oh);
        for (let x = 0; x < ow; x++) {
          const x0 = Math.floor(x * w / ow), x1 = Math.ceil((x + 1) * w / ow);
          const total = integral[y1 * stride + x1] - integral[y0 * stride + x1]
            - integral[y1 * stride + x0] + integral[y0 * stride + x0];
          // 原二值积分精确；分别按高、宽做F32除法后，才提升到F64传播。
          const seed = Math.fround(Math.fround(total / (y1 - y0)) / (x1 - x0));
          pooled[y * ow + x] = seed;
          denominator += seed;
        }
      }
      active = { h, w, oh, ow, denominator: Math.max(denominator, 1) };
    },
    finish(encoder, shape) {
      if (!active) throw new Error("presence input not prepared");
      const { oh, ow, denominator } = active, pixels = oh * ow;
      if (JSON.stringify(shape) !== JSON.stringify([1, 64, oh, ow])
          || !(encoder instanceof Float64Array) || encoder.length !== 64 * pixels || !encoder.every(Number.isFinite)) {
        throw new Error("complete finite F64 enc3.5 required");
      }
      for (let c = 0; c < 64; c++) {
        let local = 0, global = 0;
        for (let i = 0; i < pixels; i++) {
          const value = encoder[c * pixels + i];
          local += value * pooled[i];
          global += value;
        }
        features[c] = local / denominator;
        features[64 + c] = global / pixels;
      }
      let value = 0;
      for (let c = 0; c < 128; c++) value += features[c] * originalWeights[c];
      value += originalBias;
      const output = Math.fround(value);
      if (!Number.isFinite(output)) throw new Error("nonfinite presence output");
      active = null;
      return new Float32Array([output]);
    },
    reset() { active = null; },
  };
}

// 装配接口单独导出以便验证事件消费和失败语义；单元替身不构成完整模型控制。
export function attachF64Presence(maskRuntime, weights, bias) {
  const presence = createPresenceComputer(weights, bias);
  let running = false;
  return {
    plan(h, w) {
      dimensions(h, w);
      return { mask: maskRuntime.plan(h, w), presenceAuxiliaryArrayBytes: presence.auxiliaryArrayBytes,
        processPeakMemoryMeasured: false };
    },
    async run(candidate, h, w, ratios) {
      if (running) throw new Error("concurrent two-head F64 call rejected");
      running = true;
      try {
        presence.prepare(candidate, h, w);
        let head = null, captures = 0;
        const result = await maskRuntime.run(candidate, h, w, ratios, (event) => {
          if (event.op === "gelu" && event.name === "enc3" && event.suffix === "5") {
            if (++captures !== 1) throw new Error("duplicate F64 encoder boundary");
            head = presence.finish(event.values, event.shape);
          }
        });
        if (captures !== 1 || !head) throw new Error("missing F64 encoder boundary");
        return { ...result, presence: head, presenceExecuted: true,
          presencePrecision: "f32_parameters_binary_seed_pool_f32_then_f64_encoder_features_head_final_f32",
          presenceAuxiliaryArrayBytes: presence.auxiliaryArrayBytes };
      } finally { presence.reset(); running = false; }
    },
  };
}

export async function createTwoHeadF64Runtime(wasmBytes, config, maskWeights, presenceWeights, presenceBias) {
  const runtime = await createMaskRuntime(wasmBytes, config, maskWeights);
  return attachF64Presence(runtime, presenceWeights, presenceBias);
}
