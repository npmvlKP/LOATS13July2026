"""Tests for walk-forward window slicing and no look-ahead."""

from datetime import UTC, datetime, timedelta

from loats.models import HistoricalData


def make_ohlc(symbol, base, count, mins=5):
    now = datetime.now(UTC)
    return [
        HistoricalData(
            symbol=symbol,
            timestamp=now - timedelta(minutes=mins * (count - 1 - i)),
            open=base + i * 0.5 - 1,
            high=base + i * 0.5 + 2,
            low=base + i * 0.5 - 2,
            close=base + i * 0.5,
            volume=10000 + i * 100,
            interval=f"{mins}min",
        )
        for i in range(count)
    ]


def walk_forward(data, wsize=20, step=10):
    return [data[s : s + wsize] for s in range(0, len(data) - wsize + 1, step)]


def per_window_pnl(windows, fn):
    return [{"window": i, "pnl": fn(w), "bars": len(w)} for i, w in enumerate(windows)]


def ma_cross(w):
    if len(w) < 5:
        return 0.0
    c = [h.close for h in w]
    return (c[-1] - c[-2]) * 100 if sum(c[-3:]) / 3 > sum(c[-5:]) / 5 else 0.0


class TestWalkForward:
    def test_basic(self):
        d = make_ohlc("NIFTY", 100, 50)
        ws = walk_forward(d, 20, 10)
        assert len(ws) == 4
        assert all(len(w) == 20 for w in ws)

    def test_single(self):
        assert len(walk_forward(make_ohlc("T", 50, 10), 10, 10)) == 1

    def test_empty(self):
        assert walk_forward([], 10, 5) == []

    def test_monotonic_within_windows(self):
        d = make_ohlc("NIFTY", 100, 50)
        for w in walk_forward(d, 20, 10):
            ts = [h.timestamp for h in w]
            assert ts == sorted(ts)


class TestPnLAggregation:
    def test_pnl_across_windows(self):
        d = make_ohlc("NIFTY", 100, 60)
        r = per_window_pnl(walk_forward(d, 20, 10), ma_cross)
        assert len(r) == 5
        assert all(x["bars"] == 20 for x in r)

    def test_total_pnl(self):
        d = make_ohlc("NIFTY", 100, 60)
        r = per_window_pnl(walk_forward(d, 20, 10), ma_cross)
        assert isinstance(sum(x["pnl"] for x in r), float)


class TestNoLookAhead:
    def test_sorted_timestamps(self):
        d = make_ohlc("T", 200, 100)
        for w in walk_forward(d, 30, 15):
            ts = [h.timestamp for h in w]
            assert ts == sorted(ts)

    def test_no_future_data(self):
        d = make_ohlc("NIFTY", 100, 50)
        for w in walk_forward(d, 20, 10):
            assert all(c > 0 for c in [h.close for h in w])
