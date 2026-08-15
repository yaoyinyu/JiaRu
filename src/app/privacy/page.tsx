import { AppShell } from "@/components/AppShell";

const principleSections = [
  { number: "01", icon: "shield", title: "本地优先", text: "「甲如」将隐私放在首位：照片、摄像头画面与识别计算尽可能在浏览器本地完成，让你的个人内容留在自己的设备上。" },
  { number: "02", icon: "cloud-off", title: "不上传照片", text: "你上传或拍摄的任何照片都不会被发送到「甲如」服务器，也不会被存储、分析或用于任何训练。" },
  { number: "03", icon: "eye-off", title: "不追踪", text: "我们不使用 Cookie 追踪、不采集使用统计、没有用户账户体系，也没有云同步。你的使用行为不归我们所有。" },
];

const featureSections = [
  { number: "04", icon: "brush", title: "图片试色", badge: "数据：不出设备", text: "在试色编辑器中，上传的照片只在浏览器本地完成校验、解码与 Canvas 涂色；满意的结果由你主动点击「保存」下载到设备，整个过程不经过任何服务器。" },
  { number: "05", icon: "sparkles", title: "AI 生图", badge: "数据：仅文字 → 第三方", text: "AI 生成只发送你输入或选择的文字描述，绝不发送照片。服务端会把这段文字转发给第三方图像生成服务（Agnes AI），生成结果由你的浏览器直接访问第三方图片地址；请勿在描述中输入身份证号、电话等个人信息。" },
  { number: "06", icon: "camera", title: "AR 实时预览", badge: "数据：仅内存", text: "AR 模式中摄像头画面仅在浏览器内存中实时处理（手部关键点检测与指甲绘制），不录制、不存储、不上传。AR 预览不提供保存功能，关闭页面后画面即消失。" },
  { number: "07", icon: "search", title: "自动识别与图库", badge: "数据：不出设备", text: "美甲纹理的自动识别与参考图定位均在浏览器本地完成，参考图不会被上传。灵感图库当前为内置素材，不涉及个人数据。" },
];

const otherSections = [
  { number: "08", icon: "link", title: "第三方服务", text: "除 AI 生图依赖第三方图像生成服务外，「甲如」不接入任何广告、统计或分析 SDK。第三方仅收到你输入的描述文字，无法获取你的照片或摄像头画面。" },
  { number: "09", icon: "shield-check", title: "你的权利", text: "由于服务器不保存任何照片或个人信息，你的数据天然不会离开设备，无需申请删除。如对任何数据流向有疑问，欢迎随时联系我们。" },
  { number: "10", icon: "file-text", title: "政策更新", text: "本页会随功能变化及时更新，更新日期见页面底部。涉及数据流向的重大变化会在本页显著说明。" },
];

