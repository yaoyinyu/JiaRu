import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { pngBuffer, pngDataUrl, TINY_PNG_DATA_URL } from "./helpers";

/**
 * 2026-09-05 评审 #11：6 条浏览器关键行为回归（Playwright）。
 * ①编辑器上传→25 笔→重置 ②原尺寸导出 ③AI 参考比例 ④AI→收录→AR
 * ⑤登录过期续期 ⑥切换多份共享纹理。
 * 其中①②依赖 #8 修复、③依赖 #9-A 修复、⑥依赖 #9-B 修复后的行为。
 */

const TMP_DIR = path.join(process.cwd(), ".playwright-tmp");
// 与 playwright.config.ts webServer.env.JWT_SECRET 保持一致
const SEED_JWT_SECRET = "e2e-playwright-jwt-secret-0123456789";

/** 读取页面首个 canvas 的当前内容（dataURL）。 */
async function canvasDataUrl(page: import("@playwright/test").Page): Promise<string> {
  return page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    if (!canvas) throw new Error("页面没有 canvas");
    return canvas.toDataURL("image/png");
  });
}

/** 在画布上完成一笔（按下→短拖→抬起）。 */
async function drawStroke(
  page: import("@playwright/test").Page,
  x: number,
  y: number
): Promise<void> {
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 10, y + 6, { steps: 2 });
  await page.mouse.up();
}

test("评审#11-①：编辑器上传→25 笔→重置回原图基线", async ({ page, context }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto("/editor");
  const photo = await pngBuffer(context, 800, 1200, "#c96a8f");
  await page.setInputFiles('input[type="file"]', {
    name: "photo.png",
    mimeType: "image/png",
    buffer: photo,
  });

  const canvas = page.locator("canvas");
  await expect
    .poll(() => canvas.evaluate((el) => (el as HTMLCanvasElement).width), { timeout: 30_000 })
    .toBe(400); // 800×1200 → 预览最长边 400/600 → 400×600

  const baseline = await canvasDataUrl(page);

  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  for (let i = 0; i < 25; i++) {
    await drawStroke(
      page,
      (box?.x ?? 0) + 30 + (i % 5) * 20,
      (box?.y ?? 0) + 40 + Math.floor(i / 5) * 12
    );
  }
  // 25 笔后撤销/重置均可用（评审复现：旧实现 20 份快照淘汰后撤销栈失真）
  await expect(page.getByRole("button", { name: "撤销" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "重置" })).toBeEnabled();
  await expect
    .poll(() => canvasDataUrl(page))
    .not.toBe(baseline);

  await page.getByRole("button", { name: "重置" }).click();
  // 评审复现断言：重置必须回到原图基线（旧实现回到第 6 笔的快照状态）
  await expect.poll(() => canvasDataUrl(page), { timeout: 15_000 }).toBe(baseline);
  expect(pageErrors).toEqual([]);
});

test("评审#11-②：编辑器 4096 方图原尺寸导出", async ({ page, context }) => {
  await page.goto("/editor");
  const photo = await pngBuffer(context, 4096, 4096, "#4a7fb5");
  await page.setInputFiles('input[type="file"]', {
    name: "big.png",
    mimeType: "image/png",
    buffer: photo,
  });

  const canvas = page.locator("canvas");
  await expect
    .poll(() => canvas.evaluate((el) => (el as HTMLCanvasElement).width), { timeout: 30_000 })
    .toBe(400); // 预览仍为 400×400
  await canvasDataUrl(page);

  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await drawStroke(page, (box?.x ?? 0) + 100, (box?.y ?? 0) + 100);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "保存" }).click();
  const download = await downloadPromise;
  const filePath = await download.path();
  expect(filePath).toBeTruthy();

  // PNG 头：8 字节签名 + IHDR 宽高（大端，偏移 16/20）
  const bytes = readFileSync(filePath as string);
  expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  // 评审复现断言：旧实现导出 400×400，修复后必须原尺寸
  expect(bytes.readUInt32BE(16)).toBe(4096);
  expect(bytes.readUInt32BE(20)).toBe(4096);
  expect(download.suggestedFilename()).toMatch(/^jiaru-\d+\.png$/);
});

test("评审#11-③：AI 参考图 3:4 就近映射进生成请求", async ({ page, context }) => {
  await page.goto("/ai-generate");
  const reference = await pngBuffer(context, 900, 1200, "#b05a7e"); // 恰为 3:4
  await page.setInputFiles('input[type="file"]', {
    name: "ref.png",
    mimeType: "image/png",
    buffer: reference,
  });
  await expect(page.getByText("已添加参考图")).toBeVisible({ timeout: 30_000 });

  let capturedRatio: unknown = null;
  await page.route("**/api/generate-ai", async (route) => {
    const body = route.request().postDataJSON() as { ratio?: unknown } | null;
    capturedRatio = body?.ratio ?? null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ imageUrl: TINY_PNG_DATA_URL }),
    });
  });

  await page.getByRole("textbox").fill("银色亮片渐变美甲");
  await page.getByRole("button", { name: /生成我的美甲设计/ }).click();
  await page.waitForResponse("**/api/generate-ai");
  // 评审复现断言：旧实现把 3:4 错映射为 2:3
  expect(capturedRatio).toBe("3:4");
});

