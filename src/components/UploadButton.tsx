"use client";

import { Icon } from "@/components/Icon";

interface UploadButtonProps {
  onUpload: (file: File) => void | Promise<void>;
}

export function UploadButton({ onUpload }: UploadButtonProps) {
  const handleChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await onUpload(file);
  };

  return (
    <label className="group relative flex min-h-[320px] w-full cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[24px] border border-dashed border-[#d9b3a6] bg-[radial-gradient(circle_at_50%_20%,rgba(207,163,150,.22),transparent_42%),rgba(255,255,255,.62)] px-6 text-center transition hover:border-[#ac5145] hover:bg-[var(--surface)] sm:min-h-[390px]">
      <span className="absolute inset-5 rounded-[20px] border border-[var(--line)] opacity-70" aria-hidden="true" />
      <span className="relative grid h-20 w-20 place-items-center rounded-[26px] bg-[var(--coral-soft)] shadow-[var(--neu-out-md)] transition duration-300 group-hover:-translate-y-1 group-hover:scale-105"><Icon name="upload" className="h-9 w-9 text-[#ac5145]" /></span>
      <span className="relative mt-6 text-base font-semibold text-[#292a27]">选择或拍摄手部照片</span>
      <span className="relative mt-2 max-w-xs text-xs leading-5 text-[#75766c]">支持 JPG、PNG 与 WebP，最大 10 MB，分辨率 320–4096 像素</span>
      <span className="relative mt-5 rounded-full border border-pink-100 bg-[var(--surface)] px-4 py-2 text-xs font-medium text-[#ac5145] shadow-sm">浏览照片</span>
      <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={handleChange} className="sr-only" />
    </label>
  );
}