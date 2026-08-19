import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * 自研 JWT（HS256）—— 文档 §10.1 认证选型：自研 JWT + 多方式登录。
 * 不引入外部依赖，仅使用 Node 内置 crypto。
 * Payload 约定：{ sub: 用户ID, sid: 会话ID, iat, exp, typ }
 *  - sub  = user id
 *  - sid  = session id（服务端 session 表校验，支持踢下线）
 *  - typ  = "access" | "refresh"
 */

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
}

export function signJwt(payload: Omit<JwtPayload, "iat" | "exp"> & { expiresInSec: number }, secret: string): string {
  const now = Math.floor(Date.now() / 1000);
  const header = base64urlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64urlEncode(
    JSON.stringify({
      sub: payload.sub,
      sid: payload.sid,
      typ: payload.typ,
      iat: now,
      exp: now + payload.expiresInSec,
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
  if (parsed.exp && parsed.exp < Math.floor(Date.now() / 1000)) return null;
  if (parsed.typ !== "access" && parsed.typ !== "refresh") return null;
  if (!parsed.sub || !parsed.sid) return null;
  return parsed;
}
