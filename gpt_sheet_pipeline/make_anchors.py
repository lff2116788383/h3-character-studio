# -*- coding: utf-8 -*-
"""素体锚点标注: 手工读网格图标注 8 帧关键点 (cell 内坐标, cell=256x512)。
产出:
  - anchors.json            锚点数据 (换装系统的共享动作真源)
  - body_anchored_sheet.png 带锚点标记的素体 sheet (GPT 部件生成的参考图)
锚点: wrist_r=持刀手腕(红) elbow_r=持刀肘(蓝) ankle_a=前踝(绿) ankle_b=后踝(黄)
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
WORK = HERE / "output" / "swap_parts"
COLS, ROWS = 4, 2
CW, CH = 256, 512

FRAMES = [
    {"wrist_r": [85, 322], "elbow_r": [100, 272], "ankle_a": [100, 440], "ankle_b": [142, 465]},
    {"wrist_r": [90, 326], "elbow_r": [108, 275], "ankle_a": [95, 420], "ankle_b": [150, 478]},
    {"wrist_r": [88, 324], "elbow_r": [106, 272], "ankle_a": [100, 455], "ankle_b": [175, 468]},
    {"wrist_r": [80, 320], "elbow_r": [100, 270], "ankle_a": [105, 468], "ankle_b": [185, 452]},
    {"wrist_r": [85, 330], "elbow_r": [105, 278], "ankle_a": [95, 452], "ankle_b": [140, 478]},
    {"wrist_r": [92, 330], "elbow_r": [110, 278], "ankle_a": [95, 420], "ankle_b": [150, 478]},
    {"wrist_r": [88, 328], "elbow_r": [106, 275], "ankle_a": [100, 458], "ankle_b": [180, 468]},
    {"wrist_r": [82, 322], "elbow_r": [102, 272], "ankle_a": [105, 472], "ankle_b": [190, 458]},
]

COLORS = {"wrist_r": (255, 0, 0), "elbow_r": (0, 0, 255),
          "ankle_a": (0, 255, 0), "ankle_b": (255, 255, 0)}


def main() -> None:
    data = {"cell_size": [CW, CH], "layout": {"cols": COLS, "rows": ROWS},
            "direction": "right", "frames": [dict(index=i, **f) for i, f in enumerate(FRAMES)]}
    (WORK / "anchors.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    sheet = Image.open(WORK.parent / "swap" / "body_sheet.png").convert("RGB")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(FRAMES):
        ox, oy = (i % COLS) * CW, (i // COLS) * CH
        for name, (x, y) in f.items():
            x, y = ox + x, oy + y
            c = COLORS[name]
            for off in (0,):  # 黑描边十字 + 彩色内核
                d.line([(x - 9, y), (x + 9, y)], fill=(0, 0, 0), width=5)
                d.line([(x, y - 9), (x, y + 9)], fill=(0, 0, 0), width=5)
            d.line([(x - 9, y), (x + 9, y)], fill=c, width=3)
            d.line([(x, y - 9), (x, y + 9)], fill=c, width=3)
    sheet.save(WORK / "body_anchored_sheet.png")
    print(f"[done] anchors.json + body_anchored_sheet.png → {WORK}")


if __name__ == "__main__":
    main()
