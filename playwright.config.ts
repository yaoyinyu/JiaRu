import { defineConfig } from "@playwright/test";
import path from "node:path";

/**
 * Playwright 浏览器回归配置（2026-09-05 评审 #11）。
 * - 用例目录 e2e/（*.spec.ts），与 tests/ 的 Node test runner 互不干扰；
 * - webServer 用 next dev（http，127.0.0.1 亦属浏览器安全上下文，getUserMedia 可用）；
 * - JIARU_DB_PATH 指向 .playwright-tmp/ 临时库，绝不读写真实 data/ 用户库；
 * - JWT_SECRET 显式注入，与 e2e/seed-auth.ts 的种子签名密钥保持一致；
 * - Chromium 启动参数注入 fake camera，供 /ar-tryon 的 getUserMedia 使用。
 */

const PORT = 3399;
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
    },
    contextOptions: { permissions: ["camera"] },
    actionTimeout: 15_000,
  },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --port 3399",
    url: `${baseURL}/privacy`,
    reuseExistingServer: false,
    timeout: 300_000,
    stdout: "ignore",
    stderr: "pipe",
    env: {
      ...process.env,
      JIARU_DB_PATH: path.join(__dirname, ".playwright-tmp", "e2e-user.db"),
      JWT_SECRET: "e2e-playwright-jwt-secret-0123456789",
    },
  },
});
