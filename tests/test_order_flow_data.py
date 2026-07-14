from __future__ import annotations

import hashlib
import urllib.error

import pandas as pd
import pytest

from src.data import order_flow
from src.data.order_flow import (
    FuturesKlineArchiveSpec,
    PublicArchiveSpec,
    archive_path,
    normalize_agg_trades,
    normalize_futures_klines,
    normalize_metrics,
    parse_checksum,
    sha256_file,
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> '_FakeResponse':
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _: int = -1) -> bytes:
        payload, self.payload = self.payload, b''
        return payload


def _agg_trade_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            'agg_trade_id': [1, 2, 3],
            'price': [100.0, 101.0, 102.0],
            'quantity': [2.0, 3.0, 5.0],
            'first_trade_id': [10, 11, 12],
            'last_trade_id': [10, 11, 12],
            'transact_time': [
                1704067200000,
                1704067260000,
                1704153540000,
            ],
            'is_buyer_maker': [False, True, False],
        }
    )


def test_archive_spec_uses_official_futures_path_and_local_structure(tmp_path) -> None:
    spec = PublicArchiveSpec('aggTrades', 'BTCUSDT', '2024-01-01')

    assert spec.url == (
        'https://data.binance.vision/data/futures/um/daily/aggTrades/'
        'BTCUSDT/BTCUSDT-aggTrades-2024-01-01.zip'
    )
    assert archive_path(tmp_path, spec) == (
        tmp_path
        / 'raw'
        / 'aggTrades'
        / 'BTCUSDT'
        / '2024'
        / 'BTCUSDT-aggTrades-2024-01-01.zip'
    )
    monthly = PublicArchiveSpec(
        'aggTrades',
        'BTCUSDT',
        '2024-01',
        cadence_override='monthly',
    )
    assert '/monthly/aggTrades/' in monthly.url
    kline = FuturesKlineArchiveSpec('BTCUSDT', '2024-01-01')
    assert kline.url.endswith(
        '/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2024-01-01.zip'
    )
    monthly_kline = FuturesKlineArchiveSpec(
        'BTCUSDT',
        '2024-01',
        cadence_override='monthly',
    )
    assert monthly_kline.url.endswith(
        '/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2024-01.zip'
    )


def test_checksum_parser_and_file_hash_are_exact(tmp_path) -> None:
    payload = b'order-flow'
    path = tmp_path / 'sample.zip'
    path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()

    assert parse_checksum(f'{expected}  sample.zip\n') == expected
    assert sha256_file(path) == expected


