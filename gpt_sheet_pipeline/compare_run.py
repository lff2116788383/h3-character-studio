# -*- coding: utf-8 -*-
"""对比实验驱动: 一次性生成 3 张 sheet → QC 评分 → 选优放入 output/compare/right/。"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fit_canvas, matte_cell, slice_sheet  # noqa: E402
from gen_sheets import CELLS, PROMPT, phase_for  # noqa: E402
from gpt_client import generate_img2img  # noqa: E402

HERE = Path(__file__).resolve().parent
MASTER = HERE / "output" / "compare_master_right.png"
WORK = HERE / "output" / "compare"
WORK.mkdir(parents=True, exist_ok=True)


def score_sheet(sheet_path: Path):
    masks, frames = [], []
    for cell in slice_sheet(sheet_path):
        f = fit_canvas(matte_cell(cell))
        frames.append(f)
        masks.append(np.asarray(f)[..., 3] > 128)
    ious = []
    for i in range(len(masks) - 1):
        inter = np.logical_and(masks[i], masks[i + 1]).sum()
        union = np.logical_or(masks[i], masks[i + 1]).sum()
        ious.append(inter / max(union, 1))
    inter = np.logical_and(masks[0], masks[-1]).sum()
    union = np.logical_or(masks[0], masks[-1]).sum()
    loop = inter / max(union, 1)
    cxs = [np.argwhere(m).T[1].mean() for m in masks]
    return {"adjacent_mean": float(np.mean(ious)), "adjacent_min": float(np.min(ious)),
            "loop": float(loop), "x_drift": float(max(cxs) - min(cxs)), "frames": frames}


def main() -> int:
    prompt = PROMPT.format(cols=4, rows=2, facing="screen RIGHT", start=0, end=CELLS - 1,
                           f0=0, phase0=phase_for(0))
    results = {}
    for r in range(3):
        out = WORK / f"sheet-{r}.png"
        generate_img2img(prompt, [MASTER], out, size="1024x1024")
        s = score_sheet(out)
        results[r] = s
        print(f"[score] sheet-{r}: adjacent_mean={s['adjacent_mean']:.3f} "
              f"min={s['adjacent_min']:.3f} loop={s['loop']:.3f} x_drift={s['x_drift']:.1f}px", flush=True)
    best = max(results, key=lambda r: results[r]["adjacent_mean"] * 0.5 + results[r]["loop"] * 0.5)
    print(f"[best] sheet-{best}")
    dest = WORK / "right"
    dest.mkdir(exist_ok=True)
    shutil.copy(WORK / f"sheet-{best}.png", dest / "sheet-00.png")
    for r in results:  # 每张 sheet 的帧预览
        sheet = Image.new("RGB", (256 * 4 + 30, 256 * 2 + 10), (36, 36, 42))
        for i, f in enumerate(results[r]["frames"]):
            sheet.paste(f, ((i % 4) * (256 + 10), (i // 4) * (256 + 10)), f)
        sheet.save(WORK / f"preview-sheet-{r}.png")
    print(f"[done] best → {dest/'sheet-00.png'}, previews → preview-sheet-*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
