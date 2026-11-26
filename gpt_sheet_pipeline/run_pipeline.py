# -*- coding: utf-8 -*-
"""编排器: 一条命令跑完 生成 → 构建。

用法:
  python run_pipeline.py --config config.yaml --direction right   # 生成4张sheet并构建
  python run_pipeline.py --config config.yaml --direction right --skip-gen   # 只构建(已有sheet)
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    ap.add_argument("--direction", required=True)
    ap.add_argument("--sheets", type=int, default=4)
    ap.add_argument("--skip-gen", action="store_true")
    args = ap.parse_args()
    if not args.skip_gen:
        master_dir = Path(args.config).parent
        import yaml
        cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
        master = HERE / cfg.get("master_template", "../examples/jade-traveler/masters/{direction}.png").format(direction=args.direction)
        gen = subprocess.run([sys.executable, str(HERE / "gen_sheets.py"), "--master", str(master),
                              "--direction", args.direction, "--sheets", str(args.sheets),
                              "--work", str(HERE / cfg["work_root"])])
        if gen.returncode != 0:
            return gen.returncode
    build = subprocess.run([sys.executable, str(HERE / "build_character.py"), "--config", args.config])
    return build.returncode


if __name__ == "__main__":
    sys.exit(main())
