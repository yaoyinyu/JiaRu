import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * 自研 JWT（HS256）—— 文档 §10.1 认证选型：自研 JWT + 多方式登录。
 * 不引入外部依赖，仅使用 Node 内置 crypto。
 * Payload 约定：{ sub: 用户ID, sid: 会话ID, iat, exp, typ, iss, aud }
 *  - sub  = user id
 *  - sid  = session id（服务端 session 表校验，支持踢下线）
 *  - typ  = "access" | "refresh"
 *  - iss  = 签发者（2026-09-24 安全审计修复 L3）
 *  - aud  = 受众（同上；防止 access / refresh 或其他系统签发的令牌被交叉使用）
 */

/** 签发者与受众常量；校验时不匹配即拒绝 */
export const JWT_ISSUER = "jiaru";
export const JWT_AUDIENCE = "jiaru-web";

function base64urlEncode(input: Buffer | string): string {
  return Buffer.from(input).toString("base64url");
}

function base64urlDecode(input: string): Buffer {
  return Buffer.from(input, "base64url");
}

interface JwtPayload {
  sub: string;
  sid: string;
  typ: "access" | "refresh";
  iat: number;
  exp: number;
  iss: string;
  aud: string;
}

export function signJwt(
  payload: Omit<JwtPayload, "iat" | "exp" | "iss" | "aud"> & { expiresInSec: number },
  secret: string
): string {
  const now = Math.floor(Date.now() / 1000);
  const header = base64urlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64urlEncode(
    JSON.stringify({
      sub: payload.sub,
      sid: payload.sid,
      typ: payload.typ,
      iat: now,
      exp: now + payload.expiresInSec,
      iss: JWT_ISSUER,
      aud: JWT_AUDIENCE,
    })
  );
  const signingInput = `${header}.${body}`;
  const signature = createHmac("sha256", secret).update(signingInput).digest("base64url");
  return `${signingInput}.${signature}`;
}

/** 校验 JWT 签名与过期时间；非法或过期返回 null */
export function verifyJwt(token: string, secret: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [header, body, signature] = parts;
  const signingInput = `${header}.${body}`;

  // 2026-09-24 安全审计修复 L3：显式固定算法，杜绝 alg 混淆（如 none / RS→HS 降级）。
  let headerObj: { alg?: unknown };
  try {
    headerObj = JSON.parse(base64urlDecode(header).toString("utf8")) as { alg?: unknown };
  } catch {
    return null;
  }
  if (headerObj.alg !== "HS256") return null;

  const expected = createHmac("sha256", secret).update(signingInput).digest();
  let actual: Buffer;
  try {
    actual = base64urlDecode(signature);
  } catch {
    return null;
  }
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    return null;
  }
  let parsed: JwtPayload;
  try {
    parsed = JSON.parse(base64urlDecode(body).toString("utf8")) as JwtPayload;
  } catch {
    return null;
  }
  if (typeof parsed.exp !== "number" || parsed.exp < Math.floor(Date.now() / 1000)) return null;
  if (parsed.typ !== "access" && parsed.typ !== "refresh") return null;
  if (typeof parsed.sub !== "string" || !parsed.sub) return null;
  if (typeof parsed.sid !== "string" || !parsed.sid) return null;
  // 2026-09-24 安全审计修复 L3：校验 iss / aud，避免其他方签发的合法签名令牌被接受。
  if (parsed.iss !== JWT_ISSUER) return null;
  if (parsed.aud !== JWT_AUDIENCE) return null;
  return parsed;
}
