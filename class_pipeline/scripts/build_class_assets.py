# -*- coding: utf-8 -*-
"""Step 4: 一锅出 sheet → 每动作透明底 sprite 资产 + manifest.json。

流程: 按 ROW_LAYOUT 切格(补行条优先覆盖对应动作) → 背景重估抠底(复用
common.matte_cell 思路 + 边框环带背景重估, 抗暗角) → 脚底/水平对齐到统一
cell → 拼每动作 8 格透明 sheet(原生分辨率, 不放大保清晰) → 写 manifest。

用法:
  python build_class_assets.py --class-dir class_pipeline/swordsman
  python build_class_assets.py --class-dir class_pipeline/swordsman --cell 256 256
输出:
  <class-dir>/assets/<motion>.png        8 格透明底 sheet (cols=8, frames=8)
  <class-dir>/assets/manifest.json       {motion: {sheet, cols, frames, cell, dir}}
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys_path = str(HERE)
import sys  # noqa: E402

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)
from common import MAGENTA  # noqa: E402  (本目录自包含副本)

import cv2  # noqa: E402

# 与 gen_all_in_one.py 的 ROW_LAYOUT 保持一致: 行号 → 动作名
ROW_LAYOUT = ["walk", "idle", "attack1", "attack2", "death", "run", "hit", "spare"]
COLS = 8
EMPTY_ROWS = {"hit", "spare"}  # 纯品红/不足 8 格的行不产资产


def cell_bg(cell_rgb: np.ndarray, band: int = 3) -> np.ndarray:
    ring = np.concatenate([
        cell_rgb[:band].reshape(-1, 3),
        cell_rgb[-band:].reshape(-1, 3),
        cell_rgb[:, :band].reshape(-1, 3),
        cell_rgb[:, -band:].reshape(-1, 3),
    ])
    return np.median(ring, axis=0).astype(np.float32)


def matte_cell(cell: Image.Image) -> Image.Image | None:
    """背景重估抠底 + 形态学清理 + 最大连通域 + 描边 despill。空格返回 None。

    despill(继承自 common.matte_cell): 前景边缘带内的品红偏色像素(绿通道被压低)
    抬回中性色——不处理会出现品红 halo 描边。
    """
    rgb = np.asarray(cell.convert("RGB"), dtype=np.float32)
    dist = np.linalg.norm(rgb - cell_bg(rgb), axis=-1)
    alpha = (dist > 60).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, connectivity=8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha = (labels == biggest).astype(np.uint8)
    if alpha.mean() < 0.03:
        return None
    # v3: 1px 腐蚀吃掉轮廓 halo 环 + 全局去品红(发梢/衣料混入品红的过渡像素在
    # 前景内部, 边缘带 despill 够不着)。判定 r、b 同高且 g 显著低 = 品红系;
    # 红腰带/流苏 b 低不受影响。
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8), iterations=1)
    # v3.1: 腐蚀会把原本细桥连接的脏边碎块切成孤岛(悬空白点), 二次连通域过滤
    n2, labels2, stats2, _ = cv2.connectedComponentsWithStats(alpha, connectivity=8)
    if n2 > 1:
        min_area = max(25, int(0.0004 * alpha.size))
        for i in range(1, n2):
            if stats2[i, cv2.CC_STAT_AREA] < min_area:
                alpha[labels2 == i] = 0
    fg = alpha > 0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    r2 = (r + b) / 2
    m = r2 - g
    cast = fg & (r > 90) & (b > 90) & (m > 20)
    rgb[..., 0][cast] -= m[cast] * 0.7
    rgb[..., 2][cast] -= m[cast] * 0.7
    rgb[..., 1][cast] += m[cast] * 0.35
    return Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha * 255]), "RGBA")


def align_frames(frames: list[Image.Image], cell_w: int, cell_h: int) -> list[Image.Image]:
    """脚底对齐: 每帧按 alpha bbox 裁剪 → 以全部帧的最大宽/高归一化画布 →
    脚底贴同一水平线, 水平中心对齐(帧间脚底/重心稳定, 播放不抖)。"""
    cropped = []
    for f in frames:
        bbox = f.getbbox()
        cropped.append(f.crop(bbox) if bbox else f)
    max_w = max(f.width for f in cropped)
    max_h = max(f.height for f in cropped)
    cw, chh = max(max_w, cell_w), max(max_h, cell_h)
    out = []
    for f in cropped:
        canvas = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
        canvas.paste(f, (cw // 2 - f.width // 2, chh - f.height), f)
        out.append(canvas)
    return out


def load_sheet_rows(cd: Path) -> dict[str, list[Image.Image]]:
    """主 sheet 8 行切格; 有 <motion>_row_fix*.png 则整行替换为补行条切格。"""
    sheet_path = max(cd.glob("sheets/all_in_one_v*.png"), key=lambda p: p.stat().st_mtime)
    img = Image.open(sheet_path).convert("RGB")
    w, h = img.size
    cw, ch = w // COLS, h // len(ROW_LAYOUT)
    print(f"[src] {sheet_path.name} cell={cw}x{ch}")
    rows: dict[str, list[Image.Image]] = {}
    for r, motion in enumerate(ROW_LAYOUT):
        rows[motion] = [img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)) for c in range(COLS)]
    # 补行条整行替换(取最新): 先等比缩放到主 sheet 格尺寸, 再裁掉上下品红空白
    for motion in list(rows):
        fixes = sorted(cd.glob(f"sheets/{motion}_row_fix*.png"), key=lambda p: p.stat().st_mtime)
        if not fixes:
            continue
        fix = Image.open(fixes[-1]).convert("RGB")
        fix = fix.resize((COLS * cw, ch), Image.LANCZOS)  # 横条 8:1 ↔ 主格 8:1, 等比缩放
        arr = np.asarray(fix, dtype=np.float32)
        ring = np.concatenate([arr[:3].reshape(-1, 3), arr[-3:].reshape(-1, 3),
                               arr[:, :3].reshape(-1, 3), arr[:, -3:].reshape(-1, 3)])
        bg = np.median(ring, axis=0).astype(np.float32)
        fg_rows = (np.linalg.norm(arr - bg, axis=-1) > 60).any(axis=1)
        ys = np.nonzero(fg_rows)[0]
        top, bottom = (int(ys[0]), int(ys[-1]) + 1) if len(ys) else (0, ch)
        pad = max(2, (bottom - top) // 20)
        top, bottom = max(0, top - pad), min(ch, bottom + pad)
        rows[motion] = [fix.crop((c * cw, top, (c + 1) * cw, bottom)) for c in range(COLS)]
        print(f"[patch] {motion} ← {fixes[-1].name} (内容条 {bottom - top}px, 缩放至 {cw}x{ch})")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", required=True, type=Path)
    ap.add_argument("--cell", type=int, nargs=2, default=(256, 256), help="目标画布最小边(保持原生不放大)")
    args = ap.parse_args()
    cd = args.class_dir
    out_dir = cd / "assets"
    out_dir.mkdir(exist_ok=True)

    rows = load_sheet_rows(cd)
    manifest = {"schema": "class-assets-v1", "class": cd.name, "motions": {}}
    for motion in ROW_LAYOUT:
        if motion in EMPTY_ROWS:
            continue
        cells = [matte_cell(c) for c in rows[motion]]
        frames = [c for c in cells if c is not None]
        if len(frames) < COLS:
            print(f"[warn] {motion}: {len(frames)}/{COLS} 格有效, 跳过(先补行)")
            continue
        aligned = align_frames(frames, *args.cell)
        cw, chh = aligned[0].size
        sheet = Image.new("RGBA", (cw * COLS, chh), (0, 0, 0, 0))
        for i, f in enumerate(aligned):
            sheet.paste(f, (i * cw, 0), f)
        out = out_dir / f"{motion}.png"
        sheet.save(out, optimize=True)
        manifest["motions"][motion] = {
            "sheet": out.name, "cols": COLS, "frames": COLS,
            "cell": [cw, chh], "fps": 11 if motion in ("walk", "run") else (6 if motion == "idle" else 8),
            "loop": motion in ("walk", "idle", "run"),
        }
        print(f"[ok] {motion}: {COLS} 帧 cell={cw}x{chh} → {out.name}")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {out_dir}/manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
