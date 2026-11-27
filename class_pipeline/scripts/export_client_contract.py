# -*- coding: utf-8 -*-
"""Step 4b: class assets(manifest+sheets) → hd2d-mmo crescent-traveler 同契约导出。

对齐目标(客户端 character_animation.gd 实际消费的字段, 逐一对齐):
  character.json : schema_version/id/version/default_direction/size/pivot/pixel_size
                   directions.<d>.{manifest, idle_frame} + stationary_behavior
  animation.json : atlas / pivot / frames[].{region, duration_ms} (gd 只读这三个)
                   + path/sha256/visible_bounds 溯源字段(旧产线契约, 客户端忽略)
  atlas.png      : 8列 + gutter2 + margin1, 帧 256×256, 脚底 y=240 / 水平中心 x=128
                   (crescent fit_canvas 同规格; class 资产脚底贴 255, 此处重新锚定)

布局:
  client_contract/
  ├── character.json          # crescent 精确键 + "motions" 扩展键(客户端忽略未知键)
  ├── right/                  # walk clip drop-in(移动=walk, 静止=idle_frame, 同 crescent)
  │   ├── animation.json | atlas.png | frames/00000.. | report.json
  └── motions/<motion>/       # 扩展: 全动作 clip(idle/attack1/attack2/death/run)
      └── animation.json | atlas.png | frames/ | report.json

用法: python export_client_contract.py --class-dir <class_pipeline/swordsman>
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SIZE = 256
PIVOT = (128, 240)          # crescent 契约: 脚底 y=240, 水平中心 x=128
MAX_DIM = 248               # fit_canvas 同规格: 内容最长边 ≤248
ATLAS_COLS = 8
GUTTER = 2
MARGIN = 1
PALETTE_COLORS = 96
FPS_DEFAULT = {"walk": 11, "run": 11, "idle": 6}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reanchor(frame: Image.Image) -> Image.Image:
    """class 对齐版帧(脚底贴画布底) → crescent 锚定(脚底 y=240, 中心 x=128)。"""
    bbox = frame.getbbox()
    if bbox:
        frame = frame.crop(bbox)
    w, h = frame.size
    if max(w, h) > MAX_DIM:
        s = MAX_DIM / max(w, h)
        frame = frame.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    w, h = frame.size
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(frame, (PIVOT[0] - w // 2, PIVOT[1] - h), frame)
    return canvas


def visible_bounds(img: Image.Image) -> list[int]:
    a = np.asarray(img)[..., 3]
    ys, xs = np.where(a > 10)
    if len(xs) == 0:
        return [0, 0, 0, 0]
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def quantize_shared(frames: list[Image.Image], colors: int):
    """全动作共享一块色板(旧产线同策略, MEDIANCUT 无抖动, alpha 回填)。"""
    step = max(1, len(frames) // 8)
    samples = frames[::step]
    strip = Image.new("RGB", (SIZE * len(samples), SIZE))
    for i, f in enumerate(samples):
        strip.paste(f.convert("RGB"), (i * SIZE, 0))
    pal = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)

    def apply(frame: Image.Image) -> Image.Image:
        q = frame.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE)
        out = q.convert("RGBA")
        out.putalpha(frame.getchannel("A"))
        return out

    palette = pal.getpalette()[: colors * 3]
    return apply, [list(p) for p in zip(*[iter(palette)] * 3)]


def split_durations(total_ms: int, n: int) -> list[int]:
    base, rem = divmod(total_ms, n)
    return [base + 1 if i < rem else base for i in range(n)]


def qc_metrics(frames: list[Image.Image]) -> dict:
    def a(img):
        return np.asarray(img)[..., 3] > 128

    masks = [a(f) for f in frames]
    ious = []
    for i in range(len(masks) - 1):
        inter = np.logical_and(masks[i], masks[i + 1]).sum()
        union = np.logical_or(masks[i], masks[i + 1]).sum()
        ious.append(inter / max(union, 1))
    inter = np.logical_and(masks[0], masks[-1]).sum()
    union = np.logical_or(masks[0], masks[-1]).sum()
    return {"adjacent_iou_mean": round(float(np.mean(ious)), 3),
            "adjacent_iou_min": round(float(np.min(ious)), 3),
            "loop_closure_iou": round(float(inter / max(union, 1)), 3)}


def build_clip(name: str, frames: list[Image.Image], out_dir: Path, durations: list[int],
               loop: bool, fps: int, palette_rgb: list, rel: str | None = None) -> list[dict]:
    """写 <rel>/{animation.json, atlas.png, frames/, report.json}, 返回 frames 元数据。"""
    rel = rel or name
    frames_dir = out_dir / rel / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = len(frames)
    cols = min(ATLAS_COLS, n)
    rows = (n + cols - 1) // cols
    aw = MARGIN * 2 + cols * (SIZE + GUTTER) - GUTTER
    ah = MARGIN * 2 + rows * (SIZE + GUTTER) - GUTTER
    atlas = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
    entries = []
    for i, frame in enumerate(frames):
        col, row = i % cols, i // cols
        ox, oy = MARGIN + col * (SIZE + GUTTER), MARGIN + row * (SIZE + GUTTER)
        atlas.paste(frame, (ox, oy))
        fp = frames_dir / f"{i:05d}.png"
        frame.save(fp, optimize=True)
        entries.append({
            "path": f"frames/{i:05d}.png",
            "sha256": sha256(fp),
            "region": [ox, oy, SIZE, SIZE],
            "visible_bounds": visible_bounds(frame),
            "duration_ms": durations[i],
        })
    atlas.save(out_dir / rel / "atlas.png", optimize=True)
    animation = {
        "version": 1, "size": [SIZE, SIZE], "pivot": list(PIVOT), "loop": loop,
        "atlas": "atlas.png", "fps": fps,
        "effective_source_size": [SIZE, SIZE], "review": "pending",
        "palette_rgb": palette_rgb, "frames": entries,
    }
    (out_dir / rel / "animation.json").write_text(
        json.dumps(animation, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {
        "version": 1, "pivot": list(PIVOT), "loop": loop, "fps": fps,
        "effective_source_size": [SIZE, SIZE], "palette_rgb": palette_rgb,
        "durations_ms": durations,
        "sources": [{"kind": "class_pipeline assets", "manifest": "assets/manifest.json"}],
        "provenance": {"pipeline": "class_pipeline", "matting": "bg-reestimate+despill (build_class_assets)",
                       "palette": f"shared mediancut {PALETTE_COLORS}", "anchor": "feet y=240 center x=128"},
        "warnings": ["review pending: 需 Step5 播放目检"],
        "visual_review": "pending",
    }
    (out_dir / rel / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", required=True, type=Path)
    args = ap.parse_args()
    cd = args.class_dir
    manifest = json.loads((cd / "assets" / "manifest.json").read_text(encoding="utf-8"))
    motions = manifest["motions"]
    if not motions:
        print("[error] assets/manifest.json 无动作, 先跑 build_class_assets.py")
        return 1

    # 1) 载入全部动作帧并重锚定到 crescent 规格
    frames_by_motion: dict[str, list[Image.Image]] = {}
    meta = {}
    for name, m in motions.items():
        sheet = Image.open(cd / "assets" / m["sheet"]).convert("RGBA")
        cols, cell_w, cell_h = m["cols"], m["cell"][0], m["cell"][1]
        frames = []
        for i in range(m["frames"]):
            cell = sheet.crop((i * cell_w, 0, (i + 1) * cell_w, cell_h))
            frames.append(reanchor(cell))
        frames_by_motion[name] = frames
        meta[name] = m
        print(f"[load] {name}: {len(frames)} 帧 cell={cell_w}x{cell_h} → 重锚定 y={PIVOT[1]}")

    # 2) 全动作共享色板量化
    all_frames = [f for fs in frames_by_motion.values() for f in fs]
    apply_pal, palette_rgb = quantize_shared(all_frames, PALETTE_COLORS)
    for name in frames_by_motion:
        frames_by_motion[name] = [apply_pal(f) for f in frames_by_motion[name]]

    # 3) 导出: right/=walk drop-in; motions/=全动作扩展
    out_root = cd / "client_contract"
    out_root.mkdir(exist_ok=True)
    motion_paths = {}
    for name, frames in frames_by_motion.items():
        m = meta[name]
        fps = m.get("fps", FPS_DEFAULT.get(name, 8))
        dur = split_durations(round(1000 / fps) * len(frames), len(frames))
        loop = bool(m.get("loop", False))
        sub = "right" if name == "walk" else f"motions/{name}"
        build_clip(name, frames, out_root, dur, loop, fps, palette_rgb, rel=sub)
        motion_paths[name] = {"manifest": f"{sub}/animation.json", "fps": fps, "loop": loop}
        qc = qc_metrics(frames)
        print(f"[qc] {name}: {qc} fps={fps} loop={loop}")
        (out_root / sub / "qc.json").write_text(
            json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")

    # 4) character.json: crescent 精确键 + motions 扩展键
    walk_frames = frames_by_motion["walk"]
    idle_frame = int(np.argmin([np.asarray(f)[..., 3].sum() for f in walk_frames]))
    character = {
        "schema_version": 1, "id": cd.name, "version": "v1",
        "default_direction": "right", "size": [SIZE, SIZE], "pivot": list(PIVOT),
        "pixel_size": 0.009,
        "directions": {
            "right": {"manifest": "right/animation.json", "idle_frame": idle_frame,
                      "generation": "class-pipeline-gpt"}
        },
        "stationary_behavior": "Hold a reviewed balanced frame from the current direction; "
                               "no separately generated idle animation.",
        "motions": {d: {name: p["manifest"] for name, p in motion_paths.items()}
                    for d in ("right",)},  # 扩展键: 客户端忽略未知键, 客户端接入立项后启用
        "notes": "drop-in 兼容 crescent-traveler v1 契约; idle/attack/death 走 motions/ 扩展,"
                 " 待客户端支持多 clip 后切换; 真实 idle 动作在 motions/idle。",
    }
    (out_root / "character.json").write_text(
        json.dumps(character, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] → {out_root} (character.json + right/ + motions/{len(motion_paths) - 1})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
