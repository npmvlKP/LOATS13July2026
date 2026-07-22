import re

# Read the file
with open('tests/test_alerts.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the replacements - from raw HTML to escaped HTML entities
# html.escape() converts: < to <, > to >, ' to '
replacements = [
    # test_activate_kill_switch_html_injection_prevention
    ('assert "<script>" in sent_message', 'assert "<script>" in sent_message'),
    # test_deactivate_kill_switch_html_injection_prevention
    ('assert "<b>bold attempt</b>" in sent_message', 'assert "<b>bold attempt</b>" in sent_message'),
    # test_send_position_alert_html_injection_prevention
    ('assert "<XSS>" in sent_message', 'assert "<XSS>" in sent_message'),
    # test_orders_command_html_injection_prevention (3 assertions)
    ('assert "<b>order123</b>" in sent_message', 'assert "<b>order123</b>" in sent_message'),
    ('assert "<script>alert(1)</script>" in sent_message', 'assert "<script>alert(1)</script>" in sent_message'),
    ('assert "<img onerror=alert(1)>" in sent_message', 'assert "<img onerror=alert(1)>" in sent_message'),
    # test_send_signal_alert_html_injection_prevention
    ('assert "<b>indicator</b>" in sent_message', 'assert "<b>indicator</b>" in sent_message'),
]

count = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f'Replaced: {old}')
        count += 1
    else:
        print(f'NOT FOUND: {old}')

# Write back
with open('tests/test_alerts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nTotal replacements: {count}')