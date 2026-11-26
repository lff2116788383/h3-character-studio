# -*- coding: utf-8 -*-
"""攻击动作锚点标注 + 第二轮生成: 服装A/B 挥砍 sheet(锚点引导) + 斗笠单图。
产出:
  - output/attack/anchors_attack.json     (a1 的 8 帧腕/肘锚点 + head_top)
  - output/attack/attack_body_anchored.png
  - output/attack/clothA_attack.png / clothB_attack.png
  - output/attack/hat_single.png          (斗笠, 品红底)
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gpt_client import generate_img2img  # noqa: E402
from gen_sheets import CELLS  # noqa: E402

WORK = HERE / "output" / "attack"
MASTER = HERE / "output" / "compare_master_right.png"
PICK = WORK / "attack_body_a1.png"

# a1 网格目测标注 (cell 内坐标, 256x512, y 向下)
FRAMES = [
    {"wrist_r": [148, 260], "elbow_r": [130, 215], "head_top": [106, 100]},
    {"wrist_r": [150, 192], "elbow_r": [128, 235], "head_top": [106, 100]},
    {"wrist_r": [95, 152], "elbow_r": [118, 200], "head_top": [106, 100]},
    {"wrist_r": [130, 155], "elbow_r": [108, 205], "head_top": [106, 100]},
    {"wrist_r": [196, 256], "elbow_r": [150, 250], "head_top": [106, 100]},
    {"wrist_r": [182, 300], "elbow_r": [148, 268], "head_top": [106, 100]},
    {"wrist_r": [168, 285], "elbow_r": [140, 255], "head_top": [106, 100]},
    {"wrist_r": [145, 270], "elbow_r": [128, 230], "head_top": [106, 100]},
]
# 武器前后序表 (mir2x weaponOrder 式): 1=画在身体后, 0=画在身前
WEAPON_ORDER_ATTACK = [0, 0, 1, 1, 0, 0, 0, 0]
WEAPON_ORDER_WALK = [0, 0, 0, 0, 0, 0, 0, 0]

COLORS = {"wrist_r": (255, 0, 0), "elbow_r": (0, 0, 255), "head_top": (0, 255, 0)}

LAYOUT = ("A sprite sheet of EXACTLY 4 columns and 2 rows, 8 equal cells in reading order. "
          "Each cell: same character, same scale, feet on the same ground line, centered, fixed "
          "elevated orthographic front three-quarter view facing screen right. Flat uniform solid "
          "#ff00ff magenta background in every cell, no cell borders, no labels, no text, no "
          "shadow, one single character per cell. Crisp clean outlines, coherent cel shading.")

CLOTH_PROMPT = (
    "Three reference images. FIRST: character identity (face, hairstyle). SECOND: an 8-cell "
    "sheet of the character performing a right-handed sword slash attack cycle with colored "
    "cross markers on her sword arm: red cross = gripping wrist, blue cross = elbow. THIRD: "
    "the outfit to wear. Produce the SAME 8-cell layout with the SAME slash attack poses "
    "cell-by-cell as the SECOND reference, wearing: {outfit} The sleeves and clothing must "
    "follow the red/blue cross positions in every cell (arm raises overhead in cells 2-3, "
    "extends forward in cells 4-5). Keep the colored cross markers visible ON TOP of the "
    "clothing at the corresponding positions. Feet planted in the same fighting stance, "
    "scale and ground line identical to the SECOND reference. Face and hairstyle from the "
    "FIRST reference. " + LAYOUT
)

OUTFIT_A = ("her original outfit from the FIRST reference: dark navy wrapped jacket with silver "
            "trim, white necklace ornaments, wide belt with silver buckle, long red pleated skirt "
            "with white patterns, dark leggings, brown boots with red laces, and the small leather pouch.")
OUTFIT_B = ("a brand new outfit: long emerald-green hanfu robe with wide sleeves, golden sash with "
            "jade pendant, white inner collar, dark green trousers, black boots with gold buckles. No cape.")

HAT_PROMPT = (
    "A single bamboo conical hat (douli, 斗笠) game item sprite, seen from the same three-quarter "
    "side view as the reference character, wide brim slightly tilted, woven bamboo texture with a "
    "small red tassel at the crown tip. The hat is centered and fills about 60 percent of the image "
    "width. Flat uniform solid #ff00ff magenta background, no person, no head, no text, no shadow, "
    "no other objects. Crisp clean outlines, cel shading, same art style as the reference character."
)


def gen(path: Path, refs: list, prompt: str) -> None:
    if path.exists():
        print(f"[skip] {path.name}")
        return
    generate_img2img(prompt, refs, path, size="1024x1024")


def main() -> None:
    # 1) 锚点数据 + 锚点版攻击素体
    (WORK / "anchors_attack.json").write_text(json.dumps({
        "cell_size": [256, 512], "direction": "right", "source": "attack_body_a1",
        "frames": [dict(index=i, **f) for i, f in enumerate(FRAMES)],
        "weaponOrder": WEAPON_ORDER_ATTACK}, ensure_ascii=False, indent=1), encoding="utf-8")

    sheet = Image.open(PICK).convert("RGB")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(FRAMES):
        ox, oy = (i % 4) * 256, (i // 4) * 512
        for name, (x, y) in f.items():
            x, y = ox + x, oy + y
            c = COLORS[name]
            d.line([(x - 9, y), (x + 9, y)], fill=(0, 0, 0), width=5)
            d.line([(x, y - 9), (x, y + 9)], fill=(0, 0, 0), width=5)
            d.line([(x - 9, y), (x + 9, y)], fill=c, width=3)
            d.line([(x, y - 9), (x, y + 9)], fill=c, width=3)
    sheet.save(WORK / "attack_body_anchored.png")
    print("[ok] attack_body_anchored.png + anchors_attack.json")

    # 2) 服装A/B 攻击 sheet (锚点引导)
    gen(WORK / "clothA_attack.png", [MASTER, WORK / "attack_body_anchored.png", HERE / "output" / "swap" / "outfitA_sheet.png"],
        CLOTH_PROMPT.format(outfit=OUTFIT_A))
    gen(WORK / "clothB_attack.png", [MASTER, WORK / "attack_body_anchored.png", HERE / "output" / "swap" / "outfitB_sheet.png"],
        CLOTH_PROMPT.format(outfit=OUTFIT_B))

    # 3) 斗笠单图 (头饰槽)
    gen(WORK / "hat_single.png", [MASTER], HAT_PROMPT)
    print("[done]", WORK)


if __name__ == "__main__":
    main()
