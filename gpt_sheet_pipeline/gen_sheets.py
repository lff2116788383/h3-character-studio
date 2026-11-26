# -*- coding: utf-8 -*-
"""Step 1: 按方向生成行走循环 sheet（4×2=8格/sheet，27帧=4张，链式参考+首尾闭合）。

用法:
  python gen_sheets.py --master <master.png> --direction down --sheets 4
  python gen_sheets.py --master <master.png> --direction right --sheets 4 --amplitude high
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpt_client import generate_img2img  # noqa: E402

HERE = Path(__file__).resolve().parent
COLS, ROWS = 4, 2
CELLS = COLS * ROWS

# 27 帧行走循环 → 每帧相位描述（contact-recoil-passing-mid 双足交替）
def phase_for(frame_index: int) -> str:
    c = frame_index % 27
    leg = "right" if (c // 7) % 2 == 0 else "left"
    other = "left" if leg == "right" else "right"
    phase = c % 7
    if phase == 0:
        return f"contact phase: {leg} leg forward with heel striking the ground, {other} toe pushing off behind, wide stride"
    if phase in (1, 2):
        return f"early stance: weight loading onto the forward {leg} leg, feet passing closest, knees slightly bent"
    if phase in (3, 4):
        return f"passing phase: {other} leg swinging past the supporting {leg} leg, {other} knee bent and lifted forward"
    return f"push-off phase: {leg} toe pushing off the ground, body rising, arms at opposite swing extremes"


PROMPT = (
    "A sprite sheet of the exact character from the FIRST reference image (identity, face, "
    "hairstyle, outfit, colors, satchel all identical). Layout: EXACTLY {cols} columns and "
    "{rows} rows, 8 equal cells in reading order. Each cell: same character, same scale, feet "
    "on the same ground line, centered, fixed elevated orthographic front three-quarter view "
    "facing {facing}. The 8 cells CONTINUE the walk-in-place cycle from the SECOND reference "
    "sheet — global frames {start} to {end} of 27 of one full stride cycle. Gait phase of "
    "global frame {f0}: {phase0}. Frames must advance continuously cell by cell with large, "
    "clearly distinct leg swing, arms counter-swinging, natural weight shift. Hairstyle, "
    "outfit, colors, scale, ground line identical across all cells; secondary motion allowed "
    "only in ponytails and skirt hem. Flat uniform solid #ff00ff magenta background in every "
    "cell, no cell borders, no grid lines, no labels, no numbers, no text, no shadow, no "
    "ground drawing, one single character per cell. Crisp clean outlines, coherent cel "
    "shading, stable colors."
)

CLOSURE_NOTE = (
    " This is the FINAL sheet of the cycle: its last cell must arrive at the exact pose where "
    "the cycle began (the first cell of the FIRST reference sheet), so the animation loops "
    "seamlessly. The THIRD reference image shows that starting pose."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True, type=Path)
    ap.add_argument("--direction", required=True, choices=["down", "up", "left", "right"])
    ap.add_argument("--sheets", type=int, default=4, help="sheet 数量; 27帧 = 4 张(8+8+8+3)")
    ap.add_argument("--frames", type=int, default=27)
    ap.add_argument("--work", type=Path, default=HERE / "output")
    args = ap.parse_args()

    facing = {"down": "the camera (front view)", "up": "away from the camera (back view)",
              "left": "screen LEFT", "right": "screen RIGHT"}[args.direction]
    work = args.work / args.direction
    work.mkdir(parents=True, exist_ok=True)
    first_sheet = work / "sheet-00.png"
    prev = None
    total_cells = min(args.sheets * CELLS, args.frames)
    for s in range(args.sheets):
        out = work / f"sheet-{s:02d}.png"
        if out.exists():
            print(f"[skip] {out.name}")
            prev = out
            continue
        start = s * CELLS
        end = min(start + CELLS - 1, total_cells - 1)
        prompt = PROMPT.format(cols=COLS, rows=ROWS, facing=facing, start=start, end=end,
                               f0=start, phase0=phase_for(start))
        refs = [args.master] if prev is None else [args.master, prev]
        if s == args.sheets - 1 and total_cells > CELLS:
            prompt += CLOSURE_NOTE
            refs = [args.master, prev, first_sheet]
        generate_img2img(prompt, refs, out, size="1024x1024")
        prev = out
    print(f"[done] {args.sheets} sheets → {work}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
