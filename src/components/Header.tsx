"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { label: "首页", href: "/" },
  { label: "上传试色", href: "/editor" },
  { label: "图库", href: "/gallery" },
  { label: "AI 生成", href: "/ai-generate" },
  { label: "AR 试戴", href: "/ar-tryon" },
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className="fixed left-0 right-0 top-0 z-50 border-b border-white/50 bg-white/55 backdrop-blur-2xl">
      <div className="mx-auto flex h-20 w-full max-w-7xl items-center justify-between px-5 sm:px-10 lg:px-20">
        <Link href="/" className="text-[28px] font-bold tracking-[-0.5px] text-[#d4749d]" aria-label="甲如首页">
          甲如
        </Link>

        <nav className="hidden items-center gap-7 lg:flex" aria-label="主导航">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  active
                    ? "text-sm font-semibold text-[#d4749d]"
                    : "text-sm font-medium text-gray-400 transition-colors hover:text-[#d4749d]"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <Link
          href="/ar-tryon"
          className="rounded-full bg-gradient-to-b from-[#f0b8d0] to-[#d4749d] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_1px_0_rgba(255,255,255,0.25)_inset,0_4px_12px_rgba(212,116,157,0.35),0_8px_24px_rgba(212,116,157,0.15)] transition hover:-translate-y-0.5 hover:shadow-[0_1px_0_rgba(255,255,255,0.3)_inset,0_6px_16px_rgba(212,116,157,0.4),0_12px_32px_rgba(212,116,157,0.2)] active:translate-y-0.5 active:scale-[0.97] sm:px-7 sm:py-3"
        >
          开始试色
        </Link>
      </div>
    </header>
  );
}