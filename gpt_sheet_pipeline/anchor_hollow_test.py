# -*- coding: utf-8 -*-
"""空心+锚点 服装部件验证 (分层大件最后一环):
上轮 anchored 生成了完整角色(含头身), 本轮强制空心 + 保留锚点引导。
若成功: 大件也可分层; 若不稳: 采用"衣服锚点整套 + 小件单图分层"混合架构(乘法已被小件消除)。
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gpt_client import generate_img2img  # noqa: E402
from swap_parts_test import cells_in_place, compose  # noqa: E402
from anchor_swap_test import strip_anchors, qc_adjacent, flow_median, WORK as AWORK, PARTS, SWAP, MASTER  # noqa: E402

WORK = HERE / "output" / "anchor_hollow"
WORK.mkdir(parents=True, exist_ok=True)
ANCHORS = json.loads((PARTS / "anchors.json").read_text(encoding="utf-8"))

HOLLOW_PROMPT = (
    "Three reference images. FIRST: character identity reference. SECOND: an 8-cell sheet "
    "(4 columns x 2 rows) of a walking character with colored cross markers: red = wrist, "
    "blue = elbow, green/yellow = ankles. THIRD: the target outfit (emerald-green hanfu robe "
    "with wide sleeves, golden sash with jade pendant, dark green trousers, black boots). "
    "Produce the SAME 8-cell layout showing ONLY the outfit as HOLLOW FLOATING GARMENTS, as "
    "if worn by an invisible walking person: absolutely NO person - no head, no face, no "
    "hair, no neck, no skin, no hands, no body, only the empty clothing with open collar and "
    "cuffs. In each cell the sleeves bend following the red/blue cross positions, the robe "
    "hem and boots follow the green/yellow ankle crosses - the garment moves with the walk "
    "pose cell-by-cell. Keep the colored cross markers visible ON TOP of the garment at the "
    "corresponding positions. Garments positioned and scaled exactly where they sit on the "
    "body in the SECOND reference. Flat uniform solid #ff00ff magenta background in every "
    "cell, no borders, no text, no shadow. Crisp clean outlines, coherent cel shading."
)


def gen(path: Path, refs: list, prompt: str) -> None:
    if path.exists():
        print(f"[skip] {path.name}")
        return
    generate_img2img(prompt, refs, path, size="1024x1024")


def main() -> int:
    gen(WORK / "hollow_a1.png", [MASTER, PARTS / "body_anchored_sheet.png", SWAP / "outfitB_sheet.png"], HOLLOW_PROMPT)
    gen(WORK / "hollow_a2.png", [MASTER, PARTS / "body_anchored_sheet.png", SWAP / "outfitB_sheet.png"], HOLLOW_PROMPT)

    body = cells_in_place(SWAP / "body_sheet.png")
    B = cells_in_place(SWAP / "outfitB_sheet.png")
    n = min(len(body), len(B))
    body, B = body[:n], B[:n]

    sets = {}
    for tag in ("a1", "a2"):
        gl = [strip_anchors(c) for c in cells_in_place(WORK / f"hollow_{tag}.png")][:n]
        sets[tag] = {"layers": gl, "qc": qc_adjacent(gl)}
    pick = max(sets, key=lambda t: sets[t]["qc"])
    glayer = sets[pick]["layers"]
    print(f"[pick] hollow={pick}")

    # 合成 vs 整套目标
    comps, comp_iou = [], []
    for i in range(n):
        c = compose(body[i], glayer[i])
        comps.append(c)
        ca, ba = np.asarray(c), np.asarray(B[i])
        both = (ca[..., 3] > 128) & (ba[..., 3] > 128)
        comp_iou.append(round(float(both.sum() / max(((ca[..., 3] > 128) | (ba[..., 3] > 128)).sum(), 1)), 3))

    # 动幅: 袖口/下摆区域(锚点邻域)的帧间位移 —— 用服装层相邻帧 mask XOR 率辅助判断
    flow = flow_median(glayer)
    metrics = {"picked": pick, "qc": sets[pick]["qc"], "flow": flow,
               "comp_iou_vs_outfitB": comp_iou,
               "ref_full_body_anchored": {"comp_iou": [0.96, 0.943, 0.939, 0.952, 0.954, 0.95, 0.947, 0.954]},
               "ref_mannequin_no_anchor": {"comp_iou_mean": 0.795}}
    (WORK / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")

    TH_W, TH_H, GAP = 128, 256, 8
    W_img = Image.new("RGB", (5 * (TH_W + GAP) + GAP, 2 * (TH_H + 34)), (24, 24, 28))
    d = ImageDraw.Draw(W_img)

    def put(imgs, y, label):
        for k, im in enumerate(imgs):
            t = im.resize((TH_W, TH_H), Image.LANCZOS)
            W_img.paste(t, (GAP + k * (TH_W + GAP), y), t)
        d.text((GAP, y - 16), label, fill=(220, 220, 220))

    put([body[0], glayer[0], comps[0], B[0], comps[4]], 36,
        "f0: BODY | HOLLOW+ANCHOR | COMPOSITE | TARGET-B | COMPOSITE-f4")
    put([body[4], glayer[4], comps[4], B[4], comps[2]], TH_H + 70,
        "f4: BODY | HOLLOW+ANCHOR | COMPOSITE | TARGET-B | COMPOSITE-f2")
    W_img.save(WORK / "hollow_preview.png")
    print(json.dumps({"qc": sets[pick]["qc"], "flow": flow, "comp_iou": comp_iou}, ensure_ascii=False))
    print(f"[done] → {WORK / 'hollow_preview.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
