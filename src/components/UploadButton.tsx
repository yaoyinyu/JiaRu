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
    <label className="flex flex-col items-center justify-center w-full h-48
                      bg-white rounded-2xl border-2 border-dashed border-pink-200
                      cursor-pointer hover:bg-pink-50 transition-colors">
      <span className="text-4xl mb-2">📷</span>
      <span className="text-sm text-gray-400">点击上传手部照片</span>
      <span className="text-xs text-gray-300 mt-1">支持 JPG / PNG</span>
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
