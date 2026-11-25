/**
 * 切后台兜底看门狗。
 *
 * 部分安卓浏览器（实测 PA2373 Edge）在应用切后台时不派发 visibilitychange，
 * 页面仍报告 visible、定时器照常运行，但视频帧呈现（rVFC）随合成器停摆，
 * 跟踪与贴图随之冻结。隐私契约要求离开画面即停用摄像头，这里用定时器周期
 * 检查「距最近一次跟踪结果的时间」：超过 stallMs 即判定页面曾被后台挂起
 * （或熄屏），触发一次停用回调。正常前台运行时跟踪结果约 30fps 持续更新，
 * 不会误触发；主线程短暂卡顿远小于 stallMs 阈值。
 */
/** 判定后台停摆的活动间隔阈值（毫秒）。 */
export const AR_BACKGROUND_STALL_MS = 5000;

export interface BackgroundWatchdogOptions {
  /** 检测到停摆时调用一次（随后看门狗自行停用）。 */
  onStall: () => void;
  /** 返回最近一次前台活动（跟踪结果）的 performance.now() 时间戳。 */
  lastActivity: () => number;
  /** 检查周期，默认 1000ms。 */
  intervalMs?: number;
  /** 判定停摆的活动间隔阈值，默认 5000ms。 */
  stallMs?: number;
  /** 可注入时钟与定时器，便于测试。 */
  now?: () => number;
  setTimer?: (callback: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

/** 启动看门狗，返回停止函数（会话释放时调用）。 */
export function createBackgroundWatchdog(options: BackgroundWatchdogOptions): () => void {
  const intervalMs = options.intervalMs ?? 1000;
  const stallMs = options.stallMs ?? AR_BACKGROUND_STALL_MS;
  const now = options.now ?? (() => performance.now());
  const setTimer = options.setTimer ?? ((callback, ms) => setInterval(callback, ms));
  const clearTimer = options.clearTimer ?? (handle => clearInterval(handle as ReturnType<typeof setInterval>));
  let stopped = false;
  const handle = setTimer(() => {
    if (stopped) return;
    if (now() - options.lastActivity() > stallMs) {
      stopped = true;
      options.onStall();
    }
  }, intervalMs);
  return () => {
    stopped = true;
    clearTimer(handle);
  };
}