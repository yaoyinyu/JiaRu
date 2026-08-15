import { AppShell } from "@/components/AppShell";

const principleSections = [
  { number: "01", icon: "🔒", title: "本地优先", text: "「甲如」将隐私放在首位：照片、摄像头画面与识别计算尽可能在浏览器本地完成，让你的个人内容留在自己的设备上。" },
  { number: "02", icon: "🚫", title: "不上传照片", text: "你上传或拍摄的任何照片都不会被发送到「甲如」服务器，也不会被存储、分析或用于任何训练。" },
  { number: "03", icon: "👁️", title: "不追踪", text: "我们不使用 Cookie 追踪、不采集使用统计、没有用户账户体系，也没有云同步。你的使用行为不归我们所有。" },
];

const featureSections = [
  { number: "04", icon: "🎨", title: "图片试色", badge: "数据：不出设备", text: "在试色编辑器中，上传的照片只在浏览器本地完成校验、解码与 Canvas 涂色；满意的结果由你主动点击「保存」下载到设备，整个过程不经过任何服务器。" },
  { number: "05", icon: "✨", title: "AI 生图", badge: "数据：仅文字 → 第三方", text: "AI 生成只发送你输入或选择的文字描述，绝不发送照片。服务端会把这段文字转发给第三方图像生成服务（Agnes AI），生成结果由你的浏览器直接访问第三方图片地址；请勿在描述中输入身份证号、电话等个人信息。" },
  { number: "06", icon: "📷", title: "AR 实时预览", badge: "数据：仅内存", text: "AR 模式中摄像头画面仅在浏览器内存中实时处理（手部关键点检测与指甲绘制），不录制、不存储、不上传。AR 预览不提供保存功能，关闭页面后画面即消失。" },
  { number: "07", icon: "🔍", title: "自动识别与图库", badge: "数据：不出设备", text: "美甲纹理的自动识别与参考图定位均在浏览器本地完成，参考图不会被上传。灵感图库当前为内置素材，不涉及个人数据。" },
];

const otherSections = [
  { number: "08", icon: "🤝", title: "第三方服务", text: "除 AI 生图依赖第三方图像生成服务外，「甲如」不接入任何广告、统计或分析 SDK。第三方仅收到你输入的描述文字，无法获取你的照片或摄像头画面。" },
  { number: "09", icon: "🛡️", title: "你的权利", text: "由于服务器不保存任何照片或个人信息，你的数据天然不会离开设备，无需申请删除。如对任何数据流向有疑问，欢迎随时联系我们。" },
  { number: "10", icon: "📄", title: "政策更新", text: "本页会随功能变化及时更新，更新日期见页面底部。涉及数据流向的重大变化会在本页显著说明。" },
];

function SectionCard({ number, icon, title, text, badge }: { number: string; icon: string; title: string; text: string; badge?: string }) {
  return (
    <section className="group relative overflow-hidden rounded-[26px] border border-white/80 bg-white/60 p-6 shadow-[0_18px_50px_rgba(116,73,92,.07)] backdrop-blur-xl transition hover:-translate-y-1 hover:bg-white/75 hover:shadow-[0_24px_60px_rgba(116,73,92,.10)]">
      <span aria-hidden className="pointer-events-none absolute right-0 -top-3 select-none bg-gradient-to-bl from-pink-200/90 via-pink-100/45 to-transparent bg-clip-text text-[120px] font-black leading-none text-transparent transition duration-300 group-hover:from-pink-300/95 group-hover:via-pink-200/60">
        {number}
      </span>
      <div className="relative">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-100/90 to-purple-100/90 text-xl shadow-[inset_0_1px_0_rgba(255,255,255,.8)]">{icon}</span>
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
