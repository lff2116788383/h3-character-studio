# -*- coding: utf-8 -*-
"""原型资产 prep: 抠透明 + 服装对素体的 sheet 级偏移校正 + 汇总数据。
产出: prototype/assets/*.png (RGBA) + prototype/prototype_data.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from swap_parts_test import cells_in_place, matte_layer  # noqa: E402

OUT = HERE / "prototype" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
COLS, ROWS = 4, 2
CW, CH = 256, 512

# walk 素体 head_top: 2026-11-26 按实测重标 (头冠线 51-52 + attack 校准 δ=22; x=实测头中心 121-123)。
# 教训: 首版沿用了 attack 的 y≈96-100 / x≈102-108, 但 walk 与 attack 素体是不同生成批次,
# 头冠线在 cell 内相差 26px, 真实头中心 x≈125.5 —— 曾导致 walk 全帧斗笠浮空 24~27px + 整体偏左 19px。
# 锚点表必须逐动作×方向实测, 不可跨动作复用。
WALK_HEAD_TOP = [[122, 73], [123, 74], [122, 74], [121, 74], [122, 73], [122, 74], [122, 74], [121, 74]]


def reassemble(cells: list[Image.Image], size=(CW, CH)) -> Image.Image:
    sheet = Image.new("RGBA", (size[0] * COLS, size[1] * ROWS), (0, 0, 0, 0))
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % COLS) * size[0], (i // COLS) * size[1]), c)
    return sheet


def matte_sheet(src: Path, dst: Path) -> list[Image.Image]:
    cells = cells_in_place(src)
    reassemble(cells).save(dst)
    return cells


def single_rgba(src: Path, dst: Path) -> tuple[int, int]:
    img = matte_layer(Image.open(src))
    bbox = img.getbbox()
    img = img.crop(bbox)
    img.save(dst)
    return img.size


def centroid(a: np.ndarray) -> tuple[float, float]:
    ys, xs = np.where(a[..., 3] > 128)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else (128.0, 256.0)


def sheet_offset(cloth_cells: list[Image.Image], body_cells: list[Image.Image]) -> list[int]:
    """cloth 相对 body 的全局偏移: 用头顶(bbox top)与脚线(bbox bottom)双基准, 取中位数."""
    dxs, dys = [], []
    for c, b in zip(cloth_cells, body_cells):
        cb, bb = np.asarray(c)[..., 3] > 10, np.asarray(b)[..., 3] > 10
        if cb.sum() < 50 or bb.sum() < 50:
            continue
        cys, cxs = np.where(cb)
        bys, bxs = np.where(bb)
        # 垂直: 头顶差 + 脚底差的均值; 水平: bbox 中心差
        dys.append(((cys.min() - bys.min()) + (cys.max() - bys.max())) / 2.0)
        dxs.append((cxs.min() + cxs.max()) / 2.0 - (bxs.min() + bxs.max()) / 2.0)
    if not dxs:
        return [0, 0]
    return [int(round(float(np.median(dxs)))), int(round(float(np.median(dys))))]


def main() -> None:
    # 1) 素体
    body_walk = matte_sheet(HERE / "output/swap/body_sheet.png", OUT / "body_walk.png")
    body_atk = matte_sheet(HERE / "output/attack/attack_body_a1.png", OUT / "body_attack.png")

    # 2) 服装 (walk + attack) + 全局偏移
    cloth = {}
    for mid, bf, bcells in (("walk", "outfit{X}_sheet.png", body_walk), ("attack", "cloth{X}_attack.png", body_atk)):
        for x in ("A", "B"):
            cells = matte_sheet(HERE / f"output/swap/{bf.format(X=x)}" if mid == "walk"
                                else HERE / f"output/attack/{bf.format(X=x)}",
                                OUT / f"cloth{x}_{mid}.png")
            off = sheet_offset(cells, bcells)
            cloth[f"{x}_{mid}"] = off
            print(f"[offset] cloth{x}_{mid}: dx={off[0]} dy={off[1]}")

    # 3) 小件
    wsize = single_rgba(HERE / "output/anchor_swap/weapon_single.png", OUT / "weapon_rgba.png")
    hsize = single_rgba(HERE / "output/attack/hat_single.png", OUT / "hat_rgba.png")
    print(f"[weapon] {wsize}, [hat] {hsize}")

    # 4) 锚点汇总
    walk_src = json.loads((HERE / "output/swap_parts/anchors.json").read_text(encoding="utf-8"))
    walk_anchors = []
    for i, f in enumerate(walk_src["frames"]):
        walk_anchors.append({"wrist_r": f["wrist_r"], "elbow_r": f["elbow_r"],
                             "ankle_a": f["ankle_a"], "ankle_b": f["ankle_b"],
                             "head_top": WALK_HEAD_TOP[i]})
    atk_src = json.loads((HERE / "output/attack/anchors_attack.json").read_text(encoding="utf-8"))
    atk_anchors = [{"wrist_r": f["wrist_r"], "elbow_r": f["elbow_r"], "head_top": f["head_top"]}
                   for f in atk_src["frames"]]

    data = {
        "cell": [CW, CH],
        "motions": {
            "idle": {"base": "walk", "frame": 0},
            "walk": {"frames": 8, "fps": 11, "loop": True,
                     "body": "assets/body_walk.png",
                     "cloth": {"A": "assets/clothA_walk.png", "B": "assets/clothB_walk.png"},
                     "clothOffset": {"A": cloth["A_walk"], "B": cloth["B_walk"]},
                     "anchors": walk_anchors, "weaponOrder": [0] * 8},
            "attack": {"frames": 8, "fps": 12, "loop": False,
                       "body": "assets/body_attack.png",
                       "cloth": {"A": "assets/clothA_attack.png", "B": "assets/clothB_attack.png"},
                       "clothOffset": {"A": cloth["A_attack"], "B": cloth["B_attack"]},
                       "anchors": atk_anchors, "weaponOrder": atk_src["weaponOrder"]},
        },
        "weapon": {"path": "assets/weapon_rgba.png", "size": list(wsize), "length": 220},
        "headwear": {"hat": {"path": "assets/hat_rgba.png", "size": list(hsize), "mountInsetUp": 0.04}},
    }
    (HERE / "prototype" / "prototype_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[done] prototype/prototype_data.json")


if __name__ == "__main__":
    main()