function Icon({ name }: { name: string }) {
  const props = {
    viewBox: "0 0 24 24",
    width: 20,
    height: 20,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (name) {
    case "shield":
      return <svg {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>;
    case "cloud-off":
      return (
        <svg {...props}>
          <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
          <path d="m2 2 20 20" />
        </svg>
      );
    case "eye-off":
      return (
        <svg {...props}>
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
          <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
          <path d="m1 1 22 22" />
        </svg>
      );
    case "brush":
      return (
        <svg {...props}>
          <path d="m9.06 11.9 8.07-8.06a2.85 2.85 0 1 1 4.03 4.03l-8.06 8.08" />
          <path d="M7.07 14.94c-1.66 0-3 1.35-3 3.02 0 1.33-2.5 1.52-2 2.02 1.08 1.1 2.49 2.02 4 2.02 2.2 0 4-1.8 4-4.04a3.01 3.01 0 0 0-3-3.02z" />
        </svg>
      );
    case "sparkles":
      return (
        <svg {...props}>
          <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
          <path d="M20 3v4" />
          <path d="M22 5h-4" />
          <path d="M4 17v2" />
          <path d="M5 18H3" />
        </svg>
      );
    case "camera":
      return (
        <svg {...props}>
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
      );
    case "search":
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
      );
    case "link":
      return (
        <svg {...props}>
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      );
    case "shield-check":
      return (
        <svg {...props}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
    case "file-text":
      return (
        <svg {...props}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M16 13H8" />
          <path d="M16 17H8" />
          <path d="M10 9H8" />
        </svg>
      );
    default:
      return null;
  }
}

function SectionCard({ number, icon, title, text, badge }: { number: string; icon: string; title: string; text: string; badge?: string }) {
  return (
    <section className="group relative overflow-hidden rounded-[26px] border border-white/80 bg-white/60 p-6 shadow-[0_18px_50px_rgba(116,73,92,.07)] backdrop-blur-xl transition hover:-translate-y-1 hover:bg-white/75 hover:shadow-[0_24px_60px_rgba(116,73,92,.10)]">
      <span aria-hidden className="pointer-events-none absolute right-0 -top-3 select-none bg-gradient-to-bl from-pink-200/90 via-pink-100/45 to-transparent bg-clip-text text-[120px] font-black leading-none text-transparent transition duration-300 group-hover:from-pink-300/95 group-hover:via-pink-200/60">
        {number}
      </span>
      <div className="relative">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-100/90 to-purple-100/90 text-[#B95F87] shadow-[inset_0_1px_0_rgba(255,255,255,.8)]">
          <Icon name={icon} />
        </span>
      </div>
      <h2 className="relative mt-5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-lg font-semibold text-[#4D464A]">
        {title}
        {badge ? (
          <span className="rounded-full border border-pink-200/60 bg-pink-50/80 px-2.5 py-0.5 text-[10px] font-semibold tracking-wide text-[#B95F87]">{badge}</span>
        ) : null}
      </h2>
      <p className="relative mt-3 text-sm leading-7 text-[#8F868B]">{text}</p>
    </section>
  );
}

function GroupHeader({ text }: { text: string }) {
  return (
    <div className="mb-6 mt-10 flex items-center gap-3">
      <span className="h-px flex-1 bg-gradient-to-r from-transparent to-pink-200/70" />
      <span className="text-base font-bold tracking-[.12em] text-[#4D464A]">{text}</span>
      <span className="h-px flex-1 bg-gradient-to-l from-transparent to-pink-200/70" />
    </div>
  );
}

export default function PrivacyPage() {
  return (
    <AppShell eyebrow="Privacy by Design" title="你的照片，始终属于你" description="透明说明每一项数据如何流动。我们的原则很简单：能在本地完成的处理，就不离开你的设备。">
      <GroupHeader text="核心原则" />
      <div className="grid gap-4 md:grid-cols-3">
        {principleSections.map((section) => (
          <SectionCard key={section.number} {...section} />
        ))}
      </div>
      <GroupHeader text="各功能的数据流向" />
      <div className="grid gap-4 md:grid-cols-2">
        {featureSections.map((section) => (
          <SectionCard key={section.number} {...section} />
        ))}
      </div>
      <GroupHeader text="第三方、权利与更新" />
      <div className="grid gap-4 md:grid-cols-3">
        {otherSections.map((section) => (
          <SectionCard key={section.number} {...section} />
        ))}
      </div>
      <div className="mt-10 flex flex-col items-center justify-between gap-3 rounded-[26px] border border-pink-100/70 bg-white/55 px-6 py-6 text-center shadow-[0_14px_40px_rgba(116,73,92,.07)] backdrop-blur-xl sm:flex-row sm:text-left">
        <div>
          <p className="text-sm font-medium text-[#5A5156]">仍有关于隐私的问题？</p>
          <p className="mt-1 text-xs text-[#9E9499]">我们乐意说明每一个处理环节。</p>
        </div>
        <a href="mailto:3181484805@qq.com" className="rounded-full bg-gradient-to-r from-[#4A4447] to-[#6B5F66] px-6 py-3 text-xs font-medium text-white shadow-md transition hover:from-[#D4749D] hover:to-[#B95F87] hover:shadow-lg">联系我们</a>
      </div>
      <p className="mt-8 text-center text-xs tracking-wide text-[#B0A6AB]">最后更新：2026 年 8 月 15 日</p>
    </AppShell>
  );
}
