"""4x 精查裁片：每帧手臂+手部区域放大，8px 细网格，32px 坐标标签。"""
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
CW, CH, COLS = 256, 512, 4
S = 4

REGIONS = {
    "walk": {i: (150, 225, 235, 330) for i in range(8)},
    "attack": {0: (55, 175, 215, 325), 1: (35, 125, 200, 300), 2: (15, 105, 180, 290),
               3: (85, 105, 245, 275), 4: (95, 175, 245, 295), 5: (95, 145, 245, 325),
               6: (85, 175, 245, 335), 7: (55, 175, 205, 315)},
}

def load_cells(sheet):
    img = Image.open(sheet).convert("RGB")
    return [img.crop((c*CW, r*CH, (c+1)*CW, (r+1)*CH)) for r in range(2) for c in range(COLS)]

def crop_annot(cell, box, idx):
    x0, y0, x1, y1 = box
    c = cell.crop(box).resize(((x1-x0)*S, (y1-y0)*S), Image.NEAREST)
    d = ImageDraw.Draw(c)
    for gx in range(x0 - x0 % 8, x1+1, 8):
        X = (gx-x0)*S
        major = gx % 32 == 0
        d.line([(X,0),(X,c.height)], fill=(255,90,90) if major else (160,160,160), width=2 if major else 1)
        if major: d.text((X+2,2), str(gx), fill=(255,50,50))
    for gy in range(y0 - y0 % 8, y1+1, 8):
        Y = (gy-y0)*S
        major = gy % 32 == 0
        d.line([(0,Y),(c.width,Y)], fill=(80,130,255) if major else (160,160,160), width=2 if major else 1)
        if major: d.text((2,Y+2), str(gy), fill=(40,80,255))
    d.text((4, c.height-16), f"#{idx}", fill=(0,255,0))
    return c

def tiles(cells, motion, idxs, out):
    ts = [crop_annot(cells[i], REGIONS[motion][i], i) for i in idxs]
    w, h = ts[0].size
    m = Image.new("RGB", (w*2, h*2), (30,30,30))
    for i, t in enumerate(ts): m.paste(t, ((i%2)*w, (i//2)*h))
    m.save(out); print(out, m.size)

for motion in ("walk", "attack"):
    cells = load_cells(HERE/f"prototype/assets/body_{motion}.png")
    tiles(cells, motion, [0,1,2,3], HERE/f"output/zoom_{motion}_a.png")
    tiles(cells, motion, [4,5,6,7], HERE/f"output/zoom_{motion}_b.png")
