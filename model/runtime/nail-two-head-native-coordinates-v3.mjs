import { coordinateInputNames, nativeCoordinateFeeds } from "./nail-native-coordinates-v2.mjs";
import { createMaskRuntime } from "./nail-mask-f64-v3.mjs";

function finiteHead(value, shape) {
  if (value.type !== "float32" || JSON.stringify(Array.from(value.dims)) !== JSON.stringify(shape)) throw new Error("original two-head shape/domain");
}

export async function createTwoHeadRoute(ort, modelBytes, artifacts, backend) {
  if (!["wasm", "webgpu"].includes(backend)) throw new Error("explicit actual browser provider");
  const maskRuntime = backend === "wasm" ? await createMaskRuntime(artifacts.wasm, artifacts.config, artifacts.weights) : null;
  const session = await ort.InferenceSession.create(modelBytes, { executionProviders: [backend], graphOptimizationLevel: "disabled" });
  if (JSON.stringify(session.inputNames) !== JSON.stringify(["candidate", "resizeRatios", ...coordinateInputNames]) || JSON.stringify(session.outputNames) !== JSON.stringify(["mask_logits", "presence_logit"])) throw new Error("original complete ONNX IO");
  let running = false;
  return {
    async run(candidate, h, w, ratios, beforeOrt, beforeMask) {
      if (running) throw new Error("concurrent two-head route rejected");
      if (!(candidate instanceof Float32Array) || candidate.length !== h * w * 4 || !candidate.every(Number.isFinite) || !(ratios instanceof Float32Array) || ratios.length !== 4 || !ratios.every(Number.isFinite)) throw new Error("original finite inputs");
      running = true;
      try {
        await beforeOrt();
        const output = await session.run({ candidate: new ort.Tensor("float32", candidate, [1, 4, h, w]), resizeRatios: new ort.Tensor("float32", ratios, [4]), ...nativeCoordinateFeeds(ort, h, w, ratios) });
        finiteHead(output.mask_logits, [1, 1, h, w]); finiteHead(output.presence_logit, [1, 1]);
        const originalMask = new Float32Array(await output.mask_logits.getData()).slice();
        const presence = new Float32Array(await output.presence_logit.getData()).slice();
        if (!originalMask.every(Number.isFinite) || !presence.every(Number.isFinite)) throw new Error("both actual original heads finite");
        let mask = originalMask, memory = null;
        if (maskRuntime) {
          await beforeMask();
          const result = await maskRuntime.run(candidate, h, w, ratios);
          mask = result.mask;
          memory = { wasmMemoryBytes: result.wasmMemoryBytes, workspaceHighWaterBytes: result.workspaceHighWaterBytes };
        }
        return { mask, presence, unusedOriginalWasmMask: maskRuntime ? originalMask : null,
          actualPresenceExecuted: true, maskRoute: maskRuntime ? "f64_wasm_native_coordinates" : "f32_webgpu_native_coordinates", memory };
      } finally { running = false; }
    },
    release: () => session.release(),
  };
}
