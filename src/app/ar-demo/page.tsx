import Link from "next/link";

import { FlowingShell, GlassPanel, PageHero } from "@/components/FlowingShell";

const demoUrl = "http://localhost:8080/?embedded=jiaru-main";

export default function ArDemoPage() {
  return (
    <FlowingShell maxWidth="max-w-7xl" className="gap-6">
      <PageHero
        eyebrow="临时模型 Demo"
        title="JiaRu Nail AR 独立模型试跑"
        description="这里先把 JiaRu_生图 里的独立 AR demo 临时嵌入主项目，用来验证摄像头、纹理列表和实时试戴效果。"
      />

      <GlassPanel className="overflow-hidden p-4 sm:p-5">
        <div className="mb-4 flex flex-col gap-3 rounded-3xl border border-[#e8a0bf]/15 bg-white/60 p-4 text-sm leading-6 text-gray-500 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-semibold text-[#4a4a4a]">测试服务地址：{demoUrl}</p>
            <p>需要先保持 Python demo 服务运行在 8080 端口。点击 iframe 内的“启动摄像头”后，浏览器权限弹窗请选择允许。</p>
          </div>
          <Link
            href={demoUrl}
            target="_blank"
            className="inline-flex shrink-0 items-center justify-center rounded-full bg-[#d4749d] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_20px_rgba(212,116,157,0.22)] transition hover:-translate-y-0.5"
          >
            新窗口打开
          </Link>
        </div>

        <div className="overflow-hidden rounded-[28px] border border-white/70 bg-black shadow-[0_18px_60px_rgba(0,0,0,0.16)]">
          <iframe
            title="JiaRu Nail AR 模型 Demo"
            src={demoUrl}
            allow="camera; microphone; autoplay; fullscreen"
            className="h-[72vh] min-h-[620px] w-full border-0"
          />
        </div>
      </GlassPanel>
    </FlowingShell>
  );
}