test("评审#11-④：AI 生成→收录到图库→AR 试戴带入多指选取器", async ({ page, context }) => {
  await page.goto("/ai-generate");
  // mock 图必须 ≥320px：收录后在 AR 侧要过 validateImageUpload 的分辨率门
  const mockImage = await pngDataUrl(context, 640, 640, "#9a6fb8");
  await page.route("**/api/generate-ai", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ imageUrl: mockImage }),
    })
  );
  await page.getByRole("textbox").fill("测试收录链路的美甲设计");
  await page.getByRole("button", { name: /生成我的美甲设计/ }).click();

  const collectButton = page.getByRole("button", { name: /收录到图库/ });
  await expect(collectButton).toBeVisible({ timeout: 30_000 });
  await collectButton.click();
  await expect(page.getByText("已收录到图库")).toBeVisible({ timeout: 15_000 });

  // 图库「我的收录」区块出现（IndexedDB 桥），且带 AR 试戴入口
  await page.goto("/gallery");
  const collectArLink = page.locator('a[href*="/ar-tryon?collect="]').first();
  await expect(collectArLink).toBeVisible({ timeout: 20_000 });

  // 收录卡片的 AR 试戴链接 → 多指纹理选取器自动打开
  await collectArLink.click();
  await expect(page.getByText("美甲纹理提取")).toBeVisible({ timeout: 60_000 });
});

test("评审#11-⑤：access 过期后 /api/me 静默续期并下发新 Cookie", async ({ context }) => {
  mkdirSync(TMP_DIR, { recursive: true });
  const dbPath = path.join(TMP_DIR, "e2e-user.db");
  const outPath = path.join(TMP_DIR, "auth-session.json");
  execFileSync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      path.join(process.cwd(), "e2e", "seed-auth.ts"),
      dbPath,
      SEED_JWT_SECRET,
      outPath,
    ],
    { stdio: "inherit" }
  );
  const session = JSON.parse(readFileSync(outPath, "utf8")) as {
    refreshToken: string;
    expiredAccess: string;
  };

  await context.addCookies([
    { name: "jiaru_access", value: session.expiredAccess, url: "http://127.0.0.1:3399" },
    { name: "jiaru_refresh", value: session.refreshToken, url: "http://127.0.0.1:3399" },
  ]);

  const resp = await context.request.get("/api/me");
  expect(resp.status()).toBe(200);

  // 续期必须通过 Set-Cookie 下发新的 access（评审 #6：登录过期续期闭环）
  const renewedCookies = resp
    .headersArray()
    .filter(
      (header) =>
        header.name.toLowerCase() === "set-cookie" &&
        header.value.startsWith("jiaru_access=")
    );
  expect(renewedCookies.length).toBeGreaterThan(0);
  const renewedAccess = renewedCookies[0].value
    .split("jiaru_access=")[1]
    .split(";")[0];
  expect(renewedAccess).not.toBe(session.expiredAccess);
  expect(renewedAccess.split(".")).toHaveLength(3);
});

test("评审#11-⑥：切换多份共享纹理（上传×2→应用到全部→逐指切换）", async ({ page, context }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto("/ar-tryon");
  await page.getByRole("button", { name: "纹理" }).click();

  const textureA = await pngBuffer(context, 512, 512, "#d96fa3");
  const textureB = await pngBuffer(context, 512, 512, "#6fa8d9");

  async function uploadAndConfirmTexture(file: Buffer): Promise<void> {
    await page.setInputFiles('label:has-text("上传美甲照片") input[type="file"]', {
      name: "tex.png",
      mimeType: "image/png",
      buffer: file,
    });
    const cropperCanvas = page.locator("div.fixed.inset-0.z-50 canvas");
    await expect(cropperCanvas).toBeVisible({ timeout: 30_000 });
    const box = await cropperCanvas.boundingBox();
    expect(box).not.toBeNull();
    const cx = (box?.x ?? 0) + (box?.width ?? 0) / 2;
    const cy = (box?.y ?? 0) + (box?.height ?? 0) / 2;
    await page.mouse.move(cx - 60, cy - 60);
    await page.mouse.down();
    await page.mouse.move(cx + 60, cy + 60, { steps: 4 });
    await page.mouse.up();
    await page.getByRole("button", { name: "确认使用" }).click();
  }

  // 拇指 ← 纹理 A
  await uploadAndConfirmTexture(textureA);
  await expect(page.getByText("拇指纹理")).toBeVisible({ timeout: 20_000 });
  // 食指 ← 纹理 B
  await page.getByRole("button", { name: "食指", exact: true }).click();
  await uploadAndConfirmTexture(textureB);
  await expect(page.getByText("食指纹理")).toBeVisible({ timeout: 20_000 });

  // 拇指的 A 应用到全部：A 被五指共享、B 无引用被释放（#9-B 集合 diff）
  await page.getByRole("button", { name: "应用到全部" }).click();
  await expect(page.locator("button span.bg-green-400")).toHaveCount(5);

  // 逐指切换，缩略图持续可渲染（若共享 bitmap 被误关会在此抛错）
  for (const finger of ["食指", "中指", "无名指", "小指", "拇指"]) {
    await page.getByRole("button", { name: finger, exact: true }).click();
    await expect(page.getByText(`${finger}纹理`)).toBeVisible();
  }
  expect(pageErrors).toEqual([]);
});
