# -*- coding: utf-8 -*-
"""实验: 一锅出全动作 sheet(all-in-one) 的 QC——切格/空格检测/行内连续性 IoU/行条预览。

用法:
  python qc_all_in_one.py [--src master_swordsman/all_in_one_v1.png] [--grid 8]
输出:
  <src目录>/all_in_one_rows.png      行条拼图(每行8格原尺寸, 非空行竖排)
  <src目录>/all_in_one_zoom_<r>.png  指定重点行动作条 1.6x 放大
  stdout 摘要 JSON
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
MAGENTA = np.array([255, 0, 255], dtype=np.float32)
ROW_NAMES = ["walk", "idle", "attack1", "attack2", "death", "run", "hit", "spare"]


def cell_mask(cell: Image.Image) -> np.ndarray:
    rgb = np.asarray(cell.convert("RGB"), dtype=np.float32)
    dist = np.linalg.norm(rgb - MAGENTA, axis=-1)
    return (dist > 70).astype(np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=HERE / "master_swordsman" / "all_in_one_v1.png")
    ap.add_argument("--grid", type=int, default=8)
    ap.add_argument("--zoom-rows", type=str, default="0,2,3", help="需要 1.6x 放大预览的行号")
    args = ap.parse_args()

    img = Image.open(args.src).convert("RGB")
    w, h = img.size
    cw, ch = w // args.grid, h // args.grid
    out_dir = args.src.parent
    report = {"src": args.src.name, "sheet_size": [w, h], "cell": [cw, ch], "rows": []}

    row_images = []
    for r in range(args.grid):
        cells, masks, foot_ys = [], [], []
        for c in range(args.grid):
            cell = img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            m = cell_mask(cell)
            cells.append((cell, m))
            masks.append(m)
        fg_counts = [int(m.sum()) for m in masks]
        filled = [i for i, n in enumerate(fg_counts) if n > 0.02 * cw * ch]
        ious = []
        for a, b in zip(filled, filled[1:]):
            ma, mb = masks[a], masks[b]
            inter = np.logical_and(ma, mb).sum()
            union = np.logical_or(ma, mb).sum()
            ious.append(round(float(inter / union), 3) if union else 1.0)
        foot = []
        for i in filled:
            ys = np.nonzero(masks[i].any(axis=1))[0]
            foot.append(int(ys[-1]) if len(ys) else -1)
        entry = {
            "row": r, "name": ROW_NAMES[r] if r < len(ROW_NAMES) else f"r{r}",
            "filled": filled, "empty": [i for i in range(args.grid) if i not in filled],
            "adjacent_IoU": ious, "foot_y": foot,
        }
        report["rows"].append(entry)
        if filled:
            row_img = Image.new("RGB", (args.grid * cw, ch), (20, 20, 24))
            for c in range(args.grid):
                row_img.paste(cells[c][0], (c * cw, 0))
            row_images.append((r, row_img))

    # 行条拼图(非空行竖排, 行间分隔)
    if row_images:
        gap = 6
        total_h = sum(im.height for _, im in row_images) + gap * (len(row_images) - 1)
        board = Image.new("RGB", (args.grid * cw, total_h), (12, 12, 14))
        y = 0
        for r, im in row_images:
            board.paste(im, (0, y))
            y += im.height + gap
        board.save(out_dir / "all_in_one_rows.png")

    # 重点行动作条放大
    for r in [int(x) for x in args.zoom_rows.split(",")]:
        if r < len(row_images) and row_images[r][1] is not None:
            zm = row_images[r][1].resize((int(args.grid * cw * 1.6), int(ch * 1.6)), Image.NEAREST)
            zm.save(out_dir / f"all_in_one_zoom_r{r}.png")

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
