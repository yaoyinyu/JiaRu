import Link from "next/link";
import { Header } from "@/components/Header";
import { BottomNav } from "@/components/BottomNav";
import { Eyebrow, NeuCard, SectionHead } from "@/components/ui/primitives";
import { Icon } from "@/components/Icon";
import { GALLERY_IMAGES } from "@/lib/utils";
import styles from "./page.module.css";

export default function Home() {
  const curated = GALLERY_IMAGES.slice(0, 4);

  return (
    <div className={styles.page}>
      <a href="#main-content" className={styles.skipLink}>跳到主要内容</a>
      <Header />

      <main id="main-content" tabIndex={-1} className={styles.main}>
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroCopy}>
            <Eyebrow>The Everyday Muse</Eyebrow>
            <h1 id="hero-title" className={styles.heroTitle}>
              把喜欢的自己，
              <span className={styles.heroAccent}>留在每一次抬手。</span>
            </h1>
            <p className={styles.heroLede}>让喜欢，轻轻落在指尖。</p>
            <div className={styles.heroActions}>
              <Link href="/ar-tryon" className={styles.primaryAction}>
                开始试戴
                <Icon name="arrow-up-right" />
              </Link>
              <Link href="/editor" className={styles.ghostAction}>上传照片试色</Link>
            </div>
          </div>

          <figure className={styles.heroFigure}>
            <div className={styles.heroFrame}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/nail-gallery/hero-hand.jpg"
                alt="手部美甲示例：五指分别呈现不同质感与色调"
                width={1200}
                height={1499}
                className={styles.heroImage}
              />
              <span className={styles.heroVertical} aria-hidden="true">A Muse, Illustrated · AI 灵感</span>
              <figcaption className={styles.heroCaption}>
                <span className={styles.captionDot} aria-hidden="true" />
                A little more you.
              </figcaption>
            </div>
          </figure>
        </section>

        <Link href="/nail-analysis" className={styles.styleCard}>
          <span className={styles.styleIcon} aria-hidden="true">
            <Icon name="sparkles" />
          </span>
          <span className={styles.styleText}>
            <strong>找到你的风格</strong>
            <em>从几个喜欢的词开始。</em>
          </span>
          <span className={styles.styleArrow} aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none">
              <path d="M4 10h11M11 5.5 15.5 10 11 14.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </Link>

        <SectionHead
          eyebrow="Curated for You"
          title="此刻心动"
          action={
            <Link href="/gallery" className={styles.roundAction} aria-label="查看全部灵感款式">
              <Icon name="bookmark" />
            </Link>
          }
        />

        <Link href="/gallery" className={styles.searchPill}>
          <Icon name="search" />
          <span>法式、裸粉、通勤…</span>
        </Link>

        <ul className={styles.lookGrid}>
          {curated.map((look) => (
            <li key={look.id}>
              <Link href={`/editor?gallery=${look.id}`} className={styles.lookItem}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={look.src} alt={`${look.name}款式示例`} width={1024} height={1024} loading="lazy" className={styles.lookImage} />
                <span className={styles.lookName}>{look.name}</span>
              </Link>
            </li>
          ))}
        </ul>

        <NeuCard className={styles.boundaryCard}>
          <p>
            试戴需摄像头权限与安全连接（HTTPS 或本机地址）；AI 生成需联网。识别结果用于辅助定位，
            不作为正式纹理识别能力的承诺。图片默认不离开本机。
          </p>
        </NeuCard>
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
              <a href="mailto:3181484805@qq.com" className={styles.footerLink}>联系我们</a>
            </div>
          </div>
        </div>
        <div className={styles.footerDivider} />
        <div className={styles.footerBottom}>
          <span>© 2026 甲如 JiaRu. 保留所有权利。</span>
          <span>数据默认本地处理，改进计划可随时关闭</span>
        </div>
      </footer>

      <BottomNav />
    </div>
  );
}
