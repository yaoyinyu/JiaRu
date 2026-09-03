import assert from "node:assert/strict";
import test from "node:test";

import {
  fileNameFromSrc,
  findGalleryLook,
  loadCollectReference,
  loadGalleryReference,
  loadReferenceFromParams,
} from "../src/lib/gallery-bridge.ts";
import {
  setCollectStoreForTests,
  type GalleryCollectRecord,
  type GalleryCollectStore,
} from "../src/lib/gallery-collection.ts";

/** 构造一个返回图片 Blob 的假 fetch。 */
function fakeFetch(
  handler: (url: string) => { ok: boolean; status?: number; blob: Blob } | null
): typeof fetch {
  const impl = (async (url: string | URL | Request) => {
    const outcome = handler(String(url));
    if (!outcome) {
      return new Response(null, { status: 404 });
    }
    return new Response(outcome.blob, { status: outcome.ok ? 200 : 500 });
  }) as unknown as typeof fetch;
  return impl;
}

const jpegBlob = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], { type: "image/jpeg" });

test("findGalleryLook 对空/非法/未知 id 返回 null", () => {
  assert.equal(findGalleryLook(null), null);
  assert.equal(findGalleryLook(undefined), null);
  assert.equal(findGalleryLook(""), null);
  assert.equal(findGalleryLook("abc"), null);
  assert.equal(findGalleryLook("0"), null);
  assert.equal(findGalleryLook("-1"), null);
  assert.equal(findGalleryLook("1.5"), null);
  assert.equal(findGalleryLook("999"), null);
});

test("findGalleryLook 对合法 id 返回对应款式", () => {
  const look = findGalleryLook("3");
  assert.ok(look);
  assert.equal(look.id, 3);
  assert.equal(look.name, "亮片闪粉");
});

test("fileNameFromSrc 从资源路径提取文件名", () => {
  assert.equal(fileNameFromSrc("/nail-gallery/ai-look-1.jpg"), "ai-look-1.jpg");
  assert.equal(fileNameFromSrc("/"), "gallery-image.jpg");
});

test("loadGalleryReference 正常路径返回图片 File 与款式信息", async () => {
  const ref = await loadGalleryReference("2", fakeFetch(() => ({ ok: true, blob: jpegBlob() })));
  assert.ok(ref);
  assert.equal(ref.file instanceof File, true);
  assert.equal(ref.file.name, "ai-look-2.jpg");
  assert.equal(ref.file.type, "image/jpeg");
  assert.equal(ref.name, "法式白边");
  assert.ok(ref.look);
  assert.equal(ref.collect, null);
});

test("loadGalleryReference 对非法 id 不发起请求直接返回 null", async () => {
  let called = false;
  const ref = await loadGalleryReference(
    "999",
    fakeFetch(() => {
      called = true;
      return { ok: true, blob: jpegBlob() };
    })
  );
  assert.equal(ref, null);
  assert.equal(called, false);
});

test("loadGalleryReference 对网络失败/非 2xx/非图片类型降级为 null", async () => {
  const throwing: typeof fetch = (() => Promise.reject(new Error("network down"))) as unknown as typeof fetch;
  assert.equal(await loadGalleryReference("1", throwing), null);

  const notFound = fakeFetch(() => null);
  assert.equal(await loadGalleryReference("1", notFound), null);

  const serverError = fakeFetch(() => ({ ok: false, blob: jpegBlob() }));
  assert.equal(await loadGalleryReference("1", serverError), null);

  const notImage = fakeFetch(() => ({ ok: true, blob: new Blob(["x"], { type: "text/plain" }) }));
  assert.equal(await loadGalleryReference("1", notImage), null);
});

test("loadCollectReference 从注入 store 返回收录 File", async () => {
  const record: GalleryCollectRecord = {
    id: "c-1",
    blob: jpegBlob(),
    createdAt: Date.now(),
    source: { engine: "agnes", prompt: "银色亮片" },
  };
  const store: GalleryCollectStore = {
    put: async () => {},
    get: async (id) => (id === "c-1" ? record : null),
    getAll: async () => [record],
    delete: async () => {},
    clear: async () => {},
  };
  setCollectStoreForTests(store);
  try {
    const ref = await loadCollectReference("c-1");
    assert.ok(ref);
    assert.equal(ref.file.type, "image/jpeg");
    assert.equal(ref.name, "我的收录");
    assert.equal(ref.look, null);
    assert.ok(ref.collect);
    assert.equal(ref.collect.source.engine, "agnes");

    assert.equal(await loadCollectReference("missing"), null);
    assert.equal(await loadCollectReference(null), null);
  } finally {
    setCollectStoreForTests(null);
  }
});

test("loadReferenceFromParams 优先 gallery，其次 collect，二者皆无返回 null", async () => {
  const ref = await loadReferenceFromParams(
    { gallery: "1" },
    fakeFetch(() => ({ ok: true, blob: jpegBlob() }))
  );
  assert.ok(ref);
  assert.equal(ref.name, "渐变裸粉");

  assert.equal(await loadReferenceFromParams({}, fakeFetch(() => ({ ok: true, blob: jpegBlob() }))), null);
  assert.equal(await loadReferenceFromParams({ gallery: "999" }, fakeFetch(() => null)), null);
});

test("loadReferenceFromParams 在 gallery 失败时回退 collect", async () => {
  const record: GalleryCollectRecord = {
    id: "c-2",
    blob: jpegBlob(),
    createdAt: Date.now(),
    source: { engine: "seedream-pro", prompt: "复古花纹" },
  };
  const store: GalleryCollectStore = {
    put: async () => {},
    get: async (id) => (id === "c-2" ? record : null),
    getAll: async () => [record],
    delete: async () => {},
    clear: async () => {},
  };
  setCollectStoreForTests(store);
  try {
    const ref = await loadReferenceFromParams(
      { gallery: "999", collect: "c-2" },
      fakeFetch(() => null)
    );
    assert.ok(ref);
    assert.equal(ref.collect?.id, "c-2");
  } finally {
    setCollectStoreForTests(null);
  }
});
