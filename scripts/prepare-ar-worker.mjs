import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const { loadEnvConfig } = createRequire(require.resolve("next/package.json"))("@next/env");
loadEnvConfig(process.cwd());
if (process.argv.includes("--if-enabled") && process.env.NEXT_PUBLIC_AR_WORKER_CANDIDATE !== "1") {
  process.exit(0);
}

const assetDirectory = "public/vendor/mediapipe/hand-landmarker";
const modelPath = join(assetDirectory, "hand_landmarker-v1.task");
const modelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
const modelSha256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1";
const modelMatches = bytes => createHash("sha256").update(bytes).digest("hex") === modelSha256;
const cachedModel = await readFile(modelPath).catch(error => {
  if (error.code !== "ENOENT") throw error;
});

if (!cachedModel || !modelMatches(cachedModel)) {
  let bytes;
  if (process.env.AR_WORKER_MODEL_FILE) {
    bytes = await readFile(process.env.AR_WORKER_MODEL_FILE);
  } else {
    const response = await fetch(modelUrl, { signal: AbortSignal.timeout(30_000) });
    if (!response.ok) throw new Error(`Hand Landmarker 下载失败（HTTP ${response.status}）`);
    bytes = Buffer.from(await response.arrayBuffer());
  }
  if (!modelMatches(bytes)) throw new Error("Hand Landmarker 模型 SHA-256 不匹配");
  await mkdir(assetDirectory, { recursive: true });
  const temporaryPath = `${modelPath}.${process.pid}.tmp`;
  await writeFile(temporaryPath, bytes);
  await rename(temporaryPath, modelPath);
}

const sdkDirectory = dirname(require.resolve("@mediapipe/tasks-vision"));
await mkdir(join(assetDirectory, "wasm"), { recursive: true });
await copyFile(join(sdkDirectory, "vision_bundle.mjs"), join(assetDirectory, "vision_bundle.mjs"));
// MediaPipe 按浏览器支持选择 SIMD 或非 SIMD 运行文件。
for (const variant of ["internal", "nosimd_internal", "module_internal"]) {
  for (const extension of ["js", "wasm"]) {
    const file = join("wasm", `vision_wasm_${variant}.${extension}`);
    await copyFile(join(sdkDirectory, file), join(assetDirectory, file));
  }
}
