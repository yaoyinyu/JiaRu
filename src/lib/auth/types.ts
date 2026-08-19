// 用户系统核心类型（与 docs/user-system-plan.md §7 数据模型对应）
// 字段命名沿用数据表 snake_case，前端展示时再映射。

export type UserStatus = "active" | "suspended" | "pending_deletion" | "deleted";

export interface UserRow {
  id: string;
  phone: string | null;
  email: string | null;
  password_hash: string | null;
  nickname: string;
  avatar: string | null;
  age_group: string | null;
  status: UserStatus;
  agreement_version: string | null;
  created_at: number;
  deleted_at: number | null;
}

export type IdentityProvider = "phone" | "email" | "wechat" | "github";

export interface IdentityRow {
  id: number;
  user_id: string;
  provider: IdentityProvider;
  identifier: string;
  created_at: number;
  last_used_at: number;
}

export interface SessionRow {
  session_id: string;
  user_id: string;
  device_fingerprint: string | null;
  ip: string | null;
  location: string | null;
  last_seen: number;
  created_at: number;
  expires_at: number;
  revoked_at: number | null;
}

export interface ConsentRow {
  user_id: string;
  agreement_version: string | null;
  improvement_enabled: number; // 1 = 开启（默认），0 = 关闭
  improvement_updated_at: number | null;
}

export interface VerificationCodeRow {
  id: number;
  phone: string;
  purpose: string;
  code_hash: string;
  expires_at: number;
  attempts: number;
  created_at: number;
  day: string; // YYYY-MM-DD（本地时区，用于单日上限）
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

export interface AuthSessionContext {
  ip?: string | null;
  deviceFingerprint?: string | null;
}

export interface AuthConfig {
  jwtSecret: string;
  accessTtlSec?: number; // 默认 2h
  refreshTtlSec?: number; // 默认 30d
}

export interface MeResult {
  user: {
    id: string;
    phone: string | null;
    email: string | null;
    nickname: string;
    avatar: string | null;
    ageGroup: string | null;
    status: UserStatus;
    createdAt: number;
  };
  identities: Array<{ provider: IdentityProvider; identifier: string; lastUsedAt: number }>;
  consent: { improvementEnabled: boolean; agreementVersion: string | null };
}

export class AuthError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status = 400) {
    super(message);
    this.name = "AuthError";
    this.code = code;
    this.status = status;
  }
}
