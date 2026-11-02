import assert from "node:assert/strict";
import test from "node:test";

import {
  createAsyncTaskRunner,
  isAbortError,
  type AsyncTaskRunner,
  type AsyncTaskSettle,
  type AsyncTaskStatus,
} from "../src/lib/async-task.ts";

/**
 * 统一异步任务状态机竞态合同（frontend-interaction-redesign-plan §2.2 / §10.1）。
 * 语义决策见 src/lib/async-task.ts 文件头「竞态语义合同」，此处逐条冻结：
 *  a) run → cancel → promise reject AbortError ⇒ cancelled（取消不算失败）；
 *  b) run → cancel → promise 仍 resolve ⇒ cancelled（迟到结果丢弃）；
 *     对照：任务先成功后 cancel() 不追认，仍为 success；
 *  c) running 中重复 run 被拒（单飞，{ ok: false, reason: "already-running" }）；
 *  d) dispose 后 settle 不外露（promise 以 cancelled 收尾，状态冻结，run 被拒）；
 *  e) error 不 reject（同步抛错与 promise reject 同途归入 error 结算）；
 *  f) 成功路径带值（含 startedAt/finishedAt/activeKey 收尾）。
 * 另冻结：isAbortError 双条件、自定义取消原因透传、reset/cancel no-op 与状态迁移序列。
 */

/** 手动控制时序的 pending promise */
interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** 构造一个已 abort 的信号 */
function abortedSignal(): AbortSignal {
  const controller = new AbortController();
  controller.abort();
  return controller.signal;
}

/** 典型可取消任务：abort 时透传 signal.reason（等价 signal.throwIfAborted / fetch 行为） */
function abortAwarePromise<T>(signal: AbortSignal): Promise<T> {
  return new Promise<T>((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason));
  });
}

test("f) 成功路径：结算带值，状态含 startedAt/finishedAt，activeKey 收尾清空", async () => {
  const runner = createAsyncTaskRunner<string>();
  assert.equal(runner.getStatus(), "idle");
  assert.equal(runner.getActiveKey(), null);

  const start = runner.run(() => Promise.resolve("生成结果"), { key: "ai-generate" });
  assert.ok(start.ok, "run 必须成功启动");
  assert.equal(runner.getStatus(), "running");
  assert.equal(runner.isRunning(), true);
  assert.equal(runner.getActiveKey(), "ai-generate");

  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "success", value: "生成结果" });

  assert.equal(runner.getStatus(), "success");
  assert.equal(runner.isRunning(), false);
  assert.equal(runner.getActiveKey(), null);
  const state = runner.getState();
  assert.equal(state.status, "success");
  assert.equal(state.value, "生成结果");
  assert.equal(typeof state.startedAt, "number");
  assert.equal(typeof state.finishedAt, "number");
  assert.ok((state.finishedAt ?? 0) >= (state.startedAt ?? 0));
  assert.equal(state.error, undefined);
});

test("e) 错误路径：promise reject 不向外抛出，结算为 error 且状态记录原因", async () => {
  const runner = createAsyncTaskRunner<number>();
  const boom = new Error("生成失败");
  const start = runner.run(() => Promise.reject<number>(boom));
  assert.ok(start.ok);

  const outcome = await start.result; // 若实现误用 reject，此行将抛出并使测试失败
  assert.deepEqual(outcome, { status: "error", error: boom });

  const state = runner.getState();
  assert.equal(state.status, "error");
  assert.equal(state.error, boom);
  assert.equal(state.value, undefined);
});

test("e) 错误路径：fn 同步抛错同样归入 error，run 的 promise 永不 reject", async () => {
  const runner = createAsyncTaskRunner<string>();
  const boom = new Error("同步失败");
  const start = runner.run(() => {
    throw boom;
  });
  assert.ok(start.ok);
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "error", error: boom });
  assert.equal(runner.getStatus(), "error");
});

test("a) run → cancel → promise 因 AbortError 结束 ⇒ cancelled（取消不算失败）", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run((signal) => abortAwarePromise<string>(signal));
  assert.ok(start.ok);
  assert.equal(runner.getStatus(), "running");

  runner.cancel();
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "cancelled" });

  const state = runner.getState();
  assert.equal(state.status, "cancelled");
  assert.equal(state.error, undefined);
  assert.equal(runner.isRunning(), false);
});

test("b) run → cancel → promise 仍正常 resolve ⇒ cancelled（迟到的成功结果丢弃）", async () => {
  const runner = createAsyncTaskRunner<string>();
  const deferred = createDeferred<string>();
  const start = runner.run(() => deferred.promise);
  assert.ok(start.ok);

  runner.cancel(); // abort 先行
  deferred.resolve("迟到的成功"); // 任务未监听 signal，仍以成功收尾

  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "cancelled" });
  const state = runner.getState();
  assert.equal(state.status, "cancelled");
  assert.equal(state.value, undefined);
});

