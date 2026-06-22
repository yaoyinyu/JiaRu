"use client";

import { PRESET_COLORS } from "@/lib/utils";

interface ColorPaletteProps {
  selectedColor: string;
  onSelectColor: (color: string) => void;
}

export function ColorPalette({ selectedColor, onSelectColor }: ColorPaletteProps) {
  return (
    <div className="w-full">
      {/* 预设颜色 */}
      <div className="flex flex-wrap gap-3 justify-center">
        {PRESET_COLORS.map((item) => (
          <button
            key={item.name}
            title={item.name}
            onClick={() => onSelectColor(item.color)}
            className={`w-10 h-10 rounded-full shadow-sm border-2 transition-all duration-200
              ${
                selectedColor === item.color
                  ? "ring-2 ring-offset-2 ring-pink-400 scale-110"
                  : "hover:scale-105"
              }
              ${item.color === "#FFFFFF" ? "border-gray-200" : "border-transparent"}
            `}
            style={{ backgroundColor: item.color }}
          />
        ))}
      </div>

      {/* 自定义颜色 */}
      <div className="flex items-center justify-center gap-2 mt-3">
        <span className="text-xs text-gray-400">自定义:</span>
        <input
          type="color"
          value={selectedColor}
          onChange={(e) => onSelectColor(e.target.value)}
          className="w-10 h-10 rounded-full cursor-pointer border-0 p-0"
        />
      </div>
    </div>
  );
}
