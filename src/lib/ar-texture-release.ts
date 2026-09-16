/**
 * AR 纹理位图资源释放（2026-09-05 评审 #9 修复配套模块）。
 *
 * 旧实现在"应用全部"时逐项检查旧数组中"其他手指是否还有共享引用"——
 * 当同一 bitmap 被多指共享时，每个槽都能看到另一个持有者而全部跳过 close
 * （评审复现：A 四指共享、第五指为 B，B 应用全部后 A 无槽位引用但 close 0 次）。
 * 正确语义：比较更新前后仍在使用的唯一 bitmap 集合，关闭所有不再保留的资源。
 */

/**
 * 关闭 previous 中持有、但 next 不再保留的位图。
 * 同一位图即使重复出现也只关闭一次；next 中保留的引用绝不关闭。
 * 对任意带 close() 的资源类型通用（ImageBitmap / VideoFrame 等）。
 */
export function releaseRemovedBitmaps<T extends { close(): void }>(
  previous: readonly (T | null)[],
  next: readonly (T | null)[]
): void {
  const kept = new Set<T | null>(next);
  const closed = new Set<T>();
  for (const texture of previous) {
    if (!texture || kept.has(texture) || closed.has(texture)) continue;
    texture.close();
    closed.add(texture);
  }
}
