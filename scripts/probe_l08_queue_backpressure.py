"""L08 production probe: TradeDecisionEngine queue backpressure.

Verifies that a TradeDecisionEngine with maxsize=2 accepts exactly 2
enqueue_decision() calls and rejects the 3rd with status='rejected'.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loats.models import SignalType, TradeDecision
from loats.trade_decision import TradeDecisionEngine


def _mk(i: int) -> TradeDecision:
    return TradeDecision(
        symbol="NIFTY",
        decision_type=SignalType.BUY,
        composite_strength=0.8,
        timestamp=datetime.now(UTC),
        entry_price=100.0 + i,
        quantity=1,
        stop_loss=95.0,
        risk_percentage=0.02,
    )


async def main() -> None:
    eng = TradeDecisionEngine(maxsize=2)
    r1 = await eng.enqueue_decision(_mk(1))
    r2 = await eng.enqueue_decision(_mk(2))
    r3 = await eng.enqueue_decision(_mk(3))
    assert r1["status"] == "queued", f"r1={r1}"
    assert r2["status"] == "queued", f"r2={r2}"
    assert r3["status"] == "rejected" and "queue_full" in str(r3).lower(), f"r3={r3}"
    print(f"queue probe r1={r1['status']} r2={r2['status']} r3={r3['status']}")


if __name__ == "__main__":
    asyncio.run(main())
