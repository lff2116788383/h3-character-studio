# -*- coding: utf-8 -*-
"""Step 4t(透明直出): 透明 64 格 sheet → 每动作透明 sprite 资产 + manifest。

与 build_class_assets.py(品红链)的区别: 输入已是真 RGBA, **零抠图**——
无 matte/despill/腐蚀, 仅三步轻处理:
  1. alpha<10 归零(去噪)
  2. 二次连通域过滤删孤立碎块(透明直出偶发游离噪点, 面积阈值删)
  3. 脚底/水平对齐(同品红链 align_frames, 帧间稳定)
QC 用 alpha 直接算: 空格检测/相邻 IoU/脚底差, 比品红链的背景重估更简单可靠。

用法:
  python build_transparent_assets.py --class-dir swordsman \
      --sheet sheets/all_in_one_transparent_v1.png [--cell 256 256]
输出: assets/<motion>.png + assets/manifest.json + sheets/transparent_rows_<tag>.png
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_class_assets import ROW_LAYOUT, COLS, EMPTY_ROWS, align_frames  # noqa: E402


def clean_cell(cell: Image.Image) -> Image.Image:
    """透明原生清理: alpha<10 归零 + 小连通域删除。不动边缘(保留原生抗锯齿)。"""
    arr = np.asarray(cell).copy()
    alpha = arr[..., 3].astype(np.uint8)
    alpha[alpha < 10] = 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), 8)
    min_area = max(25, int(0.0004 * alpha.size))
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            alpha[labels == i] = 0
    arr[..., 3] = alpha
    return Image.fromarray(arr, "RGBA")


def qc_row(cells: list[Image.Image]) -> dict:
    """alpha 直读 QC: 覆盖率/空格/相邻 IoU/循环闭合/脚底差。"""
    masks = [np.asarray(c)[..., 3] > 128 for c in cells]
    cover = [float(m.mean()) for m in masks]
    empty = [i for i, c in enumerate(cover) if c < 0.02]
    ious = []
    for i in range(len(masks) - 1):
        inter = np.logical_and(masks[i], masks[i + 1]).sum()
        union = np.logical_or(masks[i], masks[i + 1]).sum()
        ious.append(inter / max(union, 1))
    loop = float(np.logical_and(masks[0], masks[-1]).sum() /
                 max(np.logical_or(masks[0], masks[-1]).sum(), 1))
    feet = []
    for m in masks:
        ys = np.nonzero(m.any(axis=1))[0]
        feet.append(int(ys[-1]) if len(ys) else -1)
    foot_ok = [f for f in feet if f >= 0]
    foot_spread = (max(foot_ok) - min(foot_ok)) if len(foot_ok) == len(cells) else -1
    return {"coverage": [round(c, 3) for c in cover], "empty_cells": empty,
            "adjacent_iou": [round(v, 3) for v in ious],
            "adjacent_iou_mean": round(float(np.mean(ious)), 3),
            "loop_closure_iou": round(loop, 3), "foot_spread_px": foot_spread}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", required=True, type=Path)
    ap.add_argument("--sheet", required=True, type=Path, help="透明 64 格 sheet")
    ap.add_argument("--cell", type=int, nargs=2, default=(256, 256))
    args = ap.parse_args()
    cd, sheet_path = args.class_dir, args.sheet

    img = Image.open(sheet_path).convert("RGBA")
    w, h = img.size
    cw, ch = w // COLS, h // len(ROW_LAYOUT)
    print(f"[src] {sheet_path.name} {w}x{h} cell={cw}x{ch} mode=RGBA(原生透明)")

    rows = {}
    for r, motion in enumerate(ROW_LAYOUT):
        rows[motion] = [clean_cell(img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
                        for c in range(COLS)]

    # 行条拼图(透明底贴深灰底便于目检)
    preview = Image.new("RGB", (COLS * cw, len(ROW_LAYOUT) * (ch + 4)), (24, 26, 30))
    for r, motion in enumerate(ROW_LAYOUT):
        for c in range(COLS):
            preview.paste(rows[motion][c], (c * cw, r * (ch + 4)), rows[motion][c])
    tag = sheet_path.stem
    preview_path = sheet_path.parent / f"transparent_rows_{tag}.png"
    preview.save(preview_path, optimize=True)

    manifest = {"schema": "class-assets-v1", "class": cd.name,
                "source_sheet": sheet_path.name, "pipeline": "transparent-native",
                "motions": {}}
    out_dir = cd / "assets"
    out_dir.mkdir(exist_ok=True)
    for motion in ROW_LAYOUT:
        if motion in EMPTY_ROWS:
            continue
        frames = rows[motion]
        qc = qc_row(frames)
        print(f"[qc] {motion}: mean_iou={qc['adjacent_iou_mean']} loop={qc['loop_closure_iou']} "
              f"foot_spread={qc['foot_spread_px']} empty={qc['empty_cells']}")
        if qc["empty_cells"]:
            print(f"[warn] {motion} 有空格, 仍导出但需人工复核")
        aligned = align_frames(frames, *args.cell)
        cw2, ch2 = aligned[0].size
        sheet = Image.new("RGBA", (cw2 * COLS, ch2), (0, 0, 0, 0))
        for i, f in enumerate(aligned):
            sheet.paste(f, (i * cw2, 0), f)
        out = out_dir / f"{motion}.png"
        sheet.save(out, optimize=True)
        manifest["motions"][motion] = {
            "sheet": out.name, "cols": COLS, "frames": COLS,
            "cell": [cw2, ch2], "fps": 11 if motion in ("walk", "run") else (6 if motion == "idle" else 8),
            "loop": motion in ("walk", "idle", "run"),
        }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (sheet_path.parent / f"transparent_qc_{tag}.json").write_text(
        json.dumps({m: qc_row(rows[m]) for m in ROW_LAYOUT if m not in EMPTY_ROWS},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {out_dir}/manifest.json  行条预览: {preview_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
