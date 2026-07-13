import { AppShell } from "@/components/AppShell";

const sections = [
  { number: "01", title: "本地优先", text: "「甲如」将用户隐私放在首位。我们尽可能在浏览器中完成数据处理，让你的个人内容留在自己的设备上。" },
  { number: "02", title: "照片处理", text: "你上传的手部照片全部在浏览器本地处理，不会被发送到任何服务器。抠图、涂色等操作均在本地完成。" },
  { number: "03", title: "AI 生成", text: "AI 生成功能仅发送你输入的风格描述文字，不会发送你的照片或图片，服务商无法获取你的个人图像数据。" },
  { number: "04", title: "AR 摄像头", text: "AR 模式中的摄像头画面仅在内存中实时处理，不会被录制、存储或上传到任何服务器。" },
  { number: "05", title: "数据存储", text: "你保存的试戴效果图默认存储在你的设备本地。我们不会收集、存储或分析你的个人使用数据。" },
  { number: "06", title: "联系我们", text: "如果你对隐私有任何疑问，欢迎联系我们。我们承诺用清晰、通俗的语言解释数据流向。" },
];

export default function PrivacyPage() {
  return (
    <AppShell eyebrow="Privacy by Design" title="你的照片，始终属于你" description="透明说明每一项数据如何流动。我们的原则很简单：能在本地完成的处理，就不离开你的设备。">
      <div className="grid gap-4 md:grid-cols-2">
        {sections.map((section) => (
          <section key={section.number} className="group rounded-[26px] border border-white/80 bg-white/60 p-6 shadow-[0_18px_50px_rgba(116,73,92,.07)] backdrop-blur-xl transition hover:-translate-y-1 hover:bg-white/75 hover:shadow-[0_24px_60px_rgba(116,73,92,.10)]">
            <div className="flex items-center justify-between"><span className="text-xs font-semibold tracking-[.18em] text-[#D4749D]">{section.number}</span><span className="h-2 w-2 rounded-full bg-gradient-to-br from-pink-300 to-purple-300 shadow-[0_0_0_6px_rgba(244,190,214,.16)]" /></div>
            <h2 className="mt-7 text-lg font-semibold text-[#4D464A]">{section.title}</h2>
            <p className="mt-3 text-sm leading-7 text-[#8F868B]">{section.text}</p>
          </section>
        ))}
      </div>
      <div className="mt-6 flex flex-col items-center justify-between gap-3 rounded-[24px] border border-pink-100/70 bg-white/55 px-6 py-5 text-center backdrop-blur-xl sm:flex-row sm:text-left">
        <div><p className="text-sm font-medium text-[#5A5156]">仍有关于隐私的问题？</p><p className="mt-1 text-xs text-[#9E9499]">我们乐意说明每一个处理环节。</p></div>
        <a href="mailto:hello@jiaru.app" className="rounded-full bg-[#4A4447] px-5 py-2.5 text-xs font-medium text-white transition hover:bg-[#D4749D]">联系我们</a>
      </div>
      <p className="mt-6 text-center text-xs text-[#B0A6AB]">最后更新：2026 年 7 月</p>
    </AppShell>
  );
}