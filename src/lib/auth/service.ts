import { randomUUID } from "node:crypto";
import type { UserDb } from "./db.ts";
import { signJwt, verifyJwt } from "./jwt.ts";
import {
  CODE_DAILY_LIMIT,
  CODE_MAX_ATTEMPTS,
  CODE_RESEND_INTERVAL_MS,
  CODE_TTL_MS,
  deliverSmsCode,
  generateCode,
  hashCode,
  isCodeExpired,
  todayString,
} from "./sms.ts";
import { AuthError, type AuthConfig, type AuthSessionContext, type AuthTokens, type IdentityProvider, type MeResult, type UserRow } from "./types.ts";
import { verifyCaptcha } from "./captcha.ts";

const ACCESS_TTL_SEC = 2 * 60 * 60; // 2 小时
const REFRESH_TTL_SEC = 30 * 24 * 60 * 60; // 30 天
const SESSION_TTL_MS = REFRESH_TTL_SEC * 1000;

const PHONE_RE = /^1[3-9]\d{9}$/;

/**
 * 认证业务服务（文档 §5.1 登录即注册：任一方式首次验证通过即自动创建账号并绑定）。
 * 本模块不依赖 Next.js，可在纯 Node 测试环境直接验证。
 */

export function createAuthService(db: UserDb, config: AuthConfig) {
  const accessTtl = config.accessTtlSec ?? ACCESS_TTL_SEC;
  const refreshTtl = config.refreshTtlSec ?? REFRESH_TTL_SEC;

  function issueTokens(userId: string, sessionId: string): AuthTokens {
    return {
      accessToken: signJwt({ sub: userId, sid: sessionId, typ: "access", expiresInSec: accessTtl }, config.jwtSecret),
      refreshToken: signJwt({ sub: userId, sid: sessionId, typ: "refresh", expiresInSec: refreshTtl }, config.jwtSecret),
    };
  }

  /** 创建会话记录并签发双令牌 */
  function openSession(userId: string, ctx: AuthSessionContext): AuthTokens {
    const sessionId = randomUUID();
    const now = Date.now();
    db.insertSession({
      session_id: sessionId,
      user_id: userId,
      device_fingerprint: ctx.deviceFingerprint ?? null,
      ip: ctx.ip ?? null,
      location: null,
      last_seen: now,
      created_at: now,
      expires_at: now + SESSION_TTL_MS,
      revoked_at: null,
    });
    db.insertAuditLog({ actor_id: userId, action: "login", detail: "session opened", ip: ctx.ip ?? null, at: now });
    return issueTokens(userId, sessionId);
  }

  /** 校验 access token → 会话 → 用户；失败返回 null（未登录） */
  function resolveAccessToken(token: string | undefined | null): UserRow | null {
    if (!token) return null;
    const payload = verifyJwt(token, config.jwtSecret);
    if (!payload || payload.typ !== "access") return null;
    const session = db.getSession(payload.sid);
    if (!session || session.revoked_at !== null || session.expires_at < Date.now()) return null;
    const user = db.getUserById(payload.sub);
    if (!user || user.status !== "active") return null;
    return user;
  }

  /** 校验 refresh token，返回 { session, user }；失败返回 null */
  function resolveRefreshToken(token: string | undefined | null): { sessionId: string; user: UserRow } | null {
    if (!token) return null;
    const payload = verifyJwt(token, config.jwtSecret);
    if (!payload || payload.typ !== "refresh") return null;
    const session = db.getSession(payload.sid);
    if (!session || session.revoked_at !== null || session.expires_at < Date.now()) return null;
    const user = db.getUserById(payload.sub);
    if (!user || user.status !== "active") return null;
    return { sessionId: payload.sid, user };
  }

  /** 用 refresh token 换新双令牌（轮换） */
  function rotateTokens(refreshToken: string, ctx: AuthSessionContext): AuthTokens | null {
    const resolved = resolveRefreshToken(refreshToken);
    if (!resolved) return null;
    db.revokeSession(resolved.sessionId, Date.now());
    const tokens = openSession(resolved.user.id, ctx);
    db.insertAuditLog({ actor_id: resolved.user.id, action: "token_refresh", detail: "session rotated", ip: ctx.ip ?? null, at: Date.now() });
    return tokens;
  }

  /**
   * 微信登录/注册（登录即注册）：openid 已绑定 → 登录；未绑定 → 创建账号并绑定。
   * 微信仅返回 openid 不提供手机号（§5.1），新账号 phone 为 null，
   * 前端应提示补绑手机号（/account 绑定入口）。
   */
  function wechatLoginOrRegister(
    openid: string,
    ctx: AuthSessionContext,
    profile?: { nickname?: string }
  ): { user: UserRow; tokens: AuthTokens; isNewUser: boolean } {
    if (!openid || openid.length < 8) {
      throw new AuthError("invalid_wechat_openid", "微信身份标识无效");
    }
    const existing = db.getUserByIdentity("wechat", openid);
    const now = Date.now();
    if (existing) {
      db.touchIdentity("wechat", openid, now);
      const tokens = openSession(existing.id, ctx);
      return { user: existing, tokens, isNewUser: false };
    }

    const userId = randomUUID();
    const nickname =
      (profile?.nickname && profile.nickname.trim().slice(0, 30)) || `微信用户${openid.slice(-4)}`;
    db.insertUser({
      id: userId,
      phone: null,
      email: null,
      password_hash: null,
      nickname,
      avatar: null,
      age_group: null,
      status: "active",
      agreement_version: null,
      created_at: now,
      deleted_at: null,
    });
    db.insertIdentity(userId, "wechat", openid, now);
    // 账号级改进计划偏好默认开启（与本地开关默认值一致，M1）
    db.upsertConsent(userId, 1, null, now);
    const tokens = openSession(userId, ctx);
    return { user: db.getUserById(userId)!, tokens, isNewUser: true };
  }

  /**
   * 请求短信验证码（人机验证通过 + 节流 60s + 单日 10 条）。
   * 返回 devCode 仅限开发模式（生产未配置服务商时抛 503）。
   */
  async function requestSmsCode(
    phoneRaw: string,
    captcha: { id: string; answer: string }
  ): Promise<{ devCode: string | null }> {
    const phone = phoneRaw.trim();
    if (!PHONE_RE.test(phone)) throw new AuthError("invalid_phone", "手机号格式不正确");

    // 人机验证（图形验证码）：未通过直接拒绝，不发送短信
    if (!verifyCaptcha(captcha.id, captcha.answer)) {
      throw new AuthError("captcha_failed", "人机验证未通过，请刷新后重试", 400);
    }

    const now = Date.now();
    const latest = db.getLatestCode(phone, "login");
    if (latest && now - latest.created_at < CODE_RESEND_INTERVAL_MS) {
      throw new AuthError("code_throttled", "验证码发送过于频繁，请 60 秒后再试", 429);
    }
    const dayCount = db.countCodesToday(phone, todayString(now));
    if (dayCount >= CODE_DAILY_LIMIT) {
      throw new AuthError("code_daily_limit", "今日验证码已用完，请明天再试", 429);
    }

    const code = generateCode();
    const { mode } = await deliverSmsCode(phone, code);
    db.insertCode({
      phone,
      purpose: "login",
      code_hash: hashCode(code),
      expires_at: now + CODE_TTL_MS,
      attempts: 0,
      created_at: now,
      day: todayString(now),
    });
    return { devCode: mode === "dev" ? code : null };
  }

  /**
   * 手机号验证码登录/注册：验证码正确 → 手机号已绑定则登录；未绑定则创建账号。
   */
  async function phoneCodeLoginOrRegister(
    phoneRaw: string,
    code: string,
    ctx: AuthSessionContext
  ): Promise<{ user: UserRow; tokens: AuthTokens; isNewUser: boolean }> {
    const phone = phoneRaw.trim();
    if (!PHONE_RE.test(phone)) throw new AuthError("invalid_phone", "手机号格式不正确");
    if (!/^\d{6}$/.test(code)) throw new AuthError("invalid_code", "验证码格式不正确");

    const now = Date.now();
    const record = db.getLatestCode(phone, "login");
    if (!record || isCodeExpired(record.expires_at, now)) {
      throw new AuthError("code_expired", "验证码已过期，请重新获取", 401);
    }
    if (record.attempts >= CODE_MAX_ATTEMPTS) {
      throw new AuthError("code_too_many_attempts", "尝试次数过多，请重新获取验证码", 429);
    }
    if (record.code_hash !== hashCode(code)) {
      db.incrementCodeAttempts(record.id);
      throw new AuthError("bad_code", "验证码错误", 401);
    }
    // 一次性使用
    db.deleteCode(record.id);

    const existing = db.getUserByIdentity("phone", phone);
    if (existing) {
      db.touchIdentity("phone", phone, now);
      const tokens = openSession(existing.id, ctx);
      return { user: existing, tokens, isNewUser: false };
    }

    const userId = randomUUID();
    db.insertUser({
      id: userId,
      phone,
      email: null,
      password_hash: null,
      nickname: `用户${phone.slice(-4)}`,
      avatar: null,
      age_group: null,
      status: "active",
      agreement_version: null,
      created_at: now,
      deleted_at: null,
    });
    db.insertIdentity(userId, "phone", phone, now);
    db.upsertConsent(userId, 1, null, now);
    const tokens = openSession(userId, ctx);
    return { user: db.getUserById(userId)!, tokens, isNewUser: true };
  }

  /** 给当前账号补绑手机号（非手机号方式注册后，文档 §5.1 合规要求） */
  async function bindPhone(userId: string, phoneRaw: string, code: string): Promise<void> {
    const phone = phoneRaw.trim();
    if (!PHONE_RE.test(phone)) throw new AuthError("invalid_phone", "手机号格式不正确");
    const existingByIdentity = db.getUserByIdentity("phone", phone);
    if (existingByIdentity && existingByIdentity.id !== userId) {
      throw new AuthError("phone_taken", "该手机号已绑定其他账号", 409);
    }
    const now = Date.now();
    const record = db.getLatestCode(phone, "login");
    if (!record || isCodeExpired(record.expires_at, now)) {
      throw new AuthError("code_expired", "验证码已过期，请重新获取", 401);
    }
    if (record.attempts >= CODE_MAX_ATTEMPTS) {
      throw new AuthError("code_too_many_attempts", "尝试次数过多，请重新获取验证码", 429);
    }
    if (record.code_hash !== hashCode(code)) {
      db.incrementCodeAttempts(record.id);
      throw new AuthError("bad_code", "验证码错误", 401);
    }
    db.deleteCode(record.id);
    db.updateUserPhone(userId, phone);
    const identities = db.listIdentities(userId);
    if (!identities.some((i) => i.provider === "phone")) {
      db.insertIdentity(userId, "phone", phone, now);
    }
    db.insertAuditLog({ actor_id: userId, action: "bind_phone", detail: `phone=${phone}`, ip: null, at: now });
  }

  /** 查看账号登录方式（文档 §5.2 登录方式管理） */
  function listIdentities(userId: string): Array<{ provider: IdentityProvider; identifier: string; lastUsedAt: number }> {
    return db.listIdentities(userId).map((i) => ({
      provider: i.provider as IdentityProvider,
      identifier: i.identifier,
      lastUsedAt: i.last_used_at,
    }));
  }

  /** 解绑登录方式：至少保留一种（文档 §5.2） */
  function removeIdentity(userId: string, provider: string): void {
    const identities = db.listIdentities(userId);
    const target = identities.find((i) => i.provider === provider);
    if (!target) throw new AuthError("identity_not_found", "该登录方式不存在", 404);
    if (identities.length <= 1) {
      throw new AuthError("last_identity", "至少需要保留一种登录方式", 400);
    }
    // phone 作为主身份时若还有其他方式可以解绑；但若 phone 是唯一主身份则不允许
    if (provider === "phone" && identities.some((i) => i.provider === "phone" && i.provider !== provider)) {
      // 不会走到：上面已按 provider 唯一
    }
    db.deleteIdentity(userId, provider);
    db.insertAuditLog({ actor_id: userId, action: "unbind_identity", detail: `provider=${provider}`, ip: null, at: Date.now() });
  }

  /** 当前用户档案 + 登录方式 + 偏好（GET /api/me） */
  function getMe(userId: string): MeResult {
    const user = db.getUserById(userId);
    if (!user) throw new AuthError("user_not_found", "用户不存在", 404);
    const consent = db.getConsent(userId);
    return {
      user: {
        id: user.id,
        phone: user.phone,
        email: user.email,
        nickname: user.nickname,
        avatar: user.avatar,
        ageGroup: user.age_group,
        status: user.status,
        createdAt: user.created_at,
      },
      identities: listIdentities(userId),
      consent: {
        improvementEnabled: consent ? consent.improvement_enabled === 1 : true,
        agreementVersion: consent?.agreement_version ?? null,
      },
    };
  }

  /** 更新昵称/头像（PATCH /api/me） */
  function updateProfile(userId: string, patch: { nickname?: string; avatar?: string | null; ageGroup?: string | null }): void {
    const user = db.getUserById(userId);
    if (!user) throw new AuthError("user_not_found", "用户不存在", 404);
    const nickname = patch.nickname?.trim();
    if (nickname !== undefined) {
      if (nickname.length < 1 || nickname.length > 30) {
        throw new AuthError("invalid_nickname", "昵称长度需在 1-30 字之间");
      }
    }
    db.updateUserProfile(userId, {
      nickname: nickname !== undefined ? nickname : undefined,
      avatar: patch.avatar !== undefined ? patch.avatar : undefined,
      age_group: patch.ageGroup !== undefined ? patch.ageGroup : undefined,
    });
  }

  /** 账号级改进计划偏好（PATCH /api/me/improvement，§5.6） */
  function setImprovementPreference(userId: string, enabled: boolean): void {
    db.upsertConsent(userId, enabled ? 1 : 0, db.getConsent(userId)?.agreement_version ?? null, Date.now());
    db.insertAuditLog({ actor_id: userId, action: "improvement_preference", detail: `enabled=${enabled}`, ip: null, at: Date.now() });
  }

  /** 注销当前会话（POST /api/auth/logout） */
  function logout(refreshToken: string | undefined | null, ctx: AuthSessionContext): void {
    const resolved = resolveRefreshToken(refreshToken);
    if (resolved) {
      db.revokeSession(resolved.sessionId, Date.now());
      db.insertAuditLog({ actor_id: resolved.user.id, action: "logout", detail: "session revoked", ip: ctx.ip ?? null, at: Date.now() });
    }
  }

  return {
    openSession,
    resolveAccessToken,
    resolveRefreshToken,
    rotateTokens,
    wechatLoginOrRegister,
    requestSmsCode,
    phoneCodeLoginOrRegister,
    bindPhone,
    listIdentities,
    removeIdentity,
    getMe,
    updateProfile,
    setImprovementPreference,
    logout,
  };
}

export type AuthService = ReturnType<typeof createAuthService>;
