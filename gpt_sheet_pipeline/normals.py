# -*- coding: utf-8 -*-
"""解析法线 + 材质蒙版生成（产线内置版，原 normals_demo.py 收敛而来）。

与生成器完全解耦：对任意 256×256 精灵帧（GPT / H3 / 手绘皆可）按几何标注
（ellipsoid / tube 部件 + silver 多边形）解析合成法线贴图与金属蒙版，
并给出 flat / left / right / top 四向受光预览。

用法（单帧自检）:
    python normals.py <frame.png> <geometry.yaml> <out_dir>
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

SIZE = 256
MAGENTA = np.array([255, 0, 255], dtype=np.float32)
YY, XX = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
GRID = np.stack((XX, YY), axis=-1)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-8)


def load_frame(path: Path):
    """品红抠底 → 裁 bbox → 最长边缩到 248 → 底部对齐贴回 256 画布。"""
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    dist = np.linalg.norm(img - MAGENTA, axis=-1)
    alpha = (dist > 60).astype(np.uint8) * 255
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    rgba = np.dstack([img.astype(np.uint8), alpha])
    pil = Image.fromarray(rgba, "RGBA")
    bbox = pil.getbbox()
    pil = pil.crop(bbox)
    h, w = pil.height, pil.width
    scale = (SIZE - 8) / max(h, w)
    nh, nw = max(1, int(h * scale)), max(1, int(w * scale))
    pil = pil.resize((nw, nh), Image.NEAREST)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(pil, ((SIZE - nw) // 2, SIZE - 8 - nh), pil)
    return np.asarray(canvas, dtype=np.float32)


def tube_normal(points, radius, amplitude=0.72):
    distance2 = np.full((SIZE, SIZE), np.inf, np.float32)
    radial = np.zeros((SIZE, SIZE, 2), np.float32)
    for pa, pb in zip(points, points[1:]):
        a, b = np.array(pa, np.float32), np.array(pb, np.float32)
        axis = b - a
        length = max(float(np.linalg.norm(axis)), 0.1)
        t = np.clip(((GRID - a) * axis).sum(-1) / (length * length), 0, 1)
        q = a + t[..., None] * axis
        delta = GRID - q
        d2 = (delta * delta).sum(-1)
        pick = d2 < distance2
        distance2[pick] = d2[pick]
        radial[pick] = delta[pick] / radius
    xy = radial * amplitude
    xy[..., 1] *= -1
    z = np.sqrt(np.maximum(0.16, 1 - (xy * xy).sum(-1)))
    mask = distance2 <= (radius * 1.45) ** 2
    return mask, unit(np.dstack((xy, z)))


def ellipsoid_normal(spec, slope=0.65, yaw=0.0):
    cx, cy, rx, ry = spec
    x = np.clip((XX - cx) / rx, -1.15, 1.15) * slope + yaw
    y = np.clip(-(YY - cy) / ry, -1.15, 1.15) * slope
    z = np.sqrt(np.maximum(0.22, 1 - x * x - y * y))
    return unit(np.dstack((x, y, z)))


def build_normals(geo, silhouette):
    """按部件列表从后往前合成法线；region 限定部件生效范围。"""
    normal = np.zeros((SIZE, SIZE, 3), np.float32)
    normal[..., 2] = 1.0
    for part in geo["parts"]:
        if part["kind"] == "ellipsoid":
            mask = np.ones((SIZE, SIZE), bool)
            n = ellipsoid_normal(part["spec"], part.get("slope", 0.65), part.get("yaw", 0.0))
        else:  # tube
            mask, n = tube_normal(part["points"], part["radius"], part.get("amplitude", 0.72))
        region = part.get("region")
        if region:
            cx, cy, rx, ry = region
            mask &= ((XX - cx) / rx) ** 2 + ((YY - cy) / ry) ** 2 <= 1
        mask &= silhouette > 0
        normal[mask] = n[mask]
    return normal


def build_metal_mask(geo, alpha):
    metal = np.zeros((SIZE, SIZE), np.float32)
    for poly in geo.get("silver_polys", []):
        cv2.fillPoly(metal, [np.array(poly, np.int32)], 1.0)
    metal *= (alpha > 0)
    return metal


def encode(normal):
    return ((normal * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)


def lit_preview(albedo, normal, mask, light_dirs):
    """Lambert 漫反射 + 金属区 Blinn-Phong 高光。返回 (有法线, 无法线) 两版 RGBA。"""
    diffuse = albedo[..., :3].astype(np.float32) / 255.0
    alpha = albedo[..., 3]
    L = unit(np.array(light_dirs, np.float32))
    lam = np.clip((normal * L).sum(-1), 0, 1)
    V = unit(np.array([0, 0, 1], np.float32))
    H = unit(L + V)
    spec = np.clip((normal * H).sum(-1), 0, 1) ** 48 * mask
    lit = diffuse * (0.35 + 0.65 * lam[..., None]) + spec[..., None] * 0.9
    flat = diffuse * (0.35 + 0.65 * np.clip(L[2], 0, 1))
    outs = []
    for arr in (lit, flat):
        rgb = (arr * 255).clip(0, 255).astype(np.uint8)
        outs.append(np.dstack([rgb, alpha.astype(np.uint8)]))
    return outs[0], outs[1]


LIGHTS = (("light-left", [-0.7, 0.15, 0.6]), ("light-right", [0.7, 0.15, 0.6]),
          ("light-top", [0, -0.6, 0.8]))


def main():
    frame, geo_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_data = load_frame(frame)
    geo = yaml.safe_load(geo_path.read_text(encoding="utf-8"))

    normal = build_normals(geo, frame_data[..., 3])
    Image.fromarray(encode(normal)).save(out_dir / "normal_map.png")
    Image.fromarray((build_metal_mask(geo, frame_data[..., 3]) * 255).astype(np.uint8)).save(
        out_dir / "metal_mask.png")

    rows = []
    for name, ld in LIGHTS:
        lit, flat = lit_preview(frame_data, normal, build_metal_mask(geo, frame_data[..., 3]), ld)
        strip = Image.new("RGB", (SIZE * 2 + 12, SIZE), (20, 20, 24))
        strip.paste(Image.fromarray(flat, "RGBA"), (0, 0), Image.fromarray(flat, "RGBA"))
        strip.paste(Image.fromarray(lit, "RGBA"), (SIZE + 12, 0), Image.fromarray(lit, "RGBA"))
        rows.append(np.asarray(strip))
        Image.fromarray(lit, "RGBA").save(out_dir / f"{name}.png")
    Image.fromarray(np.vstack(rows)).save(out_dir / "lighting_compare.png")
    print(f"输出: normal_map.png / metal_mask.png / lighting_compare.png → {out_dir}")


if __name__ == "__main__":
    main()