test("b) 对照：任务已成功完成后再 cancel() 不追认为取消，状态保持 success", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run(() => Promise.resolve("已交付"));
  assert.ok(start.ok);
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "success", value: "已交付" });

  runner.cancel(); // 无在飞任务：不得改写已结算状态
  assert.equal(runner.getStatus(), "success");
  assert.equal(runner.getState().value, "已交付");
});

test("b) cancel() 先行、任务透传自定义 signal.reason（throwIfAborted 风格）⇒ cancelled", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run((signal) => abortAwarePromise<string>(signal));
  assert.ok(start.ok);

  runner.cancel("用户主动取消");
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "cancelled" });
  assert.equal(runner.getStatus(), "cancelled");
});

test("b) cancel() 先行、任务以非 AbortError 异常结束 ⇒ 仍按 error 保留真实失败原因", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run(
    (signal) =>
      new Promise<string>((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          setTimeout(() => reject(new Error("网络错误")), 0);
        });
      })
  );
  assert.ok(start.ok);

  runner.cancel();
  const outcome: AsyncTaskSettle<string> = await start.result;
  assert.equal(outcome.status, "error");
  if (outcome.status === "error") {
    assert.ok(outcome.error instanceof Error && outcome.error.message === "网络错误");
  }
  assert.equal(runner.getStatus(), "error");
});

test("c) 单飞：running 中重复 run 被拒且不影响首个任务，结算后可再次启动", async () => {
  const runner = createAsyncTaskRunner<string>();
  const deferred = createDeferred<string>();
  const first = runner.run(() => deferred.promise, { key: "first" });
  assert.ok(first.ok);

  const second = runner.run(() => Promise.resolve("不该执行"));
  assert.ok(!second.ok, "running 中重复 run 必须被拒绝");
  if (!second.ok) assert.equal(second.reason, "already-running");
  assert.equal(runner.getActiveKey(), "first");

  deferred.resolve("首个任务结果");
  const firstOutcome = await first.result;
  assert.deepEqual(firstOutcome, { status: "success", value: "首个任务结果" });

  const third = runner.run(() => Promise.resolve("再次启动"));
  assert.ok(third.ok);
  const thirdOutcome = await third.result;
  assert.deepEqual(thirdOutcome, { status: "success", value: "再次启动" });
});

test("d) dispose：在飞任务被 abort，状态定格 cancelled，run 从此被拒", async () => {
  const runner = createAsyncTaskRunner<string>();
  let observedSignal: AbortSignal | null = null;
  const deferred = createDeferred<string>();
  const start = runner.run((signal) => {
    observedSignal = signal;
    return deferred.promise;
  });
  assert.ok(start.ok);

  runner.dispose();
  assert.equal(runner.isDisposed(), true);
  assert.equal(runner.getStatus(), "cancelled");
  assert.ok(observedSignal !== null && observedSignal.aborted, "dispose 必须 abort 在飞任务");

  const refused = runner.run(() => Promise.resolve("不该启动"));
  assert.ok(!refused.ok, "dispose 后 run 必须被拒绝");
  if (!refused.ok) assert.equal(refused.reason, "disposed");
});

test("d) dispose 后 settle 不外露：迟到 resolve 只以 cancelled 收尾，状态不被改写", async () => {
  const runner = createAsyncTaskRunner<string>();
  const deferred = createDeferred<string>();
  const start = runner.run(() => deferred.promise);
  assert.ok(start.ok);

  runner.dispose();
  deferred.resolve("不该外露的结果");
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "cancelled" });

  const state = runner.getState();
  assert.equal(state.status, "cancelled");
  assert.equal(state.value, undefined);
  assert.equal(state.error, undefined);
});

test("d) dispose 后 settle 不外露：迟到 reject 同样只以 cancelled 收尾", async () => {
  const runner = createAsyncTaskRunner<string>();
  const deferred = createDeferred<string>();
  const start = runner.run(() => deferred.promise);
  assert.ok(start.ok);

  runner.dispose();
  deferred.reject(new Error("不该外露的失败"));
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "cancelled" });
  assert.equal(runner.getState().status, "cancelled");
});

test("双条件防冒充：信号未 abort 时任务自行抛 AbortError ⇒ error 而非 cancelled", async () => {
  const runner = createAsyncTaskRunner<string>();
  const impostor = new DOMException("内部控制器中止", "AbortError");
  const start = runner.run(() => Promise.reject<string>(impostor));
  assert.ok(start.ok);

  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "error", error: impostor });
  assert.equal(runner.getStatus(), "error");
});

