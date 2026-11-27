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
      --sheet sheets/all_in_one_transparent_v1.png [--cell 256 256] \
      [--direction right]
输出: assets/<direction>/<motion>.png + assets/manifest.json(class-assets-v2,
      directions.<direction> 聚合) + sheets/transparent_rows_<tag>.png
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


def apply_row_fixes(cd: Path, rows: dict, cw: int, direction: str = "right") -> dict:
    """补行条整行替换(取最新 <motion>_row_fix_transparent[_<direction>]_v*.png)。

    透明原生做法: alpha 内容带裁上下空白 → 等比缩放到主 sheet 宽度 → 切 8 格。
    替换后帧高可与主 sheet 不同, 脚底对齐统一交给 align_frames, 无需手工补齐。
    (对应品红链 build_class_assets.load_sheet_rows 的 row_fix 逻辑, 透明版免背景估计)
    方向匹配: right 补行条无后缀, up/down 带方向后缀(与 gen_row --facing 命名一致)。
    """
    for motion in list(rows):
        pattern = (f"sheets/{motion}_row_fix_transparent_v*.png" if direction == "right"
                   else f"sheets/{motion}_row_fix_transparent_{direction}_v*.png")
        fixes = sorted(cd.glob(pattern), key=lambda p: p.stat().st_mtime)
        if not fixes:
            continue
        fix = Image.open(fixes[-1]).convert("RGBA")
        a = np.asarray(fix)[..., 3]
        ys = np.nonzero((a > 10).any(axis=1))[0]
        if len(ys):
            fix = fix.crop((0, int(ys[0]), fix.width, int(ys[-1]) + 1))
        s = (COLS * cw) / fix.width
        fix = fix.resize((COLS * cw, max(1, round(fix.height * s))), Image.LANCZOS)
        rows[motion] = [clean_cell(fix.crop((c * cw, 0, (c + 1) * cw, fix.height)))
                        for c in range(COLS)]
        print(f"[fix] {motion} ← {fixes[-1].name} (补行整行替换)")
    return rows


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
    ap.add_argument("--direction", default="right", choices=["right", "up", "down"],
                    help="朝向(四方向扩展): 各方向资产入 assets/<direction>/, "
                         "manifest(class-assets-v2) 按 directions.<direction> 聚合")
    args = ap.parse_args()
    cd, sheet_path, direction = args.class_dir, args.sheet, args.direction

    img = Image.open(sheet_path).convert("RGBA")
    w, h = img.size
    cw, ch = w // COLS, h // len(ROW_LAYOUT)
    print(f"[src] {sheet_path.name} {w}x{h} cell={cw}x{ch} mode=RGBA(原生透明)")

    rows = {}
    for r, motion in enumerate(ROW_LAYOUT):
        rows[motion] = [clean_cell(img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
                        for c in range(COLS)]
    rows = apply_row_fixes(cd, rows, cw, direction)

    # 行条拼图(透明底贴深灰底便于目检; 补行替换后帧高可不同, 统一缩到主行高)
    preview = Image.new("RGB", (COLS * cw, len(ROW_LAYOUT) * (ch + 4)), (24, 26, 30))
    for r, motion in enumerate(ROW_LAYOUT):
        for c in range(COLS):
            cell = rows[motion][c]
            if cell.height != ch:
                s = ch / cell.height
                cell = cell.resize((max(1, round(cell.width * s)), ch), Image.LANCZOS)
            preview.paste(cell, (c * cw, r * (ch + 4)), cell)
    tag = sheet_path.stem
    preview_path = sheet_path.parent / f"transparent_rows_{tag}.png"
    preview.save(preview_path, optimize=True)

    manifest = {"schema": "class-assets-v2", "class": cd.name, "directions": {}}
    mp = cd / "assets" / "manifest.json"
    if mp.exists():
        old = json.loads(mp.read_text(encoding="utf-8"))
        if isinstance(old.get("directions"), dict):
            manifest["directions"] = old["directions"]
        elif old.get("motions"):  # v1 扁平结构一次性迁移为 directions.right
            manifest["directions"]["right"] = {
                "source_sheet": old.get("source_sheet", ""),
                "pipeline": old.get("pipeline", "transparent-native"),
                "motions": old["motions"],
            }
    out_dir = cd / "assets" / direction
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest["directions"][direction] = {
        "source_sheet": sheet_path.name, "pipeline": "transparent-native", "motions": {},
    }
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
        manifest["directions"][direction]["motions"][motion] = {
            "sheet": out.name, "cols": COLS, "frames": COLS,
            "cell": [cw2, ch2], "fps": 11 if motion in ("walk", "run") else (6 if motion == "idle" else 8),
            "loop": motion in ("walk", "idle", "run"),
        }

    (cd / "assets" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (sheet_path.parent / f"transparent_qc_{tag}.json").write_text(
        json.dumps({m: qc_row(rows[m]) for m in ROW_LAYOUT if m not in EMPTY_ROWS},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] assets/{direction}/ → manifest.json(directions.{direction})  "
          f"行条预览: {preview_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
