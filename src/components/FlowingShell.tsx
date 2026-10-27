"use client";

import { Header } from "@/components/Header";
import { BottomNav } from "@/components/BottomNav";

interface FlowingShellProps {
  children: React.ReactNode;
  maxWidth?: string;
  className?: string;
}

/**
 * 轻量壳层（原“流动色块 + 毛玻璃”视觉已废弃）。
 * 现与 AppShell 共用同一套新拟态品牌基底，仅保留自定义最大宽度能力。
 */
export function FlowingShell({
  children,
  maxWidth = "max-w-md",
  className = "",
}: FlowingShellProps) {
  return (
    <div className="relative min-h-dvh bg-[var(--paper)] text-[var(--ink)]">
      <Header />

      <main className={`relative mx-auto flex w-full ${maxWidth} flex-col px-4 pb-28 pt-6 sm:pb-10 ${className}`}>
        {children}
      </main>

      <BottomNav />
    </div>
  );
}

export function PageHero({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section className="mb-6">
      <p className="mb-3 font-[var(--serif)] text-[11px] uppercase tracking-[.22em] text-[var(--coral-text)]">
        {eyebrow}
      </p>
      <h1 className="text-balance font-[var(--serif)] text-2xl font-medium leading-tight text-[var(--ink)] sm:text-3xl">
        {title}
      </h1>
      <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
        {description}
      </p>
    </section>
  );
}

export function GlassPanel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`neu-card overflow-hidden ${className}`}>
      {children}
    </section>
  );
}
