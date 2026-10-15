import { createMaskRuntime } from "./nail-mask-f64-v2.mjs";
import { schedule as previousSchedule } from "./nail-mask-f64.mjs";

const sha = async (bytes) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (x) => x.toString(16).padStart(2, "0")).join("");
const jsonBytes = (raw) => JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw));
function require(value, message) { if (!value) throw new Error(message); }
function difference(a, b) {
  require(a.length === b.length, "complete array denominator");
  let maxAbs = 0, signDifferences = 0;
  for (let i = 0; i < a.length; i++) {
    require(Number.isFinite(a[i]) && Number.isFinite(b[i]), "all finite elements");
    maxAbs = Math.max(maxAbs, Math.abs(a[i] - b[i]));
    signDifferences += Number((a[i] >= 0) !== (b[i] >= 0));
  }
  return { maxAbs, nativeLogitSignPixelDifferences: signDifferences };
}

export async function auditSynthetic(referenceBinding, io, backend) {
  require(["node", "browser"].includes(backend), "explicit synthetic runtime backend");
  async function readBound(ref) {
    const raw = await io.read(ref.path);
    require(await sha(raw) === ref.sha256, "frozen resource SHA: " + ref.path);
    return raw;
  }
  const report = jsonBytes(await readBound(referenceBinding));
  const plan = jsonBytes(await readBound(report.plan));
  require(plan.purpose === "independent_synthetic_full_mask_wasm_not_two_head_release", "independent complete mask control only");
  require(report.ok && plan.projectModelInputsAllowed === 0 && plan.learnedInputsAllowed === 0 && !plan.presenceExecutionClaimed && plan.productHold, "zero learned/project budget and HOLD");
  require(plan.requiredMaxAbs === undefined && plan.finalMaskMaxAbsError === 1e-4 && plan.smallStageMaxAbsError === 1e-9 && plan.maxErfAbsError === 1e-13 && plan.decodedPixelDifferencesAllowed === 0, "fixed original final and tighter operator gates");
  require(plan.fixedWasmMemoryBytes === 268435456 && plan.nodeSyntheticMaskInputsAllowed === 4 && plan.browserSyntheticMaskInputsAllowed === 4 && plan.erfScalarGridPointsPerBackend === 20001, "complete independent synthetic budget");
  require(JSON.stringify(plan.cases.map((c) => [c.h, c.w])) === JSON.stringify([[7, 9], [31, 35], [96, 100], [628, 628]]), "full even/odd/maximum control scope");
  require(JSON.stringify(plan.cases) === JSON.stringify(report.records.map(({ id, h, w, allStageRaw }) => ({ id, h, w, allStageRaw }))), "all records and ordered cases");
  for (const ref of Object.values(plan.sources)) await readBound(ref);
  const config = jsonBytes(await readBound(plan.config)), weights = new Float32Array(await readBound(plan.weights));
  const wasm = await readBound(plan.wasm), module = new WebAssembly.Module(wasm);
  const imports = WebAssembly.Module.imports(module).map((row) => `${row.module}.${row.name}:${row.kind}`).sort();
  require(JSON.stringify(imports) === JSON.stringify(["env.exp:function", "env.memory:memory"]), "only explicit F64 host exp and bounded linear memory imports");
  const runtime = await createMaskRuntime(wasm, config, weights, plan.fixedWasmMemoryBytes);
  require(plan.all74Shapes.length === 74 && plan.all74Shapes.every((row, i) => row.ordinal === i + 1 && row.candidateIdentity.identity.split === "train"), "all74 train shapes, no project input execution");
  const memoryRows = plan.all74Shapes.map((row) => {
    const [batch, channels, h, w] = row.shape;
    require(batch === 1 && channels === 4, "original four-channel native interface");
    return { ordinal: row.ordinal, h, w, currentBytes: runtime.plan(h, w).highWaterBytes,
      previousBytes: previousSchedule(h, w, runtime.heapStart).highWaterBytes };
  });
  require(memoryRows.every((row) => row.currentBytes <= plan.fixedWasmMemoryBytes), "complete scope statically fits bounded memory");
  await io.json("memory-plan.json", { ok: true, newProjectModelInputs: 0, records: memoryRows,
    oldUnreachableOrdinals: memoryRows.filter((row) => row.previousBytes > plan.fixedWasmMemoryBytes).map((row) => row.ordinal),
    currentUnreachableOrdinals: [], wasmMemoryBytes: runtime.memory.buffer.byteLength,
    wholeBrowserProcessPeakMemoryClaimed: false });
  await io.json("erf-start.json", { points: plan.erfScalarGridPointsPerBackend, backend });
  const erfInput = new Float64Array(await readBound(report.erfInput));
  const erfReference = new Float64Array(await readBound(report.erfReference));
  require(erfInput.length === plan.erfScalarGridPointsPerBackend, "full scalar grid");
  const erfActual = Float64Array.from(erfInput, (x) => runtime.erf64(x));
  const erfComparison = difference(erfActual, erfReference);
  await io.raw("erf-actual.f64", erfActual);
  await io.json("erf-done.json", { ...erfComparison, actualSha256: await sha(erfActual.buffer) });
  require(erfComparison.maxAbs <= plan.maxErfAbsError, "full erf numerical gate");
  const records = [];
  let concurrencyRejected = false;
  for (const record of report.records) {
    require(record.stages.length === 36, "all36 executable kernel stages");
    const candidate = new Float32Array(await readBound(record.candidate));
    const ratios = new Float32Array(record.ratios), observed = [];
    await io.json(`${record.ordinal}-start.json`, { id: record.id, candidate: record.candidate, backend });
    const result = await runtime.run(candidate, record.h, record.w, ratios, async (stage) => {
      const expected = record.stages[stage.ordinal];
      require(stage.op === expected.op && (stage.name ?? null) === expected.name && (stage.suffix ?? null) === expected.suffix && JSON.stringify(stage.shape) === JSON.stringify(expected.shape), "exact stage identity/order/shape");
      require(stage.values.every(Number.isFinite), "all whole intermediate values finite");
      const raw = stage.values.buffer.slice(stage.values.byteOffset, stage.values.byteOffset + stage.values.byteLength);
      const saved = { ordinal: stage.ordinal, op: stage.op, name: stage.name ?? null, suffix: stage.suffix ?? null,
        shape: stage.shape, sha256: await sha(raw), bytes: raw.byteLength };
      if (expected.raw) {
        const referenceBytes = await readBound(expected.raw);
        const reference = expected.dtype === "float32" ? new Float32Array(referenceBytes) : new Float64Array(referenceBytes);
        saved.comparison = difference(stage.values, reference);
        await io.raw(`${record.ordinal}-stage${stage.ordinal}.bin`, raw);
        require(saved.comparison.maxAbs <= (expected.dtype === "float32" ? plan.finalMaskMaxAbsError : plan.smallStageMaxAbsError), "whole stored stage numerical gate");
        if (expected.dtype === "float32") require(saved.comparison.nativeLogitSignPixelDifferences === 0, "synthetic native final sign pixels");
      }
      observed.push(saved);
      if (record.ordinal === 1 && stage.ordinal === 0) {
        try { await runtime.run(candidate, record.h, record.w, ratios); }
        catch (error) { concurrencyRejected = error.message === "concurrent runtime call rejected"; }
        require(concurrencyRejected, "concurrent forward refused before kernel");
      }
    });
    require(observed.length === 36 && result.presenceExecuted === false, "full mask only, no inherited presence claim");
    require(await sha(result.mask.buffer) === observed.at(-1).sha256, "returned final bytes equal actual captured final stage");
    require(result.mask.some((value, i) => value !== Math.fround(Math.fround(candidate[3 * record.h * record.w + i] * 8) - 4)), "actual nonzero mask correction");
    const row = { id: record.id, ordinal: record.ordinal, h: record.h, w: record.w, stages: observed,
      elapsedMs: result.elapsedMs, wasmMemoryBytes: result.wasmMemoryBytes,
      workspaceHighWaterBytes: result.workspaceHighWaterBytes, peakLiveWorkspaceBytes: result.peakLiveWorkspaceBytes,
      materializedConcatBytes: result.materializedConcatBytes, presenceExecuted: false };
    records.push(row); await io.json(`${record.ordinal}-done.json`, row);
    await io.progress({ phase: "synthetic_mask", backend, ordinal: record.ordinal, elapsedMs: result.elapsedMs });
  }
  let invalidRatiosRejected = false, nonfiniteRejected = false, insufficientMemoryRejected = false;
  const first = report.records[0], input = new Float32Array(await readBound(first.candidate));
  try { await runtime.run(input, first.h, first.w, new Float32Array(4)); }
  catch (error) { invalidRatiosRejected = error.message === "original F32 native resize ratios"; }
  const bad = input.slice(); bad[0] = NaN;
  try { await runtime.run(bad, first.h, first.w, new Float32Array(first.ratios)); }
  catch (error) { nonfiniteRejected = error.message === "complete finite F32 candidate"; }
  try { await createMaskRuntime(wasm, config, weights, 131072); }
  catch (error) { insufficientMemoryRejected = error.message === "parameter memory overflow"; }
  require(invalidRatiosRejected && nonfiniteRejected && insufficientMemoryRejected && concurrencyRejected, "all invalid calls fail before model kernels");
  const result = { ok: true, backend, reference: referenceBinding, plan: report.plan, records,
    erfComparison, concurrencyRejected, invalidRatiosRejected, nonfiniteRejected, insufficientMemoryRejected,
    projectModelInputs: 0, learnedInputs: 0, presenceExecuted: false, fullTwoHeadGatePassed: false,
    wholeBrowserProcessPeakMemoryClaimed: false, formalReleaseAllowed: false, productHold: true };
  await io.json("report.json", result);
  return result;
}
