import type { ReactNode } from "react";
import { Header } from "./Header";
import { BottomNav } from "./BottomNav";
import styles from "./AppShell.module.css";

type AppShellProps = { eyebrow: string; title: string; description?: string; children: ReactNode; wide?: boolean; shiftUp?: boolean };

export function AppShell({ eyebrow, title, description, children, wide = false, shiftUp = false }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <a href="#main-content" className={styles.skipLink}>跳到主要内容</a>
      <Header />
      <main id="main-content" tabIndex={-1} className={`${styles.main} ${wide ? styles.wide : ""} ${shiftUp ? styles.shiftUp : ""}`}>
        <header className={styles.pageHeader}>
          <p className={styles.eyebrow}>{eyebrow}</p>
          <h1>{title}</h1>
          {description ? <p className={styles.description}>{description}</p> : null}
        </header>
        <div className={styles.content}>{children}</div>
      </main>
      <footer className={styles.footer}>
        <span>甲如 JiaRu</span>
        <span>在指尖，遇见更好的选择</span>
      </footer>
      <BottomNav />
    </div>
  );
}
