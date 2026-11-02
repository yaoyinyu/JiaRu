"use client";

/**
 * `useAsyncTask`：统一异步任务 Hook（frontend-interaction-redesign-plan §2.2）。
 *
 * `src/lib/async-task.ts` 状态机的 React 薄封装，本文件不写任何业务：
 * - `run` / `cancel` / `reset` 直接委托 runner 实例（单飞、取消不算失败、结算永不
 *   reject 等竞态语义全部由 runner 合同保证，见 async-task.ts 文件头）；
 * - 卸载安全：`useEffect` 卸载时 `dispose()`，此后 runner 的 settle 不再写入本组件
 *   state（`isDisposed()` 守卫）；
 * - runner 以 `useState` 惰性工厂创建：每个组件实例独享一个，StrictMode 的
 *   「卸载 → 重挂」天然得到全新 runner，无需任何重建分支，也不在渲染期读 ref。
 */

import { useCallback, useEffect, useState } from "react";
import {
  createAsyncTaskRunner,
  type AsyncTaskRunOptions,
  type AsyncTaskRunStart,
  type AsyncTaskRunner,
  type AsyncTaskState,
} from "@/lib/async-task";

export interface UseAsyncTaskReturn<T> {
  /** 当前任务状态快照（success 时含产物 value，error 时含原因 error） */
  state: AsyncTaskState<T>;
  /** 启动任务（单飞）：running 中再调返回 `{ ok: false, reason: "already-running" }` */
  run: (
    fn: (signal: AbortSignal) => Promise<T>,
    opts?: AsyncTaskRunOptions
  ) => AsyncTaskRunStart<T>;
  /** 取消当前任务（取消不算失败，结算仍以任务 promise 走向为准） */
  cancel: (reason?: unknown) => void;
  /** 回到 idle（running 中为 no-op，必须先 cancel） */
  reset: () => void;
  isRunning: boolean;
}

export function useAsyncTask<T>(): UseAsyncTaskReturn<T> {
  const [runner] = useState<AsyncTaskRunner<T>>(() => createAsyncTaskRunner<T>());
  const [state, setState] = useState<AsyncTaskState<T>>(() => runner.getState());

  useEffect(() => {
    return () => {
      // 卸载安全：dispose 后 settle 一律不外露，不会写入已卸载组件的 state
      runner.dispose();
    };
  }, [runner]);

  const run = useCallback<UseAsyncTaskReturn<T>["run"]>(
    (fn, opts) => {
      const start = runner.run(fn, opts);
      if (start.ok) {
        void start.result.then(() => {
          // dispose（含卸载）之后不再应用任何结算结果
          if (runner.isDisposed()) return;
          setState(runner.getState());
        });
      }
      return start;
    },
    [runner]
  );

  const cancel = useCallback(
    (reason?: unknown) => {
      runner.cancel(reason);
    },
    [runner]
  );

  const reset = useCallback(() => {
    runner.reset();
    setState(runner.getState());
  }, [runner]);

  return { state, run, cancel, reset, isRunning: state.status === "running" };
}
