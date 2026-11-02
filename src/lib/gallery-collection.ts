/**
 * 图库「我的收录」持久化层（IndexedDB，浏览器端专属）。
 *
 * 设计要点：
 * - 存储后端通过 GalleryCollectStore 接口注入，默认实现为原生 IndexedDB
 *   （单例，库名 jiaru-gallery / store collects / keyPath id）。
 * - **读取路径**（listCollects）在 SSR 或无 indexedDB 环境降级为 no-op，
 *   返回空列表，绝不抛错。
 * - **写入路径**（addCollect / deleteCollect / clearCollects）在无可用
 *   IndexedDB 时抛出 CollectUnavailableError，绝不静默假成功；写入成功后
 *   还会回读验证，回读不到同样视为失败。
 * - probeCollectStorage() 供 UI 在展示「收录」能力前探测可用性。
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

/** 收录存储能力状态：UI 据此决定是否展示可收录入口。 */
export type CollectStorageStatus = "available" | "unavailable" | "checking" | "error";

/** 存储不可用的具体原因（用于分类用户提示）。 */
export type CollectUnavailableReason =
  | "indexed_db_missing"
  | "indexed_db_open_failed"
  | "storage_denied"
  | "quota_exceeded"
  | "unknown";

/** 写入路径在存储不可用/写入验证失败时抛出的错误。 */
export class CollectUnavailableError extends Error {
  readonly reason: CollectUnavailableReason;

  constructor(reason: CollectUnavailableReason, message?: string) {
    super(message ?? collectUnavailableMessage(reason));
    this.name = "CollectUnavailableError";
    this.reason = reason;
  }
}

/** 存储不可用原因对应的用户提示文案。 */
export function collectUnavailableMessage(reason: CollectUnavailableReason): string {
  switch (reason) {
    case "indexed_db_missing":
      return "当前浏览器不支持本地收藏";
    case "indexed_db_open_failed":
      return "本地收藏存储暂时无法打开，请重试";
    case "storage_denied":
      return "浏览器阻止了本地存储，请检查站点权限";
    case "quota_exceeded":
      return "本地存储空间不足，请删除部分收录";
    case "unknown":
      return "收录失败，请重试";
  }
}

/**
 * 把任意收录路径错误归类为用户提示文案：
 * 识别 CollectUnavailableError 与常见浏览器存储错误名，其余归为 unknown。
 */
export function collectErrorToMessage(err: unknown): string {
  if (err instanceof CollectUnavailableError) {
    return collectUnavailableMessage(err.reason);
  }
  const name = (err as { name?: string } | null)?.name ?? "";
  if (name === "QuotaExceededError" || name === "NS_ERROR_DOM_QUOTA_REACHED") {
    return collectUnavailableMessage("quota_exceeded");
  }
  if (name === "SecurityError") {
    return collectUnavailableMessage("storage_denied");
  }
  return collectUnavailableMessage("unknown");
}

const DB_NAME = "jiaru-gallery";
const DB_VERSION = 1;
const STORE_NAME = "collects";

/** SSR / 无 IndexedDB 环境的安全降级：全部为 no-op（仅用于读取路径）。 */
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

/** 取当前生效的收录 store（读取路径）：测试注入 > 原生 IndexedDB > no-op。 */
export function getCollectStore(): GalleryCollectStore {
  if (storeOverride) return storeOverride;
  if (cachedDefault === undefined) {
    cachedDefault = createIndexedDbCollectStore() ?? createNoopCollectStore();
  }
  const store = cachedDefault;
  return store ?? createNoopCollectStore();
}

/** 测试专用：注入/清除（传 null）store 覆盖。 */
export function setCollectStoreForTests(store: GalleryCollectStore | null): void {
  storeOverride = store;
  cachedDefault = undefined;
}

/** 探测当前浏览器是否支持本地收录（不写入任何数据，仅做一次空读）。 */
export async function probeCollectStorage(): Promise<CollectStorageStatus> {
  if (storeOverride) return "available";
  const store = createIndexedDbCollectStore();
  if (!store) return "unavailable";
  try {
    await store.get("__collect_probe__");
    return "available";
  } catch {
    return "unavailable";
  }
}

/**
 * 解析写入路径使用的 store：显式传入 > 测试注入 > 原生 IndexedDB。
 * 前两者皆无可用 IndexedDB 时抛出 CollectUnavailableError（不降级 no-op）。
 */
function resolveWriteStore(store?: GalleryCollectStore): GalleryCollectStore {
  if (store) return store;
  if (storeOverride) return storeOverride;
  const created = createIndexedDbCollectStore();
  if (!created) {
    throw new CollectUnavailableError("indexed_db_missing");
  }
  return created;
}

/** 生成记录 id；crypto.randomUUID 不可用时退化为时间戳 + 随机数。 */
function createRecordId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `collect-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * 收录一张图片：生成记录并持久化，返回完整记录（含 id 与创建时间）。
 * 存储不可用、写入失败或写入后回读不到时抛错——调用方不得把本函数
 * 失败当作收录成功。
 */
export async function addCollect(
  blob: Blob,
  source: GalleryCollectSource,
  store?: GalleryCollectStore
): Promise<GalleryCollectRecord> {
  const target = resolveWriteStore(store);
  const record: GalleryCollectRecord = {
    id: createRecordId(),
    blob,
    createdAt: Date.now(),
    source: { ...source },
  };
  await target.put(record);
  const verified = await target.get(record.id);
  if (!verified) {
    throw new CollectUnavailableError("unknown", "收录写入验证失败");
  }
  return record;
}

/** 列出全部收录，按创建时间降序（最新在前）。读取路径无存储时返回空。 */
export async function listCollects(
  store: GalleryCollectStore = getCollectStore()
): Promise<GalleryCollectRecord[]> {
  const records = await store.getAll();
  return [...records].sort((a, b) => b.createdAt - a.createdAt);
}

/** 删除单条收录。存储不可用时抛出 CollectUnavailableError。 */
export async function deleteCollect(
  id: string,
  store?: GalleryCollectStore
): Promise<void> {
  await resolveWriteStore(store).delete(id);
}

/** 清空全部收录。存储不可用时抛出 CollectUnavailableError。 */
export async function clearCollects(store?: GalleryCollectStore): Promise<void> {
  await resolveWriteStore(store).clear();
}
