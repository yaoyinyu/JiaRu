"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { UploadButton } from "@/components/UploadButton";
import { NailCanvas } from "@/components/NailCanvas";
import { ColorPalette } from "@/components/ColorPalette";
import { FINGER_NAMES } from "@/lib/utils";

export default function EditorPage() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [nailColors, setNailColors] = useState<string[]>(Array(5).fill("#E8A0BF"));
  const [activeFinger, setActiveFinger] = useState(0);
  const [brushSize] = useState(15);
  const currentColor = nailColors[activeFinger];

  useEffect(() => () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);

  const handleUpload = (file: File) => setImageUrl(URL.createObjectURL(file));
  const changeColor = (color: string) => {
    const updated = [...nailColors];
    updated[activeFinger] = color;
    setNailColors(updated);
  };
  const applyToAll = () => setNailColors(Array(5).fill(currentColor));

  return (
    <AppShell
      eyebrow="Photo Studio"
      title={imageUrl ? "在照片上试出你的心动甲色" : "上传一张照片，开始自由试色"}
      description="照片只在你的浏览器中处理。选择不同手指与颜色，像在真实甲片上一样轻松调整。"
    >
      {!imageUrl ? (
        <div className="grid gap-5 md:grid-cols-[1.25fr_.75fr]">
          <section className="rounded-[28px] border border-white/80 bg-white/65 p-3 shadow-[0_24px_70px_rgba(116,73,92,.10)] backdrop-blur-2xl sm:p-5">
            <UploadButton onUpload={handleUpload} />
          </section>
          <aside className="rounded-[28px] border border-white/75 bg-white/55 p-6 shadow-[0_20px_60px_rgba(116,73,92,.07)] backdrop-blur-xl">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-100 to-purple-100 text-xl">✦</span>
            <h2 className="mt-5 text-lg font-semibold text-[#4A4447]">获得更自然的效果</h2>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-[#90878C]">
              <li className="flex gap-3"><span className="text-[#D4749D]">01</span><span>选择光线均匀、手指清晰的正面照片</span></li>
              <li className="flex gap-3"><span className="text-[#D4749D]">02</span><span>逐个选择手指，可为每一指搭配不同颜色</span></li>
              <li className="flex gap-3"><span className="text-[#D4749D]">03</span><span>用撤销与重置随时回退，满意后保存到本地</span></li>
            </ul>
            <div className="mt-6 rounded-2xl border border-pink-100/70 bg-pink-50/55 px-4 py-3 text-xs leading-5 text-[#9A7C89]">🔒 本地优先：照片不会离开你的设备</div>
          </aside>
        </div>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="rounded-[30px] border border-white/80 bg-white/62 p-4 shadow-[0_24px_70px_rgba(116,73,92,.10)] backdrop-blur-2xl sm:p-6">
            <NailCanvas imageUrl={imageUrl} nailColors={nailColors} activeFinger={activeFinger} brushSize={brushSize} />
          </section>
          <aside className="rounded-[28px] border border-white/80 bg-white/70 p-5 shadow-[0_20px_60px_rgba(116,73,92,.08)] backdrop-blur-2xl lg:sticky lg:top-24">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#CF6F99]">Color Lab</p>
                <h2 className="mt-1 text-lg font-semibold text-[#4A4447]">手指与颜色</h2>
              </div>
              <button onClick={() => setImageUrl(null)} className="rounded-xl border border-pink-100 bg-white/80 px-3 py-2 text-xs text-[#9A7C89] transition hover:border-pink-200 hover:text-[#D4749D]">更换照片</button>
            </div>
            <div className="grid grid-cols-5 gap-1.5 rounded-2xl bg-pink-50/60 p-1.5">
              {FINGER_NAMES.map((name, index) => (
                <button key={name} onClick={() => setActiveFinger(index)} className={`rounded-xl px-1 py-2 text-[11px] transition ${activeFinger === index ? "bg-white font-medium text-[#CF6F99] shadow-sm" : "text-[#9B9297] hover:bg-white/60"}`}>{name}</button>
              ))}
            </div>
            <div className="my-5 flex items-center gap-3 rounded-2xl border border-pink-100/70 bg-white/70 p-3">
              <span className="h-9 w-9 rounded-full border-2 border-white shadow-[0_3px_12px_rgba(0,0,0,.12)]" style={{ backgroundColor: currentColor }} />
              <div className="min-w-0 flex-1">
                <p className="text-xs text-[#A1989D]">{FINGER_NAMES[activeFinger]}当前颜色</p>
                <p className="text-sm font-medium uppercase text-[#514A4E]">{currentColor}</p>
              </div>
              <button onClick={applyToAll} className="text-xs font-medium text-[#CF6F99] hover:text-[#B95580]">应用全部</button>
            </div>
            <ColorPalette selectedColor={currentColor} onSelectColor={changeColor} />
            <p className="mt-5 text-center text-xs leading-5 text-[#AAA1A6]">选色后，在指甲位置点击或拖动涂抹</p>
          </aside>
        </div>
      )}
    </AppShell>
  );
}
