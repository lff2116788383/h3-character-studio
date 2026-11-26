"""从 jade 素体 sheet 派生 RPG Maker 式部件：干净裸模（光头）+ 发型图层。

输入: output/derived_raw/ 下 seedream 编辑产物（白底、可能 1536px）+ prototype/assets/ 原 sheet
输出: prototype/assets/clean_body_{walk,attack}.png / hair_clean_{walk,attack}.png（1024 sheet，逐帧对齐）
     output/derived_preview_{walk,attack}.png（原图|裸模|发型|合成 对照）
处理: 边界连通白底去除（保留封闭白色如月牙发簪）→ 逐帧互相关对齐
     （裸模 vs 原帧 alpha 最大化交集；发型 vs hair_region=原alpha&~裸模alpha）
     attack 第4帧(抬手帧)生成失败时，从原 sheet 按 hair_region+颜色阈值重建该帧发型。
"""
import numpy as np
import cv2
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / 'output' / 'derived_raw'
ASSETS = ROOT / 'prototype' / 'assets'
PREVIEW = ROOT / 'output'
CW, CH, COLS, ROWS = 256, 512, 4, 2


def load1024(path: Path) -> Image.Image:
    im = Image.open(path).convert('RGBA')
    if im.size != (1024, 1024):
        im = im.resize((1024, 1024), Image.LANCZOS)
    return im


def remove_white_bg(im: Image.Image, tol: int = 30) -> Image.Image:
    """边界连通的背景色区域变透明（以边界中值颜色为基准、按颜色距离判背景）。
    封闭的浅色（月牙发簪、衣内高光）不与边界连通，保留。"""
    arr = np.array(im)
    h, w = arr.shape[:2]
    border = np.concatenate([arr[0, :, :3], arr[-1, :, :3],
                             arr[:, 0, :3], arr[:, -1, :3]]).astype(np.float32)
    base = np.median(border, axis=0)
    dist = np.linalg.norm(arr[..., :3].astype(np.float32) - base, axis=2)
    cand = dist <= tol
    n, labels = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border_labels.discard(0)
    bg = np.isin(labels, list(border_labels))
    arr[..., 3] = np.where(bg, 0, arr[..., 3])
    return Image.fromarray(arr, 'RGBA')


def cell(im_arr: np.ndarray, idx: int) -> np.ndarray:
    r, c = divmod(idx, COLS)
    return im_arr[r * CH:(r + 1) * CH, c * CW:(c + 1) * CW].copy()


def best_offset(mask: np.ndarray, ref: np.ndarray, rng: int = 40):
    H, W = mask.shape
    pad = np.zeros((H + 2 * rng, W + 2 * rng), bool)
    pad[rng:rng + H, rng:rng + W] = mask
    best = (0, 0, -1.0)
    for dy in range(-rng, rng + 1):
        for dx in range(-rng, rng + 1):
            win = pad[rng + dy:rng + dy + H, rng + dx:rng + dx + W]
            inter = int(np.count_nonzero(ref & win))
            if inter > best[2]:
                best = (dx, dy, inter)
    dx, dy, inter = best
    iou = inter / max(1, int(np.count_nonzero(mask | ref)))
    return dx, dy, iou


