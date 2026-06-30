"""
量化回测系统 — FastAPI 入口。

启动方式：
    python main.py
然后浏览器打开 http://127.0.0.1:8000
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()


def configure_console_encoding() -> None:
    """Keep Python output readable in UTF-8 terminals."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


configure_console_encoding()

# 日志
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="量化回测系统", version="0.1.0")

# 静态文件
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# 路由
from src.web.routes import router  # noqa: E402

app.include_router(router)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"\nQuant Backtest System: http://{host}:{port}\n")
    uvicorn.run("main:app", host=host, port=port, reload=True)
