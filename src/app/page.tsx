import Link from "next/link";
import { Header } from "@/components/Header";
import styles from "./page.module.css";

type Feature = {
  title: string;
  description: string;
  href: string;
  icon: "upload" | "gallery" | "sparkles" | "camera";
};

const features: Feature[] = [
  {
    title: "上传试色",
    description: "拍张手的照片，选喜欢的颜色涂在指甲上",
    href: "/editor",
    icon: "upload",
  },
  {
    title: "灵感图库",
    description: "浏览精选美甲款式，找到你的心动设计",
    href: "/gallery",
    icon: "gallery",
  },
  {
    title: "AI 生成",
    description: "用文字描述你想要的风格，AI 帮你生成美甲效果",
    href: "/ai-generate",
    icon: "sparkles",
  },
  {
    title: "AR 试戴",
    description: "打开摄像头，美甲实时贴合手指，动一动就能看效果",
    href: "/ar-tryon",
    icon: "camera",
  },
];

function FeatureIcon({ name }: { name: Feature["icon"] }) {
  if (name === "upload") {
    return (
      <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <rect x="3" y="9" width="22" height="15" rx="3" stroke="currentColor" strokeWidth="2" />
        <path d="m9 17 3-3 4 5 3-3 3 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="6" r="3" stroke="currentColor" strokeWidth="2" />
        <path d="M14 6h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  if (name === "gallery") {
    return (
      <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="2" />
        <rect x="16" y="3" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="2" />
        <rect x="3" y="16" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="2" />
        <rect x="16" y="16" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="2" />
      </svg>
    );
  }

  if (name === "sparkles") {
    return (
      <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <path d="m14 3 2.5 7.5L24 13l-7.5 2.5L14 23l-2.5-7.5L4 13l7.5-2.5L14 3Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="21" cy="20" r="2" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="7" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect x="4" y="8" width="20" height="14" rx="3" stroke="currentColor" strokeWidth="2" />
      <circle cx="14" cy="15" r="4" stroke="currentColor" strokeWidth="2" />
      <circle cx="14" cy="15" r="1.5" fill="currentColor" />
      <path d="M4 12h16" stroke="currentColor" opacity=".3" />
    </svg>
  );
}

export default function Home() {
  return (
    <div className={styles.page}>
      <div className={styles.ambientLayer} aria-hidden="true">
        <span className={`${styles.ambientBlob} ${styles.ambientA}`} />
        <span className={`${styles.ambientBlob} ${styles.ambientB}`} />
        <span className={`${styles.ambientBlob} ${styles.ambientC}`} />
        <span className={`${styles.ambientBlob} ${styles.ambientD}`} />
        <span className={`${styles.ambientBlob} ${styles.ambientE}`} />
      </div>
      <div className={styles.frostGlass} aria-hidden="true" />

      <Header />

      <main>
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroContent}>
            <p className={styles.badge}>你的随身美甲师</p>
            <h1 id="hero-title" className={styles.heroTitle}>找到属于你的完美甲色</h1>
            <p className={styles.heroDescription}>
              上传照片或开启摄像头，即时预览美甲效果。无需下载，浏览器打开就能用。
            </p>
          </div>

          <div id="features" className={styles.bentoGrid}>
            {features.map((feature) => (
              <Link key={feature.href} href={feature.href} className={styles.card}>
                <span className={styles.cardIcon}>
                  <FeatureIcon name={feature.icon} />
                </span>
                <span className={styles.cardTitle}>{feature.title}</span>
                <span className={styles.cardDescription}>{feature.description}</span>
              </Link>
            ))}
          </div>
        </section>
      </main>

      <footer id="about" className={styles.footer}>
        <div className={styles.footerTop}>
          <div className={styles.footerBrand}>
            <Link href="/" className={styles.footerLogo}>甲如</Link>
            <span className={styles.footerTagline}>在指尖遇见更好的美甲选择</span>
          </div>
          <div className={styles.footerLinks}>
            <div className={styles.footerLinkGroup}>
              <span className={styles.footerLinkTitle}>产品</span>
              <Link href="/editor" className={styles.footerLink}>上传试色</Link>
              <Link href="/ai-generate" className={styles.footerLink}>AI 生成</Link>
              <Link href="/ar-tryon" className={styles.footerLink}>AR 试戴</Link>
            </div>
            <div className={styles.footerLinkGroup}>
              <span className={styles.footerLinkTitle}>支持</span>
              <Link href="/privacy" className={styles.footerLink}>隐私政策</Link>
              <a href="mailto:hello@jiaru.app" className={styles.footerLink}>联系我们</a>
            </div>
          </div>
        </div>
        <div className={styles.footerDivider} />
        <div className={styles.footerBottom}>
          <span>© 2026 甲如 JiaRu. 保留所有权利。</span>
          <span>照片在本地处理，不上传至服务器</span>
        </div>
      </footer>
    </div>
  );
}