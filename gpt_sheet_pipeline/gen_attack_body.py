# -*- coding: utf-8 -*-
"""挥砍素体 sheet 生成 ×2 抽卡: 右向单手刀势(空手, 武器后续锚点挂载)。
产出: output/attack/attack_body_a1.png / a2.png
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gpt_client import generate_img2img  # noqa: E402

WORK = HERE / "output" / "attack"
WORK.mkdir(parents=True, exist_ok=True)
MASTER = HERE / "output" / "compare_master_right.png"
BODY = HERE / "output" / "swap" / "body_sheet.png"

LAYOUT = ("A sprite sheet of EXACTLY 4 columns and 2 rows, 8 equal cells in reading order. "
          "Each cell: same character, same scale, feet planted on the same ground line, centered, "
          "fixed elevated orthographic front three-quarter view facing screen right. Flat uniform "
          "solid #ff00ff magenta background in every cell, no cell borders, no labels, no text, "
          "no shadow, one single character per cell. Crisp clean outlines, coherent cel shading.")

PROMPT = (
    "Two reference images. The FIRST defines the character's face, hairstyle and identity. "
    "The SECOND is her 8-cell sheet in a base layer, for scale, ground line and on-screen "
    "position. Redraw the exact same character from the FIRST reference performing ONE RIGHT-"
    "HANDED SWORD SLASH attack cycle, facing screen right, EMPTY HANDS (the sword will be "
    "composited separately later, so the right hand is a gripping fist). The 8 cells in "
    "reading order are the attack phases: cell 1 ready stance, right arm drawn back; cell 2 "
    "windup, right arm raised up behind the shoulder, body twisted; cell 3 windup peak, arm "
    "fully cocked back; cell 4 swing starts, arm sweeping forward overhead; cell 5 strike, "
    "arm extended forward at chest height; cell 6 strike end, arm low in front; cell 7 "
    "follow-through, body leaning forward; cell 8 recover back to ready stance. She wears "
    "ONLY the same tight white sleeveless undershirt and dark fitted shorts as the SECOND "
    "reference: bare arms and legs. Preserve her face, twin braids, silver hair cuffs and "
    "moon headdress exactly. Feet stay planted in fighting stance in every cell. " + LAYOUT
)

for i in (1, 2):
    out = WORK / f"attack_body_a{i}.png"
    if out.exists():
        print(f"[skip] {out.name}")
        continue
    generate_img2img(PROMPT, [MASTER, BODY], out, size="1024x1024")
print("[done]", WORK)
