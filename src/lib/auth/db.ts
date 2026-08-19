import { DatabaseSync } from "node:sqlite";
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
  revoked_at INTEGER
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
  day TEXT NOT NULL
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

export interface UserDb {
  close(): void;
  // users
  insertUser(row: Omit<UserRow, "created_at"> & { created_at?: number }): void;
  getUserById(id: string): UserRow | undefined;
  getUserByIdentity(provider: string, identifier: string): UserRow | undefined;
  updateUserProfile(id: string, patch: { nickname?: string; avatar?: string | null; age_group?: string | null }): void;
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
  // consents
  getConsent(userId: string): ConsentRow | undefined;
  upsertConsent(userId: string, improvementEnabled: number, agreementVersion: string | null, now: number): void;
  // verification codes
  getLatestCode(phone: string, purpose: string): VerificationCodeRow | undefined;
  insertCode(row: Omit<VerificationCodeRow, "id">): void;
  incrementCodeAttempts(id: number): void;
  countCodesToday(phone: string, day: string): number;
  deleteCode(id: number): void;
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
  const db = new DatabaseSync(dbPath);
  db.exec("PRAGMA journal_mode = WAL;");
  db.exec(SCHEMA);

  const stmt = {
    insertUser: db.prepare(
      `INSERT INTO users (id, phone, email, password_hash, nickname, avatar, age_group, status, agreement_version, created_at, deleted_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ),
    getUserById: db.prepare(`SELECT * FROM users WHERE id = ?`),
    getUserByIdentity: db.prepare(
      `SELECT u.* FROM users u
       JOIN user_identities i ON i.user_id = u.id
       WHERE i.provider = ? AND i.identifier = ?`
    ),
    updateUserProfile: db.prepare(
      `UPDATE users SET nickname = COALESCE(?, nickname), avatar = COALESCE(?, avatar), age_group = COALESCE(?, age_group) WHERE id = ?`
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
      `INSERT INTO user_sessions (session_id, user_id, device_fingerprint, ip, location, last_seen, created_at, expires_at, revoked_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ),
    getSession: db.prepare(`SELECT * FROM user_sessions WHERE session_id = ?`),
    revokeSession: db.prepare(`UPDATE user_sessions SET revoked_at = ? WHERE session_id = ?`),
    touchSession: db.prepare(`UPDATE user_sessions SET last_seen = ?, ip = COALESCE(?, ip) WHERE session_id = ?`),
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
    deleteCode: db.prepare(`DELETE FROM verification_codes WHERE id = ?`),
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
      stmt.updateUserProfile.run(patch.nickname ?? null, patch.avatar ?? null, patch.age_group ?? null, id);
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
        row.revoked_at
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
    deleteCode(id) {
      stmt.deleteCode.run(id);
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
