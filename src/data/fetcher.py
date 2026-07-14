"""
数据获取模块：从交易所拉取历史 K 线数据并保存到本地 CSV。

用法：
    python -m src.data.fetcher                          # 默认 BTC/USDT 1h 拉 1 年
    python -m src.data.fetcher --symbol ETH/USDT --timeframe 4h --days 90
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")  # 加载 .env（回测阶段不需要 API key，但保留入口）

logger = logging.getLogger(__name__)


def configure_console_encoding() -> None:
    """Keep CLI output readable in UTF-8 terminals."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

# CSV 列名：与 backtesting.py 的期望对齐（Open/High/Low/Close/Volume 大写）
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# 币安国内可用域名列表（按优先级尝试）
_BINANCE_URLS = [
    "https://api.binance.com",     # 国际站
]


class DataFetcher:
    """从交易所拉取 K 线数据并保存为 CSV。"""

    def __init__(
        self,
        exchange_id: str = "binance",
        proxy: str | None = None,
        timeout: int = 30000,
    ) -> None:
        config: dict = {
            "enableRateLimit": True,  # 币安有频率限制，开启自动限速
            "timeout": timeout,
        }

        # 代理设置（支持 http://127.0.0.1:7890 格式）
        if proxy:
            config["proxies"] = {
                "http": proxy,
                "https": proxy,
            }
            logger.info("Using proxy: %s", proxy)

        # 币安自定义域名（仅当 BINANCE_API_URL 环境变量有值时覆盖）
        if exchange_id == "binance":
            custom_url = os.getenv("BINANCE_API_URL", "")
            if custom_url:
                base_url = custom_url.rstrip("/")
                # ccxt binance 的 URL 是嵌套结构
                config["urls"] = {
                    "api": {
                        "public": base_url,
                        "private": base_url,
                        "sapi": base_url,
                        "fapiPublic": base_url,
                        "fapiPrivate": base_url,
                        "dapiPublic": base_url,
                        "dapiPrivate": base_url,
                    }
                }

        self.exchange: ccxt.Exchange = getattr(ccxt, exchange_id)(config)

    def fetch_ohlcv(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """从交易所拉取 OHLCV 数据。

        Args:
            symbol: 交易对象，如 BTC/USDT、ETH/USDT
            timeframe: K 线周期，1m/5m/15m/1h/4h/1d/1w
            since: 起始时间（UTC），None 表示最近 1 年
            until: 结束时间（UTC，包含边界），None 表示拉到交易所可用最新数据
            limit: 拉取条数（交易所单次通常最大 1000）

        Returns:
            DataFrame，索引为 UTC 时间，列为 Open/High/Low/Close/Volume
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=365)

        since_ms = int(since.timestamp() * 1000)
        until_ms = int(until.timestamp() * 1000) if until is not None else None
        all_candles: list[list[float]] = []

        logger.info(
            "Fetching %s %s since %s (limit=%s)",
            symbol,
            timeframe,
            since.isoformat(),
            limit or "default",
        )

        # 分批拉取（币安每次最多 1000 条）
        while True:
            new_candles = self.exchange.fetch_ohlcv(
                symbol,
                timeframe,
                since=since_ms,
                limit=limit or 1000,
            )

            if not new_candles:
                break

            if until_ms is None:
                filtered_candles = new_candles
            else:
                filtered_candles = [candle for candle in new_candles if int(candle[0]) <= until_ms]

            all_candles.extend(filtered_candles)

            # 下一批的起始时间
            last_ts = new_candles[-1][0]
            if until_ms is not None and int(last_ts) >= until_ms:
                break

            if last_ts == since_ms and len(new_candles) == 1:
                break

            since_ms = last_ts + 1

            # 如果拉取的条数小于请求的 limit，说明已经拉完了
            if len(new_candles) < (limit or 1000):
                break

        logger.info("Fetched %d candles for %s %s", len(all_candles), symbol, timeframe)

        # 转换为 DataFrame
        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "Open", "High", "Low", "Close", "Volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)

        # 去重（有时边界会重）
        df = df[~df.index.duplicated(keep="first")]

        return df[_COLUMNS]

    def fetch_and_save(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        since: datetime | None = None,
        until: datetime | None = None,
        data_dir: str | Path = DEFAULT_DATA_DIR,
    ) -> Path:
        """拉取数据并保存到 CSV。

        Returns:
            保存的文件路径
        """
        df = self.fetch_ohlcv(symbol=symbol, timeframe=timeframe, since=since, until=until)

        # 文件命名：BTC_USDT_1h.csv
        safe_symbol = symbol.replace("/", "_")
        filename = f"{safe_symbol}_{timeframe}.csv"
        filepath = Path(data_dir) / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(filepath)
        logger.info("Saved %d rows to %s", len(df), filepath)

        return filepath

    def load_local(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        data_dir: str | Path = DEFAULT_DATA_DIR,
    ) -> pd.DataFrame:
        """从本地 CSV 加载已有数据。"""
        safe_symbol = symbol.replace("/", "_")
        filepath = Path(data_dir) / f"{safe_symbol}_{timeframe}.csv"

        if not filepath.exists():
            raise FileNotFoundError(f"本地数据不存在: {filepath}，请先运行 fetch_and_save")

        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        logger.info("Loaded %d rows from %s", len(df), filepath)
        return df


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    configure_console_encoding()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="从交易所拉取历史 K 线数据")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对象（默认 BTC/USDT）")
    parser.add_argument("--timeframe", default="1h", help="K 线周期（默认 1h）")
    parser.add_argument("--days", type=int, default=365, help="拉取天数（默认 365）")
    parser.add_argument("--data-dir", default="./data", help="数据存储目录")
    parser.add_argument("--proxy", default=None, help="HTTP 代理地址（如 http://127.0.0.1:7890）")
    parser.add_argument("--exchange", default="binance", help="交易所 ID（ccxt 格式，默认 binance）")
    args = parser.parse_args()

    fetcher = DataFetcher(exchange_id=args.exchange, proxy=args.proxy)
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    filepath = fetcher.fetch_and_save(
        symbol=args.symbol,
        timeframe=args.timeframe,
        since=since,
        data_dir=args.data_dir,
    )
    print(f"数据已保存: {filepath}")
