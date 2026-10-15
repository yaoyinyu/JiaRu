import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { createHash } from "node:crypto";
import { auditSynthetic } from "../runtime/audit-mask-f64-synthetic.mjs";

const [referencePath, output] = process.argv.slice(2);
if (!referencePath || !output) throw new Error("reference report and exclusive output required");
const root = process.cwd(), out = path.resolve(output);
if (!out.startsWith(path.join(root, "model", "reviews") + path.sep)) throw new Error("isolated review root");
const binding = async (p) => ({ path: path.resolve(p), sha256: createHash("sha256").update(await fs.readFile(p)).digest("hex") });
await fs.mkdir(out);
async function write(name, raw) {
  if (path.basename(name) !== name) throw new Error("flat unique output");
  const handle = await fs.open(path.join(out, name), "wx");
  try { await handle.writeFile(raw); await handle.sync(); } finally { await handle.close(); }
}
const reference = await binding(referencePath);
await write("execution.json", JSON.stringify({ reference, backend: "node", sources: await Promise.all([
  "model/runtime/audit-mask-f64-synthetic.mjs", "model/runtime/nail-mask-f64-v2.mjs",
  "model/training/audit-reviewed-mask-wasm-node.mjs", process.execPath].map(binding)),
  node: process.version, nodeSyntheticMaskInputsAllowed: 4, learnedInputsAllowed: 0, restartAllowed: false }, null, 2));
try {
  await auditSynthetic(reference, {
    read: async (p) => { const b = await fs.readFile(p); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); },
    json: async (name, value) => write(name, JSON.stringify(value, null, 2) + "\n"),
    raw: async (name, value) => write(name, new Uint8Array(value.buffer ?? value, value.byteOffset ?? 0, value.byteLength)),
    progress: async (value) => process.stdout.write(JSON.stringify(value) + "\n"),
  }, "node");
  process.stdout.write(JSON.stringify({ ok: true, report: await binding(path.join(out, "report.json")) }) + "\n");
} catch (error) {
  await write("failure.json", JSON.stringify({ ok: false, error: error.stack, restartAllowed: false }));
  throw error;
}
