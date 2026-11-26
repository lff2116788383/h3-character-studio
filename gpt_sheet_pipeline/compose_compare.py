# -*- coding: utf-8 -*-
"""最终对比合成: 原版帧 vs GPT 帧, 同一几何标注 + 同光照, 5 列面板。"""
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from normals import build_metal_mask, build_normals, lit_preview, load_frame  # noqa: E402

SIZE = 256
GEO = yaml.safe_load((HERE / "output/compare/geometry-shared.yaml").read_text(encoding="utf-8"))
LIGHTS = [("flat", None), ("left", [-0.7, 0.15, 0.6]), ("right", [0.7, 0.15, 0.6]), ("top", [0, -0.6, 0.8])]


def panels(frame_path: Path):
    data = load_frame(frame_path)
    normal = build_normals(GEO, np.asarray(data)[..., 3])
    metal = build_metal_mask(GEO, np.asarray(data)[..., 3])
    out = []
    for name, ld in LIGHTS:
        if ld is None:
            rgb = (np.asarray(data)[..., :3]).astype(np.uint8)
            out.append(np.dstack([rgb, np.asarray(data)[..., 3].astype(np.uint8)]))
        else:
            lit, _ = lit_preview(data, normal, metal, ld)
            out.append(lit)
    return out, normal


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, 22], fill=(20, 20, 24))
    d.text((8, 5), text, fill=(230, 230, 230))
    return img


orig_panels, orig_n = panels(HERE / "output/compare/orig_f0_canonical.png")
gpt_panels, gpt_n = panels(HERE / "output/compare/gpt_best_canonical.png")

cols = len(orig_panels)
gap = 8
W = cols * SIZE + (cols + 1) * gap
H = 2 * (SIZE + 26) + gap * 3 + 20
sheet = Image.new("RGB", (W, H), (24, 24, 28))
row_y = [gap + 26, gap * 2 + 26 * 2 + SIZE]
row_names = ["ORIGINAL (client frame 0)", "GPT sheet best frame"]
for ri, (name, panels_) in enumerate(zip(row_names, [orig_panels, gpt_panels])):
    y = row_y[ri]
    lab = label(Image.new("RGB", (W, 26), (24, 24, 28)), name)
    sheet.paste(lab, (0, y - 26))
    for ci, p in enumerate(panels_):
        x = gap + ci * (SIZE + gap)
        rgba = Image.fromarray(p, "RGBA")
        sheet.paste(rgba, (x, y), rgba)
# 法线图缩略附在右侧
th = 160
for ri, (nm, tag) in enumerate([(orig_n, "orig normal"), (gpt_n, "gpt normal")]):
    thumb = Image.fromarray(((nm * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)).resize((th, th))
    x = W - th - gap
    sheet.paste(thumb, (x, row_y[ri] + SIZE - th))
sheet.save(HERE / "output/compare/final_compare.png")
print("saved final_compare.png", sheet.size)
