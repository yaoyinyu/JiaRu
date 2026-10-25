import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { pngBuffer } from "./helpers";

/**
 * /account 个人资料编辑回归（Playwright）：
 * ①加载骨架 ②加载失败重试 ③字段校验、保存成功、取消与刷新后持久化 ④保存失败反馈 ⑤移动端无横向溢出。
 * 登录态经 e2e/seed-auth.ts 写入与 webServer 相同的临时库（.playwright-tmp/），不触碰真实 data/ 用户库。
 */

const TMP_DIR = path.join(process.cwd(), ".playwright-tmp");
// 与 playwright.config.ts webServer.env.JWT_SECRET 保持一致
const SEED_JWT_SECRET = "e2e-playwright-jwt-secret-0123456789";

async function signIn(context: BrowserContext): Promise<void> {
  mkdirSync(TMP_DIR, { recursive: true });
  const dbPath = path.join(TMP_DIR, "e2e-user.db");
  const outPath = path.join(TMP_DIR, "profile-session.json");
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
    { stdio: "ignore" }
  );
  const session = JSON.parse(readFileSync(outPath, "utf8")) as {
    refreshToken: string;
    expiredAccess: string;
  };
  // access 已过期：页面首个 /api/me 会经 refresh 静默续期，同时覆盖续期路径
  await context.addCookies([
    { name: "jiaru_access", value: session.expiredAccess, url: "http://127.0.0.1:3399" },
    { name: "jiaru_refresh", value: session.refreshToken, url: "http://127.0.0.1:3399" },
  ]);
}

async function openAccount(page: Page): Promise<void> {
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "个人资料" })).toBeVisible({ timeout: 30_000 });
}

async function enterEdit(page: Page): Promise<void> {
  const editButton = page.getByRole("button", { name: "编辑资料", exact: true });
  if (await editButton.isVisible().catch(() => false)) await editButton.click();
  await expect(page.getByLabel(/昵称/)).toBeVisible();
}

/** 资料卡片内反馈：页面根节点还有 Next 的 route announcer（同 role=alert），必须限定范围 */
function profileFeedback(page: Page) {
  return page.getByRole("region", { name: "个人资料" }).getByRole("alert");
}

test("个人资料：骨架 → 校验拦截 → 保存成功 → 取消确认 → 刷新持久化", async ({ page, context }) => {
  await signIn(context);
  // 临时库会保留上一轮的档案：本轮取值必须唯一，否则「无改动」会让保存按钮保持禁用
  const suffix = Date.now().toString().slice(-6);
  const nicknameValue = `E2E测试用户${suffix}`;
  const bioValue = `偏爱奶咖色系与短圆甲型（${suffix}），日常通勤为主。`;
  const contactValue = `e2e${suffix}@jiaru.app`;

  // ① 加载骨架：人为延迟 /api/me（dev 下 effect 会双跑，需对每次 GET 都生效），
  //    确认加载态可见后再放行真实请求
  let slow = true;
  await page.route("**/api/me", async (route) => {
    if (slow && route.request().method() === "GET") {
      await new Promise((resolve) => setTimeout(resolve, 2500));
    }
    await route.continue();
  });
  await page.goto("/account");
  await expect(page.getByText("正在读取账号信息…")).toBeVisible();
  slow = false;
  await expect(page.getByRole("heading", { name: "个人资料" })).toBeVisible({ timeout: 30_000 });
  await page.unroute("**/api/me");

  // ② 空状态与编辑入口
  await expect(page.getByRole("button", { name: "编辑资料", exact: true })).toBeVisible();
  await enterEdit(page);

  // ③ 昵称必填：清空后保存被拦截，停留编辑态
  const nickname = page.getByLabel(/昵称/);
  await nickname.fill("");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(profileFeedback(page)).toContainText("请填写昵称");
  await expect(page.getByLabel(/昵称/)).toBeVisible();

  // ④ 联系方式按所选类型校验
  await nickname.fill(nicknameValue);
  await page.getByLabel("联系方式类型").selectOption("email");
  await page.getByLabel("联系方式", { exact: true }).fill("not-an-email");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(profileFeedback(page)).toContainText("请填写有效邮箱地址");

  // ⑤ 补齐合法值 + 上传头像后保存成功
  await page.getByLabel("联系方式", { exact: true }).fill(contactValue);
  await page.getByLabel("简介").fill(bioValue);
  const avatar = await pngBuffer(context, 240, 180, "#d96fa3");
  await page.locator('input[type="file"]').setInputFiles({
    name: "avatar.png",
    mimeType: "image/png",
    buffer: avatar,
  });
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("个人资料已保存")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "个人资料" })).toBeVisible();
  await expect(page.getByText(bioValue)).toBeVisible();
  await expect(page.getByText(contactValue)).toBeVisible();
  await expect(page.locator('img[alt$="的头像"]')).toBeVisible();

  // ⑥ 取消：有未保存修改时先确认，确认后丢弃改动
  await enterEdit(page);
  await page.getByLabel(/昵称/).fill("临时昵称");
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑资料", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: nicknameValue })).toBeVisible();

  // ⑦ 刷新后仍是服务端保存的数据
  await page.reload();
  await expect(page.getByRole("heading", { name: nicknameValue })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(contactValue)).toBeVisible();
  await expect(page.locator('img[alt$="的头像"]')).toBeVisible();

  // ⑧ 保存失败：PATCH 返回 500 时给出明确错误并保留编辑态
  await enterEdit(page);
  await page.route("**/api/me", async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "模拟服务异常，请稍后重试" }),
      });
      return;
    }
    await route.continue();
  });
  await page.getByLabel("简介").fill("保存失败场景的简介");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(profileFeedback(page)).toContainText("模拟服务异常，请稍后重试");
  await expect(page.getByLabel("简介")).toBeVisible();
  await page.unroute("**/api/me");
});

test("个人资料：加载失败给出重试入口并能恢复", async ({ page, context }) => {
  await signIn(context);
  // dev 下 effect 双跑会发两次 GET：失败态必须对每次请求都成立，直到用户点重试
  let failing = true;
  await page.route("**/api/me", async (route) => {
    if (failing && route.request().method() === "GET") {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "服务不可用" }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/account");
  await expect(page.getByText("账号信息加载失败")).toBeVisible({ timeout: 30_000 });

  failing = false;
  await page.getByRole("button", { name: "重新加载" }).click();
  await expect(page.getByRole("heading", { name: "个人资料" })).toBeVisible({ timeout: 30_000 });
  await page.unroute("**/api/me");
});

test("个人资料：移动端 360px 无横向溢出且编辑表单可用", async ({ page, context }) => {
  await signIn(context);
  await page.setViewportSize({ width: 360, height: 740 });
  await openAccount(page);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await enterEdit(page);
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeVisible();
  const editOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(editOverflow).toBeLessThanOrEqual(1);
});
