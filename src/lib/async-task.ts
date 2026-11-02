/**
 * 统一异步任务状态机核心（frontend-interaction-redesign-plan §2.2 `useAsyncTask`）。
 *
 * 与 React 完全解耦的控制器工厂，供 `src/lib/use-async-task.ts` 消费，也可独立复用。
 *
 * 竞态语义合同（实现与测试均按此冻结）：
 *
 * 1. 单飞：同一时刻只允许一个 `run`。running 中再次 `run` 不抛错、不并发执行，
 *    返回 `{ ok: false, reason: "already-running" }`；dispose 后再次 `run`
 *    返回 `{ ok: false, reason: "disposed" }`。
 * 2. 结算永不 reject：`run` 返回的 promise 恒以 `AsyncTaskSettle` resolve
 *    （success / cancelled / error 三态），调用方统一按 `status` 分支处理。
 *    fn 同步抛错也归入 error 结算。
 * 3. 取消不算失败，但取消以 settle 先后为准：
 *    - 任务先 settle 成功、之后才 `cancel()`：不追认，状态保持 success
 *      （即「abort 发生时若任务已成功完成则仍算 success」）；
 *    - `cancel()` 先行（signal.aborted）：之后任务即使正常 resolve，
 *      迟到的结果也一律丢弃并结算为 cancelled（不得向已取消的界面回灌成功）；
 *      任务按约定 reject `signal.reason`（含自定义原因，如 `signal.throwIfAborted()`）
 *      或抛出 AbortError 时同样结算为 cancelled；
 *    - `cancel()` 先行、任务却以非 AbortError 的异常结束：仍按 error 结算，
 *      保留真实失败原因（任务实现应在收到 abort 后透传 `signal.reason`）；
 *    - 信号未 abort 时任务自行抛出的 AbortError（内部控制器泄漏冒充取消）按 error 结算：
 *      判定走 `isAbortError` 的「signal.aborted + DOMException/Error 名为 AbortError」双条件。
 * 4. cancel 不强制结算：`cancel()` 只触发 abort，结算仍以任务 promise 的最终走向为准。
 *    任务必须监听 signal 并及时结束，否则状态停留 running。
 * 5. 卸载安全：`dispose()` 立即 abort 在飞任务、状态定格为 cancelled 并冻结；
 *    此后所有 settle 一律不外露——run 的 promise 以 `{ status: "cancelled" }` 收尾，
 *    真实成功值/错误不再进入状态机，`run`/`reset` 均被拒绝或忽略。
 * 6. reset 只在非 running 时生效（必须先 cancel），避免「状态 idle 却仍有在飞任务」的谎报。
 *
 * `opts.key` 仅为可选元数据（`getActiveKey()` 可读），供调用方做同 key 防重复提交的
 * UI 提示；并发防护由单飞机制统一提供，不按 key 区分。
 */

export type AsyncTaskStatus = "idle" | "running" | "cancelled" | "error" | "success";

export interface AsyncTaskState<T = unknown> {
  status: AsyncTaskStatus;
  /** 仅当 status === "error" 时存在的失败原因（unknown，由调用方自行窄化） */
  error?: unknown;
  startedAt?: number;
  finishedAt?: number;
  /** 仅当 status === "success" 时存在的产物快照，供 Hook 透出（方案 §6.3「保留上一版结果」消费） */
  value?: T;
}

export interface AsyncTaskRunOptions {
  /** 可选任务键：running 期间可经 `getActiveKey()` 读取，settle 后清空 */
  key?: string;
}

/** 任务结算结果：run 的 promise 永不 reject，恒以此三态之一 resolve */
export type AsyncTaskSettle<T> =
  | { status: "success"; value: T }
  | { status: "cancelled" }
  | { status: "error"; error: unknown };

/** run() 的启动结果：拒绝并发/已销毁时不抛错、不执行任务，返回 `{ ok: false, reason }` */
export type AsyncTaskRunStart<T> =
  | { ok: true; result: Promise<AsyncTaskSettle<T>> }
  | { ok: false; reason: "already-running" | "disposed" };

export interface AsyncTaskRunner<T> {
  /** 启动任务（单飞）。fn 收到的 AbortSignal 即本次任务的取消令牌 */
  run(
    fn: (signal: AbortSignal) => Promise<T>,
    opts?: AsyncTaskRunOptions
  ): AsyncTaskRunStart<T>;
  /** 中止当前任务（可选自定义原因）；无在飞任务时为 no-op */
  cancel(reason?: unknown): void;
  getStatus(): AsyncTaskStatus;
  /** 状态快照（每次返回新对象，外部改写不影响内部状态机） */
  getState(): AsyncTaskState<T>;
  /** running 期间返回本次 run 的 key，其余时刻返回 null */
  getActiveKey(): string | null;
  isRunning(): boolean;
  isDisposed(): boolean;
  /** 回到 idle 并清空 error/value/时间戳；running 中为 no-op（必须先 cancel） */
  reset(): void;
  /** 卸载安全：abort 在飞任务并冻结状态机，此后所有 settle 不外露（见文件头合同 5） */
  dispose(): void;
}

