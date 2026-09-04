# F8-L-05 Closure — bloombergquint RSS feed validation (recorded fallback)

**Closed:** 2026-09-04 · **Priority:** P3 (carried since FR1 as F6-L-06,
re-carried as F8-L-05 in 01Sep2026-FR.md) · **Branch:** `fix/fr7-wave`

## Finding

The sentiment RSS source list was unvalidated end-to-end. TODO-27d removed
the defunct `https://www.bloombergquint.com/markets-feed` (domain migrated to
bqprime/ndtvprofit; endpoint 404 non-RSS) and centralized the list in
`settings.rss_feeds` (ET, Moneycontrol, Livemint), but nothing proved the
remaining feeds actually serve RSS: no CI job, no startup gate, no recorded
fallback. Required test per the finding: "feed validator in CI or startup
with recorded fallback."

## Root cause

`validate_rss_feed` existed (orchestrator) and ran per sentiment cycle, but
validation was ephemeral — there was no deterministic, offline-verifiable
artifact binding the configured feed list to known-good payloads, so a
defunct-feed regression (the bloombergquint class of bug) could re-enter
via `RSS_FEEDS` env override with nothing to catch it.

## Fix (four layers)

1. `src/loats/rss_validation.py` — production module: manifest loader
   (fail-closed `RssManifestError`), offline recorded-source validation
   (http(s) URL, defunct-feed marker guard, fixture presence, RSS/XML
   signature, >=1 `<item>`, channel-link host identity), live
   `validate_feed` (delegates to `loats.orchestrator.validate_rss_feed`),
   and `run_startup_gate` (offline authoritative, live pass advisory —
   a transient outage degrades to WARNING and never blocks startup).
2. `tests/fixtures/rss/recorded-sources.json` + 3 recorded fixtures —
   curl-captured 2026-09-04 from the live feeds (HTTP 200, XML
   content-type, RSS 2.0; 50/15/35 `<item>` entries), the recorded
   fallback itself.
3. Startup wiring — `TradingOrchestrator.start()` runs the gate before the
   first cycle: the offline manifest validation is authoritative and runs
   inline (deterministic, no network); the advisory live drift pass is
   DETACHED (`_rss_live_drift_pass`) so a dead network can never stall
   trading startup, and is cancelled in `shutdown()`.
4. CI + health check — new `rss-feeds` CI job (offline validator, no
   network) and HC-28 in `scripts/fr7_health_check.py` (out-of-process
   `validate_rss_feeds.py --offline`). CLI entry:
   `python scripts/validate_rss_feeds.py [--offline|--check|--json-out]`.

Manifest <-> `settings.rss_feeds` lockstep and the defunct-feed guard are
asserted in `tests/test_rss_validation.py::TestLiveRepositoryContract`
(executed by the CI pytest job).

### Scope boundary (deliberate)

The host-identity check binds each fixture to its source host via the
*channel* `<link>` only — the identity element that fails on a
bloombergquint-class domain re-point. Item-level `<link>` hosts are NOT
checked: syndicated articles legitimately point at third-party hosts, and
the recorded fixtures are git-tracked bytes, so any tampering is visible in
review rather than detectable by heuristics. Feed validation proves
availability and identity, not article authenticity; sentiment remains one
gated source among several (VIX/TA/breakers) and never trades alone.

### Adversarial-review hardening (2026-09-04, H1–H9)

A fresh-eyes subagent review produced nine findings; dispositions:

* **H1 (blocker, fixed):** the CI `rss-feeds` job ran the validator without
  installing project deps (structlog/pydantic_settings are imported via the
  loats package) — red on every clean runner. Job now runs `pip install .`
  first. Lesson recorded: the repo-hygiene job's no-install pattern only
  works for stdlib-only scripts.
* **H2 (major, fixed):** the gate validated only manifest URLs, not the
  EFFECTIVE `settings.rss_feeds` — an `RSS_FEEDS` env override carrying the
  defunct URL sailed through. `check_effective_feed_settings()` now runs in
  the gate (defunct/non-http rejected; unknown extras warned; settings-
  unreadable environments skip gracefully).
* **H3 (minor, fixed):** gate failure was log-only; `_validate_rss_startup_gate`
  now also emits `alerts.send_system_alert(..., "error")` (alert path itself
  failure-isolated).
* **H4 (minor, closed as upstream):** Moneycontrol serves a stale-cached
  feed (two same-day fetches byte-identical, Apr-2024 pubDates). Fixture is
  a faithful recording; staleness documented in the manifest note.
* **H5 (minor, fixed):** ceiling math corrected 424 → 425 (eval script is
  the 9th tracked file).
* **H6 (minor, fixed):** closure doc re-synced (29 tests, detached drift
  pass, `live=` param).
* **H7 (minor, deliberate):** channel-level identity only — see scope
  boundary above.
* **H8 (minor, fixed):** `FEED_SIGNATURES` tightened to actual document
  roots (`<rss`, `<feed`, `<rdf:rdf`); bare `<?xml`/`<channel` accepted any
  well-formed XML.
* **H9 (minor, fixed):** added `test_start_runs_gate_before_cycle_task` —
  a real end-to-end `TradingOrchestrator.start()` execution asserting the
  gate completes before the cycle task is created (source-grep alone could
  not catch a reordering regression).

## Evidence

* `scripts/validate_rss_feeds.py --offline` → `3/3 recorded feeds valid`,
  exit 0 (deterministic; re-runnable in CI and by the HC-28 gate).
* Live drift pass 2026-09-04: all three settings feeds validated over real
  network through `loats.orchestrator.validate_rss_feed`.
* `tests/test_rss_validation.py`: 35 tests (manifest fail-closed paths,
  offline validation anomalies, effective-settings override guard,
  startup-gate degradation semantics, detached live-drift-pass lifecycle,
  end-to-end start() ordering, live-repo contract).
* Tracked-file ceiling re-pinned 416 → 425 in lockstep (F8-C-02) for the
  9 new tracked files.
