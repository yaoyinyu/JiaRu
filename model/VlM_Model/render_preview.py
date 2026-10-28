"""把 matting.py 的输出整理成人能看的产物：框选图 + 单枚抠图 + 归一化纹理 + 汇总图。

用法：
    python render_preview.py out\run-nail\nail-01 out\input\nail-01.jpg out\nail-result

产物：
    boxes.jpg           原图上画出每个实例的框与编号
    cutout-<i>.png      单枚 RGBA 抠图（带 alpha）
    texture-<i>.png     旋正、等比缩放到 256x512 的纹理（供贴图/纹理库使用）
    cutouts-sheet.png   抠图横向汇总
    textures-sheet.png  纹理横向汇总
    nails.json          框坐标、面积、耗时
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

RUN = Path(sys.argv[1])
SRC = Path(sys.argv[2])
DST = Path(sys.argv[3])
DST.mkdir(parents=True, exist_ok=True)

TEX_W, TEX_H = 256, 512

result = json.loads((RUN / "result.json").read_text(encoding="utf-8"))
image = Image.open(SRC).convert("RGB")
rgba_full = image.convert("RGBA")

W, H = image.size
scale = min(1.0, 1400 / max(W, H))
board = image.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
draw = ImageDraw.Draw(board)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
except Exception:  # noqa: BLE001
    font = ImageFont.load_default()


def principal_angle(mask: np.ndarray) -> float:
    ys, xs = np.nonzero(mask)
    if len(xs) < 32:
        return 0.0
    x = xs - xs.mean()
    y = ys - ys.mean()
    mu20 = float((x * x).mean())
    mu02 = float((y * y).mean())
    mu11 = float((x * y).mean())
    return 0.5 * float(np.degrees(np.arctan2(2 * mu11, mu20 - mu02)))


def normalize_texture(crop: Image.Image) -> Image.Image:
    """把指甲旋正、缩放到统一尺寸，透明边缘保持 alpha。"""
    alpha = np.array(crop.getchannel("A"))
    ang = principal_angle(alpha > 127)
    rot = crop.rotate(-ang, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))
    bbox = rot.getchannel("A").getbbox()
    if bbox:
        rot = rot.crop(bbox)
    # 尖端朝上：比较上下两半的平均宽度
    a = np.array(rot.getchannel("A"))
    rows = (a > 127).sum(axis=1)
    half = len(rows) // 2
    if half and rows[:half].mean() > rows[half:].mean():
        rot = rot.rotate(180, expand=True)
    r = min(TEX_W / rot.width, TEX_H / rot.height)
    small = rot.resize((max(1, int(rot.width * r)), max(1, int(rot.height * r))), Image.LANCZOS)
    canvas = Image.new("RGBA", (TEX_W, TEX_H), (0, 0, 0, 0))
    canvas.alpha_composite(small, ((TEX_W - small.width) // 2, (TEX_H - small.height) // 2))
    return canvas


cutouts = []
textures = []
for item in result["instances"]:
    idx = item["index"]
    x1, y1, x2, y2 = item["bbox"]
    pad = int(0.06 * max(x2 - x1, y2 - y1)) + 4
    cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
    cx2, cy2 = min(W, x2 + pad), min(H, y2 + pad)

    bx1, by1, bx2, by2 = [int(round(v)) for v in item["box"]]
    draw.rectangle([bx1 * scale, by1 * scale, bx2 * scale, by2 * scale], outline=(255, 40, 90), width=4)
    draw.text((bx1 * scale + 6, by1 * scale + 4), f"#{idx}", fill=(255, 40, 90), font=font)

    alpha = Image.open(RUN / f"alpha-{idx}.png").convert("L")
    cut = rgba_full.copy()
    cut.putalpha(alpha)
    crop = cut.crop((cx1, cy1, cx2, cy2))
    crop.save(DST / f"cutout-{idx}.png")

    tex = normalize_texture(crop)
    tex.save(DST / f"texture-{idx}.png")
    textures.append((idx, tex, item["area"]))

    preview = Image.new("RGBA", crop.size, (32, 32, 36, 255))
    preview.alpha_composite(crop)
    cutouts.append((idx, preview.convert("RGB"), item["area"]))

board.save(DST / "boxes.jpg", quality=92)


def sheet(items, path, height, label):
    cells = []
    for idx, im, area in items:
        r = height / im.height
        cells.append((idx, im.resize((max(1, int(im.width * r)), height), Image.LANCZOS), area))
    padx, lab = 18, 30
    total = sum(c[1].width for c in cells) + padx * (len(cells) + 1)
    img = Image.new("RGB", (total, height + lab + padx * 2), (24, 24, 28))
    d = ImageDraw.Draw(img)
    x = padx
    for idx, im, area in cells:
        img.paste(im, (x, padx), im if im.mode == "RGBA" else None)
        d.text((x, padx + height + 4), f"#{idx} {area}px", fill=(220, 220, 230), font=font)
        x += im.width + padx
    img.save(path)
    print("写出", path.name, f"({label})")


sheet(cutouts, DST / "cutouts-sheet.png", 220, "抠图")
sheet([(i, t, a) for i, t, a in textures], DST / "textures-sheet.png", 300, "归一化纹理")

summary = {
    "image": SRC.name,
    "width": W,
    "height": H,
    "prompt": result["prompt"],
    "metrics": result["metrics"],
    "nails": [
        {"index": i["index"], "box": i["box"], "bbox": i["bbox"], "area": i["area"]}
        for i in result["instances"]
    ],
}
(DST / "nails.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"产物目录 {DST}：{len(cutouts)} 枚")
