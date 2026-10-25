import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { createInMemoryUserDb, createUserDb } from "../src/lib/auth/db.ts";
import { createAuthService } from "../src/lib/auth/service.ts";
import { AuthError } from "../src/lib/auth/types.ts";
import {
  PROFILE_LIMITS,
  countChars,
  diffProfileFields,
  normalizeContactValue,
  parseAvatarDataUrl,
  toProfileInput,
  validateProfileInput,
} from "../src/lib/profile/profile.ts";

const SECRET = "test-secret-at-least-16-chars";

function makeAuth() {
  const db = createInMemoryUserDb();
  const auth = createAuthService(db, { jwtSecret: SECRET });
  return { db, auth };
}

function dataUrl(mime: string, bytes: number[]): string {
  return `data:image/${mime};base64,${Buffer.from(bytes).toString("base64")}`;
}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d];
const JPEG_SIGNATURE = [0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01];
const WEBP_SIGNATURE = [0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50];

// ── 字段校验 ──

test("nickname is required, length bounded and free of control characters", () => {
  assert.equal(validateProfileInput({ nickname: "  " }).errors.nickname, "请填写昵称");
  assert.equal(
    validateProfileInput({ nickname: "甲".repeat(PROFILE_LIMITS.nicknameMax + 1) }).errors.nickname,
    `昵称最多 ${PROFILE_LIMITS.nicknameMax} 个字符`
  );
  assert.equal(validateProfileInput({ nickname: "小美\n第二行" }).errors.nickname, "昵称不能包含换行或控制字符");
  const trimmed = validateProfileInput({ nickname: "  小美  " });
  assert.equal(trimmed.ok, true);
  assert.equal(trimmed.value.nickname, "小美");
});

test("nickname length counts code points so emoji take one slot each", () => {
  assert.equal(countChars("💅"), 1);
  const ok = validateProfileInput({ nickname: "💅".repeat(PROFILE_LIMITS.nicknameMax) });
  assert.equal(ok.ok, true);
  assert.ok(validateProfileInput({ nickname: "💅".repeat(PROFILE_LIMITS.nicknameMax + 1) }).errors.nickname);
});

test("bio is optional but bounded and trimmed", () => {
  assert.equal(validateProfileInput({ nickname: "小美", bio: "x".repeat(PROFILE_LIMITS.bioMax + 1) }).errors.bio,
    `简介最多 ${PROFILE_LIMITS.bioMax} 个字符`);
  const empty = validateProfileInput({ nickname: "小美", bio: "   " });
  assert.equal(empty.ok, true);
  assert.equal(empty.value.bio, "");
  assert.equal(validateProfileInput({ nickname: "小美", bio: " 爱奶咖色系 " }).value.bio, "爱奶咖色系");
});

test("contact value is validated per selected type", () => {
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "email", contact: "not-an-email" }).errors.contact,
    "请填写有效邮箱地址");
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "email", contact: "hi@jiaru.app" }).ok, true);

  assert.equal(validateProfileInput({ nickname: "小美", contactType: "phone", contact: "12345" }).errors.contact,
    "请填写 11 位手机号");
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "phone", contact: "13800138000" }).ok, true);

  assert.ok(validateProfileInput({ nickname: "小美", contactType: "wechat", contact: "1abc" }).errors.contact);
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "wechat", contact: "jiaru_nails" }).ok, true);

  assert.ok(validateProfileInput({ nickname: "小美", contactType: "other", contact: "x" }).errors.contact);
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "other", contact: "小红书 @甲如" }).ok, true);

  // 空联系方式视为不填写，不校验值格式
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "email", contact: "   " }).ok, true);
});

test("phone contact is normalized so +86 / spaces / dashes store the same number", () => {
  assert.equal(normalizeContactValue("phone", " +86 138-0013-8000 "), "13800138000");
  assert.equal(validateProfileInput({ nickname: "小美", contactType: "phone", contact: "+86 138 0013 8000" }).value.contact,
    "13800138000");
});

test("diffProfileFields only reports editable fields that changed", () => {
  const base = toProfileInput({ nickname: "小美", bio: null, contact: null, contactType: null });
  assert.deepEqual(diffProfileFields(base, { ...base }), []);
  assert.deepEqual(diffProfileFields(base, { ...base, nickname: "小美美" }), ["nickname"]);
  assert.deepEqual(diffProfileFields(base, { ...base, contact: "jiaru_nails" }), ["contact"]);
});

// ── 头像 Data URL ──

test("avatar accepts null (clear) and well-formed png/jpeg/webp", () => {
  assert.deepEqual(parseAvatarDataUrl(null), { ok: true, dataUrl: null });
  assert.deepEqual(parseAvatarDataUrl("   "), { ok: true, dataUrl: null });
  for (const [mime, bytes] of [
    ["png", PNG_SIGNATURE],
    ["jpeg", JPEG_SIGNATURE],
    ["webp", WEBP_SIGNATURE],
  ] as const) {
    const url = dataUrl(mime, bytes);
    const parsed = parseAvatarDataUrl(url);
    assert.equal(parsed.ok, true, `${mime} should be accepted`);
    assert.equal(parsed.ok && parsed.dataUrl, url);
  }
});

