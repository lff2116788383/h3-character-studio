# -*- coding: utf-8 -*-
"""实验: 高清母版 → 程序像素化 demo（真像素网格 + 量化色板）。

链路: 品红抠底 → bbox 裁剪 → BOX 降采样到目标像素高 → 中位切分量化色板
     → alpha 硬二值化(像素风无半透明) → NEAREST 放大回 cell 规格。
输出左右对比图: 左=原高清(抠底缩放), 右=像素化版(品红底)。

用法:
  python pixelate_demo.py [--src master_swordsman/walk_master.png]
                          [--target-h 56] [--colors 40] [--scale 4]
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
MAGENTA = np.array([255, 0, 255], dtype=np.float32)


def matte(img: Image.Image) -> Image.Image:
    """品红 chroma key + 形态学清理, 返回 RGBA。"""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    dist = np.linalg.norm(rgb - MAGENTA, axis=-1)
    alpha = (dist > 70).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha * 255]), "RGBA")


def pixelate(img: Image.Image, target_h: int, colors: int, scale: int) -> Image.Image:
    """高清 RGBA → 真像素 RGBA(NEAREST 放大)。"""
    bbox = img.getbbox()
    img = img.crop(bbox) if bbox else img
    w, h = img.size
    nw = max(1, round(w * target_h / h))
    small = img.resize((nw, target_h), Image.BOX)  # BOX 降采样比 LANCZOS 干净
    # 中位切分量化到统一色板(真像素感的核心: 颜色数有限)
    q = small.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT).convert("RGB")
    a = np.asarray(small.split()[3])
    a = np.where(a > 127, 255, 0).astype(np.uint8)  # alpha 硬二值化
    out = np.dstack([np.asarray(q), a])
    px = Image.fromarray(out, "RGBA")
    return px.resize((nw * scale, target_h * scale), Image.NEAREST)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=HERE / "master_swordsman" / "walk_master.png")
    ap.add_argument("--target-h", type=int, default=56, help="角色真像素高度(逸剑风约 48~64)")
    ap.add_argument("--colors", type=int, default=40)
    ap.add_argument("--scale", type=int, default=4)
    args = ap.parse_args()

    src = Image.open(args.src)
    px = pixelate(matte(src), args.target_h, args.colors, args.scale)
    grid_w = px.width // args.scale

    # 贴 256×256 cell(脚底 y=240 居中), 再铺品红底做母版同款底色
    cell = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    cell.paste(px, (128 - px.width // 2, 240 - px.height), px)
    mag = Image.new("RGBA", (256, 256), (255, 0, 255, 255))
    mag.alpha_composite(cell)

    # 对比图: 左=原高清抠底, 右=像素化(品红底)
    left = matte(src)
    lb = left.getbbox()
    left = left.crop(lb) if lb else left
    left.thumbnail((256, 256), Image.LANCZOS)
    board = Image.new("RGBA", (560, 320), (28, 28, 32, 255))
    board.paste(left, (30, 290 - left.height), left)
    board.paste(mag, (300, 290 - mag.height), mag)
    out = args.src.with_name(f"pixelate_demo_{args.src.stem}.png")
    board.save(out)
    print(f"[ok] pixel grid {grid_w}x{args.target_h} (x{args.scale}, {args.colors} colors) -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
