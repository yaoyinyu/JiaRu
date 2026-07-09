import Link from "next/link";

const navItems = [
  { label: "首页", href: "/" },
  { label: "功能", href: "#features" },
  { label: "关于", href: "#about" },
];

const featureCards = [
  {
    title: "上传试色",
    desc: "上传手部照片，选择喜欢的颜色或纹理，快速预览指尖效果。",
    href: "/editor",
    icon: "upload",
  },
  {
    title: "灵感图库",
    desc: "浏览精选美甲款式，找到适合你的风格与配色灵感。",
    href: "/gallery",
    icon: "grid",
  },
  {
    title: "AI 生成",
    desc: "用文字描述想要的风格，让 AI 生成新的美甲设计方向。",
    href: "/ai-generate",
    icon: "sparkle",
  },
  {
    title: "AR 试戴",
    desc: "打开摄像头，实时把美甲效果贴合到手指上。",
    href: "/ar-tryon",
    icon: "camera",
  },
];

function FeatureIcon({ icon }: { icon: string }) {
  if (icon === "upload") {
    return (
      <svg viewBox="0 0 28 28" aria-hidden="true">
        <rect x="3" y="9" width="22" height="15" rx="3" />
        <path d="M9 17l3-3 4 5 3-3 3 3" />
        <circle cx="10" cy="6" r="3" />
        <path d="M14 6h8" />
      </svg>
    );
  }

  if (icon === "grid") {
    return (
      <svg viewBox="0 0 28 28" aria-hidden="true">
        <rect x="3" y="3" width="9" height="9" rx="2" />
        <rect x="16" y="3" width="9" height="9" rx="2" />
        <rect x="3" y="16" width="9" height="9" rx="2" />
        <rect x="16" y="16" width="9" height="9" rx="2" />
      </svg>
    );
  }

  if (icon === "sparkle") {
    return (
      <svg viewBox="0 0 28 28" aria-hidden="true">
        <path d="M14 3l2.5 7.5L24 13l-7.5 2.5L14 23l-2.5-7.5L4 13l7.5-2.5L14 3z" />
        <circle cx="21" cy="20" r="2" />
        <circle cx="7" cy="21" r="1.5" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 28 28" aria-hidden="true">
      <rect x="4" y="8" width="20" height="14" rx="3" />
      <circle cx="14" cy="15" r="4" />
      <circle cx="14" cy="15" r="1.5" className="fill-current" />
      <path d="M4 12h16" opacity="0.3" />
    </svg>
  );
}

export default function Home() {
  return (
    <main className="relative min-h-dvh overflow-hidden bg-gradient-to-b from-[#fff5f7] to-white text-[#4a4a4a]">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="home-ambient-blob home-amb-a" />
        <div className="home-ambient-blob home-amb-b" />
        <div className="home-ambient-blob home-amb-c" />
        <div className="home-ambient-blob home-amb-d" />
        <div className="home-ambient-blob home-amb-e" />
        <div className="absolute inset-0 bg-white/30 backdrop-blur-[50px] backdrop-saturate-[1.3]" />
      </div>

      <header className="relative z-10 flex h-20 items-center justify-between px-5 sm:px-10 lg:px-20">
        <Link href="/" className="text-[28px] font-bold tracking-[-0.5px] text-[#d4749d]" aria-label="甲如首页">
          甲如
        </Link>
        <nav className="hidden items-center gap-10 md:flex" aria-label="主导航">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={
                item.href === "/"
                  ? "text-base font-medium text-[#d4749d]"
                  : "text-base font-normal text-gray-400 transition-colors hover:text-[#d4749d]"
              }
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/ar-tryon"
          className="rounded-full bg-gradient-to-b from-[#f0b8d0] to-[#d4749d] px-6 py-3 text-sm font-semibold text-white shadow-[0_1px_0_rgba(255,255,255,0.25)_inset,0_4px_12px_rgba(212,116,157,0.35),0_8px_24px_rgba(212,116,157,0.15)] transition hover:-translate-y-0.5 hover:shadow-[0_1px_0_rgba(255,255,255,0.3)_inset,0_6px_16px_rgba(212,116,157,0.4),0_12px_32px_rgba(212,116,157,0.2)] active:translate-y-0.5 active:scale-[0.97] sm:px-7 sm:py-3.5 sm:text-base"
        >
          开始试色
        </Link>
      </header>

      <section className="relative z-10 flex min-h-[calc(100dvh-80px)] flex-col items-center justify-center gap-10 px-4 py-16 sm:px-10 lg:px-20 lg:py-24">
        <div className="flex max-w-2xl flex-col items-center gap-6 text-center">
          <p className="rounded-full border border-[#e8a0bf]/25 bg-gradient-to-b from-[#fff5f7] to-[#ffe8ee] px-4 py-1.5 text-sm font-medium text-[#d4749d] shadow-[0_2px_8px_rgba(212,116,157,0.06)]">
            你的随身美甲师
          </p>
          <h1 className="max-w-3xl text-balance text-[clamp(2rem,5vw,3.5rem)] font-bold leading-tight">
            找到属于你的完美甲色
          </h1>
          <p className="max-w-2xl text-balance text-[clamp(0.95rem,1.4vw,1.125rem)] leading-7 text-gray-400">
            上传照片或开启摄像头，即时预览美甲效果。无需下载，浏览器打开就能用。
          </p>
        </div>

        <div
          id="features"
          className="grid w-full max-w-xl grid-cols-1 gap-4 rounded-[28px] border border-[#e8a0bf]/15 bg-white/60 p-4 shadow-[0_8px_32px_rgba(232,160,191,0.08)] sm:grid-cols-2 sm:p-5 xl:max-w-6xl xl:grid-cols-4"
        >
          {featureCards.map((card) => (
            <Link
              key={card.href}
              href={card.href}
              className="group flex flex-col items-center gap-3 rounded-[20px] bg-gradient-to-b from-white to-[#fff5f7] p-6 text-center shadow-[0_0_0_1px_rgba(232,160,191,0.1)_inset,0_1px_3px_rgba(212,116,157,0.06),0_4px_12px_rgba(212,116,157,0.08),0_12px_32px_rgba(212,116,157,0.04)] transition duration-300 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-[0_0_0_1px_rgba(232,160,191,0.15)_inset,0_2px_6px_rgba(212,116,157,0.1),0_8px_20px_rgba(212,116,157,0.14),0_20px_48px_rgba(212,116,157,0.08)] active:-translate-y-0.5 active:scale-[0.98]"
            >
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#fff5f7] to-[#ffe8ee] text-[#d4749d] shadow-[0_2px_8px_rgba(212,116,157,0.1),0_0_0_1px_rgba(232,160,191,0.12)_inset]">
                <span className="[&_svg]:h-7 [&_svg]:w-7 [&_svg]:fill-none [&_svg]:stroke-current [&_svg]:stroke-2 [&_svg]:[stroke-linecap:round] [&_svg]:[stroke-linejoin:round]">
                  <FeatureIcon icon={card.icon} />
                </span>
              </span>
              <span className="text-lg font-semibold text-[#4a4a4a]">{card.title}</span>
              <span className="text-balance text-sm leading-6 text-gray-400">{card.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <footer id="about" className="relative z-10 flex flex-col items-center gap-10 px-5 pb-10 pt-16 sm:px-10 lg:px-20">
        <div className="flex w-full max-w-7xl flex-col justify-between gap-10 md:flex-row">
          <div className="flex flex-col gap-3">
            <span className="text-2xl font-bold text-[#d4749d]">甲如</span>
            <span className="text-sm text-gray-400">在指尖遇见更好的美甲选择</span>
          </div>
          <div className="flex flex-wrap gap-12 sm:gap-20">
            <div className="flex flex-col gap-2.5">
              <span className="mb-1 text-sm font-semibold text-[#4a4a4a]">产品</span>
              <Link href="/editor" className="text-sm text-gray-400 hover:text-[#d4749d]">
                上传试色
              </Link>
              <Link href="/ai-generate" className="text-sm text-gray-400 hover:text-[#d4749d]">
                AI 生成
              </Link>
              <Link href="/ar-tryon" className="text-sm text-gray-400 hover:text-[#d4749d]">
                AR 试戴
              </Link>
            </div>
            <div className="flex flex-col gap-2.5">
              <span className="mb-1 text-sm font-semibold text-[#4a4a4a]">支持</span>
              <Link href="/privacy" className="text-sm text-gray-400 hover:text-[#d4749d]">
                隐私政策
              </Link>
              <a href="mailto:support@example.com" className="text-sm text-gray-400 hover:text-[#d4749d]">
                联系我们
              </a>
            </div>
          </div>
        </div>
        <div className="h-px w-full max-w-7xl bg-[#fff0f5]" />
        <div className="flex w-full max-w-7xl flex-col justify-between gap-2 text-sm text-gray-400 md:flex-row">
          <span>2026 甲如 JiaRu. 保留所有权利。</span>
          <span>照片在本地处理，不上传至服务器。</span>
        </div>
      </footer>

      <style>{`
        .home-ambient-blob {
          position: absolute;
          border-radius: 9999px;
          filter: blur(90px);
          opacity: 0.58;
          animation-timing-function: ease-in-out;
          animation-iteration-count: infinite;
          will-change: transform, border-radius;
        }
        .home-amb-a { width: 750px; height: 750px; left: 45%; top: -30%; background: #e8a0bf; animation: home-amb-1 20s infinite; }
        .home-amb-b { width: 580px; height: 580px; left: 5%; top: 45%; background: #a694e4; animation: home-amb-2 24s infinite; }
        .home-amb-c { width: 460px; height: 460px; left: 60%; top: 42%; background: #ffd278; animation: home-amb-3 18s infinite; }
        .home-amb-d { width: 640px; height: 640px; left: 15%; top: -5%; background: #ffb4c8; animation: home-amb-4 26s infinite; }
        .home-amb-e { width: 520px; height: 520px; left: 30%; top: 35%; background: #fff0f5; animation: home-amb-5 22s infinite; }
        @keyframes home-amb-1 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          20% { transform: translate(-130px,90px) scale(1.35,0.55) rotate(15deg); border-radius: 35% 65% 58% 42%; }
          40% { transform: translate(80px,-180px) scale(0.5,1.6) rotate(-12deg); border-radius: 68% 32% 40% 60%; }
          60% { transform: translate(-160px,-70px) scale(1.25,0.7) rotate(22deg); border-radius: 42% 58% 65% 35%; }
          80% { transform: translate(50px,140px) scale(0.6,1.45) rotate(-18deg); border-radius: 60% 40% 35% 65%; }
        }
        @keyframes home-amb-2 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          25% { transform: translate(140px,-100px) scale(0.55,1.5) rotate(-20deg); border-radius: 62% 38% 45% 55%; }
          50% { transform: translate(-120px,130px) scale(1.45,0.55) rotate(14deg); border-radius: 38% 62% 60% 40%; }
          75% { transform: translate(60px,-80px) scale(0.8,1.25) rotate(-8deg); border-radius: 55% 45% 38% 62%; }
        }
        @keyframes home-amb-3 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          25% { transform: translate(-110px,110px) scale(1.4,0.5) rotate(18deg); border-radius: 40% 60% 55% 45%; }
          50% { transform: translate(70px,-150px) scale(0.5,1.55) rotate(-15deg); border-radius: 65% 35% 42% 58%; }
          75% { transform: translate(130px,60px) scale(1.15,1.3) rotate(6deg); border-radius: 50% 50% 60% 40%; }
        }
        @keyframes home-amb-4 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          25% { transform: translate(100px,-130px) scale(0.55,1.5) rotate(-22deg); border-radius: 60% 40% 48% 52%; }
          50% { transform: translate(-140px,80px) scale(1.5,0.55) rotate(20deg); border-radius: 35% 65% 58% 42%; }
          75% { transform: translate(-50px,-100px) scale(0.75,1.2) rotate(-6deg); border-radius: 52% 48% 40% 60%; }
        }
        @keyframes home-amb-5 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          33% { transform: translate(-100px,-90px) scale(1.3,0.6) rotate(-10deg); border-radius: 42% 58% 55% 45%; }
          66% { transform: translate(90px,100px) scale(0.55,1.45) rotate(12deg); border-radius: 62% 38% 40% 60%; }
        }
        @media (prefers-reduced-motion: reduce) {
          .home-ambient-blob {
            animation: none;
          }
        }
      `}</style>
    </main>
  );
}