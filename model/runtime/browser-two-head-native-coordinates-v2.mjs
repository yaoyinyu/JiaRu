import { createTwoHeadRoute } from "./nail-two-head-native-coordinates-v2.mjs";
import { nativeCoordinateArrays } from "./nail-native-coordinates-v2.mjs";
import { captureCoordinates } from "./verify-mask-wasm-coordinates.mjs";

const status = document.querySelector("#status"), button = document.querySelector("#run");
const hex = async (bytes) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (x) => x.toString(16).padStart(2, "0")).join("");
const encode = (value) => new TextEncoder().encode(JSON.stringify(value));
const config = await (await fetch("/config")).json();
const pageId = crypto.randomUUID();
async function read(ref) {
  const response = await fetch("/resource?path=" + encodeURIComponent(ref.path));
  if (!response.ok) throw new Error(await response.text());
  const bytes = await response.arrayBuffer();
  if (await hex(bytes) !== ref.sha256) throw new Error("frozen resource SHA");
  return bytes;
}
async function post(route, value, requestId = pageId) {
  const bytes = value instanceof ArrayBuffer || ArrayBuffer.isView(value) ? value : encode(value);
  const digest = await hex(bytes), headers = { "X-Content-Sha256": digest, "X-Page-Id": pageId, "X-Request-Id": requestId };
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(route, { method: "POST", headers, body: bytes });
      const body = await response.text();
      if (!response.ok) throw new Error(body);
      const ack = JSON.parse(body);
      if (ack.sha256 !== digest) throw new Error("persisted ACK SHA mismatch");
      return;
    } catch (error) { if (attempt === 2) throw error; }
  }
}
const failure = async (error) => {
  status.textContent = "FAIL: " + error.stack;
  await post("/failure", { error: error.stack, restartAllowed: false });
};
let artifacts;
try {
  if (!navigator.gpu || !crossOriginIsolated) throw new Error("actual WebGPU and isolated loopback required");
  const adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
  if (!adapter) throw new Error("real GPU adapter required");
  const info = adapter.info;
  const adapterInfo = { vendor: info.vendor, architecture: info.architecture, device: info.device, description: info.description };
  if (adapterInfo.vendor !== "nvidia" || adapterInfo.architecture !== "lovelace" || !navigator.userAgent.includes("Chrome/155.")) throw new Error("frozen actual browser/GPU policy");
  await post("/claim", { pageId, userAgent: navigator.userAgent, adapterInfo, crossOriginIsolated,
    ortVersion: ort.env.versions.web, executionSha256: config.executionSha256 });
  const wasm = await read(config.preflight.wasm);
  const references = new Map(config.preflight.cases.flatMap((c) => c.coordinateAxes.flatMap((a) => Object.values(a.fields))).map((r) => [r.path, r]));
  const coordinate = await captureCoordinates(wasm, config.preflight.cases,
    (p) => read(references.get(p)), (name, raw) => post("/coordinate/" + name, raw));
  let hostCoordinateFieldsVerified = 0;
  for (const row of config.preflight.cases) {
    const ratios = new Float32Array(await read(row.resizeRatios));
    const host = Object.values(nativeCoordinateArrays(row.h, row.w, ratios));
    let index = 0;
    for (const axis of row.coordinateAxes) for (const field of ["lower", "upper", "weight0", "weight1"]) {
      const actual = host[index++];
      const values = actual.integer ? BigInt64Array.from(actual.values, BigInt) : actual.values;
      const raw = new Uint8Array(values.buffer, values.byteOffset, values.byteLength);
      if (await hex(raw) !== axis.fields[field].sha256) throw new Error("whole native host coordinate mismatch");
      hostCoordinateFieldsVerified++;
    }
  }
  if (hostCoordinateFieldsVerified !== config.preflight.cases.length * 16) throw new Error("full native host coordinate denominator");
  coordinate.hostCoordinateFieldsVerified = hostCoordinateFieldsVerified;
  await post("/coordinates-complete", coordinate);
  artifacts = { wasm, config: JSON.parse(new TextDecoder().decode(await read(config.preflight.parameterConfig))),
    weights: new Float32Array(await read(config.preflight.parameterPack)) };
  status.textContent = `${config.preflight.cases.length * 16}份原F32/整数坐标字节通过；等待CPU门。`;
  const timer = setInterval(async () => {
    const r = await (await fetch("/ready")).json();
    if (r.ready) { clearInterval(timer); button.disabled = false; status.textContent = `已就绪：执行全${config.preflight.cases.length}×WASM/WebGPU实际双头。`; }
  }, 500);
} catch (error) { await failure(error); }

button.onclick = async () => {
  button.disabled = true;
  const records = [];
  try {
    ort.env.wasm.wasmPaths = "/ort/"; ort.env.wasm.numThreads = 1; ort.env.wasm.proxy = false; ort.env.logLevel = "error";
    const model = await read(config.preflight.model);
    for (const backend of ["wasm", "webgpu"]) {
      const route = await createTwoHeadRoute(ort, model, artifacts, backend);
      try {
        for (const row of config.preflight.cases) {
          const input = new Float32Array(await read(row.input)), ratios = new Float32Array(await read(row.resizeRatios));
          const requestId = crypto.randomUUID(), base = { backend, ordinal: row.ordinal, pageId, requestId,
            candidateIdentity: row.candidateIdentity, inputSha256: row.input.sha256, resizeRatiosSha256: row.resizeRatios.sha256 };
          const started = performance.now();
          const result = await route.run(input, row.h, row.w, ratios,
            () => post(`/start/${backend}/${row.ordinal}`, base, requestId),
            () => post(`/mask-start/${row.ordinal}`, base, requestId));
          const arrays = { mask: result.mask, presence: result.presence };
          if (result.unusedOriginalWasmMask) arrays.unused = result.unusedOriginalWasmMask;
          for (const [head, value] of Object.entries(arrays)) await post(`/capture/${backend}/${row.ordinal}/${head}`, value, requestId);
          await post(`/done/${backend}/${row.ordinal}`, { ...base, actualPresenceExecuted: result.actualPresenceExecuted,
            maskRoute: result.maskRoute, memory: result.memory, elapsedMsWithCapture: performance.now() - started }, requestId);
          records.push({ backend, ordinal: row.ordinal });
          status.textContent = `${backend} ${row.ordinal}/${config.preflight.cases.length} 已捕获实际两头；PRODUCT HOLD。`;
        }
      } finally { await route.release(); }
    }
    await post("/terminal", { pageId, records, actualPresenceExecuted: true });
    status.textContent = "控制捕获完成；以独立重放报告判断门，不自动解除HOLD。";
  } catch (error) { await failure(error); }
};
