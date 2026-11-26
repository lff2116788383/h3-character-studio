"""肤色 blob 检测：每帧列出候选手部区域（躯干/腿部区域的肤色连通块）。"""
import numpy as np, cv2
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
CW, CH, COLS = 256, 512, 4

def cells(sheet):
    img = np.array(Image.open(sheet).convert("RGB"))
    return [img[r*CH:(r+1)*CH, c*CW:(c+1)*CW] for r in range(2) for c in range(COLS)]

# 采样肤色：脸部区域(约 y=120-160, x=140-170, faces right → 脸在右下方向)
img0 = cells(HERE/"prototype/assets/body_walk.png")[0]
samples = [tuple(img0[y, x]) for y, x in [(140,150),(150,155),(160,150),(300,200),(295,205)]]
print("samples:", samples)

LOWER = np.array([140, 90, 70], np.uint8)   # HSV 下界(肤色)
UPPER = np.array([220, 180, 190], np.uint8)

for motion in ("walk", "attack"):
    cs = cells(HERE/f"prototype/assets/body_{motion}.png")
    print(f"\n== {motion} ==")
    for i, c in enumerate(cs):
        hsv = cv2.cvtColor(c, cv2.COLOR_RGB2HSV)
        # 肤色 H≈0-25, S 中等, V 中高（以采样为准, 打印后调）
        mask = cv2.inRange(hsv, (0, 30, 120), (28, 120, 255))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
        n, lab, stats, cent = cv2.connectedComponentsWithStats(mask)
        cands = []
        for k in range(1, n):
            x, y, w, h, area = stats[k]
            if area < 40: continue
            cands.append((int(cent[k][0]), int(cent[k][1]), area, (x, y, w, h)))
        cands.sort(key=lambda t: -t[2])
        print(f" f{i}: " + " | ".join(f"({cx},{cy}) a={a} bb={bb}" for cx, cy, a, bb in cands[:6]))
