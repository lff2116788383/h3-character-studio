# -*- coding: utf-8 -*-
"""公共工具: sheet 切片、品红抠底 + 描边去污染(depill)、脚底对齐。"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SIZE = 256
PIVOT = (128, 240)
MAGENTA = np.array([255, 0, 255], dtype=np.float32)
COLS, ROWS = 4, 2


def slice_sheet(sheet_path: Path) -> list[Image.Image]:
    img = Image.open(sheet_path)
    w, h = img.size
    cw, ch = w // COLS, h // ROWS
    cells = []
    for i in range(COLS * ROWS):
        col, row = i % COLS, i // COLS
        cells.append(img.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)))
    return cells


def matte_cell(cell: Image.Image) -> Image.Image:
    """品红 chroma key + 边缘去污染(despill) + 形态学清理。返回 RGBA。"""
    rgb = np.asarray(cell.convert("RGB"), dtype=np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    dist = np.linalg.norm(rgb - MAGENTA, axis=-1)
    alpha = (dist > 70).astype(np.uint8)
    # 形态学: 闭填小孔 → 开去噪点
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    fg = alpha > 0
    # 描边去污染: 前景边缘带内所有"品红偏色"像素(绿通道被压低)抬回中性色
    edge_band = cv2.dilate(fg.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    r2 = (r + b) / 2
    cast = edge_band & fg & (r > 60) & (b > 60) & (g < r2 - 15)
    rgb[..., 1][cast] = np.maximum(g[cast], r2[cast] * 0.88)
    rgba = np.dstack([rgb.clip(0, 255).astype(np.uint8), (fg * 255).astype(np.uint8)])
    out = Image.fromarray(rgba, "RGBA")
    # 保留最大连通域, 防止背景碎块
    return keep_largest(out)


def keep_largest(img: Image.Image) -> Image.Image:
    arr = np.asarray(img).copy()
    n, labels, stats, _ = cv2.connectedComponentsWithStats((arr[..., 3] > 0).astype(np.uint8), 8)
    if n <= 2:
        return img
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = 1 + int(np.argmax(areas))
    arr[..., 3][(labels > 0) & (labels != keep)] = 0
    return Image.fromarray(arr, "RGBA")


def fit_canvas(img: Image.Image, max_dim: int = 248) -> Image.Image:
    """裁 alpha bbox → 等比缩放(最长边≤max_dim) → 贴到 256 画布, 脚底 y=240, 水平居中 x=128。"""
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    scale = min(max_dim / max(w, h), 1.0) if max(w, h) > max_dim else min(max_dim / max(w, h), 1.0)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px, py = PIVOT
    canvas.paste(img, (px - nw // 2, py - nh), img)
    return canvas


def visible_bounds(img: Image.Image) -> list[int]:
    a = np.asarray(img)[..., 3]
    ys, xs = np.where(a > 10)
    if len(xs) == 0:
        return [0, 0, 0, 0]
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
