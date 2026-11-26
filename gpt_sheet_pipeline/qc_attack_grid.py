# -*- coding: utf-8 -*-
"""QC 网格视图: 服装攻击 sheet + 斗笠。"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import slice_sheet  # noqa: E402


def grid(sheet_path: Path, out: Path, cols=4, rows=2) -> None:
    img = Image.open(sheet_path)
    w, h = img.size
    cw, ch = w // cols, h // rows
    S = Image.new("RGB", (cols * (cw + 4), rows * (ch + 24)), (30, 30, 34))
    d = ImageDraw.Draw(S)
    for i in range(cols * rows):
        x, y = (i % cols) * (cw + 4), (i // cols) * (ch + 24) + 20
        cell = img.crop((i % cols * cw, i // cols * ch, (i % cols + 1) * cw, (i // cols + 1) * ch))
        S.paste(cell.convert("RGB"), (x, y))
        d.text((x + 4, y - 16), f"f{i}", fill=(255, 255, 0))
    S.save(out)
    print("saved", out, S.size)


grid(HERE / "output/attack/clothB_attack.png", HERE / "output/attack/clothB_attack_grid.png")
grid(HERE / "output/attack/clothA_attack.png", HERE / "output/attack/clothA_attack_grid.png")
grid(HERE / "output/attack/hat_single.png", HERE / "output/attack/hat_grid.png", cols=1, rows=1)
