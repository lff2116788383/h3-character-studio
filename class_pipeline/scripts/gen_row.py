# -*- coding: utf-8 -*-
"""Step 2b: 缺格补行——为跳格/跑偏的动作单独生成一条 8 格横条。

剑客 pilot 实测: attack2 行 c3 跳格, 单行条一次补成（横条比 64 格大表更容
易守住网格）。API 侧尺寸档有限(1536x1024), prompt 要求"画面中央一行 8 格、
上下留品红", 产物宽 8 等分切格, 垂直方向按内容 bbox 裁条。

用法:
  python gen_row.py --class-dir class_pipeline/swordsman --motion attack2
  python gen_row.py --class-dir class_pipeline/swordsman --motion death \
      --poses "第1格后仰；第2格踉跄；……；第8格平躺"
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gpt_client import generate_img2img  # noqa: E402

SIZE = "1536x1024"  # API 稳定横档; 8 格横条居中, 上下留品红由后处理裁掉

# 逐格姿势表（无则用动作整段描述）
POSES = {
    "attack2": (
        "突刺攻击一次性，逐格姿势：第1格背剑站立重心下沉；第2格右手拔剑于腰侧剑柄朝前；"
        "第3格半蹲蓄力剑于腰后；第4格向右全力水平直刺，剑身完全伸出剑刃朝前，前弓步；"
        "第5格刺势保持剑身微下压；第6格收剑回腰侧前滑步；第7格站直剑归腰侧；"
        "第8格回到背剑站立姿势与第1格闭合"
    ),
}


def build_prompt(motion: str, poses: str, sheet: Path) -> str:
    return (
        f"一张单行 8 格横条 sprite 动作表（8列×1行），水平居中排列在画面中部，"
        f"每格一个全身角色，格子上下留纯品红 #ff00ff 空白，背景全为纯品红 #ff00ff，"
        f"无格线无文字无标号无阴影无地面。角色与画风严格同第一张参考图（全动作总表）"
        f"中{motion}行的风格与配色：赭棕短打、藏青披风、深棕斗笠、黑色高单马尾、"
        f"腰间酒葫芦，黑鞘长剑只背在背后（攻击格拔剑在手），严禁腰间横挂剑鞘，"
        f"清晰轮廓 cel shading，面朝画面右侧三四分之三视角，同比例同脚底水平线。"
        f"动作={poses}。第二张参考图是该动作的母版姿势参考。"
        f"（当前 sheet: {sheet.name}）"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", required=True, type=Path)
    ap.add_argument("--motion", required=True, help="动作名, 如 attack2")
    ap.add_argument("--poses", help="8 格逐格姿势描述; 缺省用内置 POSES 表或动作整段描述")
    ap.add_argument("--sheet", type=Path, help="被修的大 sheet; 默认 sheets/ 下最新 all_in_one_v*.png")
    ap.add_argument("--attack-master", type=Path, help="姿势参考; 默认 masters/attack_master.png")
    ap.add_argument("--version", type=int, default=2, help="输出命名 <motion>_row_fix_v<n>.png")
    args = ap.parse_args()

    cd = args.class_dir
    sheet = args.sheet or max(cd.glob("sheets/all_in_one_v*.png"), key=lambda p: p.stat().st_mtime)
    attack_master = args.attack_master or cd / "masters" / "attack_master.png"
    for ref in (sheet, attack_master):
        if not ref.exists():
            raise SystemExit(f"缺少参考图: {ref}")

    poses = args.poses or POSES.get(args.motion, f"{args.motion} 完整 8 格动作循环，首尾闭合")
    out = cd / "sheets" / f"{args.motion}_row_fix_v{args.version}.png"
    generate_img2img(build_prompt(args.motion, poses, sheet), [sheet, attack_master], out, size=SIZE)
    print(f"[done] {out}")
    print("[next] python qc_sheet.py --sheet <out> --cols 8 --rows 1 检查; 通过后 build_class_assets.py 会优先采用补行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
