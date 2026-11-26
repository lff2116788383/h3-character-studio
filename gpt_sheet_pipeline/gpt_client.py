# -*- coding: utf-8 -*-
"""gpt-image-2 生图客户端（自包含，供 gpt_sheet_pipeline 使用）。

密钥来源: 环境变量 GPT_IMAGE_API_KEY 或本目录 .secret-ui.env。
"""
import base64
import io
import os
import time
from pathlib import Path

import requests
from PIL import Image

BASE_URL = "https://proxy.onetoken.uk"
MODEL = "gpt-image-2"
DIR = Path(__file__).resolve().parent


def load_api_key() -> str:
    key = os.environ.get("GPT_IMAGE_API_KEY", "").strip()
    if key:
        return key
    try:
        with (DIR / ".secret-ui.env").open(encoding="utf-8") as config:
            for line in config:
                name, separator, value = line.strip().partition("=")
                if separator and name.strip() == "GPT_IMAGE_API_KEY":
                    key = value.strip()
                    if key:
                        return key
    except FileNotFoundError:
        pass
    raise RuntimeError("缺少 GPT_IMAGE_API_KEY: 设置环境变量或在 gpt_sheet_pipeline/.secret-ui.env 配置")


def _download(payload: dict, proxies) -> bytes:
    b64 = payload.get("b64_json", "")
    if b64:
        return base64.b64decode(b64)
    url = payload.get("url", "")
    if not url:
        raise RuntimeError("响应中缺少图像数据")
    response = requests.get(url, timeout=180, proxies=proxies)
    response.raise_for_status()
    return response.content


def generate_img2img(prompt: str, ref_paths: list, out_path: Path, size: str = "1024x1024") -> Path:
    """图生图(edits): 多参考图 + prompt → PNG。失败重试 3 次(第 2 次起走本地代理)。"""
    out_path = Path(out_path)
    if out_path.exists():
        return out_path
    api_key = load_api_key()
    multipart = []
    for p in ref_paths:
        p = Path(p)
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        multipart.append(("image[]", (p.name, p.read_bytes(), mime)))
    data = {"model": MODEL, "prompt": prompt, "size": size, "n": "1"}
    last_error = ""
    for attempt in range(3):
        proxies = None if attempt == 0 else {"https": "http://127.0.0.1:7897"}
        try:
            t = time.time()
            r = requests.post(
                f"{BASE_URL}/v1/images/edits",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files=multipart,
                timeout=600,
                proxies=proxies,
            )
            print(f"[gen] {out_path.name} attempt={attempt+1} http={r.status_code} {time.time()-t:.1f}s", flush=True)
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                time.sleep(2 + attempt * 3)
                continue
            raw = _download(r.json()["data"][0], proxies)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img = Image.open(io.BytesIO(raw))
            img.load()
            img.save(out_path, optimize=True)
            return out_path
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"[:120]
            print(f"[retry] {out_path.name} {last_error}", flush=True)
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"generation failed for {out_path.name}: {last_error}")
