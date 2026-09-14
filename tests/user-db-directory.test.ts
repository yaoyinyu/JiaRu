import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createUserDb } from "../src/lib/auth/db.ts";

test("createUserDb creates missing parent directories and opens the database", () => {
  const tmpRoot = mkdtempSync(path.join(tmpdir(), "jiaru-db-test-"));
  try {
    // 两层父目录都不存在（模拟干净克隆后 data/ 未创建）
    const dbPath = path.join(tmpRoot, "fresh-data", "nested", "jiaru-user.db");
    assert.equal(existsSync(dbPath), false);

    const db = createUserDb(dbPath);
    try {
      assert.equal(existsSync(dbPath), true, "database file should be created");
      // 数据库可用：写入并读回
      db.insertUser({
        id: "u-test-1",
        phone: "13800138000",
        email: null,
        password_hash: null,
        nickname: "测试",
        avatar: null,
        age_group: null,
        status: "active",
        agreement_version: null,
        deleted_at: null,
      });
      const user = db.getUserById("u-test-1");
      assert.ok(user, "inserted user should be readable");
      assert.equal(user?.nickname, "测试");
    } finally {
      db.close();
    }
  } finally {
    rmSync(tmpRoot, { recursive: true, force: true });
  }
});