/**
 * 判定一次 rejection 是否属于「本次取消」造成的 AbortError。
 * 双条件合同：① 信号确实已被 abort（排除任务内部自行 AbortError 冒充取消）；
 * ② 错误名为 AbortError（DOMException / Error 的 name 属性）。
 */
export function isAbortError(error: unknown, signal: AbortSignal): boolean {
  if (!signal.aborted) return false;
  if (typeof error !== "object" || error === null) return false;
  const name: unknown = (error as { name?: unknown }).name;
  return typeof name === "string" && name === "AbortError";
}

export function createAsyncTaskRunner<T>(): AsyncTaskRunner<T> {
  let status: AsyncTaskStatus = "idle";
  let startedAt: number | undefined;
  let finishedAt: number | undefined;
  let lastError: unknown;
  let value: T | undefined;
  let controller: AbortController | null = null;
  let activeKey: string | null = null;
  let disposed = false;

  const snapshotState = (): AsyncTaskState<T> => {
    const state: AsyncTaskState<T> = { status };
    if (startedAt !== undefined) state.startedAt = startedAt;
    if (finishedAt !== undefined) state.finishedAt = finishedAt;
    if (status === "error") state.error = lastError;
    if (status === "success") state.value = value;
    return state;
  };

  const markSettled = (
    next: Exclude<AsyncTaskStatus, "idle" | "running">,
    error?: unknown,
    settledValue?: T
  ): void => {
    status = next;
    finishedAt = Date.now();
    lastError = error;
    value = settledValue;
    controller = null;
    activeKey = null;
  };

  const run = (
    fn: (signal: AbortSignal) => Promise<T>,
    opts?: AsyncTaskRunOptions
  ): AsyncTaskRunStart<T> => {
    if (disposed) return { ok: false, reason: "disposed" };
    if (status === "running") return { ok: false, reason: "already-running" };

    const ac = new AbortController();
    controller = ac;
    activeKey = opts?.key ?? null;
    status = "running";
    startedAt = Date.now();
    finishedAt = undefined;
    lastError = undefined;
    value = undefined;

    let resolveOutcome!: (settle: AsyncTaskSettle<T>) => void;
    const outcome = new Promise<AsyncTaskSettle<T>>((resolve) => {
      resolveOutcome = resolve;
    });

    let inner: Promise<T>;
    try {
      inner = Promise.resolve(fn(ac.signal));
    } catch (syncError) {
      // fn 同步抛错与 promise reject 同途：归入 error 结算，run 永不 reject
      inner = Promise.reject(syncError);
    }

    void inner.then(
      (fulfilled) => {
        if (disposed) {
          // 卸载后 settle：真实值不外露，promise 以 cancelled 收尾，状态保持冻结
          resolveOutcome({ status: "cancelled" });
          return;
        }
        if (ac.signal.aborted) {
          // 取消先于结算发生：迟到的正常结果一律按取消丢弃（合同 3）
          markSettled("cancelled");
          resolveOutcome({ status: "cancelled" });
          return;
        }
        markSettled("success", undefined, fulfilled);
        resolveOutcome({ status: "success", value: fulfilled });
      },
      (reason) => {
        if (disposed) {
          resolveOutcome({ status: "cancelled" });
          return;
        }
        if (
          ac.signal.aborted &&
          (reason === ac.signal.reason || isAbortError(reason, ac.signal))
        ) {
          // 任务透传 signal.reason（含自定义取消原因）或抛 AbortError：取消不算失败
          markSettled("cancelled");
          resolveOutcome({ status: "cancelled" });
          return;
        }
        markSettled("error", reason);
        resolveOutcome({ status: "error", error: reason });
      }
    );

    return { ok: true, result: outcome };
  };

  const cancel = (reason?: unknown): void => {
    if (disposed || status !== "running") return;
    controller?.abort(reason);
  };

  const reset = (): void => {
    if (disposed || status === "running") return;
    status = "idle";
    startedAt = undefined;
    finishedAt = undefined;
    lastError = undefined;
    value = undefined;
  };

  const dispose = (): void => {
    if (disposed) return;
    disposed = true;
    if (status === "running") {
      // 卸载安全：中止在飞任务并定格状态；后续 settle 一律不外露（合同 5）
      controller?.abort();
      status = "cancelled";
      finishedAt = Date.now();
      activeKey = null;
      controller = null;
    }
  };

  return {
    run,
    cancel,
    getStatus: () => status,
    getState: snapshotState,
    getActiveKey: () => activeKey,
    isRunning: () => status === "running",
    isDisposed: () => disposed,
    reset,
    dispose,
  };
}
