# -*- coding: utf-8 -*-
"""锚点分层换装验证 (方案核心实验, 纯离线, 不碰 hd2d-mmo 客户端):
  A) 武器单图 + 锚点旋转变换 (传奇式: 刀只画 1 张, 27 帧位置由 腕/肘锚点 程序决定)
  B) 锚点引导衣服生成: 素体 sheet 带彩色锚点十字 → GPT 生成同布局绿袍(保留锚点)
     → 去锚点色得干净服装层, 与上轮"无形人台"层比动幅
  C) 合成回放: 素体 + 服装层 + 武器层 → 预览 + 指标
产出: output/anchor_swap/
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import MAGENTA, slice_sheet  # noqa: E402
from gpt_client import generate_img2img  # noqa: E402
from swap_parts_test import cells_in_place, compose, matte_layer  # noqa: E402

WORK = HERE / "output" / "anchor_swap"
WORK.mkdir(parents=True, exist_ok=True)
PARTS = HERE / "output" / "swap_parts"
SWAP = HERE / "output" / "swap"
MASTER = HERE / "output" / "compare_master_right.png"
ANCHORS = json.loads((PARTS / "anchors.json").read_text(encoding="utf-8"))

WEAPON_PROMPT = (
    "A single Chinese dao saber, game item sprite, VERTICAL with the blade pointing straight "
    "up and the grip at the bottom: straight dark iron blade with a bright edge, small bronze "
    "guard, dark wrapped hilt, red tassel tied at the pommel. The saber is centered and fills "
    "about 70 percent of the image height. Flat uniform solid #ff00ff magenta background, no "
    "person, no hand, no text, no shadow, no other objects. Crisp clean outlines, cel shading, "
    "same pixel-art style as the reference character."
)

GARMENT_PROMPT = (
    "Three reference images. FIRST: character identity (face, hair). SECOND: an 8-cell sheet "
    "(4 columns x 2 rows) of the character walking in a base layer, with colored cross markers "
    "on her body: red cross = weapon wrist, blue cross = elbow, green and yellow crosses = "
    "ankles. THIRD: the target outfit (emerald-green hanfu robe with wide sleeves, golden "
    "sash with jade pendant, dark green trousers, black boots). Produce the SAME 8-cell "
    "layout with the SAME walk poses cell-by-cell as the SECOND reference, the character now "
    "wearing the outfit from the THIRD reference. CRITICAL: the sleeve cuffs must follow the "
    "red/blue cross positions (arms swing), the robe hem and boots must follow the "
    "green/yellow ankle crosses (legs stride) - the clothing moves WITH the body in every "
    "cell. Keep the colored cross markers visible ON TOP of the clothing at the corresponding "
    "anchor locations, same colors, same positions. Face and hairstyle from the FIRST "
    "reference. Flat uniform solid #ff00ff magenta background in every cell, no borders, no "
    "text, no shadow. Crisp clean outlines, coherent cel shading."
)


def gen(path: Path, refs: list, prompt: str) -> None:
    if path.exists():
        print(f"[skip] {path.name}")
        return
    generate_img2img(prompt, refs, path, size="1024x1024")


def strip_anchors(img: Image.Image) -> Image.Image:
    """去除锚点十字 (红/蓝/亮绿/黄纯色), alpha 置 0。"""
    a = np.asarray(img).copy()
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    red = (r > 170) & (g < 90) & (b < 90)
    blue = (b > 170) & (r < 90) & (g < 90)
    green = (g > 190) & (r < 120) & (b < 120)
    yellow = (r > 200) & (g > 200) & (b < 100)
    m = red | blue | green | yellow
    # 只删小面积标记, 防止误伤大片服装色: 连通域面积 <= 400
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    kill = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] <= 400:
            kill |= (labels == i)
    a[..., 3][kill] = 0
    return Image.fromarray(a, "RGBA")


def flow_median(frames: list[Image.Image]) -> float:
    """部件层相邻帧光流中位 (动幅指标): 在两层 mask 并集区域上计算。"""
    vals = []
    for i in range(len(frames) - 1):
        a, b = np.asarray(frames[i]), np.asarray(frames[i + 1])
        ga = cv2.cvtColor(a[..., :3], cv2.COLOR_RGB2GRAY)
        gb = cv2.cvtColor(b[..., :3], cv2.COLOR_RGB2GRAY)
        ga[a[..., 3] == 0] = 0
        gb[b[..., 3] == 0] = 0
        flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 4, 17, 4, 7, 1.5, 0)
        mag = np.linalg.norm(flow, axis=-1)
        region = (a[..., 3] > 128) | (b[..., 3] > 128)
        if region.sum() > 200:
            vals.append(float(np.median(mag[region])))
    return round(float(np.mean(vals)), 3) if vals else 0.0


def qc_adjacent(frames: list[Image.Image]) -> float:
    masks = [np.asarray(f)[..., 3] > 128 for f in frames]
    ious = [np.logical_and(masks[i], masks[i + 1]).sum() / max(np.logical_or(masks[i], masks[i + 1]).sum(), 1)
            for i in range(len(masks) - 1)]
    return round(float(np.mean(ious)), 3)


def load_weapon(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    layer = matte_layer(img)
    bbox = layer.getbbox()
    return layer.crop(bbox) if bbox else layer


def place_weapon(body: Image.Image, weapon: Image.Image, wrist, elbow,
                 target_len: float = 210.0) -> tuple[Image.Image, dict]:
    """刀(原图竖直刃朝上) 旋转到前臂方向, 握把贴手腕锚点。"""
    w, h = weapon.size
    scale = target_len / h
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    wp = weapon.resize((nw, nh), Image.LANCZOS)
    # 前臂方向角 (图像坐标 y 向下)
    ang = math.degrees(math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0]))
    # 原刀竖直向上 = -90°; PIL rotate 逆时针为正(图像坐标需取负)
    rot = -(ang + 90.0)
    wr = wp.rotate(rot, expand=True, resample=Image.BICUBIC)
    # 握把点 = 原图底部中点, 旋转后在 expand 画布中的位置
    cx, cy = nw / 2, nh / 2
    gx0, gy0 = nw / 2, nh  # 握把(未旋转)
    theta = math.radians(rot)
    # PIL rotate: 逆时针(屏幕) => 在图像坐标系中的旋转公式
    dx, dy = gx0 - cx, gy0 - cy
    rx = dx * math.cos(theta) + dy * math.sin(theta)
    ry = -dx * math.sin(theta) + dy * math.cos(theta)
    grip = (wr.width / 2 + rx, wr.height / 2 + ry)
    px = int(round(wrist[0] - grip[0]))
    py = int(round(wrist[1] - grip[1]))
    canvas = Image.new("RGBA", body.size, (0, 0, 0, 0))
    canvas.paste(wr, (px, py), wr)
    return compose(body, canvas), {"angle": round(ang, 1), "grip_at": [int(wrist[0]), int(wrist[1])]}


def main() -> int:
    # A) 武器单图 (只生成 1 张)
    gen(WORK / "weapon_single.png", [MASTER], WEAPON_PROMPT)
    # B) 锚点引导绿袍 sheet × 2 抽
    gen(WORK / "garment_anchor_a1.png", [MASTER, PARTS / "body_anchored_sheet.png", SWAP / "outfitB_sheet.png"], GARMENT_PROMPT)
    gen(WORK / "garment_anchor_a2.png", [MASTER, PARTS / "body_anchored_sheet.png", SWAP / "outfitB_sheet.png"], GARMENT_PROMPT)

    body = cells_in_place(SWAP / "body_sheet.png")
    B = cells_in_place(SWAP / "outfitB_sheet.png")
    prev = cells_in_place(PARTS / "garment_a1.png")  # 上轮无形人台层
    n = min(len(body), len(B), len(prev))
    body, B, prev = body[:n], B[:n], prev[:n]

    # 新服装层 (去锚点色), 按 QC 选优
    sets = {}
    for tag in ("a1", "a2"):
        gl = [strip_anchors(c) for c in cells_in_place(WORK / f"garment_anchor_{tag}.png")][:n]
        sets[tag] = {"layers": gl, "qc": qc_adjacent(gl), "flow": flow_median(gl)}
    pick = max(sets, key=lambda t: sets[t]["qc"])
    glayer = sets[pick]["layers"]
    print(f"[pick] anchored garment={pick}")

    # 动幅对比: 上轮无形人台 vs 锚点引导
    motion = {"prev_mannequin_flow": flow_median(prev),
              "anchored_flow": sets[pick]["flow"],
              "anchored_qc": sets[pick]["qc"], "other_qc": sets["a2" if pick == "a1" else "a1"]["qc"]}

    # A) 武器逐帧锚点放置
    weapon = load_weapon(WORK / "weapon_single.png")
    print(f"[weapon] sprite size={weapon.size}")
    weapon_info = []
    comp_weapon = []
    for i in range(n):
        f = ANCHORS["frames"][i]
        c, info = place_weapon(body[i], weapon, f["wrist_r"], f["elbow_r"])
        comp_weapon.append(c)
        weapon_info.append(info)

    # C) 总合成: 素体+服装层, 再+武器
    comps, full = [], []
    comp_stats = []
    for i in range(n):
        c = compose(body[i], glayer[i])
        comps.append(c)
        f = ANCHORS["frames"][i]
        fc, _ = place_weapon(c, weapon, f["wrist_r"], f["elbow_r"])
        full.append(fc)
        ca, ba = np.asarray(c), np.asarray(B[i])
        both = (ca[..., 3] > 128) & (ba[..., 3] > 128)
        iou = both.sum() / max(((ca[..., 3] > 128) | (ba[..., 3] > 128)).sum(), 1)
        comp_stats.append(round(float(iou), 3))

    (WORK / "metrics.json").write_text(json.dumps(
        {"picked": pick, "motion": motion, "comp_iou_vs_outfitB": comp_stats,
         "weapon": weapon_info}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 预览: 行1 f0 行2 f4: BODY|GARMENT|BODY+GARMENT|+WEAPON|TARGET-B; 行3 武器4帧
    TH_W, TH_H, GAP = 128, 256, 8
    W_img = Image.new("RGB", (5 * (TH_W + GAP) + GAP, 3 * (TH_H + 34)), (24, 24, 28))
    d = ImageDraw.Draw(W_img)

    def put(imgs, y, label):
        for k, im in enumerate(imgs):
            t = im.resize((TH_W, TH_H), Image.LANCZOS)
            W_img.paste(t, (GAP + k * (TH_W + GAP), y), t)
        d.text((GAP, y - 16), label, fill=(220, 220, 220))

    put([body[0], glayer[0], comps[0], full[0], B[0]], 36,
        "f0: BODY | GARMENT-ANCHORED | BODY+GARMENT | +WEAPON | TARGET-B")
    put([body[4], glayer[4], comps[4], full[4], B[4]], TH_H + 70,
        "f4: BODY | GARMENT-ANCHORED | BODY+GARMENT | +WEAPON | TARGET-B")
    put([comp_weapon[0], comp_weapon[2], comp_weapon[4], comp_weapon[6], weapon],
        2 * (TH_H + 70), "weapon on anchors f0/f2/f4/f6 + single sprite")
    W_img.save(WORK / "anchor_preview.png")

    print(json.dumps({"motion": motion, "comp_iou": comp_stats}, ensure_ascii=False))
    print(f"[done] → {WORK / 'anchor_preview.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
