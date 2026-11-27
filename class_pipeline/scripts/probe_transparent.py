# -*- coding: utf-8 -*-
"""探针: 验证 proxy.onetoken.uk 的 gpt-image-2 是否支持 background=transparent。

背景问题: 产线目前强制"品红底生成→抠图"。官方 gpt-image 系列支持
background=transparent + output_format=png 直接出真 alpha。本探针发一次
最小请求验证: ①参数是否被接受 ②返回是否真 RGBA ③边缘/棋盘格质量。

用法: python probe_transparent.py [ref_image]
产出: swordsman/sheets/transparent_probe/{raw_response.txt, probe_transparent.png, alpha_report.txt}
"""
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpt_client import BASE_URL, MODEL, load_api_key  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "swordsman" / "sheets" / "transparent_probe"


def main() -> int:
    ref = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parent.parent / "swordsman" / "masters" / "walk_master.png"
    OUT.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()

    prompt = ("将参考图中的角色完整重绘为单帧全身 sprite：姿势、服装、配色、细节与参考图完全一致。"
              "背景必须是完全透明（alpha 全 0），严禁品红色底、严禁棋盘格纹理、严禁任何背景元素。")
    data = {
        "model": MODEL,
        "prompt": prompt,
        "size": "1024x1024",
        "n": "1",
        "background": "transparent",
        "output_format": "png",
    }
    files = [("image[]", (ref.name, ref.read_bytes(), "image/png"))]
    r = requests.post(
        f"{BASE_URL}/v1/images/edits",
        headers={"Authorization": f"Bearer {api_key}"},
        data=data,
        files=files,
        timeout=600,
    )
    (OUT / "raw_response.txt").write_text(
        f"status={r.status_code}\ncontent-type={r.headers.get('content-type')}\n\n"
        f"{r.text[:2000]}", encoding="utf-8")
    print(f"HTTP {r.status_code}")

    if r.status_code != 200:
        print("→ API 拒绝了 background=transparent 参数，品红底是现实约束。")
        print((r.text or "")[:300])
        return 1

    payload = r.json()["data"][0]
    raw = base64.b64decode(payload.get("b64_json", "")) if payload.get("b64_json") else None
    if raw is None:
        import requests as rq
        raw = rq.get(payload["url"], timeout=180).content
    img = Image.open(io.BytesIO(raw))
    img.load()
    img.save(OUT / "probe_transparent.png", optimize=True)

    rep = []
    rep.append(f"mode={img.mode} size={img.size} format={img.format}")
    if img.mode in ("RGBA", "LA") or "transparency" in img.info:
        a = np.asarray(img.convert("RGBA"))[..., 3]
        transparent = float((a < 10).mean())
        opaque = float((a > 245).mean())
        partial = 1.0 - transparent - opaque
        rep.append(f"alpha: 全透明占比={transparent:.1%} 全不透明占比={opaque:.1%} "
                   f"半透明占比={partial:.1%} min={a.min()} max={a.max()}")
        if transparent > 0.15:
            rep.append("判定: 返回了真透明底 ✓")
        else:
            rep.append("判定: 参数被接受但返回不透明/伪透明 ✗")
        checker = np.asarray(img.convert("RGB")).astype(np.float32)
        gray = checker.mean(-1)
        # 棋盘格检测: 背景区 8px 邻域方差
        mask = a < 10
        if mask.sum() > 100:
            rep.append(f"透明区平均亮度={gray[mask].mean():.1f} (棋盘格会在 60~200 之间震荡)")
    else:
        rep.append("判定: 返回无 alpha 通道 ✗")
    report = "\n".join(rep)
    (OUT / "alpha_report.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
