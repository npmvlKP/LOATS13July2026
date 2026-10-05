"""Secret-redaction log processor (H-03 defense-in-depth).

Finding H-03 (05Oct2026 paste): the OpenAlgo transport injects the API
key into every POST body (`openalgo.py` `_request`/`_async_request`,
F8-L-03 live-verified schema requirement), so any future log emitter
that renders a request payload would leak the credential into
``logs/loats.log``. Today no emitter does -- the two analyzer-payload
debug emitters log ``TradeDecision.to_analyzer_payload()`` BEFORE the
transport injects the key, and the httpx exception reprs used in
``openalgo.py`` error logs do not embed request bodies. But the
injection sits one refactor away from every call site, so the redaction
net is installed at the ONE chokepoint every rendered log line passes:
the structlog shared-processor chain inside ``loats_logging``.

Design (freeze constraints honored):

* RECURSIVE over JSON-shaped structures (dict/list/tuple/set) so nested
  payload fragments are covered, not just top-level keys.
* KEY-NAME matched, case-insensitively, against ``_REDACT_KEY_NAMES``;
  the VALUE NEVER enters the output: matched values are replaced with
  the ``_REDACTED`` sentinel regardless of their runtime type.
* LONG-SECRET matched as a value-only fallback: any string value
  matching the OpenAlgo key shape (>= 16 chars, alphanumeric plus
  ``_-@``) is redacted too, so a key that reached a log line under an
  unexpected key name still cannot survive rendering.
* Depth-capped (``_MAX_DEPTH``) and cycle-safe (``_seen`` id set) so a
  self-referential payload cannot recurse without bound.
* Non-failing BY CONTRACT: any exception inside the processor is
  swallowed and the event passes through UNMODIFIED. A redaction bug
  must never take down the application's logging (and therefore the
  application) -- the failure mode of last resort is an unredacted
  line, which the keyed sweep above makes a narrow window.
* Shared ``log secret redaction`` events must never log secret VALUES;
  this module never emits the input it inspects.

The processor is appended to ``shared_processors`` in
``configure_logging`` so BOTH the structlog-native chain and the
handlers' ``foreign_pre_chain`` (stdlib loggers) render through it.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

# Structlog drops into the event dict under this key; redaction markers
# are added under a distinct key so the two never collide.
REDACTION_EVENT_KEY = "log_secret_redaction"

# Redacted-value sentinel (deliberately not a secret-shaped string).
_REDACTED = "[REDACTED]"

# Key-name sweep: case-insensitive substring match against dict keys.
# `apikey`/`api_key`/`api-key` cover the OpenAlgo transport field and
# common aliases; the surrounding entries cover the credential family a
# trading payload could plausibly carry (broker tokens, webhook URLs).
_REDACT_KEY_NAMES: tuple[str, ...] = (
    "apikey",
    "api_key",
    "api-key",
    "secret",
    "password",
    "passwd",
    "authorization",
    "token",
    "credential",
    "session_id",
    "access_key",
    "private_key",
    "signature",
    "webhook",
)

# Value-shape fallback: OpenAlgo keys are long alphanumeric credentials.
# Anything at least this long matching the charset is treated as
# secret-shaped REGARDLESS of its key name.
_SECRET_VALUE_MIN_LEN = 16
_SECRET_VALUE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-@"
)

# Recursion guards: payloads are JSON-shaped in practice; these bounds
# only fire on adversarial/self-referential structures.
_MAX_DEPTH = 8
_MAX_ITEMS = 200


def _is_secret_shaped(value: str) -> bool:
    """True when a string VALUE matches the long-credential shape."""
    return len(value) >= _SECRET_VALUE_MIN_LEN and set(value) <= _SECRET_VALUE_CHARS


def _key_is_sensitive(key: Any) -> bool:
    """True when a mapping KEY name matches the redaction sweep."""
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(name in lowered for name in _REDACT_KEY_NAMES)


def _redact_structure(value: Any, depth: int, seen: set[int]) -> Any:
    """Return a redacted COPY of a JSON-shaped structure.

    Primitives pass through (strings through the value-shape sweep);
    containers are rebuilt depth-first. Non-JSON leaves (objects) pass
    through by reference -- str() of them is rendered downstream, not
    here.
    """
    if depth > _MAX_DEPTH:
        return value
    obj_id = id(value)
    if obj_id in seen:
        # Self-referential container: break the cycle without recursing.
        return value
    seen = seen | {obj_id}
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= _MAX_ITEMS:
                break
            if _key_is_sensitive(k):
                redacted[k] = _REDACTED
            else:
                redacted[k] = _redact_structure(v, depth + 1, seen)
        return redacted
    if isinstance(value, (list, tuple)):
        redacted_seq: list[Any] = []
        for i, item in enumerate(value):
            if i >= _MAX_ITEMS:
                break
            redacted_seq.append(_redact_structure(item, depth + 1, seen))
        if isinstance(value, tuple):
            return tuple(redacted_seq)
        return redacted_seq
    if isinstance(value, set):
        return {
            _redact_structure(item, depth + 1, seen)
            for item in list(value)[:_MAX_ITEMS]
        }
    if isinstance(value, str):
        return "[REDACTED_SECRET]" if _is_secret_shaped(value) else value
    return value


def redact_secrets(
    logger: Any,
    name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor: scrub secret-shaped values from the event.

    Runs INSIDE the shared processor chain (and therefore inside both
    formatters' ``foreign_pre_chain``), so every rendered line -- struct
    or console -- passes through here exactly once. The event's top
    level is scanned key-wise so a secret that reached the EVENT level
    (not nested in a payload value) is redacted too.
    """
    try:
        redacted: dict[str, Any] = {}
        for k, v in event_dict.items():
            if _key_is_sensitive(k):
                redacted[k] = _REDACTED
            else:
                redacted[k] = _redact_structure(v, 0, set())
        marked = any(redacted[k] != v for k, v in event_dict.items())
        if marked:
            redacted[REDACTION_EVENT_KEY] = True
        return redacted
    except Exception:
        # Never break logging on a redaction bug: pass the event through
        # unmodified (last-resort failure mode is an unredacted line).
        return event_dict
