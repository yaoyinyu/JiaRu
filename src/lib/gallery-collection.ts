/**
 * 图库「我的收录」持久化层（IndexedDB，浏览器端专属）。
 *
 * 设计要点：
 * - 存储后端通过 GalleryCollectStore 接口注入，默认实现为原生 IndexedDB
 *   （单例，库名 jiaru-gallery / store collects / keyPath id）；
 *   SSR 或无 indexedDB 环境自动降级为 no-op store，绝不抛错。
 * - 不引入第三方依赖；原生 IndexedDB 适配层由浏览器冒烟验证，
 *   业务逻辑（记录结构、排序、增删清空）由注入式内存 store 单测覆盖。
 */

export type GalleryCollectSource = {
  /** 生成引擎标识（如 agnes / seedream-pro / seedream-lite），收录场景必填。 */
  engine: string;
  /** 生成时的用户提示词摘要。 */
  prompt: string;
};

export type GalleryCollectRecord = {
  id: string;
  /** 原始图片 Blob（浏览器内持久化，不经任何服务端）。 */
  blob: Blob;
  createdAt: number;
  source: GalleryCollectSource;
};

export interface GalleryCollectStore {
  put(record: GalleryCollectRecord): Promise<void>;
  get(id: string): Promise<GalleryCollectRecord | null>;
  getAll(): Promise<GalleryCollectRecord[]>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

const DB_NAME = "jiaru-gallery";
const DB_VERSION = 1;
const STORE_NAME = "collects";

/** SSR / 无 IndexedDB 环境的安全降级：全部为 no-op。 */
function createNoopCollectStore(): GalleryCollectStore {
  return {
    put: async () => {},
    get: async () => null,
    getAll: async () => [],
    delete: async () => {},
    clear: async () => {},
  };
}

/** 原生 IndexedDB 适配层；环境不支持时返回 null。 */
export function createIndexedDbCollectStore(
  factory: IDBFactory | undefined =
    typeof indexedDB === "undefined" ? undefined : indexedDB
): GalleryCollectStore | null {
  if (!factory) return null;
  const idbFactory: IDBFactory = factory;

  async function withStore<T>(
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => IDBRequest<T> | void
  ): Promise<T> {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const open = idbFactory.open(DB_NAME, DB_VERSION);
      open.onupgradeneeded = () => {
        const db = open.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: "id" });
        }
      };
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error ?? new Error("IndexedDB 打开失败"));
      open.onblocked = () => reject(new Error("IndexedDB 被其他连接阻塞"));
    });
    try {
      return await new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, mode);
        const store = tx.objectStore(STORE_NAME);
        const request = run(store);
        let result: T | undefined;
        if (request) {
          request.onsuccess = () => {
            result = request.result;
          };
          request.onerror = () => reject(request.error ?? new Error("IndexedDB 操作失败"));
        }
        tx.oncomplete = () => resolve(result as T);
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB 事务失败"));
        tx.onabort = () => reject(tx.error ?? new Error("IndexedDB 事务中止"));
      });
    } finally {
      db.close();
    }
  }

  return {
    async put(record) {
      await withStore<void>("readwrite", (store) => {
        store.put(record);
      });
    },
    async get(id) {
      const record = await withStore<GalleryCollectRecord | undefined>(
        "readonly",
        (store) => store.get(id) as IDBRequest<GalleryCollectRecord | undefined>
      );
      return record ?? null;
    },
    async getAll() {
      const records = await withStore<GalleryCollectRecord[]>(
        "readonly",
        (store) => store.getAll() as IDBRequest<GalleryCollectRecord[]>
      );
      return records ?? [];
    },
    async delete(id) {
      await withStore<void>("readwrite", (store) => {
        store.delete(id);
      });
    },
    async clear() {
      await withStore<void>("readwrite", (store) => {
        store.clear();
      });
    },
  };
}

let storeOverride: GalleryCollectStore | null | undefined;
let cachedDefault: GalleryCollectStore | null | undefined;

/** 取当前生效的收录 store：测试注入 > 原生 IndexedDB > no-op。 */
export function getCollectStore(): GalleryCollectStore {
  if (storeOverride) return storeOverride;
  if (cachedDefault === undefined) {
    cachedDefault = createIndexedDbCollectStore() ?? createNoopCollectStore();
  }
  const store = cachedDefault;
  return store ?? createNoopCollectStore();
}

/** 测试专用：注入/清除（传 undefined）store 覆盖。 */
export function setCollectStoreForTests(store: GalleryCollectStore | null): void {
  storeOverride = store;
  cachedDefault = undefined;
}

/** 生成记录 id；crypto.randomUUID 不可用时退化为时间戳 + 随机数。 */
function createRecordId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `collect-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** 收录一张图片：生成记录并持久化，返回完整记录（含 id 与创建时间）。 */
export async function addCollect(
  blob: Blob,
  source: GalleryCollectSource,
  store: GalleryCollectStore = getCollectStore()
): Promise<GalleryCollectRecord> {
  const record: GalleryCollectRecord = {
    id: createRecordId(),
    blob,
    createdAt: Date.now(),
    source: { ...source },
  };
  await store.put(record);
  return record;
}

/** 列出全部收录，按创建时间降序（最新在前）。 */
export async function listCollects(
  store: GalleryCollectStore = getCollectStore()
): Promise<GalleryCollectRecord[]> {
  const records = await store.getAll();
  return [...records].sort((a, b) => b.createdAt - a.createdAt);
}

/** 删除单条收录。 */
export async function deleteCollect(
  id: string,
  store: GalleryCollectStore = getCollectStore()
): Promise<void> {
  await store.delete(id);
}

/** 清空全部收录。 */
export async function clearCollects(
  store: GalleryCollectStore = getCollectStore()
): Promise<void> {
  await store.clear();
}
