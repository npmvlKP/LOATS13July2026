import os
import pathlib
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from loats.config import Settings, get_settings


class TestConfig:
    def test_settings_initialization(self) -> None:
        """Test Settings initialization default values."""
        # Ensure ENVIRONMENT is set to 'development' for this test
        # F8-H-01 test isolation: conftest hard-pins SQLITE_DB_PATH /
        # AUDIT_LOG_PATH to a private temp dir for the whole suite (the
        # ``db`` singleton binds them at import), so this test pins them
        # back to the documented defaults to assert the default mapping.
        patch_dict = {
            "ENVIRONMENT": "development",
            "OPENALGO_API_KEY": "test_key",
            "SQLITE_DB_PATH": "data/loats.db",
            "AUDIT_LOG_PATH": "data/audit.log",
        }
        with patch.dict(os.environ, patch_dict, clear=False):
            test_settings = Settings()
            assert test_settings.environment == "development"
            assert test_settings.sqlite_db_path == pathlib.Path("data/loats.db")
            assert test_settings.audit_log_path == pathlib.Path("data/audit.log")
            assert test_settings.retention_days == 2555
            assert test_settings.ta_scan_interval == 60
            assert test_settings.sentiment_scan_interval == 300
            assert test_settings.signal_scan_interval == 30
            assert test_settings.default_symbol == "NIFTY"
            assert test_settings.default_timeframe == "1min"
            assert test_settings.sentiment_threshold == 0.05
            assert test_settings.request_timeout == 30.0
            # F8-M-07: VIX gate threshold is settings-derived (CMP Rule 10).
            assert test_settings.vix_gate_threshold == 15.0

    def test_settings_from_env(self) -> None:
        """Test Settings initialization environment variables."""
        env_vars = {
            "ENVIRONMENT": "production",
            "SQLITE_DB_PATH": "/custom/path/loats.db",
            "AUDIT_LOG_PATH": "/custom/path/audit.log",
            "RETENTION_DAYS": "365",
            "TA_SCAN_INTERVAL": "120",
            "SENTIMENT_SCAN_INTERVAL": "600",
            "SIGNAL_SCAN_INTERVAL": "60",
            "DEFAULT_SYMBOL": "BANKNIFTY",
            "DEFAULT_TIMEFRAME": "5min",
            "SENTIMENT_THRESHOLD": "0.1",
            "REQUEST_TIMEOUT": "45.0",
            "OPENALGO_API_KEY": "test_api_key_123",
            "OPENALGO_BASE_URL": "https://api.testopenalgo.com",
            "TELEGRAM_BOT_TOKEN": "test_bot_token_456",
            "TELEGRAM_CHAT_ID": "987654321",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            test_settings = Settings()
            assert test_settings.environment == "production"
            assert test_settings.sqlite_db_path == pathlib.Path("/custom/path/loats.db")
            assert test_settings.audit_log_path == pathlib.Path(
                "/custom/path/audit.log"
            )
            assert test_settings.retention_days == 365
            assert test_settings.ta_scan_interval == 120
            assert test_settings.sentiment_scan_interval == 600
            assert test_settings.signal_scan_interval == 60
            assert test_settings.default_symbol == "BANKNIFTY"
            assert test_settings.default_timeframe == "5min"
            assert test_settings.sentiment_threshold == 0.1
            assert test_settings.request_timeout == 45.0
            assert (
                test_settings.openalgo_api_key.get_secret_value() == "test_api_key_123"
            )
            assert test_settings.openalgo_base_url == "https://api.testopenalgo.com"
            assert (
                test_settings.telegram_bot_token.get_secret_value()
                == "test_bot_token_456"
            )
            assert test_settings.telegram_chat_id == "987654321"

    def test_settings_validation(self) -> None:
        """Test Settings validation."""
        # Provide valid API key to avoid validation error for that field
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test"}):
            with pytest.raises(ValidationError):
                Settings(environment="invalid")
            with pytest.raises(ValidationError):
                Settings(retention_days=-1)
            with pytest.raises(ValidationError):
                Settings(ta_scan_interval=0)
            with pytest.raises(ValidationError):
                Settings(sentiment_scan_interval=0)
            with pytest.raises(ValidationError):
                Settings(signal_scan_interval=0)
            with pytest.raises(ValidationError):
                Settings(sentiment_threshold=-0.1)
            with pytest.raises(ValidationError):
                Settings(sentiment_threshold=1.1)
            with pytest.raises(ValidationError):
                Settings(request_timeout=0)

    def test_get_settings(self) -> None:
        """Test get_settings function."""
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            s1 = get_settings()
            s2 = get_settings()
            assert s1 == s2
            assert isinstance(s1, Settings)

    def test_settings_initialize(self) -> None:
        """Test Settings.initialize method."""
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            test_settings = Settings()
            test_settings.initialize()

    def test_settings_repr(self) -> None:
        """Test Settings __repr__ method."""
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            test_settings = Settings()
            repr_str = repr(test_settings)
            assert "Settings(" in repr_str
            assert "environment=" in repr_str
            assert "openalgo_api_key=SecretStr('**********')" in repr_str

    def test_settings_str(self) -> None:
        """Test Settings __str__ method."""
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            test_settings = Settings()
            str_str = str(test_settings)
            assert "environment=" in str_str
            assert "openalgo_api_key=SecretStr('**********')" in str_str


# ---------------------------------------------------------------------------
# TODO-13 / F9-H-01: CMP section 4 gate thresholds are Settings-conformant
# (composite bar 0.6, opposition bar 0.4; domain 0..1 shared with the
# sentiment/composite thresholds).
# ---------------------------------------------------------------------------


class TestCMPGateThresholdsTODO13:
    def test_cmp_gate_thresholds(self) -> None:
        """CMP section 4: composite bar 0.6, opposition bar 0.4."""
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            s = Settings()
            assert s.composite_strength_threshold == 0.6
            assert s.opposition_threshold == 0.4

    def test_opposition_threshold_domain(self) -> None:
        """The opposition bar shares the 0..1 threshold domain."""
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            with pytest.raises(ValidationError):
                Settings(opposition_threshold=-0.1)
            with pytest.raises(ValidationError):
                Settings(opposition_threshold=1.1)


# ---------------------------------------------------------------------------
# F9-H-01 residue: the deploy template must carry each CMP gate bar exactly
# once, agreeing with the Settings default. PR #46 appended the corrected
# pair but left the pre-fix COMPOSITE_STRENGTH_THRESHOLD=0.5 line (born
# 4b94b932) lower in the template; python-dotenv resolves duplicate keys
# last-wins, so a deploy copying .env.example resurrected the loosened 0.5
# composite bar with every Settings-default test green (probe-proven:
# composite 0.55 PROCEEDS under the 0.5 hybrid, REJECTED under CMP 0.6/0.4).
# ---------------------------------------------------------------------------

ENV_EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / ".env.example"
GATE_BARS = ("COMPOSITE_STRENGTH_THRESHOLD", "OPPOSITION_THRESHOLD")


def _dotenv_bindings(text: str) -> list[tuple[str, str]]:
    """(key, value-without-inline-comment) for every binding line."""
    bindings = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        bindings.append((key.strip(), value.split("#", 1)[0].strip()))
    return bindings


class TestEnvExampleGateBarTemplateConformance:
    def test_each_gate_bar_appears_exactly_once(self) -> None:
        counts: dict[str, int] = {}
        for key, _ in _dotenv_bindings(ENV_EXAMPLE.read_text(encoding="utf-8")):
            counts[key] = counts.get(key, 0) + 1
        for bar in GATE_BARS:
            assert counts.get(bar, 0) == 1, (
                f"{bar} must appear exactly once in .env.example "
                f"(found {counts.get(bar, 0)}; last-wins dotenv resolution "
                "resurrects stale values)"
            )

    def test_gate_bar_template_values_match_settings_defaults(self) -> None:
        with patch.dict(os.environ, {"OPENALGO_API_KEY": "test_key"}):
            s = Settings()
        bindings = dict(_dotenv_bindings(ENV_EXAMPLE.read_text(encoding="utf-8")))
        assert float(bindings["COMPOSITE_STRENGTH_THRESHOLD"]) == (
            s.composite_strength_threshold
        )
        assert float(bindings["OPPOSITION_THRESHOLD"]) == s.opposition_threshold
