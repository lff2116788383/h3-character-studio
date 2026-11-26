# -*- coding: utf-8 -*-
"""分层部件路线验证 (第二阶段): 不再 diff 提取, 改为"无形人台"部件生成——
  1) garment-only sheet: 只有绿袍悬浮(空心、保持穿着形状), 逐格跟随素体姿态/位置
  2) weapon-only sheet: 只有直刀, 跟随右手位置 (传奇式武器层)
  3) 合成: 素体帧 + 服装层(alpha-over) → 与整套路线的 outfitB 对比
产出: output/swap_parts/ 下 sheets + metrics + preview
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import MAGENTA, matte_cell, slice_sheet  # noqa: E402
from gpt_client import generate_img2img  # noqa: E402

WORK = HERE / "output" / "swap_parts"
WORK.mkdir(parents=True, exist_ok=True)
SWAP = HERE / "output" / "swap"
BODY_SHEET = SWAP / "body_sheet.png"        # 已验证的素体
OUTFIT_B = SWAP / "outfitB_sheet.png"       # 整套路线目标(对照)

GARMENT_PROMPT = (
    "Three reference images. The THIRD image shows the complete outfit to extract: a long "
    "emerald-green hanfu robe with wide sleeves, golden sash with jade pendant, white inner "
    "collar, dark green trousers, black boots with gold buckles. The SECOND image is an 8-cell "
    "sheet of the same character walking in a base layer. Produce the SAME 4-column 2-row "
    "8-cell layout: in each cell show ONLY this outfit as a hollow floating garment set, shaped "
    "exactly as if worn by an invisible person walking - follow the walk pose of each cell of "
    "the SECOND reference: sleeves bent at the elbows with the arm swing, robe hem swinging "
    "with the leg stride, sash and jade pendant at waist height, trousers and boots in the leg "
    "stride position. Place each garment at the exact on-screen position and scale where it "
    "sits on the body in the SECOND reference cells. Absolutely NO person and NO body: no "
    "head, no face, no hair, no neck, no skin, no hands, no flesh - only the hollow clothing. "
    "Collar and cuffs are open holes. Flat uniform solid #ff00ff magenta background in every "
    "cell, no cell borders, no labels, no text, no shadow. Crisp clean outlines, coherent cel "
    "shading, same art style as the references."
)

WEAPON_PROMPT = (
    "Reference image: an 8-cell sheet (4 columns x 2 rows) of a walking character seen from "
    "the side, facing right. Produce the SAME 4-column 2-row 8-cell layout: in each cell show "
    "ONLY a single Chinese dao saber - straight dark iron blade, small bronze guard, dark "
    "wrapped hilt with a red tassel - floating on magenta background, held as if gripped in "
    "the character's right hand: follow the right hand position and walking rhythm cell-by-cell "
    "of the reference sheet, blade angled naturally with the swing. The hilt grip end sits "
    "exactly where the reference character's right hand is in that cell. Absolutely NO hand, "
    "NO arm, NO body, NO person, NO clothes - only the saber. Flat uniform solid #ff00ff "
    "magenta background in every cell, no borders, no text, no shadow. Crisp clean outlines, "
    "cel shading, same art style as the reference."
)


def gen(path: Path, refs: list, prompt: str) -> None:
    if path.exists():
        print(f"[skip] {path.name}")
        return
    generate_img2img(prompt, refs, path, size="1024x1024")


def matte_layer(cell: Image.Image) -> Image.Image:
    """原位抠底(不裁剪不缩放, 保留 sheet 内定位), 去小碎块, 不做 keep_largest。"""
    rgb = np.asarray(cell.convert("RGB"), dtype=np.float32)
    dist = np.linalg.norm(rgb - MAGENTA, axis=-1)
    alpha = (dist > 70).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    fg = alpha > 0
    edge_band = cv2.dilate(fg.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    r2 = (r + b) / 2
    cast = edge_band & fg & (r > 60) & (b > 60) & (g < r2 - 15)
    rgb[..., 1][cast] = np.maximum(g[cast], r2[cast] * 0.88)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 40:
            alpha[labels == i] = 0
    rgba = np.dstack([rgb.clip(0, 255).astype(np.uint8), (alpha * 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA")


def cells_in_place(sheet: Path) -> list[Image.Image]:
    return [matte_layer(c) for c in slice_sheet(sheet)]


def robe_target_mask(body: np.ndarray, clothed: np.ndarray) -> np.ndarray:
    """整套路线的服装区域(对照真值): 相对素体变化 或 新增剪影。"""
    changed = np.linalg.norm(clothed[..., :3].astype(np.float32) - body[..., :3].astype(np.float32), axis=-1) > 40
    occlude = (clothed[..., 3] > 128) & (body[..., 3] < 128)
    m = (changed | occlude) & (clothed[..., 3] > 128)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return m > 0


def best_offset(gmask: np.ndarray, target: np.ndarray, rng: int = 12) -> dict:
    """服装层 vs 目标区域的平移搜索: 返回 (0,0) 处 IoU 与最优偏移处的 IoU/偏移量。"""
    def iou_at(dx, dy):
        shifted = np.roll(np.roll(gmask, dy, axis=0), dx, axis=1)
        inter = (shifted & target).sum()
        union = (shifted | target).sum()
        return inter / max(union, 1)
    iou0 = iou_at(0, 0)
    best, bestdx, bestdy = iou0, 0, 0
    for dx in range(-rng, rng + 1, 2):
        for dy in range(-rng, rng + 1, 2):
            v = iou_at(dx, dy)
            if v > best:
                best, bestdx, bestdy = v, dx, dy
    return {"iou0": round(float(iou0), 3), "iou_best": round(float(best), 3),
            "best_dx": bestdx, "best_dy": bestdy}


def compose(body: Image.Image, layer: Image.Image) -> Image.Image:
    return Image.alpha_composite(body, layer)


def main() -> int:
    # 1) garment-only sheet × 2 attempts
    gen(WORK / "garment_a1.png", [BODY_SHEET, OUTFIT_B], GARMENT_PROMPT)
    gen(WORK / "garment_a2.png", [BODY_SHEET, OUTFIT_B], GARMENT_PROMPT)
    # 2) weapon-only sheet
    gen(WORK / "weapon_sheet.png", [BODY_SHEET], WEAPON_PROMPT)

    body = cells_in_place(BODY_SHEET)
    B = cells_in_place(OUTFIT_B)
    n = min(len(body), len(B))
    body, B = body[:n], B[:n]

    # 3) 服装层质量: vs 整套路线服装区域(真值)
    garment_sets = {}
    for tag in ("a1", "a2"):
        gl = cells_in_place(WORK / f"garment_{tag}.png")[:n]
        per = []
        for i in range(n):
            gm = np.asarray(gl[i])[..., 3] > 128
            tm = robe_target_mask(np.asarray(body[i]), np.asarray(B[i]))
            per.append({"mask_px": int(gm.sum()), **best_offset(gm, tm)})
        garment_sets[tag] = (gl, per)
    pick = max(garment_sets, key=lambda t: float(np.mean([p["iou0"] for p in garment_sets[t][1]])))
    glayer, gper = garment_sets[pick]
    print(f"[pick] garment attempt={pick}")

    # 4) 合成回放 + 与整套目标对比
    comp_stats = []
    comps = []
    for i in range(n):
        c = compose(body[i], glayer[i])
        comps.append(c)
        ca, ba = np.asarray(c), np.asarray(B[i])
        both = (ca[..., 3] > 128) & (ba[..., 3] > 128)
        sim = float(np.abs(ca[..., :3].astype(np.float32) - ba[..., :3].astype(np.float32))[both].mean()) if both.sum() else 999
        iou = both.sum() / max(((ca[..., 3] > 128) | (ba[..., 3] > 128)).sum(), 1)
        comp_stats.append({"sim_mad": round(sim, 1), "iou_vs_outfitB": round(float(iou), 3)})

    # 5) 武器层
    weapon = cells_in_place(WORK / "weapon_sheet.png")[:n]
    wpx = [int((np.asarray(w)[..., 3] > 128).sum()) for w in weapon]
    wcomp = [compose(body[i], weapon[i]) for i in range(min(n, len(weapon)))]

    metrics = {"picked": pick, "garment_per_frame": gper, "composite_vs_outfitB": comp_stats,
               "weapon_mask_px": wpx}
    (WORK / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")

    # 预览: 行1 f0, 行2 f4: BODY | GARMENT | BODY+GARMENT | TARGET-B ; 行3 武器: BODY|SWORD|COMP ×2帧
    SIZE_P, GAP = 256, 10
    W = Image.new("RGB", (4 * (SIZE_P + GAP), 3 * (SIZE_P + 30)), (24, 24, 28))
    d = ImageDraw.Draw(W)

    def put(imgs, y, label):
        for k, im in enumerate(imgs):
            W.paste(im, (k * (SIZE_P + GAP) + GAP, y), im)
        d.text((GAP, y - 22), label, fill=(220, 220, 220))

    put([body[0], glayer[0], comps[0], B[0]], 30, f"frame0: BODY | GARMENT({pick}) | BODY+GARMENT | TARGET-B")
    put([body[4], glayer[4], comps[4], B[4]], SIZE_P + 60, "frame4: BODY | GARMENT | BODY+GARMENT | TARGET-B")
    if len(wcomp) >= 5:
        put([body[0], weapon[0], wcomp[0], body[4], weapon[4], wcomp[4]], 2 * (SIZE_P + 60),
            "weapon layer: BODY | SWORD | BODY+SWORD (f0, f4)")
    W.save(WORK / "parts_preview.png")
    print(json.dumps({"iou0_mean": round(float(np.mean([p['iou0'] for p in gper])), 3),
                      "iou_best_mean": round(float(np.mean([p['iou_best'] for p in gper])), 3),
                      "offsets": [[p['best_dx'], p['best_dy']] for p in gper],
                      "comp_iou": [c['iou_vs_outfitB'] for c in comp_stats],
                      "weapon_px": wpx}, ensure_ascii=False))
    print(f"[done] → {WORK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
