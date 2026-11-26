"""生成锚点目检图：walk/attack 素体 sheet 逐帧 1.5x 放大 + 16px 网格 + 现有估算值十字标。
用法: python calib_annot.py  → 输出 output/calib_walk_0.png 等 4 张（每张 4 帧 2x2）
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CW, CH = 256, 512
COLS = 4

OLD = {
    "walk": {"wrist_r": [[85,322],[92,330],[88,328],[90,329],[87,325],[91,331],[89,330],[90,329]],
             "elbow_r": [[92,290],[95,296],[93,294],[94,295],[93,292],[95,297],[94,296],[94,295]]},
    "attack": {"wrist_r": [[148,260],[150,192],[95,152],[130,155],[196,256],[182,300],[168,285],[145,270]],
               "elbow_r": [[135,225],[138,200],[110,175],[122,175],[160,215],[155,240],[148,230],[138,215]]},
}

def load_cells(sheet):
    img = Image.open(sheet).convert("RGBA")
    cells = []
    for i in range(8):
        c, r = i % COLS, i // COLS
        cells.append(img.crop((c*CW, r*CH, (c+1)*CW, (r+1)*CH)))
    return cells

def annotate(cell, motion, idx):
    s = 1.5
    big = cell.resize((int(CW*s), int(CH*s)), Image.NEAREST).convert("RGB")
    d = ImageDraw.Draw(big)
    for x in range(0, CW+1, 16):
        w = 2 if x % 64 == 0 else 1
        col = (255,120,120) if x % 64 == 0 else (150,150,150)
        d.line([(x*s,0),(x*s,CH*s)], fill=col, width=w)
        if x % 64 == 0 and x:
            d.text((x*s+2, 2), str(x), fill=(255,60,60))
    for y in range(0, CH+1, 16):
        w = 2 if y % 64 == 0 else 1
        col = (120,160,255) if y % 64 == 0 else (150,150,150)
        d.line([(0,y*s),(CW*s,y*s)], fill=col, width=w)
        if y % 64 == 0 and y:
            d.text((2, y*s+2), str(y), fill=(60,90,255))
    old = OLD[motion]
    for key, col in (("wrist_r",(0,255,0)), ("elbow_r",(255,0,255))):
        x, y = old[key][idx]
        d.line([(x*s-12,y*s),(x*s+12,y*s)], fill=col, width=2)
        d.line([(x*s,y*s-12),(x*s,y*s+12)], fill=col, width=2)
        d.text((x*s+4, y*s-14), f"{key[0]}{idx}", fill=col)
    d.rectangle([0,0,big.width-1,big.height-1], outline=(0,0,0), width=3)
    d.text((6, CH*s-20), f"#{idx}", fill=(0,0,0))
    return big

def montage(cells, motion, lo, hi, out):
    tiles = [annotate(cells[i], motion, i) for i in range(lo, hi)]
    w, h = tiles[0].size
    m = Image.new("RGB", (w*2, h*2), (40,40,40))
    for i, t in enumerate(tiles):
        m.paste(t, ((i%2)*w, (i//2)*h))
    m.save(out)
    print(out, m.size)

for motion in ("walk", "attack"):
    cells = load_cells(HERE / f"prototype/assets/body_{motion}.png")
    montage(cells, motion, 0, 4, HERE / f"output/calib_{motion}_a.png")
    montage(cells, motion, 4, 8, HERE / f"output/calib_{motion}_b.png")
