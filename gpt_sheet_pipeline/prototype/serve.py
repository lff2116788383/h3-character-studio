# -*- coding: utf-8 -*-
"""本地起服务预览换装原型: python serve.py [port]
浏览器打开 http://127.0.0.1:<port>/index.html
"""
import http.server
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ROOT = Path(__file__).resolve().parent

class Handler(http.server.SimpleHTTPRequestHandler):
    # Windows 注册表常把 .js 映射成 text/plain, 导致浏览器拒绝加载 ES module
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
        ".png": "image/png",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)


with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as srv:
    print(f"prototype → http://127.0.0.1:{PORT}/index.html  (Ctrl+C 停止)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
