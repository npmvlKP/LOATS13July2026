#!/usr/bin/env python3
"""F8-C-01 external verification: production CMP decision chain is live.

Standalone, self-contained verifier proving the F8-C-01 remediation:
  1. The orchestrator emits 4 distinct enum-tagged signal sources
     (static source scan).
  2. The exact production source set passes the diversity gate
     (4/7 = 0.571 >= 0.5), while the pre-fix 3-source set is rejected.
  3. The REAL price_action producer, driven against fixture OHLCV bars,
     persists a signal tagged ``price_action`` (live DB round-trip).
  4. The REAL four producers, driven together, store >=4 signals whose
     sources satisfy ``validate_signal_sources`` - Step 1 of
     ``create_trade_decision`` passes on production-path output.
  5. Single-engine invariant: scheduler emits zero signals (F8-H-03) and
    the orchestrator retains the full 4-enum production source set (static).
  6. A full decision cycle: real producer signals -> _execute_cmp_strategy
     -> TradeDecision persisted (gating rules mocked; ANALYZE-safe).
  7. Mutation safety: a mutated COPY of the orchestrator (price_action
     emission removed) fails the HC-15 registry probe; the working tree
     is never modified.

Exit code 0 = all checks pass. ASCII-safe output for Windows consoles.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

if sys.platform == "win32":  # ASCII-safe console output (Windows cp1252)
    try:
        if hasattr(sys.stdout, "buffer") and not isinstance(
            sys.stdout, io.TextIOWrapper
        ):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
    except (OSError, ValueError, AttributeError):
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

PASS = 0
FAIL = 0


def ok(name: str, detail: str) -> None:
    global PASS
    PASS += 1
    print(f"[PASS] {name}: {detail}")


def bad(name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    print(f"[FAIL] {name}: {detail}")


def resolve_python() -> str:
    for cand in (
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    ):
        if cand.exists():
            return str(cand)
    return sys.executable


PY = resolve_python()

REQUIRED_SOURCES = {
    "TECHNICAL_ANALYSIS": "ta",
    "SENTIMENT": "sentiment",
    "VOLATILITY": "volatility",
    "PRICE_ACTION": "price_action",
}


# ------------------------------------------------------------------ helpers -


def fixture_rows(n: int = 60) -> list:
    """Deterministic OHLCV bars: mild uptrend, final 5 bars clean up-closes."""
    from loats.models import HistoricalData

    now = datetime.now(UTC)
    rows = []
    close = 24500.0
    for i in range(n):
        open_ = close
        close = close - 8.0 if i % 3 == 2 else close + 12.0
        rows.append(
            HistoricalData(
                symbol="NIFTY",
                timestamp=now - timedelta(minutes=5 * (n - 1 - i)),
                open=open_,
                high=max(open_, close) + 6.0,
                low=min(open_, close) - 6.0,
                close=close,
                volume=1_000_000,
                interval="5min",
            )
        )
    last = rows[-6].close
    for bar in rows[-5:]:
        bar.open = last
        bar.close = last + 15.0
        bar.high = bar.close + 4.0
        bar.low = bar.open - 4.0
        last = bar.close
    return rows


def payload_of(rows: list) -> dict:
    return {
        "data": [
            {
                "timestamp": r.timestamp.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    }


def quote_payload_for(last_price: float) -> dict:
    return {
        "data": {
            "NIFTY": {
                "last_price": last_price,
                "open": last_price - 20.0,
                "high": last_price + 30.0,
                "low": last_price - 40.0,
                "close": last_price - 10.0,
                "volume": 5_000_000,
                "change": 25.0,
                "change_percent": 0.1,
            }
        }
    }


def sentiment_fixture() -> object:
    from loats.models import SentimentAnalysisResult

    return SentimentAnalysisResult(
        symbol="NIFTY",
        timestamp=datetime.now(UTC),
        sentiment_score=0.6,
        sentiment_label="positive",
        news_count=5,
        positive_count=3,
        negative_count=1,
        neutral_count=1,
        top_news=[],
    )


def boundary_patches(orch, db, payload: dict, quote: dict):
    """The standard OpenAlgo/RSS boundary mock stack (nothing else mocked)."""
    return (
        patch("loats.orchestrator.db", db),
        patch.object(orch, "_safe_get_history", new_callable=AsyncMock),
        patch.object(orch, "_safe_get_quotes", new_callable=AsyncMock),
        patch("loats.orchestrator.validate_rss_feed", new_callable=AsyncMock),
        patch(
            "loats.orchestrator.sentiment.analyze_symbol_sentiment",
            new_callable=AsyncMock,
        ),
    )


# ------------------------------------------------------------------ checks --


def check_1_static_emission_sites() -> None:
    text = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(encoding="utf-8")
    sites = set(re.findall(r"StrengthSource\.([A-Z_]+)\.value", text))
    missing = set(REQUIRED_SOURCES) - sites
    if len(sites) >= 4 and not missing:
        ok(
            "1. orchestrator emission sites",
            f"{len(sites)} distinct enum tags: {sorted(sites)}",
        )
    else:
        bad(
            "1. orchestrator emission sites",
            f"only {sorted(sites)}; missing {sorted(missing)}",
        )


def check_2_gate_arithmetic() -> None:
    from loats.strength import StrengthEngine

    engine = StrengthEngine()

    def probe(srcs: list[str]):
        return engine.validate_signal_sources(
            [SimpleNamespace(metadata={"source": s}) for s in srcs]
        )

    pre = probe(["ta", "sentiment", "volatility"])
    post = probe(["ta", "sentiment", "volatility", "price_action"])
    div3 = pre[1].get("diversity_score")
    div4 = post[1].get("diversity_score")
    if (
        pre[0] is False
        and post[0] is True
        and isinstance(div3, float)
        and isinstance(div4, float)
        and abs(div4 - 4 / 7) < 1e-9
    ):
        ok(
            "2. gate arithmetic",
            f"3-src rejected ({div3:.4f} < 0.5); production 4-src set passes "
            f"({div4:.4f} >= 0.5)",
        )
    else:
        bad("2. gate arithmetic", f"pre={pre} post={post}")


def check_3_live_price_action_producer() -> None:
    from loats.database import Database
    from loats.orchestrator import TradingOrchestrator
    from loats.strength import StrengthSource

    rows = fixture_rows(60)
    payload = payload_of(rows)

    with tempfile.TemporaryDirectory() as td:
        db = Database(db_path=Path(td) / "v.db", audit_log_path=Path(td) / "a.jsonl")
        db._initialize_database()
        orch = TradingOrchestrator()

        async def run() -> list:
            with (
                patch("loats.orchestrator.db", db),
                patch.object(orch, "_safe_get_history", new_callable=AsyncMock) as mh,
            ):
                mh.return_value = payload
                await orch._execute_price_action_analysis()
            return await db.async_get_latest_signals("NIFTY", limit=5)

        stored = asyncio.run(run())
        if len(stored) == 1 and (
            stored[0].metadata.get("source") == StrengthSource.PRICE_ACTION.value
        ):
            ok(
                "3. live price_action producer",
                f"stored signal source={stored[0].metadata['source']} "
                f"type={stored[0].signal_type.value} "
                f"strength={stored[0].strength:.3f}",
            )
        else:
            bad(
                "3. live price_action producer",
                f"stored={len(stored)} meta={stored[0].metadata if stored else None}",
            )
        db.close_all()


def check_4_all_four_producers_stored_set() -> None:
    from loats.database import Database
    from loats.orchestrator import TradingOrchestrator
    from loats.strength import StrengthEngine

    rows = fixture_rows(60)
    payload = payload_of(rows)
    quote = quote_payload_for(rows[-1].close)

    with tempfile.TemporaryDirectory() as td:
        db = Database(db_path=Path(td) / "v.db", audit_log_path=Path(td) / "a.jsonl")
        db._initialize_database()
        orch = TradingOrchestrator()

        async def run() -> list:
            with (
                patch("loats.orchestrator.db", db),
                patch.object(orch, "_safe_get_history", new_callable=AsyncMock) as mh,
                patch.object(orch, "_safe_get_quotes", new_callable=AsyncMock) as mq,
                patch(
                    "loats.orchestrator.validate_rss_feed",
                    new_callable=AsyncMock,
                ) as mrss,
                patch(
                    "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                    new_callable=AsyncMock,
                ) as msent,
            ):
                mh.return_value = payload
                mq.return_value = quote
                mrss.return_value = True
                msent.return_value = sentiment_fixture()
                await orch._execute_ta_analysis()
                await orch._execute_sentiment_analysis()
                await orch._execute_volatility_analysis()
                await orch._execute_price_action_analysis()
            return await db.async_get_latest_signals("NIFTY", limit=10)

        stored = asyncio.run(run())
        sources = {s.metadata.get("source") for s in stored}
        expected = set(REQUIRED_SOURCES.values())
        engine = StrengthEngine()
        vok, vdet = engine.validate_signal_sources(stored)
        if expected <= sources and vok is True:
            ok(
                "4. four producers -> stored set passes gate",
                f"{len(stored)} signals, sources={sorted(sources)}, "
                f"diversity={vdet.get('diversity_score'):.4f}",
            )
        else:
            bad(
                "4. four producers -> stored set passes gate",
                f"stored={len(stored)} sources={sorted(sources)} vok={vok}",
            )
        db.close_all()


def check_5_scheduler_tags() -> None:
    """Check 5 (stale-check remediation, F8-M-02 follow-up).

    F8-H-03 retired all scheduler signal-emitting jobs — the orchestrator
    is the sole signal engine of record, so the old grep for scheduler
    ``scan_type``/source tags could never pass again. The invariant it
    was proxying is now asserted directly: the scheduler must contain
    ZERO signal-emission tokens, and the full production source set
    (4 enum tags, all emitted by the orchestrator) must remain present.
    """
    sched = (REPO_ROOT / "src" / "loats" / "scheduler.py").read_text(encoding="utf-8")
    signal_tokens = re.findall(r"StrengthSource|scan_type|\bSignal\b", sched)
    orch = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(encoding="utf-8")
    sites = set(re.findall(r"StrengthSource\.([A-Z_]+)\.value", orch))
    missing = set(REQUIRED_SOURCES) - sites
    if not signal_tokens and not missing:
        ok(
            "5. single-engine source tags",
            "scheduler emits zero signals (F8-H-03); orchestrator retains "
            f"{len(sites)} enum sources: {sorted(sites)}",
        )
    else:
        bad(
            "5. single-engine source tags",
            f"scheduler signal tokens={signal_tokens[:5]} "
            f"orchestrator missing={sorted(missing)}",
        )


def check_6_full_decision_cycle() -> None:
    from loats.database import Database
    from loats.orchestrator import TradingOrchestrator

    rows = fixture_rows(60)
    payload = payload_of(rows)
    quote = quote_payload_for(rows[-1].close)
    funds = {
        "data": {
            "available_cash": 100000.0,
            "utilized_margin": 20000.0,
            "available_margin": 80000.0,
            "total_equity": 120000.0,
        }
    }

    with tempfile.TemporaryDirectory() as td:
        db = Database(db_path=Path(td) / "v.db", audit_log_path=Path(td) / "a.jsonl")
        db._initialize_database()
        orch = TradingOrchestrator()

        async def run() -> list:
            # Phase 1: run the four REAL producers.
            with (
                patch("loats.orchestrator.db", db),
                patch.object(orch, "_safe_get_history", new_callable=AsyncMock) as mh,
                patch.object(orch, "_safe_get_quotes", new_callable=AsyncMock) as mq,
                patch(
                    "loats.orchestrator.validate_rss_feed",
                    new_callable=AsyncMock,
                ) as mrss,
                patch(
                    "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                    new_callable=AsyncMock,
                ) as msent,
            ):
                mh.return_value = payload
                mq.return_value = quote
                mrss.return_value = True
                msent.return_value = sentiment_fixture()
                await orch._execute_ta_analysis()
                await orch._execute_sentiment_analysis()
                await orch._execute_volatility_analysis()
                await orch._execute_price_action_analysis()

            # Phase 2: decision cycle on the real stored signals (only the
            # gating rule engine and funding boundaries are mocked).
            with (
                patch("loats.trade_decision.rules_engine") as mrules,
                patch("loats.orchestrator.db", db),
                patch.object(orch, "_safe_get_history", new_callable=AsyncMock) as mh2,
                patch.object(orch, "_safe_get_quotes", new_callable=AsyncMock) as mq2,
                patch.object(orch, "_safe_get_funds", new_callable=AsyncMock) as mf,
                patch.object(
                    orch, "_safe_get_position_book", new_callable=AsyncMock
                ) as mp,
            ):
                mrules.apply_gating_rules.return_value = (
                    True,
                    {"reason": "gating_passed"},
                )
                mrules.check_position_limits.return_value = (
                    True,
                    {"reason": "within_limits"},
                )
                mrules.session_state = "REGULAR"
                mh2.return_value = payload
                mq2.return_value = quote
                mf.return_value = funds
                mp.return_value = {"data": []}
                await orch.initialize()
                await orch._execute_cmp_strategy()
                await orch.shutdown()
            return await asyncio.to_thread(
                db.get_trade_decisions, symbol="NIFTY", limit=1
            )

        decisions = asyncio.run(run())
        if len(decisions) == 1:
            d = decisions[0]
            ok(
                "6. full decision cycle",
                f"TradeDecision {d.decision_id} status={d.status} "
                f"strength={d.composite_strength:.4f}",
            )
        else:
            bad(
                "6. full decision cycle",
                f"expected exactly 1 decision, got {len(decisions)}",
            )
        db.close_all()


def check_7_mutation_safety() -> None:
    """Mutate a COPY of orchestrator.py; the HC-15 probe must fail.

    The probe reads ``src/loats/orchestrator.py`` relative to its own
    location, so we copy the probe next to a mutated tree snapshot in a
    temp dir and run it with the venv interpreter. The working tree is
    never touched.
    """
    import subprocess

    with tempfile.TemporaryDirectory() as td:
        tree = Path(td) / "snap"
        (tree / "src" / "loats").mkdir(parents=True)
        (tree / "scripts").mkdir(parents=True)
        orch_text = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        mutated = orch_text.replace(
            '"source": StrengthSource.PRICE_ACTION.value,',
            '"source": "mutated_out",',
        )
        if mutated == orch_text:
            bad("7. mutation safety", "mutation anchor not found in source")
            return
        (tree / "src" / "loats" / "orchestrator.py").write_text(
            mutated, encoding="utf-8"
        )
        probe_src = (REPO_ROOT / "scripts" / "probe_hc15_strength_gate.py").read_text(
            encoding="utf-8"
        )
        (tree / "scripts" / "probe_hc15_strength_gate.py").write_text(
            probe_src, encoding="utf-8"
        )
        result = subprocess.run(
            [PY, str(tree / "scripts" / "probe_hc15_strength_gate.py")],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=60,
        )
        if result.returncode != 0:
            ok(
                "7. mutation safety",
                "HC-15 probe FAILED on mutated copy (rc="
                f"{result.returncode}) as required; working tree untouched",
            )
        else:
            bad(
                "7. mutation safety",
                "HC-15 probe PASSED on mutated copy - production check is "
                "not catching producer removal",
            )


# -------------------------------------------------------------------- main --


def main() -> int:
    print("=" * 72)
    print("F8-C-01 EXTERNAL VERIFICATION - production CMP decision chain")
    print("=" * 72)
    check_1_static_emission_sites()
    check_2_gate_arithmetic()
    check_3_live_price_action_producer()
    check_4_all_four_producers_stored_set()
    check_5_scheduler_tags()
    check_6_full_decision_cycle()
    check_7_mutation_safety()
    print("-" * 72)
    print(f"RESULT: {PASS}/{PASS + FAIL} checks passed")
    if FAIL:
        print("STATUS : FAILURES PRESENT - chain NOT verified live")
        return 1
    print("STATUS : ALL CHECKS PASSED - production chain verified live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
