# -*- coding: utf-8 -*-
"""QC: 一锅出 sheet / 补行条的切格检查（空格检测 + 行内连续性 IoU + 行条拼图）。

v2 修正: 品红底有暗角/纹理, 固定 #ff00ff 阈值会把暗角判成前景
（v1 实验 foot_y 全=191、IoU 虚高 0.99 即此污染）。本版按格用
边框环带重估背景色, 并取最大连通域作前景。

用法:
  python qc_sheet.py --class-dir class_pipeline/swordsman              # 查最新 all_in_one
  python qc_sheet.py --sheet <path> --cols 8 --rows 1                  # 查补行条
输出:
  <sheet目录>/qc/<name>_rows.png      行条拼图(每行原尺寸, 非空行竖排)
  <sheet目录>/qc/<name>_report.json   机器可读报告
  stdout 摘要
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROW_NAMES = ["walk", "idle", "attack1", "attack2", "death", "run", "hit", "spare"]


def cell_bg(cell_rgb: np.ndarray, band: int = 3) -> np.ndarray:
    """用格子边框环带估计该格背景色(中位数, 抗暗角)。"""
    ring = np.concatenate([
        cell_rgb[:band].reshape(-1, 3),
        cell_rgb[-band:].reshape(-1, 3),
        cell_rgb[:, :band].reshape(-1, 3),
        cell_rgb[:, -band:].reshape(-1, 3),
    ])
    return np.median(ring, axis=0).astype(np.float32)


def cell_mask(cell_rgb: np.ndarray) -> np.ndarray:
    dist = np.linalg.norm(cell_rgb - cell_bg(cell_rgb), axis=-1)
    alpha = (dist > 60).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # 只保留最大连通域: 暗角残块/漂浮噪点不再计入前景
    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, connectivity=8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha = (labels == biggest).astype(np.uint8)
    return alpha


def qc_grid(img: Image.Image, cols: int, rows: int, row_names: list) -> dict:
    w, h = img.size
    cw, ch = w // cols, h // rows
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    report = {"sheet_size": [w, h], "cell": [cw, ch], "cols": cols, "rows": rows, "rows_data": []}
    row_images = []
    for r in range(rows):
        masks, foot_ys = [], []
        for c in range(cols):
            cell = rgb[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            m = cell_mask(cell)
            masks.append(m)
            ys = np.nonzero(m.any(axis=1))[0]
            foot_ys.append(int(ys[-1]) if len(ys) else -1)
        fg_ratio = [float(m.mean()) for m in masks]
        filled = [i for i, v in enumerate(fg_ratio) if v > 0.03]
        ious = []
        for a, b in zip(filled, filled[1:]):
            ma, mb = masks[a], masks[b]
            union = np.logical_or(ma, mb).sum()
            ious.append(round(float(np.logical_and(ma, mb).sum() / union), 3) if union else 1.0)
        name = row_names[r] if r < len(row_names) else f"r{r}"
        entry = {
            "row": r, "name": name, "filled": filled,
            "empty": [i for i in range(cols) if i not in filled],
            "fg_ratio": [round(v, 3) for v in fg_ratio],
            "adjacent_IoU": ious, "foot_y": foot_ys,
        }
        report["rows_data"].append(entry)
        if filled:
            strip = img.crop((0, r * ch, w, (r + 1) * ch))
            row_images.append((r, strip))
    report["nonempty_rows"] = [r for r, _ in row_images]
    return report, row_images


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", type=Path, help="默认查 sheets/ 下最新 all_in_one_v*.png")
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=8)
    args = ap.parse_args()

    if args.sheet is None:
        cd = args.class_dir
        if cd is None:
            raise SystemExit("需要 --sheet 或 --class-dir")
        args.sheet = max(cd.glob("sheets/all_in_one_v*.png"), key=lambda p: p.stat().st_mtime)

    img = Image.open(args.sheet).convert("RGB")
    report, row_images = qc_grid(img, args.cols, args.rows, ROW_NAMES)
    report["src"] = args.sheet.name

    out_dir = args.sheet.parent / "qc"
    out_dir.mkdir(exist_ok=True)
    stem = args.sheet.stem
    if row_images:
        gap = 6
        total_h = sum(im.height for _, im in row_images) + gap * (len(row_images) - 1)
        board = Image.new("RGB", (img.width, total_h), (12, 12, 14))
        y = 0
        for _, im in row_images:
            board.paste(im, (0, y))
            y += im.height + gap
        board.save(out_dir / f"{stem}_rows.png")
    (out_dir / f"{stem}_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # stdout 摘要
    print(f"== QC {args.sheet.name} ({img.width}x{img.height}) ==")
    for e in report["rows_data"]:
        flag = "OK " if not e["empty"] else "!! "
        iou_s = " ".join(f"{v:.2f}" for v in e["adjacent_IoU"])
        foot_spread = max(e["foot_y"]) - min(e["foot_y"]) if e["foot_y"] else -1
        print(f"{flag}r{e['row']} {e['name']:<8} filled={e['filled']} empty={e['empty']} "
              f"IoU[{iou_s}] footSpread={foot_spread}px")
    print(f"[out] {out_dir}/{stem}_rows.png, {stem}_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
