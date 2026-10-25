import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import path from "node:path";
import type {
  ConsentRow,
  IdentityRow,
  SessionRow,
  UserRow,
  VerificationCodeRow,
} from "./types";

/**
 * 用户系统数据库层（SQLite，Node 24 内置 node:sqlite，零依赖）。
 * 生产环境可平滑替换为 Postgres：本文件是唯一的 SQL 边界，
 * 上层 service 只依赖这里导出的函数签名。
 */

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  phone TEXT UNIQUE,
  email TEXT UNIQUE,
  password_hash TEXT,
  nickname TEXT NOT NULL DEFAULT '',
  avatar TEXT,
  age_group TEXT,
  bio TEXT,
  contact TEXT,
  contact_type TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  agreement_version TEXT,
  created_at INTEGER NOT NULL,
  deleted_at INTEGER
);

CREATE TABLE IF NOT EXISTS user_identities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  identifier TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  last_used_at INTEGER NOT NULL,
  UNIQUE(provider, identifier)
);
CREATE INDEX IF NOT EXISTS idx_identities_user ON user_identities(user_id);

CREATE TABLE IF NOT EXISTS user_sessions (
  session_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_fingerprint TEXT,
  ip TEXT,
  location TEXT,
  last_seen INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  refresh_nonce TEXT,
  prev_refresh_nonce TEXT,
  prev_nonce_expires_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS user_consents (
  user_id TEXT PRIMARY KEY,
  agreement_version TEXT,
  improvement_enabled INTEGER NOT NULL DEFAULT 1,
  improvement_updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS verification_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'login',
  code_hash TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  day TEXT NOT NULL,
  consumed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_codes_phone ON verification_codes(phone);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id TEXT,
  action TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  ip TEXT,
  at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_logs(at);
`;

/** 档案写入补丁：只写出现的键；显式 null 表示清空该字段（不出现的键保持原值） */
export interface UserProfilePatch {
  nickname?: string | null;
  avatar?: string | null;
  age_group?: string | null;
  bio?: string | null;
  contact?: string | null;
  contact_type?: string | null;
}

/** 新用户插入参数：档案可选字段可省略（默认 null） */
export type NewUserRow = Omit<UserRow, "created_at" | "bio" | "contact" | "contact_type"> & {
  created_at?: number;
  bio?: string | null;
  contact?: string | null;
  contact_type?: string | null;
};

export interface UserDb {
  close(): void;
  // users
  insertUser(row: NewUserRow): void;
  getUserById(id: string): UserRow | undefined;
  getUserByIdentity(provider: string, identifier: string): UserRow | undefined;
  updateUserProfile(id: string, patch: UserProfilePatch): void;
  updateUserPhone(id: string, phone: string): void;
  // identities
  insertIdentity(userId: string, provider: string, identifier: string, now: number): void;
  listIdentities(userId: string): IdentityRow[];
  countIdentities(userId: string): number;
  deleteIdentity(userId: string, provider: string): void;
  touchIdentity(provider: string, identifier: string, now: number): void;
  // sessions
  insertSession(row: SessionRow): void;
  getSession(sessionId: string): SessionRow | undefined;
  revokeSession(sessionId: string, now: number): void;
  touchSession(sessionId: string, now: number, ip?: string | null): void;
  /** 轮换 refresh 凭据：旧 nonce 退到宽限位并记宽限到期时间 */
  rotateRefreshNonce(sessionId: string, nonce: string, prevExpiresAt: number): void;
  // consents
  getConsent(userId: string): ConsentRow | undefined;
  upsertConsent(userId: string, improvementEnabled: number, agreementVersion: string | null, now: number): void;
  // verification codes
  getLatestCode(phone: string, purpose: string): VerificationCodeRow | undefined;
  insertCode(row: Omit<VerificationCodeRow, "id" | "consumed_at">): void;
  incrementCodeAttempts(id: number): void;
  countCodesToday(phone: string, day: string): number;
  /**
   * 消费（标记已使用）而非物理删除：发送台账必须与验证码生命周期分离，
   * 否则成功登录会抹掉发送历史，60 秒节流与单日 10 条上限立即被绕过
   * （2026-09-05 评审 #7：发送计数 1→0 复现缺陷）。
   */
  markCodeConsumed(id: number, now: number): void;
  /** 事务封装：fn 抛错时回滚并原样抛出（用于换绑等跨表一致写） */
  transaction(fn: () => void): void;
  /** 换绑：同一 phone 身份原地改绑新手机号（UNIQUE 冲突由调用方转译） */
  rebindIdentityPhone(userId: string, newPhone: string, now: number): void;
  /** 解绑 phone 身份时同步清空 users.phone（资料与身份一致） */
  clearUserPhone(userId: string): void;
  /** 审计日志（M5：登录/注销等敏感操作留痕） */
  insertAuditLog(row: {
    actor_id: string | null;
    action: string;
    detail: string;
    ip: string | null;
    at: number;
  }): void;
}

export function createUserDb(dbPath: string): UserDb {
  // 干净部署时数据目录可能不存在：node:sqlite 打开缺失父目录的文件路径
  // 会抛 ERR_SQLITE_ERROR(errcode=14, unable to open database file)，
  // 且按 /api/me → requireUser → getAuthService 的调用链，首次匿名请求
  // 就会触发。这里先确保父目录存在（:memory: 除外）。
  if (dbPath !== ":memory:") {
    const dir = path.dirname(dbPath);
    if (dir && dir !== ".") {
      mkdirSync(dir, { recursive: true });
    }
  }
  let db: DatabaseSync;
  try {
    db = new DatabaseSync(dbPath);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(
      `无法打开用户数据库 ${dbPath}：${msg}（请确认该路径的父目录存在且可写，或调整 JIARU_DB_PATH）`
    );
  }
  db.exec("PRAGMA journal_mode = WAL;");
  db.exec(SCHEMA);
  // 旧库迁移：consumed_at 列在 2026-09-16 引入（发送台账与验证码生命周期分离）。
  // CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，这里按 PRAGMA 结果补。
  const codeColumns = db.prepare(`PRAGMA table_info(verification_codes)`).all() as Array<{ name: string }>;
  if (!codeColumns.some((c) => c.name === "consumed_at")) {
    db.exec(`ALTER TABLE verification_codes ADD COLUMN consumed_at INTEGER`);
  }
  // 旧库迁移：refresh 轮换凭据列在 2026-09-27 引入（M2：refresh token 轮换与重放检测）。
  const sessionColumns = db.prepare(`PRAGMA table_info(user_sessions)`).all() as Array<{ name: string }>;
  for (const [column, ddl] of [
    ["refresh_nonce", "TEXT"],
    ["prev_refresh_nonce", "TEXT"],
    ["prev_nonce_expires_at", "INTEGER"],
  ] as const) {
    if (!sessionColumns.some((c) => c.name === column)) {
      db.exec(`ALTER TABLE user_sessions ADD COLUMN ${column} ${ddl}`);
    }
  }
  // 旧库迁移：个人档案列在 2026-10-23 引入（简介/公开联系方式由 /account 资料编辑写入）。
  const userColumns = db.prepare(`PRAGMA table_info(users)`).all() as Array<{ name: string }>;
  for (const [column, ddl] of [
    ["bio", "TEXT"],
    ["contact", "TEXT"],
    ["contact_type", "TEXT"],
  ] as const) {
    if (!userColumns.some((c) => c.name === column)) {
      db.exec(`ALTER TABLE users ADD COLUMN ${column} ${ddl}`);
    }
  }

  const stmt = {
    insertUser: db.prepare(
      `INSERT INTO users (id, phone, email, password_hash, nickname, avatar, age_group, bio, contact, contact_type, status, agreement_version, created_at, deleted_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ),
    getUserById: db.prepare(`SELECT * FROM users WHERE id = ?`),
    getUserByIdentity: db.prepare(
      `SELECT u.* FROM users u
       JOIN user_identities i ON i.user_id = u.id
       WHERE i.provider = ? AND i.identifier = ?`
    ),
    updateUserPhone: db.prepare(`UPDATE users SET phone = ? WHERE id = ?`),
    insertIdentity: db.prepare(
      `INSERT INTO user_identities (user_id, provider, identifier, created_at, last_used_at) VALUES (?, ?, ?, ?, ?)`
    ),
    listIdentities: db.prepare(`SELECT * FROM user_identities WHERE user_id = ? ORDER BY id`),
    countIdentities: db.prepare(`SELECT COUNT(*) AS n FROM user_identities WHERE user_id = ?`),
    deleteIdentity: db.prepare(`DELETE FROM user_identities WHERE user_id = ? AND provider = ?`),
    touchIdentity: db.prepare(
      `UPDATE user_identities SET last_used_at = ? WHERE provider = ? AND identifier = ?`
    ),
    insertSession: db.prepare(
      `INSERT INTO user_sessions (session_id, user_id, device_fingerprint, ip, location, last_seen, created_at, expires_at, revoked_at, refresh_nonce)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ),
    getSession: db.prepare(`SELECT * FROM user_sessions WHERE session_id = ?`),
    revokeSession: db.prepare(`UPDATE user_sessions SET revoked_at = ? WHERE session_id = ?`),
    touchSession: db.prepare(`UPDATE user_sessions SET last_seen = ?, ip = COALESCE(?, ip) WHERE session_id = ?`),
    rotateRefreshNonce: db.prepare(
      `UPDATE user_sessions
       SET prev_refresh_nonce = refresh_nonce, refresh_nonce = ?, prev_nonce_expires_at = ?
       WHERE session_id = ?`
    ),
    getConsent: db.prepare(`SELECT * FROM user_consents WHERE user_id = ?`),
    upsertConsent: db.prepare(
      `INSERT INTO user_consents (user_id, agreement_version, improvement_enabled, improvement_updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(user_id) DO UPDATE SET
         agreement_version = excluded.agreement_version,
         improvement_enabled = excluded.improvement_enabled,
         improvement_updated_at = excluded.improvement_updated_at`
    ),
    getLatestCode: db.prepare(
      `SELECT * FROM verification_codes WHERE phone = ? AND purpose = ? ORDER BY id DESC LIMIT 1`
    ),
    insertCode: db.prepare(
      `INSERT INTO verification_codes (phone, purpose, code_hash, expires_at, attempts, created_at, day)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ),
    incrementCodeAttempts: db.prepare(`UPDATE verification_codes SET attempts = attempts + 1 WHERE id = ?`),
    countCodesToday: db.prepare(
      `SELECT COUNT(*) AS n FROM verification_codes WHERE phone = ? AND day = ?`
    ),
    markCodeConsumed: db.prepare(`UPDATE verification_codes SET consumed_at = ? WHERE id = ?`),
    rebindIdentityPhone: db.prepare(
      `UPDATE user_identities SET identifier = ?, last_used_at = ? WHERE user_id = ? AND provider = 'phone'`
    ),
    clearUserPhone: db.prepare(`UPDATE users SET phone = NULL WHERE id = ?`),
    insertAuditLog: db.prepare(
      `INSERT INTO audit_logs (actor_id, action, detail, ip, at) VALUES (?, ?, ?, ?, ?)`
    ),
  };

  return {
    close() {
      db.close();
    },
    insertUser(row) {
      stmt.insertUser.run(
        row.id,
        row.phone,
        row.email,
        row.password_hash,
        row.nickname,
        row.avatar,
        row.age_group,
        row.bio ?? null,
        row.contact ?? null,
        row.contact_type ?? null,
        row.status,
        row.agreement_version,
        row.created_at ?? Date.now(),
        row.deleted_at
      );
    },
    getUserById(id) {
      return stmt.getUserById.get(id) as UserRow | undefined;
    },
    getUserByIdentity(provider, identifier) {
      return stmt.getUserByIdentity.get(provider, identifier) as UserRow | undefined;
    },
    updateUserProfile(id, patch) {
      // 只写调用方显式提供的列：值为 null 时清空（头像/简介/联系方式可被移除），
      // 未出现的列保持原值。列名来自固定白名单，值全部走占位符。
      const columns = ["nickname", "avatar", "age_group", "bio", "contact", "contact_type"] as const;
      const entries = columns
        .filter((column) => patch[column] !== undefined)
        .map((column) => [column, patch[column] ?? null] as const);
      if (entries.length === 0) return;
      const sql = `UPDATE users SET ${entries.map(([column]) => `${column} = ?`).join(", ")} WHERE id = ?`;
      db.prepare(sql).run(...entries.map(([, value]) => value), id);
    },
    updateUserPhone(id, phone) {
      stmt.updateUserPhone.run(phone, id);
    },
    insertIdentity(userId, provider, identifier, now) {
      stmt.insertIdentity.run(userId, provider, identifier, now, now);
    },
    listIdentities(userId) {
      return stmt.listIdentities.all(userId) as unknown as IdentityRow[];
    },
    countIdentities(userId) {
      const row = stmt.countIdentities.get(userId) as { n: number };
      return Number(row?.n ?? 0);
    },
    deleteIdentity(userId, provider) {
      stmt.deleteIdentity.run(userId, provider);
    },
    touchIdentity(provider, identifier, now) {
      stmt.touchIdentity.run(now, provider, identifier);
    },
    insertSession(row) {
      stmt.insertSession.run(
        row.session_id,
        row.user_id,
        row.device_fingerprint,
        row.ip,
        row.location,
        row.last_seen,
        row.created_at,
        row.expires_at,
        row.revoked_at,
        row.refresh_nonce ?? null
      );
    },
    getSession(sessionId) {
      return stmt.getSession.get(sessionId) as SessionRow | undefined;
    },
    revokeSession(sessionId, now) {
      stmt.revokeSession.run(now, sessionId);
    },
    touchSession(sessionId, now, ip) {
      stmt.touchSession.run(now, ip ?? null, sessionId);
    },
    rotateRefreshNonce(sessionId, nonce, prevExpiresAt) {
      stmt.rotateRefreshNonce.run(nonce, prevExpiresAt, sessionId);
    },
    getConsent(userId) {
      return stmt.getConsent.get(userId) as ConsentRow | undefined;
    },
    upsertConsent(userId, improvementEnabled, agreementVersion, now) {
      stmt.upsertConsent.run(userId, agreementVersion, improvementEnabled, now);
    },
    getLatestCode(phone, purpose) {
      return stmt.getLatestCode.get(phone, purpose) as VerificationCodeRow | undefined;
    },
    insertCode(row) {
      stmt.insertCode.run(row.phone, row.purpose, row.code_hash, row.expires_at, row.attempts, row.created_at, row.day);
    },
    incrementCodeAttempts(id) {
      stmt.incrementCodeAttempts.run(id);
    },
    countCodesToday(phone, day) {
      const row = stmt.countCodesToday.get(phone, day) as { n: number };
      return Number(row?.n ?? 0);
    },
    markCodeConsumed(id, now) {
      stmt.markCodeConsumed.run(now, id);
    },
    transaction(fn) {
      db.exec("BEGIN IMMEDIATE");
      try {
        fn();
        db.exec("COMMIT");
      } catch (err) {
        try {
          db.exec("ROLLBACK");
        } catch {
          // 回滚失败时保留原错误
        }
        throw err;
      }
    },
    rebindIdentityPhone(userId, newPhone, now) {
      stmt.rebindIdentityPhone.run(newPhone, now, userId);
    },
    clearUserPhone(userId) {
      stmt.clearUserPhone.run(userId);
    },
    insertAuditLog(row) {
      stmt.insertAuditLog.run(row.actor_id, row.action, row.detail, row.ip, row.at);
    },
  };
}

/** 以内存数据库创建一个实例（测试用） */
export function createInMemoryUserDb(): UserDb {
  return createUserDb(":memory:");
}
