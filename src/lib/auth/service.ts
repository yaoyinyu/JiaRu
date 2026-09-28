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
// refresh 剩余寿命滑动阈值已随 M2 轮换移除：每次续期都重签 refresh，不再仅在末期滑动。
/**
 * 轮换宽限窗口（2026-09-27 修复 M2）：旧 refresh 在被替换后仍可继续使用的时长。
 * 用于容纳并发请求（浏览器同时发多个请求、携带的是同一个旧 Cookie），
 * 以及上一次响应 Cookie 未落盘的情况。窗口内命中旧 nonce 视为正常轮换；
 * 窗口外仍使用旧 nonce 即判定为「重放」，整条会话吊销。
 */
const DEFAULT_REFRESH_GRACE_MS = 5 * 60 * 1000;

const PHONE_RE = /^1[3-9]\d{9}$/;

/**
 * 认证业务服务（文档 §5.1 登录即注册：任一方式首次验证通过即自动创建账号并绑定）。
 * 本模块不依赖 Next.js，可在纯 Node 测试环境直接验证。
 */

export function createAuthService(db: UserDb, config: AuthConfig) {
  const accessTtl = config.accessTtlSec ?? ACCESS_TTL_SEC;
  const refreshTtl = config.refreshTtlSec ?? REFRESH_TTL_SEC;

  function issueAccessToken(userId: string, sessionId: string): string {
    return signJwt({ sub: userId, sid: sessionId, typ: "access", expiresInSec: accessTtl }, config.jwtSecret);
  }

  /**
   * 签发 refresh 令牌。`jti` 为该份 refresh 的一次性凭据，落库在会话行上，
   * 续期时逐个轮换并可据以识别重放（2026-09-27 修复 M2）。
   */
  function issueRefreshToken(userId: string, sessionId: string, jti = randomUUID()): string {
    return signJwt({ sub: userId, sid: sessionId, typ: "refresh", jti, expiresInSec: refreshTtl }, config.jwtSecret);
  }

  /** 创建会话记录并签发双令牌（refresh 带一次性 jti 并落库） */
  function openSession(userId: string, ctx: AuthSessionContext): AuthTokens {
    const sessionId = randomUUID();
    const now = Date.now();
    const refreshJti = randomUUID();
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
      refresh_nonce: refreshJti,
      prev_refresh_nonce: null,
      prev_nonce_expires_at: null,
    });
    db.insertAuditLog({ actor_id: userId, action: "login", detail: "session opened", ip: ctx.ip ?? null, at: now });
    return {
      accessToken: issueAccessToken(userId, sessionId),
      refreshToken: issueRefreshToken(userId, sessionId, refreshJti),
    };
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
   * 静默续期（2026-09-27 修复 M2，改为「轮换 + 宽限 + 重放检测」）。
   *
   * 旧行为：refresh 有效就签发新 access，refresh 原样返回、永不失效——
   * 一旦 refresh 泄露，攻击者可在 30 天内无限次换 access，且无法被发现。
   *
   * 新行为：每次续期都签发一份带新 `jti` 的 refresh，旧 jti 退到宽限位；
   *  - 宽限窗口内使用旧 jti → 视为并发请求，正常轮换（并发安全不退化）；
   *  - 宽限窗口外仍用旧 jti → 判定为重放，吊销整条会话并记审计日志；
   *  - 会话行尚无 nonce（本次部署前建的老会话）→ 兼容放行并补写 nonce。
   *
   * 调用方必须用 {@link applyRenewedCookies} 把新 refresh 写回 Cookie，
   * 否则轮换出的新令牌会丢失（本项目 13 处 requireUser 调用点均已回写）。
   */
  function renewFromRefresh(refreshToken: string | undefined | null): AuthTokens | null {
    const resolved = resolveRefreshToken(refreshToken);
    if (!resolved) return null;
    const payload = refreshToken ? verifyJwt(refreshToken, config.jwtSecret) : null;
    if (!payload) return null;

    const now = Date.now();
    const session = db.getSession(resolved.sessionId);
    if (!session) return null;

    const graceMs = graceWindowMs();
    const jti = payload.jti ?? null;
    const isCurrent = jti !== null && jti === session.refresh_nonce;
    const withinGrace =
      jti !== null &&
      jti === session.prev_refresh_nonce &&
      session.prev_nonce_expires_at !== null &&
      now < session.prev_nonce_expires_at;

    // 老会话兼容：部署前建立的会话没有 nonce，首次续期时补上，不误判为重放。
    const legacySession = session.refresh_nonce === null;

    if (!legacySession && !isCurrent && !withinGrace) {
      db.revokeSession(resolved.sessionId, now);
      db.insertAuditLog({
        actor_id: resolved.user.id,
        action: "refresh_replay_detected",
        detail: `sid=${resolved.sessionId} jti=${jti ?? "none"}`,
        ip: null,
        at: now,
      });
      return null;
    }

    const nextJti = randomUUID();
    db.rotateRefreshNonce(resolved.sessionId, nextJti, now + graceMs);
    return {
      accessToken: issueAccessToken(resolved.user.id, resolved.sessionId),
      refreshToken: issueRefreshToken(resolved.user.id, resolved.sessionId, nextJti),
    };
  }

  function graceWindowMs(): number {
    const raw = Number(process.env.JIARU_REFRESH_GRACE_SEC);
    if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_REFRESH_GRACE_MS;
    return Math.min(raw, 24 * 60 * 60) * 1000;
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
    captcha: { id: string; answer: string },
    clientIp?: string | null
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
    const { mode } = await deliverSmsCode(phone, code, clientIp);
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
   * 校验并消费一条手机验证码（过期/超次/错误/已消费一律拒绝）。
   * 消费=标记 consumed_at，发送台账保留（60 秒节流与单日 10 条继续依据完整台账）。
   */
  function consumeValidatedCode(phone: string, code: string): void {
    const now = Date.now();
    const record = db.getLatestCode(phone, "login");
    if (!record || isCodeExpired(record.expires_at, now)) {
      throw new AuthError("code_expired", "验证码已过期，请重新获取", 401);
    }
    if (record.attempts >= CODE_MAX_ATTEMPTS) {
      throw new AuthError("code_too_many_attempts", "尝试次数过多，请重新获取验证码", 429);
    }
    if (record.consumed_at !== null) {
      throw new AuthError("code_expired", "验证码已被使用，请重新获取", 401);
    }
    if (record.code_hash !== hashCode(code)) {
      db.incrementCodeAttempts(record.id);
      throw new AuthError("bad_code", "验证码错误", 401);
    }
    db.markCodeConsumed(record.id, now);
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
    consumeValidatedCode(phone, code);

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

  /**
   * 给当前账号绑定/换绑手机号（非手机号方式注册后补绑，或已有手机号换绑）。
   * users.phone 与 phone identity 必须在同一事务内一致更新：换绑只改 identity 的
   * identifier，否则出现"资料是新号、登录身份是旧号"，随后新号注册触发
   * users.phone UNIQUE 冲突（2026-09-05 评审 #7 复现缺陷）。
   */
  async function bindPhone(userId: string, phoneRaw: string, code: string): Promise<void> {
    const phone = phoneRaw.trim();
    if (!PHONE_RE.test(phone)) throw new AuthError("invalid_phone", "手机号格式不正确");
    // 2026-09-24 安全审计修复：先消费验证码，再判断号码归属。
    // 原实现先查归属，未持验证码的攻击者可以凭 409("已绑定其他账号") 与
    // code_expired 的差异枚举已注册手机号；现在两者在未通过验证码时返回一致。
    consumeValidatedCode(phone, code);
    const existingByIdentity = db.getUserByIdentity("phone", phone);
    if (existingByIdentity && existingByIdentity.id !== userId) {
      throw new AuthError("phone_taken", "该手机号已绑定其他账号", 409);
    }
    const now = Date.now();
    try {
      db.transaction(() => {
        const identities = db.listIdentities(userId);
        const phoneIdentity = identities.find((i) => i.provider === "phone");
        if (phoneIdentity) {
          // 换绑（或重复绑定同一号码的幂等写）：users.phone 与 identity 原地一致更新
          db.updateUserPhone(userId, phone);
          db.rebindIdentityPhone(userId, phone, now);
        } else {
          // 补绑：此前没有任何 phone 身份
          db.updateUserPhone(userId, phone);
          db.insertIdentity(userId, "phone", phone, now);
        }
        db.insertAuditLog({
          actor_id: userId,
          action: "bind_phone",
          detail: `phone=${phone} mode=${phoneIdentity ? "rebind" : "bind"}`,
          ip: null,
          at: now,
        });
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("UNIQUE")) {
        // users.phone / (provider, identifier) 唯一约束：号码已被其他账号占用
        throw new AuthError("phone_taken", "该手机号已绑定其他账号", 409);
      }
      throw err;
    }
  }

  /** 查看账号登录方式（文档 §5.2 登录方式管理） */
  function listIdentities(userId: string): Array<{ provider: IdentityProvider; identifier: string; lastUsedAt: number }> {
    return db.listIdentities(userId).map((i) => ({
      provider: i.provider as IdentityProvider,
      identifier: i.identifier,
      lastUsedAt: i.last_used_at,
    }));
  }

  /** 解绑登录方式：至少保留一种（文档 §5.2）；解绑 phone 时资料与身份同步清空 */
  function removeIdentity(userId: string, provider: string): void {
    const identities = db.listIdentities(userId);
    const target = identities.find((i) => i.provider === provider);
    if (!target) throw new AuthError("identity_not_found", "该登录方式不存在", 404);
    if (identities.length <= 1) {
      throw new AuthError("last_identity", "至少需要保留一种登录方式", 400);
    }
    db.deleteIdentity(userId, provider);
    if (provider === "phone") {
      // 资料与身份一致：identity 已删除，users.phone 不能残留（否则无法再次绑定同号）
      db.clearUserPhone(userId);
    }
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
    renewFromRefresh,
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
