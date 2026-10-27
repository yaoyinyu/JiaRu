"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/Icon";
import styles from "./Header.module.css";

const navigation = [
  { href: "/", label: "为你", match: (p: string) => p === "/" },
  { href: "/ar-tryon", label: "试戴", match: (p: string) => p.startsWith("/ar-tryon") || p.startsWith("/editor") },
  { href: "/ai-generate", label: "创作", match: (p: string) => p.startsWith("/ai-generate") },
  { href: "/nail-analysis", label: "分析", match: (p: string) => p.startsWith("/nail-analysis") },
  { href: "/account", label: "我的", match: (p: string) => p.startsWith("/account") || p.startsWith("/login") },
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link href="/" className={styles.brand} aria-label="甲如首页">
          <span className={styles.lockup}>
            <span className={styles.wordmark} aria-hidden="true">JiaRu</span>
            <span className={styles.atelier} aria-hidden="true">nail atelier</span>
          </span>
          <span className={styles.divider} aria-hidden="true" />
          <span className={styles.brandCn}>甲如</span>
        </Link>

        <nav className={styles.nav} aria-label="主导航">
          {navigation.map((item) => {
            const active = item.match(pathname);
            return (
              <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className={styles.actions}>
          <Link href="/editor" className={styles.iconButton} aria-label="上传照片试色">
            <Icon name="upload" />
          </Link>
          <Link
            href="/gallery"
            className={styles.iconButton}
            aria-label="灵感图库与收藏"
            aria-current={pathname.startsWith("/gallery") ? "page" : undefined}
          >
            <Icon name="bookmark" />
          </Link>
        </div>
      </div>
    </header>
  );
}
