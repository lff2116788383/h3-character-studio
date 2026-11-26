# -*- coding: utf-8 -*-
"""分层路线二次分析 v2:
  - 修正校准方向: best_offset 里 roll(+dy)=内容下移, 衣袍整体偏高 → 校准 = shift(g, +mdx, +mdy)
  - 单元格实为 256x512, 预览改为半尺寸缩略图 (128x256) 防重叠
  - 增加每帧最优偏移(per-frame)合成作为上限参照; 武器持手启发式用正确腰带高度带
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import slice_sheet  # noqa: E402
from swap_parts_test import cells_in_place, compose, robe_target_mask, best_offset  # noqa: E402

WORK = HERE / "output" / "swap_parts"
SWAP = HERE / "output" / "swap"


def shift(img: Image.Image, dx: int, dy: int) -> Image.Image:
    a = np.asarray(img)
    out = np.roll(np.roll(a, dy, axis=0), dx, axis=1)
    if dy > 0:
        out[:dy] = 0
    elif dy < 0:
        out[dy:] = 0
    if dx > 0:
        out[:, :dx] = 0
    elif dx < 0:
        out[:, dx:] = 0
    return Image.fromarray(out, "RGBA")


def main() -> int:
    metrics = json.loads((WORK / "metrics.json").read_text(encoding="utf-8"))
    gper = metrics["garment_per_frame"]
    mdx = int(np.median([p["best_dx"] for p in gper]))
    mdy = int(np.median([p["best_dy"] for p in gper]))
    print(f"[calibrate] global shift dx={mdx} dy={mdy}")

    body = cells_in_place(SWAP / "body_sheet.png")
    B = cells_in_place(SWAP / "outfitB_sheet.png")
    gl = cells_in_place(WORK / f"garment_{metrics['picked']}.png")
    weapon = cells_in_place(WORK / "weapon_sheet.png")
    n = min(len(body), len(B), len(gl), len(weapon))
    body, B, gl, weapon = body[:n], B[:n], gl[:n], weapon[:n]

    gl_cal = [shift(g, mdx, mdy) for g in gl]          # 全局校准(一次, sheet 级)
    gl_pf = [shift(g, p["best_dx"], p["best_dy"]) for g, p in zip(gl, gper)]  # 每帧最优(上限)

    variants = {"raw": gl, "cal_global": gl_cal, "cal_perframe": gl_pf}
    stats = {k: [] for k in variants}
    comps = {}
    for tag, layers in variants.items():
        cs = []
        for i in range(n):
            Baa = np.asarray(B[i])
            tm = robe_target_mask(np.asarray(body[i]), Baa)
            la = np.asarray(layers[i])
            gm = la[..., 3] > 128
            c = compose(body[i], layers[i])
            ca = np.asarray(c)
            both = (ca[..., 3] > 128) & (Baa[..., 3] > 128)
            iou = both.sum() / max(((ca[..., 3] > 128) | (Baa[..., 3] > 128)).sum(), 1)
            sim = float(np.abs(ca[..., :3].astype(np.float32) - Baa[..., :3].astype(np.float32))[both].mean()) if both.sum() else 999
            stats[tag].append({"layer_iou": round(float((gm & tm).sum() / max((gm | tm).sum(), 1)), 3),
                               "comp_iou": round(float(iou), 3), "comp_mad": round(sim, 1)})
            cs.append(c)
        comps[tag] = cs

    # 武器层: 单元格 256x512, 人物居中; 持手带 = 素体剪影 y 200-340 内右侧边缘
    wstats = []
    for i in range(n):
        wa = np.asarray(weapon[i])
        wm = wa[..., 3] > 128
        ba = np.asarray(body[i])
        bm = ba[..., 3] > 128
        band = bm[200:340, :]
        xs_body = np.where(band.any(axis=0))[0]
        hand_x = int(xs_body.max()) if len(xs_body) else 128
        if wm.sum() < 50:
            wstats.append({"mask_px": 0})
            continue
        ys, xs = np.where(wm)
        wstats.append({"mask_px": int(wm.sum()), "cx": int(xs.mean()), "cy": int(ys.mean()),
                       "body_right_x": hand_x, "cx_gap": int(xs.mean()) - hand_x,
                       "over_body_ratio": round(float((wm & bm).sum() / max(int(wm.sum()), 1)), 2)})

    (WORK / "metrics_calibrated.json").write_text(json.dumps(
        {"shift": [mdx, mdy], "stats": stats, "weapon": wstats}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 预览 v2: 半尺寸缩略图 128x256, 行距足够
    TH_W, TH_H, GAP = 128, 256, 8
    cols_row12 = ["BODY", "GARMENT-RAW", "CAL-GLOBAL", "CAL-PERFRAME", "COMP-CAL", "TARGET-B"]
    W_w = len(cols_row12) * (TH_W + GAP) + GAP
    W = Image.new("RGB", (W_w, 3 * (TH_H + 34)), (24, 24, 28))
    d = ImageDraw.Draw(W)

    def put(imgs, y, label):
        for k, im in enumerate(imgs):
            t = im.resize((TH_W, TH_H), Image.LANCZOS)
            W.paste(t, (GAP + k * (TH_W + GAP), y), t)
        d.text((GAP, y - 16), label, fill=(220, 220, 220))

    put([body[0], gl[0], gl_cal[0], gl_pf[0], comps["cal_global"][0], B[0]], 36,
        "f0: " + " | ".join(cols_row12))
    put([body[4], gl[4], gl_cal[4], gl_pf[4], comps["cal_global"][4], B[4]], TH_H + 70,
        "f4: " + " | ".join(cols_row12))
    put([body[0], weapon[0], comps["raw"][0], body[4], weapon[4], comps["raw"][4]],
        2 * (TH_H + 70), "weapon: BODY | SWORD | BODY+SWORD (f0/f4)")
    W.save(WORK / "parts_preview_cal.png")

    def mean(tag, key):
        return round(float(np.mean([s[key] for s in stats[tag]])), 3)
    print(json.dumps({
        "layer_iou": {k: mean(k, "layer_iou") for k in stats},
        "comp_iou": {k: mean(k, "comp_iou") for k in stats},
        "comp_mad_cal": round(float(np.mean([s["comp_mad"] for s in stats["cal_global"]])), 1),
        "weapon": wstats}, ensure_ascii=False))
    print(f"[done] → {WORK / 'parts_preview_cal.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
