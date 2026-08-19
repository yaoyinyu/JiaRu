import { createUserDb, type UserDb } from "./db.ts";
import { getDbPath, getJwtSecret } from "./config.ts";
import { createAuthService, type AuthService } from "./service.ts";

/**
 * 服务端数据库/认证单例（Next.js Route Handler 使用）。
 * 开发模式下 Turbopack 热重载会重复执行模块，用 globalThis 兜底避免
 * 重复打开同一个 SQLite 文件。
 */

declare global {
  var __jiaruUserDb: UserDb | undefined;
  var __jiaruAuthService: AuthService | undefined;
}

export function getUserDb(): UserDb {
  if (!globalThis.__jiaruUserDb) {
    globalThis.__jiaruUserDb = createUserDb(getDbPath());
  }
  return globalThis.__jiaruUserDb;
}

export function getAuthService(): AuthService {
  if (!globalThis.__jiaruAuthService) {
    globalThis.__jiaruAuthService = createAuthService(getUserDb(), { jwtSecret: getJwtSecret() });
  }
  return globalThis.__jiaruAuthService;
}
