# -*- coding: utf-8 -*-
"""Step 2: sheet 切片 → 抠底去污染 → 统一色板 → 256画布对齐 → atlas + json 产出。

产出契约与 hd2d-mmo client / h3-character-studio 对齐:
  out_root/character.json
  out_root/<direction>/animation.json | atlas.png | frames/00000.png... | report.json

用法:
  python build_character.py --config config.yaml
  python build_character.py --config config.yaml --directions right   # 只构建指定方向
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import COLS, SIZE, fit_canvas, matte_cell, slice_sheet, visible_bounds  # noqa: E402

HERE = Path(__file__).resolve().parent
ATLAS_COLS = 8
GUTTER = 2
MARGIN = 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cells(work: Path, direction: str) -> list[Image.Image]:
    """按 sheet 序 × 格序展平成全局帧序列。"""
    cells = []
    for sheet_path in sorted((work / direction).glob("sheet-*.png")):
        cells.extend(slice_sheet(sheet_path))
    return cells


def quantize_shared(frames_by_dir: dict[str, list[Image.Image]], colors: int):
    """全方向共享一块色板（与 h3 管线同策略）, 返回量化函数。"""
    samples = []
    for frames in frames_by_dir.values():
        step = max(1, len(frames) // 6)
        for f in frames[::step]:
            samples.append(f)
    strip_w = SIZE * len(samples)
    strip = Image.new("RGB", (strip_w, SIZE))
    for i, f in enumerate(samples):
        strip.paste(f.convert("RGB"), (i * SIZE, 0))
    pal_img = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)

    def apply(frame: Image.Image) -> Image.Image:
        rgb = frame.convert("RGB")
        q = rgb.quantize(palette=pal_img, dither=Image.Dither.NONE)
        out = q.convert("RGBA")
        out.putalpha(frame.getchannel("A"))  # quantize 转换会破坏 alpha, 必须回填
        return out

    palette = pal_img.getpalette()[: colors * 3]
    return apply, [list(p) for p in zip(*[iter(palette)] * 3)]


def duration_split(total_ms: int, n: int) -> list[int]:
    base, rem = divmod(total_ms, n)
    return [base + 1 if i < rem else base for i in range(n)]


def build_direction(direction: str, frames: list[Image.Image], out_dir: Path,
                    durations: list[int], cfg: dict, palette_rgb: list) -> list[dict]:
    frames_dir = out_dir / direction / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = len(frames)
    atlas_cols = min(ATLAS_COLS, n)
    atlas_rows = (n + atlas_cols - 1) // atlas_cols
    aw = MARGIN * 2 + atlas_cols * (SIZE + GUTTER) - GUTTER
    ah = MARGIN * 2 + atlas_rows * (SIZE + GUTTER) - GUTTER
    atlas = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
    entries, source_indices = [], []
    for i, frame in enumerate(frames):
        col, row = i % atlas_cols, i // atlas_cols
        ox, oy = MARGIN + col * (SIZE + GUTTER), MARGIN + row * (SIZE + GUTTER)
        atlas.paste(frame, (ox, oy))
        fp = frames_dir / f"{i:05d}.png"
        frame.save(fp, optimize=True)
        entries.append({
            "path": f"frames/{i:05d}.png",
            "sha256": sha256(fp),
            "region": [ox, oy, SIZE, SIZE],
            "visible_bounds": visible_bounds(frame),
            "source": {"source_index": i, "source_frame_sha256": sha256(fp),
                       "original": {"gpt_sheet_cell": i, "shared_source_crop_xyxy": None}},
            "duration_ms": durations[i],
        })
        source_indices.append(i)
    atlas.save(out_dir / direction / "atlas.png", optimize=True)
    animation = {
        "version": 1, "size": [SIZE, SIZE], "pivot": list(cfg["pivot"]), "loop": True,
        "atlas": "atlas.png", "effective_source_size": [SIZE, SIZE], "review": "pending",
        "palette_rgb": palette_rgb, "frames": entries,
    }
    (out_dir / direction / "animation.json").write_text(
        json.dumps(animation, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets = sorted(p.name for p in (Path(cfg["work_root"]) / direction).glob("sheet-*.png"))
    report = {
        "version": 1, "pivot": list(cfg["pivot"]), "loop": True,
        "effective_source_size": [SIZE, SIZE], "palette_rgb": palette_rgb,
        "source_indices": source_indices, "durations_ms": durations,
        "sources": [{"kind": "gpt-image-2 sheet", "sheets": sheets}],
        "provenance": {"pipeline": "gpt_sheet_pipeline", "matting": "magenta-chromakey+despill",
                       "palette": f"shared mediancut {cfg['palette_colors']}"},
        "warnings": ["gpt sheet 相位为近似执行, 需人工抽卡复检", "review pending"],
        "visual_review": "pending",
    }
    (out_dir / direction / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return entries


def qc_metrics(frames: list[Image.Image]) -> dict:
    """相邻帧 IoU + 循环闭合, 供抽卡判断。"""
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    ap.add_argument("--directions", nargs="*", default=None)
    args = ap.parse_args()
    raw = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    cfg = dict(raw.get("config", {}))
    cfg.update({k: v for k, v in raw.items() if k != "config"})  # 顶层键覆盖/补充嵌套块
    work_root, out_root = Path(cfg["work_root"]), Path(cfg["out_root"])
    directions = args.directions or cfg["directions"]

    frames_by_dir = {}
    for d in directions:
        cells = load_cells(work_root, d)
        if not cells:
            print(f"[empty] {d}: {work_root/d} 下没有 sheet-*.png")
            continue
        frames = [fit_canvas(matte_cell(c)) for c in cells]
        frames_by_dir[d] = frames
        print(f"[matte] {d}: {len(frames)} 帧")
    if not frames_by_dir:
        return 1

    apply_pal, palette_rgb = quantize_shared(frames_by_dir, cfg["palette_colors"])
    out_root.mkdir(parents=True, exist_ok=True)
    durations = duration_split(cfg["loop_ms"], cfg["frames"])
    character = {"schema_version": 1, "id": cfg["id"], "version": cfg["version"],
                 "default_direction": cfg["default_direction"], "size": [SIZE, SIZE],
                 "pivot": list(cfg["pivot"]), "pixel_size": cfg["pixel_size"],
                 "directions": {}, "stationary_behavior":
                     "Hold a reviewed balanced frame from the current direction; no separately generated idle animation."}
    for d, frames in frames_by_dir.items():
        q_frames = [apply_pal(f) for f in frames]
        build_direction(d, q_frames, out_root, durations[: len(q_frames)], cfg, palette_rgb)
        idle = int(np.argmin([np.asarray(f)[..., 3].sum() for f in frames]))
        character["directions"][d] = {"manifest": f"{d}/animation.json", "idle_frame": idle,
                                      "generation": "gpt-sheet"}
        (out_root / d / "frames").mkdir(exist_ok=True)
        qc = qc_metrics(q_frames)
        print(f"[qc] {d}: {qc}")
    character_path = out_root / "character.json"
    character_path.write_text(json.dumps(character, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] → {out_root} (character.json + {list(frames_by_dir)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
