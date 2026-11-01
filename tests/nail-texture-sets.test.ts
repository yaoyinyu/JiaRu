import assert from "node:assert/strict";
import test from "node:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

import {
  NAIL_TEXTURE_SETS,
  closestTextureSet,
  parseHexColor,
  textureSrcFor,
} from "../src/lib/nail-texture-sets.ts";

/**
 * 编辑器纹理套装清单完整性（v1.2.176 资产登记回归）：
 *  - 每套 5 指齐全（0–4 无重复）、id 可作目录名、主色可解析；
 *  - public 纹理文件真实存在（public 目录按 process.cwd() 解析）；
 *  - closestTextureSet 灵感色映射（最近主色）与空清单/非法 hex 兜底；
 *  - textureSrcFor 指位查找。
 */

test("清单：每套 5 指齐全且 id/主色合法", () => {
  assert.ok(NAIL_TEXTURE_SETS.length > 0, "NAIL_TEXTURE_SETS 不应为空（资产已登记）");
  const ids = new Set<string>();
  for (const set of NAIL_TEXTURE_SETS) {
    assert.ok(set.id.length > 0, "套装 id 非空");
    assert.match(set.id, /^[a-z0-9-]+$/, `套装 id 仅限目录名字符：${set.id}`);
    assert.ok(!ids.has(set.id), `套装 id 重复：${set.id}`);
    ids.add(set.id);
    assert.ok(set.name.length > 0, `${set.id} 缺中文名`);
    assert.ok(set.source.length > 0, `${set.id} 缺来源说明`);
    assert.ok(parseHexColor(set.dominantColor), `${set.id} 主色非法：${set.dominantColor}`);
    const fingers = set.textures.map((item) => item.finger);
    assert.deepEqual([...fingers].sort(), [0, 1, 2, 3, 4], `${set.id} 五指不齐`);
    const srcs = new Set(set.textures.map((item) => item.src));
    assert.equal(srcs.size, 5, `${set.id} 纹理路径重复`);
  }
});

test("清单：public 纹理文件真实存在", () => {
  for (const set of NAIL_TEXTURE_SETS) {
    for (const texture of set.textures) {
      assert.match(texture.src, /^\/nail-textures\//, `src 应以 /nail-textures/ 开头：${texture.src}`);
      const file = join(process.cwd(), "public", texture.src.replace(/^\//, ""));
      assert.ok(existsSync(file), `public 缺少纹理文件：${texture.src}`);
    }
  }
});

test("closestTextureSet：返回最接近主色的套装", () => {
  if (NAIL_TEXTURE_SETS.length === 0) return;
  const target = NAIL_TEXTURE_SETS[0];
  // 精确命中某套主色时必然返回该套（自距离 0 最小）
  assert.equal(closestTextureSet(target.dominantColor)!.id, target.id);
});

test("closestTextureSet：空清单与非法 hex 兜底为 null", () => {
  // 非法 hex 直接 null（清单非空也不应抛错）
  assert.equal(closestTextureSet("not-a-color"), null);
  assert.equal(closestTextureSet(""), null);
  assert.equal(closestTextureSet("#12345"), null);
});

test("textureSrcFor：命中指位返回纹理，缺失返回 null", () => {
  const set = NAIL_TEXTURE_SETS[0];
  if (!set) return;
  const thumb = textureSrcFor(set, 0);
  assert.ok(thumb, "拇指纹理应存在");
  assert.equal(thumb!.finger, 0);
  const missing = textureSrcFor(set, 9);
  assert.equal(missing, null);
});
