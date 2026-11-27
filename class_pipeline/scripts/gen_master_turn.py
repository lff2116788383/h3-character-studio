# -*- coding: utf-8 -*-
"""Step 1b: 母版转向——从 right 透明母版生成 up(背面)/down(正面) 同姿势母版。

四方向扩展(README §4 Step6)的第一步: up/down 一锅出生成前, 母版需先转向,
否则面朝右的姿势参考会把整张 sheet 拉回右向。身份锚(立绘) + 姿势锚(源母版)
双参考, 透明直出与主产线一致。

用法:
  python gen_master_turn.py --class-dir class_pipeline/swordsman --facing up --motion walk
  python gen_master_turn.py --class-dir class_pipeline/swordsman --facing down --motion attack
输出: masters/<motion>_master_<facing>.png（约 0.09 元/张）
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gpt_client import generate_img2img  # noqa: E402

SIZE = "1024x1024"

PROMPT = {
    "up": (
        "游戏 sprite 单帧角色，同一角色转成**背面视角**（面朝画面深处远离观众，观众看到"
        "完整背部）：宽檐斗笠从背后看的弧形轮廓，黑色高马尾从斗笠后缘垂下，黑鞘长剑横背在"
        "背后剑身轮廓完整可见剑柄在左肩后垂青穗，藏青短披风自然垂落，赭棕短打劲装背面，"
        "腰间络绳酒葫芦。姿势、比例、配色、cel shading 画风与参考图中的角色完全一致，"
        "清晰轮廓，无背景元素、无阴影、无地面、无文字，背景完全透明（alpha 全 0），"
        "严禁品红色与棋盘格。全身单人立姿，脚底水平。"
    ),
    "down": (
        "游戏 sprite 单帧角色，同一角色转成**正面视角**（面朝观众）：完整正脸清晰可见，"
        "宽檐斗笠帽檐前倾遮眉，黑鞘长剑背在背后不可见仅左肩后露剑柄垂青穗，藏青短披风"
        "两肩对称垂落，赭棕短打劲装正面，腰间络绳酒葫芦。姿势、比例、配色、cel shading"
        " 画风与参考图中的角色完全一致，清晰轮廓，无背景元素、无阴影、无地面、无文字，"
        "背景完全透明（alpha 全 0），严禁品红色与棋盘格。全身单人立姿，脚底水平。"
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", required=True, type=Path)
    ap.add_argument("--facing", required=True, choices=["up", "down"])
    ap.add_argument("--motion", default="walk", choices=["walk", "attack"],
                    help="姿势源: walk→walk_master.png / attack→attack_master.png")
    ap.add_argument("--source", type=Path, help="姿势参考母版; 默认 masters/<motion>_master.png")
    ap.add_argument("--portrait", type=Path, help="身份锚立绘; 默认 portraits/lihui_hat.png")
    args = ap.parse_args()

    cd = args.class_dir
    source = args.source or cd / "masters" / f"{args.motion}_master.png"
    portrait = args.portrait or cd / "portraits" / "lihui_hat.png"
    for ref in (source, portrait):
        if not ref.exists():
            raise SystemExit(f"缺少参考图: {ref}")

    out = cd / "masters" / f"{args.motion}_master_{args.facing}.png"
    generate_img2img(PROMPT[args.facing], [portrait, source], out, size=SIZE, transparent=True)
    print(f"[done] {out}")
    print(f"[next] 四方向一锅出: python gen_all_in_one.py --class-dir {cd} "
          f"--transparent --facing {args.facing}（需 walk/attack 双母版齐）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
