import type { ReactNode } from "react";
import { Header } from "./Header";
import { AmbientMotion } from "./AmbientMotion";
import styles from "./AppShell.module.css";

type AppShellProps = { eyebrow: string; title: string; description: string; children: ReactNode; wide?: boolean; shiftUp?: boolean };

export function AppShell({ eyebrow, title, description, children, wide = false, shiftUp = false }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <div className={styles.ambient} aria-hidden="true">
        <span data-ambient-blob className={styles.pink} />
        <span data-ambient-blob className={styles.purple} />
        <span data-ambient-blob className={styles.gold} />
        <span data-ambient-blob className={styles.rose} />
        <span data-ambient-blob className={styles.white} />
      </div>
      <div className={styles.frostGlass} aria-hidden="true" />
      <AmbientMotion />
      <Header />
      <main className={`${styles.main} ${wide ? styles.wide : ""} ${shiftUp ? styles.shiftUp : ""}`}>
        <header className={styles.pageHeader}>
          <p className={styles.eyebrow}>{eyebrow}</p>
          <h1>{title}</h1>
          <p className={styles.description}>{description}</p>
        </header>
        <div className={styles.content}>{children}</div>
      </main>
      <footer className={styles.footer}>
        <span>甲如 JiaRu</span>
        <span>在指尖，遇见更好的选择</span>
      </footer>
    </div>
  );
}
