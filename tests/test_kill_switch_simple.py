"""
Kill switch tests: the classic gate check plus the P1-R resume-owner lock.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.openalgo import KillSwitchError


def test_kill_switch_check():
    """Test _check_kill_switch function raises KillSwitchError when active."""
    with patch("loats.openalgo._get_alerts") as mock_get_alerts:
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = True
        mock_get_alerts.return_value = mock_alerts

        from loats.openalgo import _check_kill_switch

        with pytest.raises(KillSwitchError):
            _check_kill_switch()


class TestResumeOwnerLock:
    """P1-R (19-Oct wave): persisted resume-owner lock semantics.

    Lock paths come from ``loats.alerts.KILL_OWNER_LOCK_PATH`` AFTER the
    conftest autouse isolation has re-pointed it at the per-test tmp dir:
    writing a hand-rolled sibling filename would miss the path the system
    actually reads.
    """

    @pytest.mark.asyncio
    async def test_activate_writes_resume_owner_lock(self):
        from loats.alerts import KILL_OWNER_LOCK_PATH, AlertSystem

        alerts = AlertSystem()
        with (
            patch.object(
                alerts,
                "_safe_get_all_orders",
                AsyncMock(return_value={"data": []}),
            ),
            patch.object(alerts, "send_alert", AsyncMock(return_value=True)),
        ):
            assert (
                await alerts.activate_kill_switch("drill", owner="tg:694928527") is True
            )
        data = json.loads(KILL_OWNER_LOCK_PATH.read_text(encoding="utf-8"))
        assert data["owner"] == "tg:694928527"
        assert data["reason"] == "drill"
        assert "activated_at" in data
        assert "pid" in data

    @pytest.mark.asyncio
    async def test_resume_by_other_owner_is_refused(self):
        from loats.alerts import KILL_OWNER_LOCK_PATH, AlertSystem

        KILL_OWNER_LOCK_PATH.write_text(
            json.dumps({"owner": "tg:111", "reason": "drill"}), encoding="utf-8"
        )
        alerts = AlertSystem()
        alerts.kill_switch_active = True
        with patch.object(
            alerts, "send_alert", AsyncMock(return_value=True)
        ) as mock_alert:
            assert await alerts.deactivate_kill_switch("nope", owner="tg:222") is False
        assert alerts.kill_switch_active is True  # halt stays latched
        assert KILL_OWNER_LOCK_PATH.exists()  # lock intact
        mock_alert.assert_awaited_once()  # refusal alert fired

    @pytest.mark.asyncio
    async def test_resume_by_owner_clears_lock(self):
        from loats.alerts import KILL_OWNER_LOCK_PATH, AlertSystem

        KILL_OWNER_LOCK_PATH.write_text(
            json.dumps({"owner": "tg:111", "reason": "drill"}), encoding="utf-8"
        )
        alerts = AlertSystem()
        alerts.kill_switch_active = True
        with patch.object(alerts, "send_alert", AsyncMock(return_value=True)):
            assert await alerts.deactivate_kill_switch("done", owner="tg:111") is True
        assert alerts.kill_switch_active is False
        assert not KILL_OWNER_LOCK_PATH.exists()

    @pytest.mark.asyncio
    async def test_auto_lock_resume_is_operator_overridable(self):
        from loats.alerts import KILL_OWNER_LOCK_PATH, AlertSystem

        KILL_OWNER_LOCK_PATH.write_text(
            json.dumps({"owner": "auto:m01-cycle-budget"}), encoding="utf-8"
        )
        alerts = AlertSystem()
        alerts.kill_switch_active = True
        with patch.object(alerts, "send_alert", AsyncMock(return_value=True)):
            assert await alerts.deactivate_kill_switch("ops", owner="tg:222") is True
        assert alerts.kill_switch_active is False
        assert not KILL_OWNER_LOCK_PATH.exists()

    def test_lock_present_holds_halt_without_flag(self):
        from loats.alerts import KILL_OWNER_LOCK_PATH, AlertSystem

        KILL_OWNER_LOCK_PATH.write_text(
            json.dumps({"owner": "auto:m01-cycle-budget"}), encoding="utf-8"
        )
        alerts = AlertSystem()
        assert alerts.is_kill_switch_active() is True  # lock alone latches

    def test_start_restores_persisted_halt(self):
        from loats.alerts import KILL_OWNER_LOCK_PATH, AlertSystem

        KILL_OWNER_LOCK_PATH.write_text(
            json.dumps({"owner": "tg:111", "reason": "drill", "activated_at": "x"}),
            encoding="utf-8",
        )
        alerts = AlertSystem()
        assert alerts.kill_switch_active is False
        alerts._restore_resume_owner_lock()
        assert alerts.kill_switch_active is True


if __name__ == "__main__":
    test_kill_switch_check()
    print("Kill switch test passed!")
