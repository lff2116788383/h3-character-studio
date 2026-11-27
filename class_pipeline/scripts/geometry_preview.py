# -*- coding: utf-8 -*-
"""geometry.yaml 标注预览: 部件叠加到帧上目检对齐, 标注迭代的基础工具。

把 tube 轴线/半径圈、ellipsoid 椭圆、silver_polys 多边形半透明叠加到
load_frame 归一化后的帧上, 输出 overlay.png。坐标错位一眼可见,
配合 normals.py 构成 "标注 → preview 目检 → normals 渲染" 迭代环。

用法:
    python geometry_preview.py <frame.png> <geometry.yaml> <out.png>
"""
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

from normals import load_frame, SIZE


def overlay(frame_arr: np.ndarray, geo: dict, out: Path) -> None:
    base = Image.fromarray(frame_arr.astype(np.uint8), "RGBA").convert("RGB")
    base = base.resize((SIZE * 2, SIZE * 2), Image.NEAREST)  # 放大2倍便于目检
    dr = ImageDraw.Draw(base, "RGBA")
    for part in geo["parts"]:
        if part["kind"] == "ellipsoid":
            cx, cy, rx, ry = part["spec"]
            dr.ellipse([(cx - rx) * 2, (cy - ry) * 2, (cx + rx) * 2, (cy + ry) * 2],
                       outline=(0, 255, 255, 220), width=2)
        else:  # tube
            pts = [(x * 2, y * 2) for x, y in part["points"]]
            dr.line(pts, fill=(255, 200, 0, 230), width=3)
            r = part["radius"] * 2
            for px, py in (pts[0], pts[-1]):
                dr.ellipse([px - r, py - r, px + r, py + r], outline=(255, 120, 0, 200), width=2)
        if part.get("region"):
            cx, cy, rx, ry = part["region"]
            dr.ellipse([(cx - rx) * 2, (cy - ry) * 2, (cx + rx) * 2, (cy + ry) * 2],
                       outline=(120, 120, 255, 140), width=1)
    for poly in geo.get("silver_polys", []):
        dr.polygon([(x * 2, y * 2) for x, y in poly], fill=(255, 0, 0, 110),
                   outline=(255, 0, 0, 255))
    base.save(out)
    print(f"[preview] {out}  (青=ellipsoid/region 黄=tube轴线 橙圈=半径 红=silver金属区)")


def main():
    frame, geo_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    frame_arr = load_frame(frame)
    geo = yaml.safe_load(geo_path.read_text(encoding="utf-8"))
    overlay(frame_arr, geo, out)


if __name__ == "__main__":
    main()
