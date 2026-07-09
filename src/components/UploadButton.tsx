"use client";

interface UploadButtonProps {
  onUpload: (file: File) => void;
}

export function UploadButton({ onUpload }: UploadButtonProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  return (
    <label className="group flex h-56 w-full cursor-pointer flex-col items-center justify-center rounded-[28px] border border-dashed border-[#e8a0bf]/40 bg-white/65 p-6 text-center shadow-[0_8px_32px_rgba(232,160,191,0.08)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:bg-white/80 hover:shadow-[0_16px_42px_rgba(212,116,157,0.12)] active:scale-[0.99]">
      <span className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#fff5f7] to-[#ffe8ee] text-3xl shadow-[0_2px_8px_rgba(212,116,157,0.1),0_0_0_1px_rgba(232,160,191,0.12)_inset]">
        📷
      </span>
      <span className="text-base font-semibold text-[#4a4a4a]">点击上传手部照片</span>
      <span className="mt-2 text-xs leading-5 text-gray-400">支持 JPG / PNG / WebP，照片只在本地处理</span>
      <input
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleChange}
        className="hidden"
      />
    </label>
  );
}