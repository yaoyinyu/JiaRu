"use client";

import { PRESET_COLORS } from "@/lib/utils";

interface ColorPaletteProps {
  selectedColor: string;
  onSelectColor: (color: string) => void;
}

export function ColorPalette({ selectedColor, onSelectColor }: ColorPaletteProps) {
  return (
    <div className="w-full">
      <div className="grid grid-cols-6 gap-2.5">
        {PRESET_COLORS.map((item) => (
          <button
            key={item.name}
            type="button"
            title={item.name}
            aria-label={`选择${item.name}`}
            aria-pressed={selectedColor === item.color}
            onClick={() => onSelectColor(item.color)}
            className={`aspect-square w-full rounded-full border-2 shadow-[0_4px_10px_rgba(63,48,55,.10)] transition duration-200 ${selectedColor === item.color ? "scale-110 border-white ring-2 ring-[#D4749D] ring-offset-2" : "border-white/80 hover:-translate-y-0.5 hover:scale-105"}`}
            style={{ backgroundColor: item.color }}
          />
        ))}
      </div>
      <label className="mt-5 flex items-center justify-between rounded-2xl border border-pink-100/70 bg-pink-50/45 px-4 py-3">
        <span><span className="block text-xs font-medium text-[#6B6166]">自定义颜色</span><span className="mt-0.5 block text-[10px] text-[#A79DA2]">打开系统取色器</span></span>
        <input type="color" value={selectedColor} onChange={(event) => onSelectColor(event.target.value)} className="h-10 w-10 cursor-pointer rounded-full border-0 bg-transparent p-0" />
      </label>
    </div>
  );
}
