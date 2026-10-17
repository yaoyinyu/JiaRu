// 隔离开发Worker协议；实际调用前必须由主线程确认已持久化的执行许可。
import { createTwoHeadF64Runtime } from "./nail-presence-f64.mjs";
import { packNativeConditionalInput } from "./native-conditional-input.mjs";

const validId = (id) => typeof id === "string" && id.length > 0 && id.length <= 200;
const hex = async (bytes) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (x) => x.toString(16).padStart(2, "0")).join("");

export function createNativeConditionalWorkerService(emit, factory = createTwoHeadF64Runtime) {
  let state = "cold", runtime = null, active = null;
  const seen = new Set(), allowed = new Map();
  function error(id, reason, consumed = false) {
    emit({ type: "execution-error", id, reason, consumed, coarseFallbackUsed: false });
  }
  return async function receive(message) {
    const id = message?.id;
    if (!validId(id)) { error(id, "invalid_request_id"); return; }
    if (message.type === "initialize") {
      if (state !== "cold") { error(id, "worker_already_initialized"); return; }
      state = "initializing";
      try {
        if (!Array.isArray(message.cases) || message.cases.length === 0) throw new Error("complete case allowlist required");
        for (const c of message.cases) {
          if (!validId(c.id) || allowed.has(c.id) || !c.candidateIdentity) throw new Error("unique stable case identity required");
          allowed.set(c.id, structuredClone(c));
        }
        const a = message.assets;
        runtime = await factory(a.wasm, a.config, a.maskWeights, a.presenceWeights, a.presenceBias);
        const plans = [];
        for (const c of allowed.values()) {
          const plan = runtime.plan(c.height, c.width);
          if (plan.mask.highWaterBytes > 256 * 1024 * 1024) throw new Error("worker memory scheduler exceeds fixed allocation");
          plans.push({ id: c.id, width: c.width, height: c.height, plan });
        }
        state = "ready";
        emit({ type: "ready", id, plans });
      } catch (problem) { state = "failed"; error(id, String(problem)); }
      return;
    }
    if (message.type === "refine") {
      if (state !== "ready") { error(id, "worker_not_ready_or_busy"); return; }
      if (seen.has(id)) { error(id, "request_already_consumed"); return; }
      const c = allowed.get(id);
      if (!c || message.width !== c.width || message.height !== c.height
          || JSON.stringify(message.candidateIdentity) !== JSON.stringify(c.candidateIdentity)) {
        error(id, "request_identity_or_dimensions_mismatch"); return;
      }
      seen.add(id); state = "preparing";
      try {
        const ratios = message.ratios;
        const h = c.height, w = c.width;
        const expected = [Math.fround(Math.floor(h / 4) / Math.floor(h / 2)), Math.fround(Math.floor(w / 4) / Math.floor(w / 2)),
          Math.fround(Math.floor(h / 2) / h), Math.fround(Math.floor(w / 2) / w)];
        if (!(ratios instanceof Float32Array) || ratios.length !== 4 || ratios.some((v, i) => v !== expected[i])) {
          throw new Error("original F32 resize ratios required");
        }
        const candidate = packNativeConditionalInput(message.rgb, message.coarse, w, h);
        const inputSha256 = await hex(candidate.buffer);
        active = { id, c, candidate, ratios, inputSha256 };
        state = "prepared";
        emit({ type: "prepared", id, candidateIdentity: c.candidateIdentity, inputSha256, width: w, height: h,
          packedBytes: candidate.byteLength });
      } catch (problem) { active = null; state = "ready"; error(id, String(problem)); }
      return;
    }
    if (message.type === "execute") {
      if (state !== "prepared" || active?.id !== id || message.inputSha256 !== active.inputSha256) {
        error(id, "missing_matching_persisted_start_permit"); return;
      }
      const job = active; state = "executing";
      const start = performance.now();
      emit({ type: "started", id, candidateIdentity: job.c.candidateIdentity, inputSha256: job.inputSha256,
        monotonicStartMs: start, wallTimeStartMs: Date.now() });
      try {
        const result = await runtime.run(job.candidate, job.c.height, job.c.width, job.ratios);
        if (!(result.mask instanceof Float32Array) || result.mask.length !== job.c.height * job.c.width || !result.mask.every(Number.isFinite)
            || !(result.presence instanceof Float32Array) || result.presence.length !== 1 || !result.presence.every(Number.isFinite)
            || !result.presenceExecuted || result.mask.buffer === result.presence.buffer) throw new Error("complete finite independent F32 two-head outputs required");
        emit({ type: "result", id, candidateIdentity: job.c.candidateIdentity, inputSha256: job.inputSha256,
          width: job.c.width, height: job.c.height, mask: result.mask, presence: result.presence,
          elapsedMs: performance.now() - start, wasmMemoryBytes: result.wasmMemoryBytes,
          workspaceHighWaterBytes: result.workspaceHighWaterBytes, presenceAuxiliaryArrayBytes: result.presenceAuxiliaryArrayBytes,
          processPeakMemoryMeasured: false, coarseFallbackUsed: false }, [result.mask.buffer, result.presence.buffer]);
      } catch (problem) { error(id, String(problem), true); }
      finally { active = null; state = "ready"; }
      return;
    }
    error(id, "unsupported_worker_message");
  };
}