def test_verified_download_retries_transient_network_error(monkeypatch, tmp_path) -> None:
    payload = b'archive'
    checksum = hashlib.sha256(payload).hexdigest().encode()
    responses: list[object] = [
        urllib.error.URLError('temporary TLS failure'),
        _FakeResponse(checksum),
        _FakeResponse(payload),
    ]
    sleeps: list[float] = []

    def fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, _FakeResponse)
        return response

    monkeypatch.setattr(order_flow.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(order_flow.time, 'sleep', lambda seconds: sleeps.append(seconds))
    destination = tmp_path / 'archive.zip'

    result = order_flow._download_verified_archive(
        url='https://example.invalid/archive.zip',
        checksum_url='https://example.invalid/archive.zip.CHECKSUM',
        destination=destination,
    )

    assert result == destination
    assert destination.read_bytes() == payload
    assert sleeps == [0.5]


def test_agg_trades_map_buyer_maker_to_taker_sell_and_fill_day() -> None:
    normalized, audit = normalize_agg_trades(
        _agg_trade_frame(),
        symbol='BTCUSDT',
        day='2024-01-01',
    )

    first = normalized.iloc[0]
    assert len(normalized) == 288
    assert first['base_volume'] == pytest.approx(5.0)
    assert first['taker_buy_base_volume'] == pytest.approx(2.0)
    assert first['taker_sell_base_volume'] == pytest.approx(3.0)
    assert first['signed_base_volume'] == pytest.approx(-1.0)
    assert first['order_flow_imbalance'] == pytest.approx(-0.2)
    assert audit.populated_five_minute_buckets == 2
    assert audit.missing_five_minute_buckets == 286
    assert audit.status == 'FAIL'


def test_duplicate_trade_id_fails_audit() -> None:
    frame = _agg_trade_frame()
    frame.loc[1, 'agg_trade_id'] = 1

    _, audit = normalize_agg_trades(
        frame,
        symbol='BTCUSDT',
        day='2024-01-01',
    )

    assert audit.duplicate_trade_ids == 1
    assert audit.status == 'FAIL'


def test_metrics_require_exact_complete_utc_five_minute_grid() -> None:
    timestamps = pd.date_range('2024-01-01', periods=288, freq='5min')
    frame = pd.DataFrame(
        {
            'create_time': timestamps.astype(str),
            'symbol': 'BTCUSDT',
            'sum_open_interest': 100.0,
            'sum_open_interest_value': 1_000.0,
            'count_toptrader_long_short_ratio': 1.1,
            'sum_toptrader_long_short_ratio': 1.2,
            'count_long_short_ratio': 1.3,
            'sum_taker_long_short_vol_ratio': 1.4,
        }
    )

    normalized, audit = normalize_metrics(
        frame,
        symbol='BTCUSDT',
        day='2024-01-01',
    )

    assert len(normalized) == 288
    assert audit.missing_five_minute_timestamps == 0
    assert audit.duplicate_timestamps == 0
    assert audit.status == 'PASS'


def test_metrics_floor_exchange_second_drift_into_five_minute_bucket() -> None:
    timestamps = pd.date_range('2024-01-01', periods=288, freq='5min')
    timestamps = timestamps.to_series(index=range(288)).astype(str)
    timestamps.iloc[27] = '2024-01-01 02:15:04'
    frame = pd.DataFrame(
        {
            'create_time': timestamps,
            'symbol': 'BTCUSDT',
            'sum_open_interest': 100.0,
            'sum_open_interest_value': 1_000.0,
            'count_toptrader_long_short_ratio': 1.1,
            'sum_toptrader_long_short_ratio': 1.2,
            'count_long_short_ratio': 1.3,
            'sum_taker_long_short_vol_ratio': 1.4,
        }
    )

    normalized, audit = normalize_metrics(
        frame,
        symbol='BTCUSDT',
        day='2024-01-01',
    )

    assert normalized.index[27] == pd.Timestamp('2024-01-01 02:15:00+00:00')
    assert audit.missing_five_minute_timestamps == 0
    assert audit.status == 'PASS'


def test_enhanced_kline_derives_taker_sell_and_signed_flow() -> None:
    timestamps = pd.date_range('2024-01-01', periods=288, freq='5min', tz='UTC')
    open_times = [int(timestamp.timestamp() * 1000) for timestamp in timestamps]
    frame = pd.DataFrame(
        {
            'open_time': open_times,
            'open': 100.0,
            'high': 101.0,
            'low': 99.0,
            'close': 100.5,
            'volume': 10.0,
            'close_time': [value + 299_999 for value in open_times],
            'quote_volume': 1_000.0,
            'count': 20,
            'taker_buy_volume': 6.0,
            'taker_buy_quote_volume': 600.0,
            'ignore': 0,
        }
    )

    normalized, audit = normalize_futures_klines(
        frame,
        symbol='BTCUSDT',
        day='2024-01-01',
    )

    first = normalized.iloc[0]
    assert first['taker_sell_volume'] == pytest.approx(4.0)
    assert first['signed_base_volume'] == pytest.approx(2.0)
    assert first['order_flow_imbalance'] == pytest.approx(0.2)
    assert audit.missing_five_minute_timestamps == 0
    assert audit.status == 'PASS'
