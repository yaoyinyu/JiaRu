import path from "node:path";

// 环境配置读取（服务端专用，勿在客户端组件引入）

/** 数据库文件路径；测试可传 :memory: */
export function getDbPath(): string {
  return process.env.JIARU_DB_PATH ?? path.join(process.cwd(), "data", "jiaru-user.db");
}

/** JWT 签名密钥；生产环境必须显式配置，开发环境使用可预测的本地密钥 */
export function getJwtSecret(): string {
  const secret = process.env.JWT_SECRET;
  if (secret && secret.length >= 16) return secret;
  if (process.env.NODE_ENV === "production") {
    throw new Error("JWT_SECRET 未配置：生产环境必须设置至少 16 位的签名密钥");
  }
  // 仅限本地开发/测试：不满足强密钥时回退，避免每次重启登录态失效
  return "jiaru-local-dev-secret-please-override-in-env";
}

/** 是否开发模式（决定验证码等降级行为） */
export function isDevMode(): boolean {
  return process.env.NODE_ENV !== "production";
}
