import importlib.util
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from loats.models import NewsItem
from loats.sentiment import SentimentAnalyzer

REPO_ROOT = Path(__file__).resolve().parents[1]

# The nltk warning can only fire while the optional [nlp] extra is absent
# (auditor F8-L-06 hole 1: once nltk is installed the warning never exists,
# so stderr-presence assertions must be conditional on its absence).
_NLTK_INSTALLED = importlib.util.find_spec("nltk") is not None

# F8-L-06 regression coverage lives at the bottom of this module (see
# TestNltkWarningSuppression): the LOATS_SUPPRESS_NLTK_WARNING knob must be
# read from the process environment BEFORE ``from newspaper import Article``
# executes, otherwise the filter is installed after the warning has fired and
# the knob is a verified no-op.

NEWSPAPER_NLTK_WARNING = "nltk is not installed"

# Prints SENTINEL-ACTIVE iff loats.sentiment's suppression guard ran for this
# process: an 'ignore' filter scoped to the newspaper4k nltk optional-extra
# message exists in warnings.filters. The filter's compiled regex is matched
# against the REAL warning text (outcome check) -- pattern-string comparisons
# are wrong because re.escape backslash-escapes the spaces.
_SUPPRESS_PROBE = (
    "import warnings, loats.sentiment; "
    "msg = 'nltk is not installed. Some NLP features will be unavailable'; "
    "hits = [f for f in warnings.filters "
    "if f[0] == 'ignore' and f[2] is UserWarning and f[1] is not None "
    "and f[1].match(msg)]; "
    "print('SENTINEL-ACTIVE' if hits else 'SENTINEL-INACTIVE')"
)


def _run_suppress_probe(env_value: str | None) -> subprocess.CompletedProcess[str]:
    """Run a fresh interpreter importing loats.sentiment with a controlled env.

    A fresh process is mandatory: the nltk UserWarning fires once per process
    at import time and the knob must be read before any loats import, so no
    in-process test can observe either side of the contract.
    """
    env = os.environ.copy()
    if env_value is None:
        env.pop("LOATS_SUPPRESS_NLTK_WARNING", None)
    else:
        env["LOATS_SUPPRESS_NLTK_WARNING"] = env_value
    return subprocess.run(
        [sys.executable, "-c", _SUPPRESS_PROBE],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def analyzer():
    return SentimentAnalyzer()


@pytest.mark.asyncio
async def test_analyze_text(analyzer):
    score, label = analyzer.analyze_text("good profit")
    assert score > 0
    assert label == "positive"
    score, label = analyzer.analyze_text("bad loss")
    assert score < 0
    assert label == "negative"
    score, label = analyzer.analyze_text("market open")
    assert label == "neutral"


def test_preprocess_text(analyzer):
    text = "Multiple   spaces\nnew lines "
    assert analyzer.preprocess_text(text) == "Multiple spaces new lines"


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment(analyzer):
    with patch(
        "loats.sentiment.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
    ) as mock_parse:
        mock_parse.return_value = [
            NewsItem(
                title="Good",
                content="Profit",
                source="test",
                url="url",
                published_date=datetime.now(),
                sentiment_score=0.8,
                sentiment_label="positive",
            )
        ]
        result = await analyzer.analyze_symbol_sentiment("TEST", ["http://test.com"])
        assert result.symbol == "TEST"
        assert result.news_count == 1
        assert result.positive_count == 1


class TestNltkWarningSuppression:
    """F8-L-06 regression: LOATS_SUPPRESS_NLTK_WARNING must actually work.

    Contract (proven broken before this test existed): the suppression guard
    in src/loats/sentiment.py sits BEFORE the ``from newspaper import Article``
    statement, because the newspaper4k parsers module emits the benign
    ``UserWarning: nltk is not installed ...`` at *its* import time. A guard
    placed after the import installs its filter too late and the knob is a
    silent no-op. Values other than the exact string "1" must NOT suppress
    anything (fail-open by design; documented in .env.example).
    """

    def test_knob_set_to_1_installs_scoped_ignore_filter(self):
        proc = _run_suppress_probe("1")
        assert proc.returncode == 0, proc.stderr
        assert "SENTINEL-ACTIVE" in proc.stdout
        # End-to-end outcome: the warning must not reach stderr in a fresh
        # process (the import-time registry is empty there, so the only thing
        # that can silence it is the filter itself).
        assert NEWSPAPER_NLTK_WARNING not in proc.stderr

    def test_knob_unset_leaves_warning_path_active(self):
        proc = _run_suppress_probe(None)
        assert proc.returncode == 0, proc.stderr
        assert "SENTINEL-INACTIVE" in proc.stdout
        # End-to-end outcome: without the knob the benign warning is visible
        # — but only while nltk is absent; the always-true invariant is the
        # fail-open SENTINEL-INACTIVE above.
        if not _NLTK_INSTALLED:
            assert NEWSPAPER_NLTK_WARNING in proc.stderr

    def test_knob_set_to_0_does_not_suppress(self):
        proc = _run_suppress_probe("0")
        assert proc.returncode == 0, proc.stderr
        assert "SENTINEL-INACTIVE" in proc.stdout
        if not _NLTK_INSTALLED:
            assert NEWSPAPER_NLTK_WARNING in proc.stderr

    def test_suppression_is_scoped_not_global_userwarning_kill(self):
        # The filter must match the specific newspaper4k message pattern, not
        # blanket-suppress every UserWarning for anyone who opts in.
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import warnings, loats.sentiment; "
                "msg = 'nltk is not installed. Some NLP features will be unavailable'; "
                "hits = [f for f in warnings.filters "
                "if f[0] == 'ignore' and f[2] is UserWarning and f[1] is not None "
                "and f[1].match(msg)]; "
                "broad = any(f[0] == 'ignore' and f[2] is UserWarning "
                "and f[1] is None for f in warnings.filters); "
                "print('SCOPED' if hits else 'MISSING'); "
                "print('BROAD' if broad else 'NARROW')",
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "LOATS_SUPPRESS_NLTK_WARNING": "1"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert "SCOPED" in proc.stdout
        assert "BROAD" not in proc.stdout
