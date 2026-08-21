#!/usr/bin/env python3
"""Fix HTML injection test assertions."""

from pathlib import Path

with Path(r"tests\test_alerts.py").open(encoding="utf-8") as f:
    content = f.read()

# The ACTUAL replacements - raw HTML -> escaped HTML entities
fixes = [
    # test_activate_kill_switch_html_injection_prevention
    (
        'assert "<script>" in sent_message  # Malicious script tag is escaped',
        'assert "<script>" in sent_message  # Malicious script tag is escaped',
    ),
    # test_deactivate_kill_switch_html_injection_prevention
    (
        'assert "<b>bold attempt</b>" in sent_message',
        'assert "<b>bold attempt</b>" in sent_message',
    ),
    # test_send_position_alert_html_injection_prevention
    ('assert "<XSS>" in sent_message', 'assert "<XSS>" in sent_message'),
    # test_orders_command_html_injection_prevention
    (
        'assert "<b>order123</b>" in sent_message',
        'assert "<b>order123</b>" in sent_message',
    ),
    (
        'assert "<script>alert(1)</script>" in sent_message',
        'assert "<script>alert(1)</script>" in sent_message',
    ),
    (
        'assert "<img onerror=alert(1)>" in sent_message',
        'assert "<img onerror=alert(1)>" in sent_message',
    ),
    # test_send_signal_alert_html_injection_prevention
    (
        'assert "<script>" in sent_message\n        assert "<b>indicator</b>" in sent_message',
        'assert "<script>" in sent_message\n        assert "<b>indicator</b>" in sent_message',
    ),
]

for old, new in fixes:
    if old in content:
        content = content.replace(old, new)
    else:
        pass

with Path(r"tests\test_alerts.py").open("w", encoding="utf-8") as f:
    f.write(content)
