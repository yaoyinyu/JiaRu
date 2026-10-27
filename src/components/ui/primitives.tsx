import type { ReactNode } from "react";
import styles from "./primitives.module.css";

/** 编辑部式小标题：珊瑚短线 + 大写字距 */
export function Eyebrow({ children, withRule = true }: { children: ReactNode; withRule?: boolean }) {
  return (
    <p className={styles.eyebrow}>
      {withRule ? <span className={styles.rule} aria-hidden="true" /> : null}
      <span>{children}</span>
    </p>
  );
}

/** 页面主标题：衬线字体，可选珊瑚色强调片段 */
export function PageHeading({
  eyebrow,
  title,
  accent,
  description,
  aside,
}: {
  eyebrow?: string;
  title: ReactNode;
  accent?: ReactNode;
  description?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className={styles.heading}>
      <div className={styles.headingText}>
        {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
        <h1 className={styles.h1}>
          {title}
          {accent ? <span className={styles.accent}>{accent}</span> : null}
        </h1>
        {description ? <p className={styles.description}>{description}</p> : null}
      </div>
      {aside ? <div className={styles.headingAside}>{aside}</div> : null}
    </header>
  );
}

/** 新拟态卡片：凸起默认，inset 用于“已选/托盘” */
export function NeuCard({
  children,
  className = "",
  inset = false,
}: {
  children: ReactNode;
  className?: string;
  inset?: boolean;
}) {
  return (
    <section className={`${inset ? styles.inset : styles.card} ${className}`}>
      {children}
    </section>
  );
}

/** 区块标题：大写小标 + 衬线标题 + 右侧动作 */
export function SectionHead({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string;
  title: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={styles.sectionHead}>
      <div>
        <p className={styles.sectionEyebrow}>{eyebrow}</p>
        <h2 className={styles.h2}>{title}</h2>
      </div>
      {action ? <div className={styles.sectionAction}>{action}</div> : null}
    </div>
  );
}

/** 描边/填充胶囊，用于状态与标签（非交互） */
export function Chip({ children, active = false }: { children: ReactNode; active?: boolean }) {
  return <span className={active ? styles.chipActive : styles.chip}>{children}</span>;
}