test("isAbortError 双条件：signal.aborted 与 AbortError 名必须同时成立", () => {
  const liveController = new AbortController();
  const notAborted = liveController.signal;
  const aborted = abortedSignal();

  assert.equal(isAbortError(new DOMException("中止", "AbortError"), aborted), true);
  assert.equal(isAbortError(new DOMException("未中止的 AbortError", "AbortError"), notAborted), false);
  assert.equal(isAbortError(new Error("普通错误"), aborted), false);
  assert.equal(isAbortError(undefined, aborted), false);
  assert.equal(isAbortError("字符串错误", aborted), false);
});

test("reset：running 中为 no-op；结算后回到 idle 并清空产物与时间戳；idle 上 cancel 是 no-op", async () => {
  const runner = createAsyncTaskRunner<string>();
  const deferred = createDeferred<string>();
  const start = runner.run(() => deferred.promise);
  assert.ok(start.ok);

  runner.reset(); // running 中必须被忽略，避免「状态 idle 却仍有在飞任务」
  assert.equal(runner.getStatus(), "running");

  deferred.resolve("ok");
  await start.result;

  runner.reset();
  assert.deepEqual(runner.getState(), { status: "idle" });
  assert.equal(runner.getActiveKey(), null);

  runner.cancel(); // idle 上取消是 no-op
  assert.equal(runner.getStatus(), "idle");
});

test("reset：error 结算后 reset 清空 error，快照回到纯 idle", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run(() => Promise.reject<string>(new Error("失败")));
  assert.ok(start.ok);
  await start.result;
  assert.equal(runner.getStatus(), "error");

  runner.reset();
  assert.deepEqual(runner.getState(), { status: "idle" });
});

test("状态迁移序列：idle → running → success", async () => {
  const runner = createAsyncTaskRunner<number>();
  const seen: AsyncTaskStatus[] = [runner.getStatus()];
  const start = runner.run(() => Promise.resolve(42));
  assert.ok(start.ok);
  seen.push(runner.getStatus());
  const outcome = await start.result;
  seen.push(runner.getStatus());
  assert.deepEqual(outcome, { status: "success", value: 42 });
  assert.deepEqual(seen, ["idle", "running", "success"]);
});

test("状态迁移序列：idle → running → cancelled", async () => {
  const runner = createAsyncTaskRunner<string>();
  const seen: AsyncTaskStatus[] = [runner.getStatus()];
  const start = runner.run((signal) => abortAwarePromise<string>(signal));
  assert.ok(start.ok);
  seen.push(runner.getStatus());
  runner.cancel();
  await start.result;
  seen.push(runner.getStatus());
  assert.deepEqual(seen, ["idle", "running", "cancelled"]);
});

test("状态迁移序列：idle → running → error", async () => {
  const runner = createAsyncTaskRunner<string>();
  const seen: AsyncTaskStatus[] = [runner.getStatus()];
  const start = runner.run(() => Promise.reject<string>(new Error("失败")));
  assert.ok(start.ok);
  seen.push(runner.getStatus());
  await start.result;
  seen.push(runner.getStatus());
  assert.deepEqual(seen, ["idle", "running", "error"]);
});

test("cancel 幂等：多次 cancel 不产生额外结算或状态抖动", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run((signal) => abortAwarePromise<string>(signal));
  assert.ok(start.ok);
  runner.cancel();
  runner.cancel("重复取消");
  const outcome = await start.result;
  assert.deepEqual(outcome, { status: "cancelled" });
  assert.equal(runner.getStatus(), "cancelled");
});

test("快照隔离：getState 返回副本，外部改写不影响内部状态机", async () => {
  const runner = createAsyncTaskRunner<string>();
  const start = runner.run(() => Promise.resolve("结果"));
  assert.ok(start.ok);
  await start.result;

  const snapshot = runner.getState();
  snapshot.status = "idle";
  snapshot.value = "被篡改";
  assert.equal(runner.getStatus(), "success");
  assert.equal(runner.getState().value, "结果");
});

test("导出合同：runner 接口完整（run/cancel/getStatus/getState/getActiveKey/isRunning/isDisposed/reset/dispose）", () => {
  const runner: AsyncTaskRunner<unknown> = createAsyncTaskRunner();
  for (const method of [
    "run",
    "cancel",
    "getStatus",
    "getState",
    "getActiveKey",
    "isRunning",
    "isDisposed",
    "reset",
    "dispose",
  ] as const) {
    assert.equal(typeof runner[method], "function", `缺少方法 ${method}`);
  }
});
