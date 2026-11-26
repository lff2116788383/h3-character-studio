# -*- coding: utf-8 -*-
"""换装系统可行性验证:
  1) 素体 sheet (贴身打底衣, 身份锚点)
  2) 服装A sheet (原版同款) / 服装B sheet (全新绿袍) — 整套重生成路线
  3) 素体↔服装 逐帧光流配准误差 + diff 服装层提取 + 合成回放 — 分层部件路线
产出: output/swap/ 下 body/outfitA/outfitB + metrics.json + 预览图
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import fit_canvas, matte_cell, slice_sheet  # noqa: E402
from gen_sheets import CELLS  # noqa: E402
from gpt_client import generate_img2img  # noqa: E402

WORK = HERE / "output" / "swap"
WORK.mkdir(parents=True, exist_ok=True)
MASTER = HERE / "output" / "compare_master_right.png"

LAYOUT = ("A sprite sheet of EXACTLY 4 columns and 2 rows, 8 equal cells in reading order. "
          "Each cell: same character, same scale, feet on the same ground line, centered, "
          "fixed elevated orthographic front three-quarter view facing screen right, walking "
          "in place with large clear leg swing and arm counter-swing. Flat uniform solid "
          "#ff00ff magenta background in every cell, no cell borders, no labels, no text, no "
          "shadow, one single character per cell. Crisp clean outlines, coherent cel shading.")

BODY_PROMPT = (
    "Redraw the exact character from the reference image wearing ONLY a plain tight white "
    "sleeveless undershirt and simple dark fitted shorts: bare arms, bare shoulders, bare "
    "lower legs, no cape, no skirt, no satchel, no jewelry, no boots (plain cloth shoes). "
    "Preserve her face, hairstyle, twin braids, silver hair cuffs and moon headdress exactly. "
    "Same adult-chibi proportions, same scale. " + LAYOUT
)

OUTFIT_PROMPT = (
    "Two reference images. The FIRST reference shows the character's face, hairstyle and "
    "identity. The SECOND is an 8-cell body sheet of the same character in a tight base "
    "layer. Produce the SAME 8-cell layout with the SAME walk poses cell-by-cell as the "
    "SECOND reference, but the character now wears: {outfit} Keep body pose, scale, ground "
    "line and on-screen position identical to the SECOND reference cells; only the clothing "
    "changes. Face and hairstyle identical to the FIRST reference. " + LAYOUT
)

OUTFIT_A = ("her original outfit from the FIRST reference: dark navy wrapped jacket with "
            "silver trim, white necklace ornaments, wide belt with silver buckle, long red "
            "pleated skirt with white patterns, dark leggings, brown boots with red laces, "
            "and the small leather pouch.")
OUTFIT_B = ("a brand new outfit: long emerald-green hanfu robe with wide sleeves, golden "
            "sash with jade pendant, white inner collar, dark green trousers, black boots "
            "with gold buckles. No cape.")


def gen(path: Path, refs: list, prompt: str) -> None:
    if path.exists():
        print(f"[skip] {path.name}")
        return
    generate_img2img(prompt, refs, path, size="1024x1024")


def load_frames(sheet: Path) -> list[Image.Image]:
    return [fit_canvas(matte_cell(c)) for c in slice_sheet(sheet)]


def flow_stats(a: np.ndarray, b: np.ndarray) -> dict:
    """a,b: RGBA uint8 256x256. 返回 a→b 光流中位幅值(px, 限前景) 与脚线/质心偏差。"""
    ga = cv2.cvtColor(a[..., :3], cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(b[..., :3], cv2.COLOR_RGB2GRAY)
    ga[a[..., 3] == 0] = 0
    gb[b[..., 3] == 0] = 0
    flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 4, 17, 4, 7, 1.5, 0)
    mag = np.linalg.norm(flow, axis=-1)
    region = (a[..., 3] > 128) & (b[..., 3] > 128)
    med = float(np.median(mag[region])) if region.sum() else 0.0
    feet_a = int(np.argwhere(a[..., 3] > 128).T[0].max())
    feet_b = int(np.argwhere(b[..., 3] > 128).T[0].max())
    xa = np.argwhere(a[..., 3] > 128).T[1].mean()
    xb = np.argwhere(b[..., 3] > 128).T[1].mean()
    return {"flow_med_px": round(med, 2), "feet_dy": feet_b - feet_a, "cx_dx": round(float(xb - xa), 1)}


def diff_layer(body: np.ndarray, clothed: np.ndarray):
    """提取服装层: 相对素体的变化像素(颜色变化 或 新增剪影)。"""
    changed = (np.linalg.norm(clothed[..., :3].astype(np.float32) - body[..., :3].astype(np.float32), axis=-1) > 40)
    occlude = (clothed[..., 3] > 128) & (body[..., 3] < 128)
    mask = (changed | occlude) & (clothed[..., 3] > 128)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    layer = clothed.copy()
    layer[..., 3] = np.where(mask > 0, clothed[..., 3], 0)
    # 部件可拆性指标: 变化像素中贴着素体剪影边缘的比例(污染代理)
    edge = cv2.dilate((body[..., 3] > 128).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    contam = float((mask.astype(bool) & edge).sum()) / max(int(mask.sum()), 1)
    return layer, mask, {"mask_px": int(mask.sum()), "edge_contamination": round(contam, 3)}


def main() -> int:
    # 1-2) 三张 sheet
    gen(WORK / "body_sheet.png", [MASTER], BODY_PROMPT)
    gen(WORK / "outfitA_sheet.png", [MASTER, WORK / "body_sheet.png"], OUTFIT_PROMPT.format(outfit=OUTFIT_A))
    gen(WORK / "outfitB_sheet.png", [MASTER, WORK / "body_sheet.png"], OUTFIT_PROMPT.format(outfit=OUTFIT_B))

    body = load_frames(WORK / "body_sheet.png")
    A = load_frames(WORK / "outfitA_sheet.png")
    B = load_frames(WORK / "outfitB_sheet.png")
    n = min(len(body), len(A), len(B))
    body, A, B = body[:n], A[:n], B[:n]

    # 3) 配准与提取指标
    metrics = {"body_vs_A": [], "body_vs_B": [], "layer_B_f0": None, "layer_B_f4": None}
    for i in range(n):
        ba = np.asarray(body[i])
        metrics["body_vs_A"].append(flow_stats(ba, np.asarray(A[i])))
        metrics["body_vs_B"].append(flow_stats(ba, np.asarray(B[i])))
    layer0, mask0, m0 = diff_layer(np.asarray(body[0]), np.asarray(B[0]))
    layer4, mask4, m4 = diff_layer(np.asarray(body[4]), np.asarray(B[4]))
    metrics["layer_B_f0"] = m0
    metrics["layer_B_f4"] = m4
    # 合成回放: 素体帧 + B 的服装层 (按 construction 应≈B帧; 关键看边缘接缝)
    comp0 = np.asarray(body[0]).copy()
    mm = mask0 > 0
    comp0[mm] = layer0[mm]
    Image.fromarray(comp0).save(WORK / "composite_f0.png")
    Image.fromarray(layer0).save(WORK / "layer_f0.png")

    # 每张 sheet 内部 QC
    def qc(frames):
        masks = [np.asarray(f)[..., 3] > 128 for f in frames]
        ious = [np.logical_and(masks[i], masks[i + 1]).sum() / max(np.logical_or(masks[i], masks[i + 1]).sum(), 1)
                for i in range(len(masks) - 1)]
        loop = np.logical_and(masks[0], masks[-1]).sum() / max(np.logical_or(masks[0], masks[-1]).sum(), 1)
        return {"adjacent_mean": round(float(np.mean(ious)), 3), "loop": round(float(loop), 3)}
    metrics["qc"] = {"body": qc(body), "outfitA": qc(A), "outfitB": qc(B)}
    (WORK / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")

    # 预览: 行1= f0 (素体|A|B), 行2= f4, 行3= 提取演示(body0|B0|layer0|composite0)
    def row3(imgs, y):
        for k, im in enumerate(imgs):
            WORK_SHEET.paste(im, (k * (SIZE_P + GAP), y), im)
    SIZE_P, GAP = 256, 10
    WORK_SHEET = Image.new("RGB", (4 * (SIZE_P + GAP), 3 * (SIZE_P + 30)), (24, 24, 28))
    from PIL import ImageDraw
    d = ImageDraw.Draw(WORK_SHEET)
    row3([body[0], A[0], B[0]], 30); d.text((GAP, 8), "frame0: BODY | OUTFIT-A | OUTFIT-B", fill=(220, 220, 220))
    row3([body[4], A[4], B[4]], SIZE_P + 60); d.text((GAP, SIZE_P + 38), "frame4: BODY | OUTFIT-A | OUTFIT-B", fill=(220, 220, 220))
    row3([body[0], B[0], Image.fromarray(layer0), Image.fromarray(comp0)], 2 * (SIZE_P + 60))
    d.text((GAP, 2 * (SIZE_P + 38)), "layer route: BODY | CLOTHED-B | EXTRACTED-LAYER | BODY+LAYER", fill=(220, 220, 220))
    WORK_SHEET.save(WORK / "swap_preview.png")
    print(json.dumps({k: metrics[k] for k in ("qc", "layer_B_f0", "layer_B_f4")}, ensure_ascii=False))
    print("flow body_vs_A:", [m["flow_med_px"] for m in metrics["body_vs_A"]])
    print("flow body_vs_B:", [m["flow_med_px"] for m in metrics["body_vs_B"]])
    print(f"[done] → {WORK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
