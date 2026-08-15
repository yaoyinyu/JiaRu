"use client";

import { useEffect } from "react";

/**
 * 背景光斑动画协调：
 * 1. 相位对齐（核心）：页面挂载时把每个光斑的 `animation-delay` 设为负的
 *    "当前全局时间 % 动画周期"，让 CSS 动画从正确相位继续播放——
 *    客户端切换页面时光斑位置无缝续接，不会从头重播；
 * 2. 页面切到后台/最小化时自动暂停动画，回到前台恢复，
 *    只针对带 `data-ambient-blob` 标记的光斑元素，减小后台显卡与 CPU 开销。
 */
export function AmbientMotion() {
  useEffect(() => {
    const apply = () => {
      const paused = document.hidden;
      document
        .querySelectorAll<HTMLElement>("[data-ambient-blob]")
        .forEach((el) => {
          el.style.animationPlayState = paused ? "paused" : "";
        });
    };

    // 相位对齐：delay = -(now % period)，动画立即从全局时间对应的进度继续。
    const syncPhase = () => {
      const now = performance.now();
      document
        .querySelectorAll<HTMLElement>("[data-ambient-blob]")
        .forEach((el) => {
          const dur = parseFloat(getComputedStyle(el).animationDuration || "0s");
          if (!dur || !Number.isFinite(dur)) return;
          const periodMs = dur * 1000;
          el.style.animationDelay = `-${(now % periodMs).toFixed(0)}ms`;
        });
    };

    syncPhase();
    document.addEventListener("visibilitychange", apply);
    return () => document.removeEventListener("visibilitychange", apply);
  }, []);
  return null;
}