def shift_cell(cellarr: np.ndarray, dx: int, dy: int) -> np.ndarray:
    H, W = cellarr.shape[:2]
    out = np.zeros_like(cellarr)
    ys0, ys1 = max(0, dy), min(H, H + dy)
    xs0, xs1 = max(0, dx), min(W, W + dx)
    out[ys0:ys1, xs0:xs1] = cellarr[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def rebuild_hair_by_color(orig_cell: np.ndarray, hair_region: np.ndarray) -> np.ndarray:
    """attack 抬手帧兜底：原帧像素在 hair_region 内按颜色阈值抠出头发。"""
    rgb = orig_cell[..., :3].astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    dark = mx < 170                                  # 黑发/深色发丝（含中调高光）
    red = (r > 120) & (g < 120) & (r - g > 40)       # 红发带
    pin = (mx >= 140) & (mx - mn < 55)               # 低饱和浅色（月牙簪/白发饰）
    mask = (dark | red | pin) & hair_region
    out = orig_cell.copy()
    out[..., 3] = np.where(mask, orig_cell[..., 3], 0)
    return out


def process(motion: str, fix_frame: int | None):
    orig = np.array(Image.open(ASSETS / f'body_{motion}.png').convert('RGBA'))
    body_raw = remove_white_bg(load1024(RAW / f'clean_body_{motion}_raw.png'))
    hair_raw = remove_white_bg(load1024(RAW / f'hair_{motion}_raw.png'))
    body_out = np.zeros_like(orig)
    hair_out = np.zeros_like(orig)
    stats = []
    for idx in range(COLS * ROWS):
        oc = cell(orig, idx)
        bc = cell(np.array(body_raw), idx)
        hc = cell(np.array(hair_raw), idx)
        oam = oc[..., 3] > 128
        bam = bc[..., 3] > 128
        dx, dy, iou = best_offset(bam, oam)
        bac = shift_cell(bc, dx, dy)
        body_out[r := idx // COLS, c := idx % COLS] if False else None
        r_, c_ = divmod(idx, COLS)
        body_out[r_ * CH:(r_ + 1) * CH, c_ * CW:(c_ + 1) * CW] = bac
        ham = (bac[..., 3] > 128)
        region = oam & ~ham
        region = cv2.morphologyEx(region.astype(np.uint8), cv2.MORPH_CLOSE,
                                   np.ones((5, 5), np.uint8)).astype(bool)
        if fix_frame == idx:
            hc = rebuild_hair_by_color(oc, region)
            ham_src = hc[..., 3] > 128
        else:
            ham_src = hc[..., 3] > 128
        hdx, hdy, hiou = best_offset(ham_src, region)
        hac = shift_cell(hc, hdx, hdy)
        hair_out[r_ * CH:(r_ + 1) * CH, c_ * CW:(c_ + 1) * CW] = hac
        stats.append((idx, dx, dy, round(iou, 3), hdx, hdy, round(hiou, 3)))
    # 输出
    Image.fromarray(body_out, 'RGBA').save(ASSETS / f'clean_body_{motion}.png')
    Image.fromarray(hair_out, 'RGBA').save(ASSETS / f'hair_clean_{motion}.png')
    # 预览: 原图 | 裸模 | 发型 | 裸模+发型合成（白底便于看）
    prev = Image.new('RGBA', (1024, 1024), (255, 255, 255, 255))
    comp = Image.alpha_composite(Image.fromarray(body_out, 'RGBA'),
                                 Image.fromarray(hair_out, 'RGBA'))
    for i, layer in enumerate([Image.fromarray(orig, 'RGBA'),
                               Image.fromarray(body_out, 'RGBA'),
                               Image.fromarray(hair_out, 'RGBA'), comp]):
        r_, c_ = divmod(i, 2)
        prev.alpha_composite(layer.resize((512, 512), Image.NEAREST), (c_ * 512, r_ * 512))
    prev.convert('RGB').save(PREVIEW / f'derived_preview_{motion}.png')
    print(f'== {motion} ==')
    for s in stats:
        print(f'  cell{s[0]}: body d=({s[1]},{s[2]}) iou={s[3]} | hair d=({s[4]},{s[5]}) iou={s[6]}')
    bad = [s for s in stats if abs(s[1]) > 22 or abs(s[2]) > 22 or s[3] < 0.55]
    if bad:
        print(f'  !! 可疑对齐: {bad}')


if __name__ == '__main__':
    process('walk', fix_frame=None)
    process('attack', fix_frame=3)   # r0c3 抬手帧，生成版有白斑，用原帧重建
    print('done')
