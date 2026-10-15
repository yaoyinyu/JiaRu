import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { createHash } from "node:crypto";
import { captureCoordinates } from "../runtime/verify-mask-wasm-coordinates.mjs";

const [source, target] = process.argv.slice(2);
const read = async (p) => { const b = await fs.readFile(p); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const binding = async (p) => ({ path: path.resolve(p), sha256: createHash("sha256").update(await fs.readFile(p)).digest("hex") });
const report = JSON.parse(await fs.readFile(source, "utf8")), root = path.resolve(target);
if (!root.startsWith(path.resolve("model/reviews") + path.sep) || report.cases.length !== 74) throw new Error("full immutable review scope");
await fs.mkdir(root);
async function raw(name, value) {
  const f = await fs.open(path.join(root, name), "wx");
  try { await f.writeFile(new Uint8Array(value)); await f.sync(); } finally { await f.close(); }
}
const json = (name, value) => raw(name, new TextEncoder().encode(JSON.stringify(value, null, 2) + "\n"));
await json("execution.json", { preflight: await binding(source), sources: await Promise.all([
  "model/training/capture-route-coordinate-preflight.mjs", "model/runtime/verify-mask-wasm-coordinates.mjs", process.execPath].map(binding)),
  coordinateCallsAllowed: 296, projectModelInputsAllowed: 0, restartAllowed: false });
try {
  const wasm = await read(report.wasm.path);
  if (createHash("sha256").update(new Uint8Array(wasm)).digest("hex") !== report.wasm.sha256) throw new Error("module SHA");
  const result = await captureCoordinates(wasm, report.cases, read, raw);
  await json("report.json", { ...result, preflight: await binding(source), coordinateArrays: 1184 });
  process.stdout.write(JSON.stringify({ ok: true, calls: result.records.length, arrays: 1184 }) + "\n");
} catch (error) { await json("failure.json", { error: error.stack, projectModelInputs: 0 }); throw error; }
