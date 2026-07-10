"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Header.module.css";

const navigation = [
  { href: "/", label: "首页" },
  { href: "/gallery", label: "灵感" },
  { href: "/ai-generate", label: "AI 设计" },
  { href: "/ar-tryon", label: "AR 试戴" },
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link href="/" className={styles.brand} aria-label="甲如首页">
          <span className={styles.brandMark} aria-hidden="true">J</span>
          <span>甲如</span>
        </Link>
        <nav className={styles.nav} aria-label="主导航">
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={active ? styles.active : undefined}>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <Link href="/editor" className={`${styles.action} ${pathname === "/editor" ? styles.actionActive : ""}`}>
          <span className={styles.actionFull}>上传试色</span>
          <span className={styles.actionShort}>试色</span>
          <span aria-hidden="true">↗</span>
        </Link>
      </div>
    </header>
  );
}
