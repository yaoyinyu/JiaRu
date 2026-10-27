"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, type IconName } from "./Icon";
import styles from "./BottomNav.module.css";

type Item = { href: string; label: string; icon: IconName; match: string[] };

const items: Item[] = [
  { href: "/", label: "为你", icon: "lightbulb", match: ["/"] },
  { href: "/ar-tryon", label: "试戴", icon: "hand", match: ["/ar-tryon", "/editor"] },
  { href: "/ai-generate", label: "创作", icon: "sparkles", match: ["/ai-generate"] },
  { href: "/nail-analysis", label: "分析", icon: "palette", match: ["/nail-analysis"] },
  { href: "/account", label: "我的", icon: "user", match: ["/account", "/login"] },
];

function isActive(pathname: string, item: Item): boolean {
  return item.match.some((base) => (base === "/" ? pathname === "/" : pathname.startsWith(base)));
}

export function BottomNav() {
  const pathname = usePathname();
  const [keyboardOpen, setKeyboardOpen] = useState(false);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    let baseline = viewport.height;
    const onResize = () => {
      // 双指缩放不应被视为键盘：只在视口高度明显收缩且宽度基本不变时判定
      const shrunk = baseline - viewport.height;
      if (viewport.height > baseline) baseline = viewport.height;
      setKeyboardOpen(shrunk > 140);
    };
    viewport.addEventListener("resize", onResize);
    return () => viewport.removeEventListener("resize", onResize);
  }, []);

  return (
    <nav className={`${styles.nav} ${keyboardOpen ? styles.hidden : ""}`} aria-label="主导航（移动端）">
      {items.map((item) => {
        const active = isActive(pathname, item);
        return (
          <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={active ? styles.active : undefined}>
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
