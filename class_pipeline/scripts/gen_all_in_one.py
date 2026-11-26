# -*- coding: utf-8 -*-
"""Step 2: 一锅出全动作 sheet（8列×8行=64格, 每行一个动作, 一次生成）。

剑客 pilot 实测（2026-11-27, 会话内 seedream 5.5）: walk/idle/attack1/death/
run/hit 六行全部成完整序列, 仅 attack2 行 c3 跳格+c5 跑偏 → 缺格用 gen_row.py
补行修复。"一锅出 + 缺格补行"产线, 相比旧链式(27帧×4张/动作)省约 3/4 成本,
且同次生成内角色一致性更好(所有帧同源, 无传话游戏退化)。

用法:
  python gen_all_in_one.py --class-dir class_pipeline/swordsman
  python gen_all_in_one.py --class-dir class_pipeline/swordsman --out <path>   # 重抽: 先删旧产物
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gpt_client import generate_img2img  # noqa: E402

COLS, ROWS = 8, 8
SIZE = "1536x1536"  # 实测上限 1536, 传 2048 会被回落; cell=192×192

# 行分配表: 行号 → (动作名, 8格动作描述)。
# 帧数规划见 README「动作与帧数」; 每行固定 8 格便于切格与工具导入。
ROW_LAYOUT = [
    ("walk", "行走循环，双足交替 contact-passing 大步幅双臂反摆，第8格姿势回到与第1格衔接成闭环"),
    ("idle", "待机呼吸循环，身体重心轻微起伏，马尾披风微飘，双脚位置不动"),
    ("attack1", "挥砍攻击一次性，从背剑起手拔剑过顶举剑→向右前方全力劈下→收势回背剑，动势连贯"),
    ("attack2", "突刺攻击一次性，收剑于腰侧→向右水平直刺剑刃朝前→收剑"),
    ("death", "死亡一次性，受击后仰→踉跄后退→腿软倒地→末格平躺地面姿势"),
    ("run", "跑步循环，比行走幅度更大身体前倾双臂大幅摆动"),
    ("hit", "受击，前3格身体后仰缩肩捂胸，其余格子保持纯品红空"),
    ("spare", "整行全部保持纯品红空格子"),
]

PROMPT_HEAD = (
    "游戏 sprite 全动作总表，一张图内 {cols}列×{rows}行共{total}个等大格子紧密排列"
    "无缝隙无间隙，每格内一个完整全身角色，纯色品红 #ff00ff 背景填满所有格子间空隙，"
    "无格线无文字无标号无阴影无地面。角色与画风严格同参考图：赭棕短打劲装、藏青短披风、"
    "腰间只挂络绳酒葫芦、黑鞘长剑背在背后剑柄露左肩垂青穗、深棕宽檐斗笠、黑色高单马尾，"
    "清晰轮廓 cel shading，严禁腰间出现任何横挂的剑或剑鞘。所有格子角色同比例同脚底水平线，"
    "面朝画面右侧的正面三四分之三视角，斗笠形态。各行动作（从上到下）："
)


def build_prompt() -> str:
    lines = [PROMPT_HEAD.format(cols=COLS, rows=ROWS, total=COLS * ROWS)]
    for i, (motion, desc) in enumerate(ROW_LAYOUT, 1):
        lines.append(f"第{i}行{COLS}格={desc}；")
    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-dir", required=True, type=Path, help="如 classes/swordsman")
    ap.add_argument("--portrait", type=Path, help="定稿立绘(斗笠形态); 默认 portraits/lihui_hat.png")
    ap.add_argument("--walk-master", type=Path, help="默认 masters/walk_master.png")
    ap.add_argument("--attack-master", type=Path, help="默认 masters/attack_master.png")
    ap.add_argument("--out", type=Path, help="输出 sheet; 默认 sheets/all_in_one_v{n}.png")
    ap.add_argument("--version", type=int, default=1, help="抽卡版本号, 命名 all_in_one_v<n>.png")
    args = ap.parse_args()

    cd = args.class_dir
    portrait = args.portrait or cd / "portraits" / "lihui_hat.png"
    walk_master = args.walk_master or cd / "masters" / "walk_master.png"
    attack_master = args.attack_master or cd / "masters" / "attack_master.png"
    out = args.out or cd / "sheets" / f"all_in_one_v{args.version}.png"

    for ref in (portrait, walk_master, attack_master):
        if not ref.exists():
            raise SystemExit(f"缺少参考图: {ref}")

    prompt = build_prompt()
    generate_img2img(prompt, [portrait, walk_master, attack_master], out, size=SIZE)
    print(f"[done] {out}\n[prompt 长度] {len(prompt)} 字")
    print("[next] python qc_sheet.py --sheet <out> 检查空格/序列, 缺格行用 gen_row.py 补")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