test("avatar rejects wrong mime, oversized payloads and signature mismatch", () => {
  const gif = `data:image/gif;base64,${Buffer.from([0x47, 0x49, 0x46, 0x38]).toString("base64")}`;
  assert.equal(parseAvatarDataUrl(gif).ok, false);

  const tooLarge = `data:image/png;base64,${Buffer.alloc(PROFILE_LIMITS.avatarMaxBytes + 1024).toString("base64")}`;
  const largeResult = parseAvatarDataUrl(tooLarge);
  assert.equal(largeResult.ok, false);
  assert.match(largeResult.ok ? "" : largeResult.error, /头像图片过大/);

  // 声明 png 实际是 jpeg 字节：签名不符，拒绝写入
  const spoofed = dataUrl("png", JPEG_SIGNATURE);
  const spoofedResult = parseAvatarDataUrl(spoofed);
  assert.equal(spoofedResult.ok, false);
  assert.match(spoofedResult.ok ? "" : spoofedResult.error, /内容与格式不一致/);

  assert.equal(parseAvatarDataUrl(123).ok, false);
  assert.equal(parseAvatarDataUrl("https://example.com/a.png").ok, false);
});

// ── 服务层 ──

test("updateProfile persists profile fields and getMe returns them", () => {
  const { auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-profile-fields", {});

  auth.updateProfile(user.id, {
    nickname: " 小美 ",
    bio: "偏爱奶咖色系短圆甲",
    contactType: "wechat",
    contact: "jiaru_nails",
    avatar: dataUrl("png", PNG_SIGNATURE),
  });

  const me = auth.getMe(user.id);
  assert.equal(me.user.nickname, "小美");
  assert.equal(me.user.bio, "偏爱奶咖色系短圆甲");
  assert.equal(me.user.contactType, "wechat");
  assert.equal(me.user.contact, "jiaru_nails");
  assert.match(me.user.avatar ?? "", /^data:image\/png;base64,/);
});

test("partial profile update keeps untouched fields", () => {
  const { auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-profile-partial", {});
  auth.updateProfile(user.id, { nickname: "小美", bio: "短圆甲爱好者", contactType: "email", contact: "hi@jiaru.app" });

  auth.updateProfile(user.id, { nickname: "小美美" });
  const me = auth.getMe(user.id);
  assert.equal(me.user.nickname, "小美美");
  assert.equal(me.user.bio, "短圆甲爱好者");
  assert.equal(me.user.contact, "hi@jiaru.app");
});

test("empty string clears bio and contact; null clears avatar", () => {
  const { auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-profile-clear", {});
  auth.updateProfile(user.id, {
    bio: "临时简介",
    contactType: "phone",
    contact: "13800138000",
    avatar: dataUrl("jpeg", JPEG_SIGNATURE),
  });

  auth.updateProfile(user.id, { bio: "", contact: "" });
  let me = auth.getMe(user.id);
  assert.equal(me.user.bio, null);
  assert.equal(me.user.contact, null);
  assert.equal(me.user.contactType, null);

  auth.updateProfile(user.id, { avatar: null });
  me = auth.getMe(user.id);
  assert.equal(me.user.avatar, null);
});

test("invalid profile input is rejected and nothing is written", () => {
  const { auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-profile-invalid", {});
  auth.updateProfile(user.id, { nickname: "原昵称", bio: "原简介" });

  assert.throws(() => auth.updateProfile(user.id, { nickname: "   " }), (err: unknown) => {
    assert.ok(err instanceof AuthError);
    assert.equal(err.message, "请填写昵称");
    assert.equal(err.status, 400);
    return true;
  });
  assert.throws(() => auth.updateProfile(user.id, { contactType: "email", contact: "abc" }), AuthError);
  assert.throws(() => auth.updateProfile(user.id, { contactType: "fax", contact: "anything" }), AuthError);
  assert.throws(() => auth.updateProfile(user.id, { avatar: "javascript:alert(1)" }), AuthError);
  assert.throws(() => auth.updateProfile(user.id, { bio: "x".repeat(PROFILE_LIMITS.bioMax + 1) }), AuthError);

  const me = auth.getMe(user.id);
  assert.equal(me.user.nickname, "原昵称");
  assert.equal(me.user.bio, "原简介");
  assert.equal(me.user.contact, null);
  assert.equal(me.user.avatar, null);
});

// ── 旧库迁移 ──

test("legacy database without profile columns is migrated in place", () => {
  const tmpRoot = mkdtempSync(path.join(tmpdir(), "jiaru-profile-db-"));
  try {
    const dbPath = path.join(tmpRoot, "legacy.db");
    const legacy = new DatabaseSync(dbPath);
    legacy.exec(`
      CREATE TABLE users (
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
      INSERT INTO users (id, phone, email, password_hash, nickname, avatar, age_group, status, agreement_version, created_at)
      VALUES ('u-legacy', '13800138000', NULL, NULL, '旧用户', NULL, NULL, 'active', NULL, 1700000000000);
    `);
    legacy.close();

    const db = createUserDb(dbPath);
    try {
      const user = db.getUserById("u-legacy");
      assert.ok(user);
      assert.equal(user?.bio ?? null, null);
      assert.equal(user?.contact ?? null, null);

      db.updateUserProfile("u-legacy", { bio: "迁移后简介", contact: "13800138000", contact_type: "phone" });
      const updated = db.getUserById("u-legacy");
      assert.equal(updated?.bio, "迁移后简介");
      assert.equal(updated?.contact, "13800138000");
      assert.equal(updated?.contact_type, "phone");

      db.updateUserProfile("u-legacy", { bio: null });
      assert.equal(db.getUserById("u-legacy")?.bio, null);
      // 未提供的列保持原值
      assert.equal(db.getUserById("u-legacy")?.contact, "13800138000");
    } finally {
      db.close();
    }
  } finally {
    rmSync(tmpRoot, { recursive: true, force: true });
  }
});
