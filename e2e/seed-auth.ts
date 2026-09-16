/**
 * 评审 #11 用例⑤（登录过期续期）的会话种子脚本。
 *
 * 用法：node --no-warnings --experimental-strip-types e2e/seed-auth.ts <dbPath> <jwtSecret> <outJson>
 *
 * 在指定 SQLite 文件中创建测试用户与会话，并输出：
 *  - refreshToken：有效 refresh token（浏览器以 jiaru_refresh Cookie 携带）；
 *  - expiredAccess：与该会话同 sub/sid 但 exp 已过期的 access token（jiaru_access）。
 *
 * 仅供 Playwright 本地回归使用；数据库路径由 playwright.config.ts 的
 * JIARU_DB_PATH 指向 .playwright-tmp/，绝不触碰真实 data/ 用户库。
 */
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { createUserDb } from "../src/lib/auth/db.ts";
import { createAuthService } from "../src/lib/auth/service.ts";
import { signJwt } from "../src/lib/auth/jwt.ts";

const [dbPath, jwtSecret, outPath] = process.argv.slice(2);
if (!dbPath || !jwtSecret || !outPath) {
  console.error(
    "usage: node --experimental-strip-types e2e/seed-auth.ts <dbPath> <jwtSecret> <outJson>"
  );
  process.exit(2);
}

mkdirSync(path.dirname(outPath), { recursive: true });
mkdirSync(path.dirname(dbPath), { recursive: true });

const db = createUserDb(dbPath);
const auth = createAuthService(db, { jwtSecret });
const { tokens } = auth.wechatLoginOrRegister("openid-e2e-playwright", {});
const refreshToken = tokens.refreshToken;
// 从 refresh payload 里取 sub/sid，签一个同会话但已过期的 access（exp = now - 60）
const payload = JSON.parse(
  Buffer.from(refreshToken.split(".")[1], "base64url").toString("utf8")
) as { sub: string; sid: string };
const expiredAccess = signJwt(
  { sub: payload.sub, sid: payload.sid, typ: "access", expiresInSec: -60 },
  jwtSecret
);
writeFileSync(
  outPath,
  JSON.stringify({ refreshToken, expiredAccess }, null, 2),
  "utf8"
);
console.log(`seeded session -> ${outPath}`);
