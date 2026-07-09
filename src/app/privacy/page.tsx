"use client";

import { FlowingShell, GlassPanel, PageHero } from "@/components/FlowingShell";

const sections = [
  {
    title: "我们重视你的隐私",
    body: "甲如采用本地优先的设计理念，尽可能在浏览器中完成图片处理和试戴预览。",
  },
  {
    title: "照片处理",
    body: "你上传的手部照片会在浏览器本地处理，用于试色、裁剪和预览，不会默认上传到服务器。",
  },
  {
    title: "AI 生成",
    body: "AI 生成功能只发送你输入的文字描述，不会发送你的个人照片或手部图像。",
  },
  {
    title: "AR 摄像头",
    body: "AR 模式调用摄像头时，画面数据仅在内存中实时处理，不会被录制、存储或上传。",
  },
  {
    title: "本地保存",
    body: "你保存的试戴效果图默认存储在自己的设备上，我们不会收集或分析你的个人使用数据。",
  },
  {
    title: "联系我们",
    body: "如果你对隐私或数据流向有任何疑问，可以随时联系我们。我们会用清晰的语言解释每一项能力的边界。",
  },
];

export default function PrivacyPage() {
  return (
    <FlowingShell>
      <PageHero
        eyebrow="隐私政策"
        title="照片优先在本地处理"
        description="我们希望你知道每一次上传、试色和 AR 预览的数据流向。"
      />

      <div className="space-y-4">
        {sections.map((section) => (
          <GlassPanel key={section.title} className="p-5">
            <h2 className="mb-2 text-sm font-semibold text-[#4a4a4a]">{section.title}</h2>
            <p className="text-sm leading-7 text-gray-500">{section.body}</p>
          </GlassPanel>
        ))}
      </div>

      <p className="mt-6 text-center text-xs text-gray-400">最后更新：2026 年 7 月</p>
    </FlowingShell>
  );
}